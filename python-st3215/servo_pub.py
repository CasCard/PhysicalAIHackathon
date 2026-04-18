#!/usr/bin/env python3
"""
Real-time MQTT publisher for ST3215 servo data.
Monitors servo parameters and publishes to MQTT broker.
Automatically sleeps when servo_control.py is running and reconnects after 3 seconds.
"""

import json
import time
import threading
import psutil
import sys
import signal
from datetime import datetime
from st3215 import ST3215
import paho.mqtt.client as mqtt


class ServoMQTTPublisher:
    def __init__(self, device="/dev/ttyUSB0", mqtt_broker="localhost", mqtt_port=1883, 
                 publish_interval=0.1, servo_ids=None):
        self.device = device
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.publish_interval = publish_interval
        self.servo_ids = servo_ids or []
        self.running = False
        self.paused = False
        self.servo = None
        self.mqtt_client = None
        self.publish_thread = None
        self.monitor_thread = None
        self.lock = threading.Lock()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print(f"\nReceived signal {signum}. Shutting down gracefully...")
        self.stop()
        sys.exit(0)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"Connected to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}")
        else:
            print(f"Failed to connect to MQTT broker. Return code: {rc}")

    def _on_mqtt_disconnect(self, client, userdata, rc):
        print(f"Disconnected from MQTT broker. Return code: {rc}")

    def _initialize_servo(self):
        """Initialize servo connection."""
        try:
            if self.servo:
                try:
                    self.servo.portHandler.closePort()
                except:
                    pass
            
            self.servo = ST3215(self.device)
            print(f"Connected to servo device: {self.device}")
            
            # Auto-discover servos if none specified
            if not self.servo_ids:
                discovered_servos = self.servo.ListServos()
                if discovered_servos:
                    self.servo_ids = discovered_servos
                    print(f"Auto-discovered servos: {self.servo_ids}")
                else:
                    print("No servos found on the bus")
                    return False
            
            return True
        except Exception as e:
            print(f"Failed to initialize servo: {e}")
            return False

    def _initialize_mqtt(self):
        """Initialize MQTT client."""
        try:
            if self.mqtt_client:
                try:
                    self.mqtt_client.disconnect()
                except:
                    pass
            
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            return True
        except Exception as e:
            print(f"Failed to initialize MQTT: {e}")
            return False

    def _is_servo_control_running(self):
        """Check if servo_control.py is currently running."""
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info['cmdline']
                    if cmdline and any('servo_control.py' in arg for arg in cmdline):
                        return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except Exception:
            return False

    def _read_servo_data(self, servo_id):
        """Read all available data from a servo."""
        data = {
            'servo_id': servo_id,
            'timestamp': datetime.now().isoformat(),
            'position': None,
            'voltage': None,
            'temperature': None,
            'current': None,
            'load': None,
            'mode': None,
            'status': None,
            'moving': None
        }
        
        try:
            # Read all sensor data
            data['position'] = self.servo.ReadPosition(servo_id)
            data['voltage'] = self.servo.ReadVoltage(servo_id)
            data['temperature'] = self.servo.ReadTemperature(servo_id)
            data['current'] = self.servo.ReadCurrent(servo_id)
            data['load'] = self.servo.ReadLoad(servo_id)
            data['mode'] = self.servo.ReadMode(servo_id)
            data['status'] = self.servo.ReadStatus(servo_id)
            data['moving'] = self.servo.IsMoving(servo_id)
            
        except Exception as e:
            print(f"Error reading servo {servo_id} data: {e}")
        
        return data

    def _publish_servo_data(self):
        """Main publishing loop."""
        while self.running:
            try:
                # Check if we should pause due to servo_control.py running
                if self._is_servo_control_running():
                    if not self.paused:
                        print("servo_control.py detected. Pausing publisher...")
                        self.paused = True
                        # Close servo connection to avoid conflicts
                        if self.servo:
                            try:
                                self.servo.portHandler.closePort()
                            except:
                                pass
                            self.servo = None
                    
                    time.sleep(1)  # Check every second while paused
                    continue
                
                # Resume if we were paused
                if self.paused:
                    print("servo_control.py finished. Resuming publisher in 3 seconds...")
                    time.sleep(3)  # Wait 3 seconds before reconnecting
                    
                    if not self._initialize_servo():
                        print("Failed to reconnect to servo. Retrying in 5 seconds...")
                        time.sleep(5)
                        continue
                    
                    self.paused = False
                    print("Publisher resumed.")
                
                # Ensure we have active connections
                if not self.servo and not self._initialize_servo():
                    print("Servo connection lost. Retrying in 5 seconds...")
                    time.sleep(5)
                    continue
                
                if not self.mqtt_client or not self.mqtt_client.is_connected():
                    if not self._initialize_mqtt():
                        print("MQTT connection lost. Retrying in 5 seconds...")
                        time.sleep(5)
                        continue
                
                # Collect and publish data from all servos
                for servo_id in self.servo_ids:
                    if not self.running:
                        break
                    
                    servo_data = self._read_servo_data(servo_id)
                    
                    # Publish to individual servo topic
                    topic = f"servo/{servo_id}/data"
                    payload = json.dumps(servo_data, indent=None, separators=(',', ':'))
                    
                    try:
                        result = self.mqtt_client.publish(topic, payload, qos=0)
                        if result.rc != mqtt.MQTT_ERR_SUCCESS:
                            print(f"Failed to publish data for servo {servo_id}")
                    except Exception as e:
                        print(f"Error publishing data for servo {servo_id}: {e}")
                
                # Publish combined data to aggregate topic
                if self.servo_ids:
                    all_data = {
                        'timestamp': datetime.now().isoformat(),
                        'servos': [self._read_servo_data(sid) for sid in self.servo_ids]
                    }
                    
                    try:
                        payload = json.dumps(all_data, indent=None, separators=(',', ':'))
                        result = self.mqtt_client.publish("servo/all/data", payload, qos=0)
                        if result.rc == mqtt.MQTT_ERR_SUCCESS:
                            print(f"Published data for {len(self.servo_ids)} servos")
                    except Exception as e:
                        print(f"Error publishing aggregate data: {e}")
                
                time.sleep(self.publish_interval)
                
            except Exception as e:
                print(f"Error in publishing loop: {e}")
                time.sleep(1)

    def start(self):
        """Start the publisher."""
        if self.running:
            print("Publisher is already running")
            return
        
        print("Starting servo MQTT publisher...")
        
        # Initialize connections
        if not self._initialize_servo():
            print("Failed to initialize servo connection")
            return False
        
        if not self._initialize_mqtt():
            print("Failed to initialize MQTT connection")
            return False
        
        self.running = True
        
        # Start publishing thread
        self.publish_thread = threading.Thread(target=self._publish_servo_data, daemon=True)
        self.publish_thread.start()
        
        print(f"Publisher started. Monitoring servos: {self.servo_ids}")
        print(f"Publishing interval: {self.publish_interval}s")
        print(f"MQTT broker: {self.mqtt_broker}:{self.mqtt_port}")
        print("Press Ctrl+C to stop...")
        
        return True

    def stop(self):
        """Stop the publisher."""
        if not self.running:
            return
        
        print("Stopping publisher...")
        self.running = False
        
        # Wait for threads to finish
        if self.publish_thread and self.publish_thread.is_alive():
            self.publish_thread.join(timeout=2)
        
        # Close connections
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
        
        if self.servo:
            try:
                self.servo.portHandler.closePort()
            except:
                pass
        
        print("Publisher stopped")

    def run_forever(self):
        """Run the publisher until interrupted."""
        if not self.start():
            return
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='ST3215 Servo MQTT Publisher')
    parser.add_argument('--device', default='/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0', help='Serial device path')
    parser.add_argument('--broker', default='localhost', help='MQTT broker address')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--interval', type=float, default=0.1, help='Publishing interval in seconds')
    parser.add_argument('--servos', type=str, help='Comma-separated list of servo IDs (auto-discover if not specified)')
    
    args = parser.parse_args()
    
    # Parse servo IDs
    servo_ids = []
    if args.servos:
        try:
            servo_ids = [int(x.strip()) for x in args.servos.split(',')]
        except ValueError:
            print("Error: Invalid servo IDs format. Use comma-separated integers.")
            sys.exit(1)
    
    # Create and run publisher
    publisher = ServoMQTTPublisher(
        device=args.device,
        mqtt_broker=args.broker,
        mqtt_port=args.port,
        publish_interval=args.interval,
        servo_ids=servo_ids
    )
    
    publisher.run_forever()


if __name__ == "__main__":
    main()