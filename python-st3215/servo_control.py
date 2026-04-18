#!/usr/bin/env python3
"""
Command line interface for ST3215 servo controller.
This script provides a CLI interface to the ST3215 servo library.
This file is intended to live inside Grafito-Edge-Services/python-st3215.
"""

import argparse
import sys
import time
from st3215 import ST3215

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='ST3215 Servo Controller CLI')
    parser.add_argument('--device', required=True, help='Serial device path')
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Move command
    move_parser = subparsers.add_parser('move', help='Move servo to position')
    move_parser.add_argument('servo_id', type=int, help='Servo ID')
    move_parser.add_argument('position', type=int, help='Position (0-4095)')
    move_parser.add_argument('speed', type=int, default=1000, nargs='?', help='Movement speed')
    
    # Rotate command
    rotate_parser = subparsers.add_parser('rotate', help='Rotate servo continuously')
    rotate_parser.add_argument('servo_id', type=int, help='Servo ID')
    rotate_parser.add_argument('speed', type=int, help='Rotation speed (-1000 to 1000)')
    
    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop servo')
    stop_parser.add_argument('servo_id', type=int, help='Servo ID')
    
    # Mode command
    mode_parser = subparsers.add_parser('mode', help='Set servo mode')
    mode_parser.add_argument('servo_id', type=int, help='Servo ID')
    mode_parser.add_argument('mode', type=int, help='Mode (0=position, 1=rotation)')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Get servo status')
    status_parser.add_argument('servo_id', type=int, help='Servo ID')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all connected servos')
    
    # Check command (comprehensive status check)
    check_parser = subparsers.add_parser('check', help='Check servo parameters')
    check_parser.add_argument('servo_id', type=int, help='Servo ID')
    
    return parser.parse_args()

def main():
    """Main function."""
    args = parse_args()
    
    # Connect to the device
    try:
        servo = ST3215(args.device)
    except Exception as e:
        print(f"Error connecting to device: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Execute the requested command
    try:
        if args.command == 'move':
            # Set position mode if not already
            servo.SetMode(args.servo_id, 0)
            # Start servo to enable torque
            servo.StartServo(args.servo_id)
            # Move to position
            servo.MoveTo(args.servo_id, args.position, speed=args.speed)
            print(f"Moved servo {args.servo_id} to position {args.position}")
            
        elif args.command == 'rotate':
            # Set rotation mode
            servo.SetMode(args.servo_id, 1)
            # Start servo
            servo.StartServo(args.servo_id)
            # Start rotation
            servo.Rotate(args.servo_id, args.speed)
            print(f"Rotating servo {args.servo_id} at speed {args.speed}")
            
        elif args.command == 'stop':
            # Stop the servo
            servo.StopServo(args.servo_id)
            print(f"Stopped servo {args.servo_id}")
            
        elif args.command == 'mode':
            # Set servo mode
            servo.SetMode(args.servo_id, args.mode)
            mode_name = "position" if args.mode == 0 else "rotation"
            print(f"Set servo {args.servo_id} to {mode_name} mode")
            
        elif args.command == 'status':
            # Read servo status
            status = servo.ReadStatus(args.servo_id)
            print(f"Servo {args.servo_id} status: {status}")
            
        elif args.command == 'list':
            # List all servos
            servo_ids = servo.ListServos()
            if servo_ids:
                print(f"Found {len(servo_ids)} servos: {servo_ids}")
            else:
                print("No servos found")
                
        elif args.command == 'check':
            # Comprehensive status check
            print(f"=== Servo {args.servo_id} Information ===")
            print(f"Position: {servo.ReadPosition(args.servo_id)}")
            print(f"Voltage: {servo.ReadVoltage(args.servo_id)}V")
            print(f"Temperature: {servo.ReadTemperature(args.servo_id)}°C")
            print(f"Current: {servo.ReadCurrent(args.servo_id)}mA")
            print(f"Load: {servo.ReadLoad(args.servo_id)}%")
            print(f"Mode: {servo.ReadMode(args.servo_id)}")
            print(f"Status: {servo.ReadStatus(args.servo_id)}")
        
    except Exception as e:
        print(f"Error executing command: {e}", file=sys.stderr)
        sys.exit(2)
    
    sys.exit(0)

if __name__ == "__main__":
    main()
