#!/usr/bin/env python3

import time
import sys
from st3215 import ST3215

def main():
    # Replace with your actual serial device
    DEVICE = '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0'
    
    # Connect to the device
    try:
        servo = ST3215(DEVICE)
        print(f"Successfully connected to {DEVICE}")
    except Exception as e:
        print(f"Error connecting to device: {e}")
        sys.exit(1)
        
    # List all connected servos
    servo_ids = servo.ListServos()
    if not servo_ids:
        print("No servos found! Check connections and try again.")
        sys.exit(1)
    
    print(f"Found {len(servo_ids)} servos with IDs: {servo_ids}")
    
    # Working with first servo found
    servo_id = servo_ids[0]
    print(f"Working with servo ID: {servo_id}")
    
    # Read servo information
    print("\n--- Servo Information ---")
    print(f"Position: {servo.ReadPosition(servo_id)}")
    print(f"Voltage: {servo.ReadVoltage(servo_id)}V")
    print(f"Temperature: {servo.ReadTemperature(servo_id)}°C")
    print(f"Current: {servo.ReadCurrent(servo_id)}mA")
    print(f"Load: {servo.ReadLoad(servo_id)}%")
    print(f"Mode: {servo.ReadMode(servo_id)}")
    
    # Start the servo (enable torque)
    print("\n--- Starting servo ---")
    servo.StartServo(servo_id)
    
    # Set servo to position mode
    servo.SetMode(servo_id, 0)
    
    # Move to center position
    print("\n--- Moving to center position ---")
    servo.MoveTo(servo_id, 2048, speed=1000)
    time.sleep(2)
    
    print("\n--- Moving to different positions ---")
    # Move to 90 degrees clockwise from center
    print("Moving to 90 degrees clockwise...")
    servo.MoveTo(servo_id, 1024, speed=1000)
    time.sleep(2)
    
    # Move to 90 degrees counterclockwise from center
    print("Moving to 90 degrees counterclockwise...")
    servo.MoveTo(servo_id, 3072, speed=1000)
    time.sleep(2)
    
    # Back to center
    print("Moving back to center...")
    servo.MoveTo(servo_id, 2048, speed=1000)
    time.sleep(2)
    
    # Demonstrate continuous rotation
    print("\n--- Demonstrating continuous rotation ---")
    servo.SetMode(servo_id, 1)  # Set to continuous rotation mode
    
    print("Rotating clockwise...")
    servo.Rotate(servo_id, 500)
    time.sleep(3)
    
    print("Rotating counterclockwise...")
    servo.Rotate(servo_id, -500)
    time.sleep(3)
    
    print("Stopping rotation...")
    servo.StopServo(servo_id)
    time.sleep(1)
    
    # Return to position mode and center
    print("\n--- Returning to position mode and center ---")
    servo.SetMode(servo_id, 0)
    servo.MoveTo(servo_id, 2048, speed=1000)
    time.sleep(2)
    
    # Check status
    status = servo.ReadStatus(servo_id)
    if status:
        print("\n--- Servo Status ---")
        print(f"Status: {status}")
    # Disable torque when done
    print("\n--- Stopping servo ---")
    servo.StopServo(servo_id)
    
    print("\nExample completed successfully!")

if __name__ == "__main__":
    main()
