#!/usr/bin/env python3
"""
scan_servos.py — Diagnostic servo scanner for the ST3215 bus
Hardware: Silicon Labs CP210x UART Bridge (Bus 003 Device 014, ID 10c4:ea60)

Usage:
    python3 scan_servos.py                      # auto-detect port
    python3 scan_servos.py --device /dev/ttyUSB0
    python3 scan_servos.py --range 1 10         # only ping IDs 1-10 (faster)
    python3 scan_servos.py --read               # also read telemetry for each found servo
"""

import argparse
import sys
import os

# Allow running from the repo root without installing the package
sys.path.insert(0, os.path.dirname(__file__))

from st3215 import ST3215

# ── known symlink created by udev for your CP210x ──────────────────────────
BY_ID = (
    "/dev/serial/by-id/"
    "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
)
FALLBACK_DEVICE = "/dev/ttyUSB0"


def find_device() -> str:
    if os.path.exists(BY_ID):
        return BY_ID
    if os.path.exists(FALLBACK_DEVICE):
        print(f"[warn] by-id symlink not found, using fallback {FALLBACK_DEVICE}")
        return FALLBACK_DEVICE
    raise FileNotFoundError(
        "Could not find the CP210x serial port. "
        "Check that the USB cable is plugged in and the device is enumerated."
    )


def scan(device: str, id_range: range, read_telemetry: bool) -> None:
    print(f"\n=== ST3215 Servo Scanner ===")
    print(f"Port   : {device}")
    print(f"ID scan: {id_range.start} → {id_range.stop - 1}  ({len(id_range)} IDs)\n")

    try:
        servo = ST3215(device)
    except Exception as exc:
        print(f"[ERROR] Cannot open port: {exc}")
        print("\nTroubleshooting tips:")
        print("  • Check 'ls -la /dev/ttyUSB*' — device must exist")
        print("  • Add yourself to the 'dialout' group:  sudo usermod -aG dialout $USER")
        print("  • Verify power to the servo bus (not just USB power)")
        sys.exit(1)

    print("Port opened successfully. Scanning…\n")

    found = []
    for sid in id_range:
        ok = servo.PingServo(sid)
        marker = "✓ FOUND" if ok else "  ----"
        print(f"  ID {sid:3d}: {marker}")
        if ok:
            found.append(sid)

    print(f"\n{'─'*40}")
    print(f"Total servos detected: {len(found)}")
    if found:
        print(f"Servo IDs found      : {found}")
    else:
        print("No servos detected.")
        print("\nPossible causes:")
        print("  1. Servo IDs may be outside the scanned range — try '--range 0 253'")
        print("  2. Servo bus has no power (check 7.4 V–12 V supply)")
        print("  3. Wrong baud rate — library uses 115200; some servos ship at 1,000,000 bps")
        print("  4. Half-duplex wiring issue — TX, RX and the servo DATA line must be bridged")
        print("  5. Loose connector on the servo bus cable")

    if read_telemetry and found:
        print(f"\n{'─'*40}")
        print("Telemetry snapshot for each detected servo:\n")
        for sid in found:
            print(f"  Servo {sid}:")
            print(f"    Position   : {servo.ReadPosition(sid)}")
            print(f"    Voltage    : {servo.ReadVoltage(sid)} V")
            print(f"    Temperature: {servo.ReadTemperature(sid)} °C")
            print(f"    Current    : {servo.ReadCurrent(sid)} mA")
            print(f"    Load       : {servo.ReadLoad(sid)} %")
            print(f"    Mode       : {servo.ReadMode(sid)}")
            print(f"    Moving     : {servo.IsMoving(sid)}")
            status = servo.ReadStatus(sid)
            if status:
                faults = [k for k, v in status.items() if not v]
                print(f"    Status     : {'OK' if not faults else 'FAULT: ' + ', '.join(faults)}")
            print()

    servo.portHandler.closePort()
    print("Port closed. Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="ST3215 servo bus scanner")
    parser.add_argument(
        "--device", default=None,
        help="Serial device path (default: auto-detect CP210x)"
    )
    parser.add_argument(
        "--range", nargs=2, type=int, metavar=("START", "END"),
        default=[0, 16],
        help="ID range to scan inclusive [START, END] (default: 0 16)"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Scan the full ID space 0-253 (slow, ~30 s)"
    )
    parser.add_argument(
        "--read", action="store_true",
        help="Read telemetry from every detected servo"
    )
    args = parser.parse_args()

    device = args.device or find_device()
    start, end = args.range
    if args.full:
        start, end = 0, 253
    id_range = range(start, end + 1)

    scan(device, id_range, read_telemetry=args.read)


if __name__ == "__main__":
    main()
