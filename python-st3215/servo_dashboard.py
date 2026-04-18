#!/usr/bin/env python3
"""
servo_dashboard.py — Web dashboard for ST3215 servo control
Usage: python3 servo_dashboard.py
Then open http://localhost:5000 in your browser
"""

import sys
import time
import threading
from flask import Flask, jsonify, request, render_template

sys.path.insert(0, '.')
from st3215.port_handler import PortHandler
from st3215.protocol_packet_handler import protocol_packet_handler
import st3215.values as V

DEVICE    = '/dev/ttyACM0'
BAUD      = 1_000_000
KNOWN_IDS = list(range(1, 7))  # IDs 1-6

app = Flask(__name__)


# ── Serial bus ───────────────────────────────────────────────────────────────
class Bus:
    def __init__(self, device: str, baud: int):
        self.lock = threading.Lock()
        ph = PortHandler(device)
        ph.baudrate = baud
        if not ph.openPort():
            raise RuntimeError(f'Cannot open {device}')
        self._pkt = protocol_packet_handler(ph)

    def r1(self, sid: int, addr: int):
        data, comm, _ = self._pkt.readTxRx(sid, addr, 1)
        if comm == 0 and isinstance(data, (list, bytes)) and len(data) == 1:
            return data[0]
        return None

    def r2(self, sid: int, addr: int):
        data, comm, _ = self._pkt.readTxRx(sid, addr, 2)
        if comm == 0 and isinstance(data, (list, bytes)) and len(data) == 2:
            return data[0] | (data[1] << 8)
        return None

    def write(self, sid: int, addr: int, values: list) -> tuple:
        return self._pkt.writeTxRx(sid, addr, len(values), values)


# ── Servo state ──────────────────────────────────────────────────────────────
servo_state: dict = {}
sw_offset:   dict = {}  # {sid: raw_position_at_zero}
sw_min:      dict = {}  # {sid: raw min limit}
sw_max:      dict = {}  # {sid: raw max limit}


def calibrated(sid: int, raw: int) -> int:
    return raw - sw_offset.get(sid, 0)


def update_state(sid: int, raw: int, volt, temp, moving: bool, mode: int) -> None:
    cal = calibrated(sid, raw)
    s = servo_state.setdefault(sid, {'min_seen': cal, 'max_seen': cal})
    s['pos']      = cal
    s['raw']      = raw
    s['volt']     = round(volt / 10, 1) if volt is not None else None
    s['temp']     = temp
    s['moving']   = moving
    s['mode']     = mode   # 0=servo, 1=motor, 2=pwm, 3=step
    s['online']   = True
    s['min_seen'] = min(s['min_seen'], cal)
    s['max_seen'] = max(s['max_seen'], cal)


def poll_loop(bus: Bus) -> None:
    while True:
        with bus.lock:
            for sid in KNOWN_IDS:
                raw  = bus.r2(sid, V.STS_PRESENT_POSITION_L)
                volt = bus.r1(sid, V.STS_PRESENT_VOLTAGE)
                temp = bus.r1(sid, V.STS_PRESENT_TEMPERATURE)
                mov  = bus.r1(sid, V.STS_MOVING)
                mode = bus.r1(sid, V.STS_MODE)
                if raw is not None:
                    update_state(sid, raw, volt, temp, bool(mov), mode or 0)
                else:
                    servo_state.setdefault(sid, {})['online'] = False
        time.sleep(0.2)


# ── Flask routes ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    result = {}
    for sid in KNOWN_IDS:
        s = servo_state.get(sid, {})
        result[str(sid)] = {
            'online':    s.get('online', False),
            'pos':       s.get('pos'),
            'raw':       s.get('raw'),
            'offset':    sw_offset.get(sid, 0),
            'min_seen':  s.get('min_seen'),
            'max_seen':  s.get('max_seen'),
            'volt':      s.get('volt'),
            'temp':      s.get('temp'),
            'moving':    s.get('moving', False),
            'mode':      s.get('mode', 0),
            'sw_min':    sw_min.get(sid),       # None = no limit set
            'sw_max':    sw_max.get(sid),
        }
    return jsonify(result)


@app.route('/api/move', methods=['POST'])
def api_move():
    data    = request.json or {}
    sid     = int(data['id'])
    cal_pos = int(data['pos'])
    speed   = int(data.get('speed', 500))
    raw_pos = cal_pos + sw_offset.get(sid, 0)
    raw_pos = max(sw_min.get(sid, 0), min(sw_max.get(sid, 4095), raw_pos))

    with _bus.lock:
        _bus.write(sid, V.STS_GOAL_POSITION_L, [
            raw_pos & 0xFF, (raw_pos >> 8) & 0xFF,
            0, 0,
            speed & 0xFF, (speed >> 8) & 0xFF,
        ])
    return jsonify({'ok': True, 'pos': cal_pos})


