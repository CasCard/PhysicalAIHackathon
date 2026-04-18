# import serial
# import time

# # Open serial connection
# ser = serial.Serial('/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0', 115200, timeout=1)
# time.sleep(1)

# def send_ping(servo_id):
#     # Format: 0xFF 0xFF [ID] 0x02 0x01 [Checksum]
#     checksum = (~(servo_id + 2 + 1) & 0xFF)
#     cmd = bytearray([0xFF, 0xFF, servo_id, 0x02, 0x01, checksum])
#     ser.write(cmd)
#     time.sleep(0.1)
#     response = ser.read(100)
#     print(f"Response: {response.hex()}")

# def send_move_command(servo_id, position, speed):
#     # Format: 0xFF 0xFF [ID] 0x07 0x03 [POS_L] [POS_H] [TIME] [SPEED_L] [SPEED_H] [CHECKSUM]
#     pos_l = position & 0xFF
#     pos_h = (position >> 8) & 0xFF
#     spd_l = speed & 0xFF
#     spd_h = (speed >> 8) & 0xFF
#     length = 7
#     instruction = 0x03  # WRITE
#     time_byte = 0
    
#     checksum = (~(servo_id + length + instruction + pos_l + pos_h + time_byte + spd_l + spd_h) & 0xFF)
    
#     cmd = bytearray([0xFF, 0xFF, servo_id, length, instruction, 
#                      pos_l, pos_h, time_byte, spd_l, spd_h, checksum])
    
#     print(f"Sending: {' '.join([f'{b:02X}' for b in cmd])}")
#     ser.write(cmd)
#     time.sleep(0.1)
#     response = ser.read(100)
#     print(f"Response: {response.hex()}")

# # Clear any pending data
# ser.flushInput()
# time.sleep(0.5)

# # Try broadcasting to all servos (ID 0xFE)
# print("Sending broadcast move command...")
# send_move_command(0xFE, 500, 1000)  # Move to position 500 at speed 1000
# time.sleep(2)

# # Try scanning for servos
# print("\nScanning for servos...")
# for id in range(1, 20):  # Try IDs 1-19
#     print(f"Pinging ID {id}...")
#     send_ping(id)
#     time.sleep(0.1)

# ser.close()

### Test 2

import serial
import time

# Open serial connection
ser = serial.Serial('/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0', 115200, timeout=1)
time.sleep(1)

def send_move_command(servo_id, position, speed):
    # Format: 0xFF 0xFF [ID] 0x07 0x03 [POS_L] [POS_H] [TIME] [SPEED_L] [SPEED_H] [CHECKSUM]
    pos_l = position & 0xFF
    pos_h = (position >> 8) & 0xFF
    spd_l = speed & 0xFF
    spd_h = (speed >> 8) & 0xFF
    length = 7
    instruction = 0x03  # WRITE
    time_byte = 0
    
    checksum = (~(servo_id + length + instruction + pos_l + pos_h + time_byte + spd_l + spd_h) & 0xFF)
    
    cmd = bytearray([0xFF, 0xFF, servo_id, length, instruction, 
                     pos_l, pos_h, time_byte, spd_l, spd_h, checksum])
    
    print(f"Sending: {' '.join([f'{b:02X}' for b in cmd])}")
    ser.write(cmd)
    time.sleep(0.1)
    response = ser.read(100)
    print(f"Response: {response.hex()}")

# Clear any pending data
ser.flushInput()

# Move servo ID 4 to different positions
servo_id = 4

print("Moving to position 500...")
send_move_command(servo_id, 500, 1000)  # Position 500, speed 1000
time.sleep(1)

print("Moving to position 100...")
send_move_command(servo_id, 100, 1000)  # Position 100, speed 1000
time.sleep(1)

print("Moving to position 900...")
send_move_command(servo_id, 900, 1000)  # Position 900, speed 1000
time.sleep(1)

ser.close()
print("Test complete!")