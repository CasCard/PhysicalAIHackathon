#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')
from st3215 import ST3215

DEVICE = '/dev/ttyUSB0'

print(f'Opening port: {DEVICE}', flush=True)
try:
    servo = ST3215(DEVICE)
    print('Port opened OK. Scanning IDs 0-253...', flush=True)
except Exception as e:
    print(f'ERROR opening port: {e}', flush=True)
    sys.exit(1)

found = []
for sid in range(0, 254):
    ok = servo.PingServo(sid)
    if ok:
        print(f'  >>> FOUND servo at ID {sid}', flush=True)
        found.append(sid)

print(flush=True)
print(f'Scan complete. Total servos found: {len(found)}', flush=True)
print(f'Servo IDs: {found}', flush=True)

if found:
    print('\n--- Telemetry ---', flush=True)
    for sid in found:
        print(f'Servo {sid}:', flush=True)
        print(f'  Position   : {servo.ReadPosition(sid)}', flush=True)
        print(f'  Voltage    : {servo.ReadVoltage(sid)} V', flush=True)
        print(f'  Temperature: {servo.ReadTemperature(sid)} C', flush=True)
        print(f'  Current    : {servo.ReadCurrent(sid)} mA', flush=True)
        print(f'  Load       : {servo.ReadLoad(sid)} %', flush=True)
        print(f'  Mode       : {servo.ReadMode(sid)}', flush=True)
        print(f'  Moving     : {servo.IsMoving(sid)}', flush=True)
        status = servo.ReadStatus(sid)
        if status:
            faults = [k for k, v in status.items() if not v]
            print(f'  Status     : {"OK" if not faults else "FAULT: " + ", ".join(faults)}', flush=True)
else:
    print('\nNo servos detected!', flush=True)
    print('Possible causes:', flush=True)
    print('  1. No power to the servo bus (need 7.4-12V supply)', flush=True)
    print('  2. Wrong baud rate (library=115200, some servos ship at 1,000,000)', flush=True)
    print('  3. Half-duplex TX/RX wiring issue', flush=True)

servo.portHandler.closePort()
print('\nPort closed.', flush=True)
