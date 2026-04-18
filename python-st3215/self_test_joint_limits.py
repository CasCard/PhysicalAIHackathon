#!/usr/bin/env python3
"""Incremental joint-limit self-test for Feetech ST3215 servos.

This script probes each servo toward lower and higher raw targets in small steps,
watching for either:
- overload fault
- lack of progress / stall
- hard 0 / 4095 raw boundary

It is intentionally conservative:
- low speed
- small step size
- per-move settle timeout
- optional torque release after each servo

Default test set is IDs 1-5.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

sys.path.insert(0, '.')

from st3215 import ST3215
from st3215.port_handler import PortHandler
import st3215.values as V

RAW_MIN = 0
RAW_MAX = 4095
DEFAULT_BAUD = 1_000_000
DEFAULT_DEVICE = '/dev/ttyACM0'


@dataclass
class ServoSample:
    pos: int | None
    moving: bool | None
    status_raw: int | None
    load: int | None
    temp: int | None
    volt_raw: int | None

    @property
    def overload(self) -> bool:
        return self.status_raw is not None and bool(self.status_raw & V.ERRBIT_OVERLOAD)

    @property
    def voltage(self) -> float | None:
        return None if self.volt_raw is None else self.volt_raw / 10.0


@dataclass
class ProbeResult:
    end_pos: int | None
    reason: str
    steps: int
    max_load: int
    saw_overload: bool


@dataclass
class ServoResult:
    sid: int
    start_pos: int | None
    low_end: int | None
    low_reason: str
    high_end: int | None
    high_reason: str
    travel: int | None
    max_load: int
    temp_c: int | None
    voltage_v: float | None


class ServoTester:
    def __init__(self, device: str, baud: int):
        self._orig_open = PortHandler.openPort

        def patched_open(port_handler):
            port_handler.baudrate = baud
            return self._orig_open(port_handler)

        PortHandler.openPort = patched_open
        self.servo = ST3215(device)

    def close(self) -> None:
        try:
            self.servo.portHandler.closePort()
        finally:
            PortHandler.openPort = self._orig_open

    def read_sample(self, sid: int) -> ServoSample:
        pos = self.servo.ReadPosition(sid)
        moving = self.servo.IsMoving(sid)
        status = self.servo.read1ByteTxRx(sid, V.STS_STATUS)
        load = self.servo.read2ByteTxRx(sid, V.STS_PRESENT_LOAD_L)
        temp = self.servo.read1ByteTxRx(sid, V.STS_PRESENT_TEMPERATURE)
        volt = self.servo.read1ByteTxRx(sid, V.STS_PRESENT_VOLTAGE)

        status_raw = status[0] if status[1] == 0 and status[2] == 0 else None
        load_raw = load[0] if load[1] == 0 and load[2] == 0 else None
        temp_raw = temp[0] if temp[1] == 0 and temp[2] == 0 else None
        volt_raw = volt[0] if volt[1] == 0 and volt[2] == 0 else None

        return ServoSample(
            pos=pos,
            moving=moving,
            status_raw=status_raw,
            load=load_raw,
            temp=temp_raw,
            volt_raw=volt_raw,
        )

    def prepare_servo(self, sid: int, speed: int, acc: int) -> None:
        self.servo.SetMode(sid, 0)
        time.sleep(0.05)
        self.servo.SetAcceleration(sid, acc)
        time.sleep(0.05)
        self.servo.SetSpeed(sid, speed)
        time.sleep(0.05)
        self.servo.StartServo(sid)
        time.sleep(0.2)

    def release_servo(self, sid: int) -> None:
        self.servo.StopServo(sid)
        time.sleep(0.1)

    def move_goal(self, sid: int, goal: int) -> bool:
        goal = max(RAW_MIN, min(RAW_MAX, goal))
        return bool(self.servo.WritePosition(sid, goal))

    def wait_settle(self, sid: int, timeout_s: float, poll_s: float) -> ServoSample:
        deadline = time.time() + timeout_s
        last = self.read_sample(sid)
        while time.time() < deadline:
            time.sleep(poll_s)
            last = self.read_sample(sid)
            if last.overload:
                return last
            if last.moving is False:
                return last
        return last

    def probe_direction(
        self,
        sid: int,
        direction: int,
        step_size: int,
        max_steps: int,
        min_progress: int,
        settle_timeout: float,
        poll_interval: float,
    ) -> ProbeResult:
        sample = self.read_sample(sid)
        current = sample.pos
        if current is None:
            return ProbeResult(None, 'no_position', 0, 0, False)

        max_load = sample.load or 0
        stall_hits = 0
        saw_overload = sample.overload

        for idx in range(1, max_steps + 1):
            target = max(RAW_MIN, min(RAW_MAX, current + direction * step_size))
            if target == current:
                return ProbeResult(current, 'raw_boundary', idx - 1, max_load, saw_overload)

            if not self.move_goal(sid, target):
                return ProbeResult(current, 'write_failed', idx - 1, max_load, saw_overload)

            settled = self.wait_settle(sid, settle_timeout, poll_interval)
            max_load = max(max_load, settled.load or 0)
            saw_overload = saw_overload or settled.overload

            if settled.pos is None:
                return ProbeResult(current, 'position_read_failed', idx, max_load, saw_overload)

            progress = abs(settled.pos - current)
            current = settled.pos

            if settled.overload:
                return ProbeResult(current, 'overload', idx, max_load, True)

            if current in (RAW_MIN, RAW_MAX):
                return ProbeResult(current, 'raw_boundary', idx, max_load, saw_overload)

            if progress < min_progress:
                stall_hits += 1
            else:
                stall_hits = 0

            if stall_hits >= 2:
                return ProbeResult(current, 'stall', idx, max_load, saw_overload)

        return ProbeResult(current, 'max_steps', max_steps, max_load, saw_overload)

    def test_servo(
        self,
        sid: int,
        speed: int,
        acc: int,
        step_size: int,
        max_steps: int,
        min_progress: int,
        settle_timeout: float,
        poll_interval: float,
        release_after: bool,
    ) -> ServoResult:
        self.prepare_servo(sid, speed, acc)
        start = self.read_sample(sid)
        start_pos = start.pos
        if start_pos is None:
            return ServoResult(sid, None, None, 'no_position', None, 'not_run', None, 0, start.temp, start.voltage)

        low = self.probe_direction(
            sid=sid,
            direction=-1,
            step_size=step_size,
            max_steps=max_steps,
            min_progress=min_progress,
            settle_timeout=settle_timeout,
            poll_interval=poll_interval,
        )

        if low.end_pos is not None:
            self.move_goal(sid, start_pos)
            time.sleep(settle_timeout)

        high = self.probe_direction(
            sid=sid,
            direction=+1,
            step_size=step_size,
            max_steps=max_steps,
            min_progress=min_progress,
            settle_timeout=settle_timeout,
            poll_interval=poll_interval,
        )

        final_sample = self.read_sample(sid)
        if release_after:
            self.release_servo(sid)

        travel = None
        if low.end_pos is not None and high.end_pos is not None:
            travel = abs(high.end_pos - low.end_pos)

        return ServoResult(
            sid=sid,
            start_pos=start_pos,
            low_end=low.end_pos,
            low_reason=low.reason,
            high_end=high.end_pos,
            high_reason=high.reason,
            travel=travel,
            max_load=max(low.max_load, high.max_load),
            temp_c=final_sample.temp,
            voltage_v=final_sample.voltage,
        )


def parse_ids(raw: str) -> list[int]:
    result = []
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            lo, hi = part.split('-', 1)
            result.extend(range(int(lo), int(hi) + 1))
        else:
            result.append(int(part))
    return sorted(dict.fromkeys(result))


def write_results_csv(path: Path, rows: Iterable[ServoResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow([
            'servo_id', 'start_pos', 'low_end', 'low_reason', 'high_end', 'high_reason',
            'travel', 'travel_deg', 'max_load', 'temp_c', 'voltage_v'
        ])
        for row in rows:
            travel_deg = None if row.travel is None else round(row.travel * 270.0 / RAW_MAX, 2)
            writer.writerow([
                row.sid, row.start_pos, row.low_end, row.low_reason, row.high_end, row.high_reason,
                row.travel, travel_deg, row.max_load, row.temp_c, row.voltage_v
            ])


def main() -> int:
    parser = argparse.ArgumentParser(description='Incremental joint-limit self-test for ST3215 servos')
    parser.add_argument('--device', default=DEFAULT_DEVICE)
    parser.add_argument('--baud', type=int, default=DEFAULT_BAUD)
    parser.add_argument('--ids', default='1-5', help='Comma-separated IDs or ranges, e.g. 1-5 or 1,3,5')
    parser.add_argument('--speed', type=int, default=120, help='Move speed in step/s')
    parser.add_argument('--acc', type=int, default=10, help='Acceleration in 100 step/s^2 units')
    parser.add_argument('--step-size', type=int, default=25, help='Raw step size per probe move')
    parser.add_argument('--max-steps', type=int, default=80, help='Maximum probe steps per direction')
    parser.add_argument('--min-progress', type=int, default=4, help='Minimum raw progress to treat as real movement')
    parser.add_argument('--settle-timeout', type=float, default=0.6)
    parser.add_argument('--poll-interval', type=float, default=0.1)
    parser.add_argument('--keep-torque', action='store_true', help='Leave torque enabled after each servo test')
    parser.add_argument('--csv', default='', help='Optional output CSV path')
    args = parser.parse_args()

    ids = parse_ids(args.ids)
    print('Self-test configuration:')
    print(f'  device      : {args.device}')
    print(f'  baud        : {args.baud}')
    print(f'  ids         : {ids}')
    print(f'  speed       : {args.speed}')
    print(f'  acceleration: {args.acc}')
    print(f'  step_size   : {args.step_size}')
    print(f'  max_steps   : {args.max_steps}')
    print('')
    print('Caution: this test drives each servo toward both ends incrementally.')
    print('Use low speeds and stop immediately if the mechanism is near collision.')
    print('')

    tester = ServoTester(args.device, args.baud)
    results: list[ServoResult] = []

    try:
        for sid in ids:
            print(f'=== Servo {sid} ===')
            result = tester.test_servo(
                sid=sid,
                speed=args.speed,
                acc=args.acc,
                step_size=args.step_size,
                max_steps=args.max_steps,
                min_progress=args.min_progress,
                settle_timeout=args.settle_timeout,
                poll_interval=args.poll_interval,
                release_after=not args.keep_torque,
            )
            results.append(result)
            travel_deg = None if result.travel is None else round(result.travel * 270.0 / RAW_MAX, 2)
            print(f'  start     : {result.start_pos}')
            print(f'  low_end   : {result.low_end}  ({result.low_reason})')
            print(f'  high_end  : {result.high_end}  ({result.high_reason})')
            print(f'  travel    : {result.travel} raw / {travel_deg} deg')
            print(f'  max_load  : {result.max_load}')
            print(f'  temp/volt : {result.temp_c} C / {result.voltage_v} V')
            print('')
    finally:
        tester.close()

    csv_path = Path(args.csv) if args.csv else Path('recordings') / f'joint_limit_self_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    write_results_csv(csv_path, results)
    print(f'Wrote summary CSV: {csv_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
