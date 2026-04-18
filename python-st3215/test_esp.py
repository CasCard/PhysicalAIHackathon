import serial
import time
import binascii

def monitor_serial():
    port = "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
    ser = serial.Serial(port, 115200, timeout=0.1)
    
    print("Serial monitoring started. Press Ctrl+C to exit.")
    
    try:
        while True:
            # Send a test command (optional)
            # Uncomment to send a PING command to servo ID 1 every 5 seconds
            # if time.time() % 5 < 0.1:
            #     cmd = bytearray([0xFF, 0xFF, 0x01, 0x02, 0x01, 0xFB])
            #     print(f">>> TX: {binascii.hexlify(cmd).decode()}")
            #     ser.write(cmd)
            
            # Read any incoming data
            if ser.in_waiting:
                data = ser.read(ser.in_waiting)
                if data:
                    print(f"<<< RX: {binascii.hexlify(data).decode()}")
                    print(f"    ASCII: {data}")
            
            time.sleep(0.01)
    
    except KeyboardInterrupt:
        print("Monitoring stopped.")
    finally:
        ser.close()

if __name__ == "__main__":
    monitor_serial()