#!/usr/bin/env python3
"""
waveshare_scan.py — Servo scanner for Waveshare Bus Servo Adapter (A)

Tries both common baud rates:
  • 1,000,000 bps  (ST3215 factory default)
  • 115,200 bps    (python-st3215 library default)

USB mode requires the jumper cap on the adapter to be in the B position.
"""

import sys
import serial
sys.path.insert(0, '.')
from st3215.port_handler import PortHandler
from st3215.protocol_packet_handler import protocol_packet_handler

DEVICE = '/dev/ttyUSB0'
BAUD_RATES = [1_000_000, 115_200]

class FastST3215(protocol_packet_handler):
    """Minimal ST3215 wrapper that accepts a custom baud rate."""
    def __init__(self, device, baudrate=1_000_000):
        self.portHandler = PortHandler(device)
        self.portHandler.baudrate = baudrate          # override before openPort
        if not self.portHandler.openPort():
            raise ValueError(f"Could not open port: {device}")
        protocol_packet_handler.__init__(self, self.portHandler)

    def ping_id(self, sid):
        model, comm, error = self.ping(sid)
        return comm == 0 and model != 0 and error == 0

    def close(self):
        self.portHandler.closePort()


def scan_at_baud(baudrate):
    print(f"\n{'='*50}")
    print(f"Scanning at {baudrate:,} bps on {DEVICE}")
    print(f"{'='*50}")
    try:
        bus = FastST3215(DEVICE, baudrate=baudrate)
    except Exception as e:
        print(f"[ERROR] Could not open port: {e}")
        return None

    found = []
    print("Pinging IDs 0–253 ...", flush=True)
    for sid in range(0, 254):
        if bus.ping_id(sid):
            print(f"  >>> FOUND servo at ID {sid}", flush=True)
            found.append(sid)

    bus.close()
    print(f"\nResult at {baudrate:,} bps: {len(found)} servo(s) found: {found}")
    return found


def read_telemetry(baudrate, found_ids):
    if not found_ids:
        return
    print(f"\n{'─'*50}")
    print(f"Telemetry at {baudrate:,} bps")
    print(f"{'─'*50}")

    # Re-open for reads (use full ST3215 class)
    from st3215 import ST3215

    # Patch baud before opening
    orig_init = PortHandler.__init__
    baud_cap = baudrate
    def patched_init(self, port_name):
        orig_init(self, port_name)
        self.baudrate = baud_cap
    PortHandler.__init__ = patched_init

    try:
        servo = ST3215(DEVICE)
    except Exception as e:
        print(f"[ERROR] {e}")
        PortHandler.__init__ = orig_init
        return
    finally:
        PortHandler.__init__ = orig_init

    for sid in found_ids:
        print(f"\nServo ID {sid}:")
        print(f"  Position   : {servo.ReadPosition(sid)}")
        print(f"  Voltage    : {servo.ReadVoltage(sid)} V")
        print(f"  Temperature: {servo.ReadTemperature(sid)} °C")
        print(f"  Current    : {servo.ReadCurrent(sid)} mA")
        print(f"  Load       : {servo.ReadLoad(sid)} %")
        print(f"  Mode       : {servo.ReadMode(sid)}")
        print(f"  Moving     : {servo.IsMoving(sid)}")
        status = servo.ReadStatus(sid)
        if status:
            faults = [k for k, v in status.items() if not v]
            print(f"  Status     : {'OK' if not faults else 'FAULT: ' + ', '.join(faults)}")

    servo.portHandler.closePort()


def main():
    print("Waveshare Bus Servo Adapter (A) — Servo Scanner")
    print("Reminder: jumper cap must be in B position for USB mode\n")

    overall_found = {}
    for baud in BAUD_RATES:
        result = scan_at_baud(baud)
        if result is not None:
            overall_found[baud] = result

    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    any_found = False
    for baud, ids in overall_found.items():
        if ids:
            any_found = True
            print(f"  ✓  {baud:,} bps → found {len(ids)} servo(s): IDs {ids}")
            read_telemetry(baud, ids)
        else:
            print(f"  ✗  {baud:,} bps → no servos")

    if not any_found:
        print("\nNo servos detected at any baud rate.")
        print("\nTroubleshooting checklist:")
        print("  [?] Is the jumper on the adapter in the B position (USB mode)?")
        print("  [?] Is the DC power supply (9-12.6 V) plugged into the adapter?")
        print("  [?] Is the servo connected to the Bus Servo port on the adapter?")
        print("  [?] Is the servo's own cable firmly seated?")
        print("  [?] Factory default servo ID is 1 — scan confirmed IDs 0-253")


if __name__ == '__main__':
    main()