@app.route('/api/motor_speed', methods=['POST'])
def api_motor_speed():
    """Set motor wheel speed. speed > 0 = CW, speed < 0 = CCW, 0 = stop."""
    data  = request.json or {}
    sid   = int(data['id'])
    speed = int(data.get('speed', 0))   # signed, -3400 to +3400

    # STS encoding: bit15=direction(1=CCW), bits0-14=magnitude
    magnitude = min(abs(speed), 3400)
    direction = 0x8000 if speed < 0 else 0
    raw_speed = magnitude | direction

    with _bus.lock:
        _bus.write(sid, V.STS_GOAL_SPEED_L, [raw_speed & 0xFF, (raw_speed >> 8) & 0xFF])
    return jsonify({'ok': True, 'speed': speed})


@app.route('/api/set_mode', methods=['POST'])
def api_set_mode():
    """Switch servo between mode 0 (servo/position) and mode 1 (motor/wheel)."""
    data = request.json or {}
    sid  = int(data['id'])
    mode = int(data['mode'])   # 0=servo, 1=motor

    with _bus.lock:
        _bus.write(sid, V.STS_LOCK, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MODE, [mode])
        time.sleep(0.05)
        # In servo mode re-enable torque; in motor mode set speed to 0 first
        if mode == 1:
            _bus.write(sid, V.STS_GOAL_SPEED_L, [0, 0])
        _bus.write(sid, V.STS_TORQUE_ENABLE, [1])
        time.sleep(0.05)
        _bus.write(sid, V.STS_LOCK, [1])
        time.sleep(0.05)

    # Reset range tracking on mode switch
    if sid in servo_state:
        raw = servo_state[sid].get('raw', 0)
        cal = calibrated(sid, raw)
        servo_state[sid]['min_seen'] = cal
        servo_state[sid]['max_seen'] = cal

    return jsonify({'ok': True, 'mode': mode})


@app.route('/api/set_joint_limit', methods=['POST'])
def api_set_joint_limit():
    """Save current raw position as the min or max software limit for a servo."""
    data  = request.json or {}
    sid   = int(data['id'])
    which = data['which']   # 'min' or 'max'
    raw   = servo_state.get(sid, {}).get('raw')
    if raw is None:
        return jsonify({'ok': False, 'error': 'No position data'}), 500

    if which == 'min':
        sw_min[sid] = raw
    else:
        sw_max[sid] = raw

    return jsonify({'ok': True, 'which': which, 'raw': raw})


@app.route('/api/clear_joint_limit', methods=['POST'])
def api_clear_joint_limit():
    """Remove the software min/max limit for a servo."""
    data  = request.json or {}
    sid   = int(data['id'])
    which = data.get('which', 'both')
    if which in ('min', 'both'):  sw_min.pop(sid, None)
    if which in ('max', 'both'):  sw_max.pop(sid, None)
    return jsonify({'ok': True})


@app.route('/api/set_zero', methods=['POST'])
def api_set_zero():
    """Set current position as software zero — no EEPROM writes."""
    sid = int((request.json or {})['id'])
    raw = servo_state.get(sid, {}).get('raw')
    if raw is None:
        return jsonify({'ok': False, 'error': 'No position data yet'}), 500

    sw_offset[sid] = raw
    if sid in servo_state:
        servo_state[sid]['min_seen'] = 0
        servo_state[sid]['max_seen'] = 0

    return jsonify({'ok': True, 'offset_raw': raw})


@app.route('/api/torque', methods=['POST'])
def api_torque():
    data   = request.json or {}
    sid    = int(data['id'])
    enable = int(bool(data.get('enable', True)))
    with _bus.lock:
        _bus.write(sid, V.STS_TORQUE_ENABLE, [enable])
    return jsonify({'ok': True, 'torque': enable})


@app.route('/api/estop', methods=['POST'])
def api_estop():
    with _bus.lock:
        for sid in KNOWN_IDS:
            _bus.write(sid, V.STS_TORQUE_ENABLE, [0])
    return jsonify({'ok': True})


@app.route('/api/clear_limits', methods=['POST'])
def api_clear_limits():
    sid = int((request.json or {})['id'])
    with _bus.lock:
        _bus.write(sid, V.STS_LOCK, [0])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MIN_ANGLE_LIMIT_L, [0x00, 0x00])
        time.sleep(0.05)
        _bus.write(sid, V.STS_MAX_ANGLE_LIMIT_L, [0xFF, 0x0F])
        time.sleep(0.05)
        _bus.write(sid, V.STS_LOCK, [1])
        time.sleep(0.05)
    return jsonify({'ok': True})


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print(f'Opening {DEVICE} at {BAUD:,} bps...')
    _bus = Bus(DEVICE, BAUD)
    print('Connected.')

    t = threading.Thread(target=poll_loop, args=(_bus,), daemon=True)
    t.start()
    print('Telemetry polling started.')
    print('Dashboard → http://localhost:5000')

    app.run(host='0.0.0.0', port=5000, debug=False)
