#!/usr/bin/env python3
"""
waveshare_acm_scan.py
Scans for ST3215 servos on the Waveshare Bus Servo Adapter (A)
connected via USB as /dev/ttyACM0
Tries 1,000,000 bps (factory default) then 115,200 bps fallback.
"""
import sys
sys.path.insert(0, '.')

from st3215.port_handler import PortHandler
from st3215.protocol_packet_handler import protocol_packet_handler

DEVICE = '/dev/ttyACM0'
BAUD_RATES = [1_000_000, 115_200]


class BusScanner(protocol_packet_handler):
    def __init__(self, device, baud):
        self.portHandler = PortHandler(device)
        self.portHandler.baudrate = baud
        if not self.portHandler.openPort():
            raise ValueError(f'Cannot open {device}')
        protocol_packet_handler.__init__(self, self.portHandler)

    def ping_id(self, sid):
        model, comm, error = self.ping(sid)
        return comm == 0 and model != 0 and error == 0

    def close(self):
        try:
            self.portHandler.closePort()
        except Exception:
            pass


def scan(device, baud):
    print(f'\n{"="*50}')
    print(f'Scanning {device} at {baud:,} bps')
    print(f'{"="*50}')
    try:
        bus = BusScanner(device, baud)
    except Exception as e:
        print(f'ERROR opening port: {e}')
        return []

    found = []
    for sid in range(0, 254):
        if bus.ping_id(sid):
            print(f'  >>> FOUND servo at ID {sid}')
            found.append(sid)
    bus.close()
    print(f'Total at {baud:,} bps: {len(found)} servo(s): {found}')
    return found


def telemetry(device, baud, ids):
    print(f'\n--- Telemetry ({baud:,} bps) ---')
    # Monkey-patch the baudrate before ST3215 opens the port
    _orig = PortHandler.openPort
    def patched_open(self):
        self.baudrate = baud
        return _orig(self)
    PortHandler.openPort = patched_open

    try:
        from st3215 import ST3215
        s = ST3215(device)
    except Exception as e:
        print(f'ERROR: {e}')
        return
    finally:
        PortHandler.openPort = _orig

    for sid in ids:
        print(f'\nServo {sid}:')
        print(f'  Position   : {s.ReadPosition(sid)}')
        print(f'  Voltage    : {s.ReadVoltage(sid)} V')
        print(f'  Temperature: {s.ReadTemperature(sid)} °C')
        print(f'  Current    : {s.ReadCurrent(sid)} mA')
        print(f'  Load       : {s.ReadLoad(sid)} %')
        print(f'  Mode       : {s.ReadMode(sid)}')
        print(f'  Moving     : {s.IsMoving(sid)}')
        st = s.ReadStatus(sid)
        if st:
            faults = [k for k, v in st.items() if not v]
            print(f'  Status     : {"OK" if not faults else "FAULT: " + ", ".join(faults)}')
    s.portHandler.closePort()


if __name__ == '__main__':
    print('Waveshare Bus Servo Adapter (A) — USB Scan')
    print(f'Device: {DEVICE}')
    print('Make sure: jumper cap = B position, DC power supply connected\n')

    for baud in BAUD_RATES:
        found = scan(DEVICE, baud)
        if found:
            telemetry(DEVICE, baud, found)
            print(f'\nSuccess! Working baud rate: {baud:,} bps')
            sys.exit(0)

    print('\nNo servos found at any baud rate.')
    print('\nChecklist:')
    print('  1. Jumper on adapter in B position (USB mode)?')
    print('  2. DC power supply (9-12.6V) plugged into adapter?')
    print('  3. Servo cable firmly connected to Bus Servo port?')
    print('  4. Try unplugging and replugging the USB cable')
    sys.exit(1)
