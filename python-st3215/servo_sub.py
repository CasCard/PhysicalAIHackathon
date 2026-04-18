#!/usr/bin/env python3
"""
MQTT subscriber for ST3215 servo data.
Receives and processes servo data from the servo_pub.py publisher.
"""

import json
import time
import sys
import signal
from datetime import datetime
import paho.mqtt.client as mqtt


class ServoMQTTSubscriber:
    def __init__(self, mqtt_broker="localhost", mqtt_port=1883, servo_ids=None):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.servo_ids = servo_ids or []
        self.running = False
        self.mqtt_client = None
        self.data_callback = None
        
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
            self._subscribe_to_topics()
        else:
            print(f"Failed to connect to MQTT broker. Return code: {rc}")

    def _on_mqtt_disconnect(self, client, userdata, rc):
        print(f"Disconnected from MQTT broker. Return code: {rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            topic = msg.topic
            payload = json.loads(msg.payload.decode())
            
            print(f"Received message on topic: {topic}")
            
            if topic == "servo/all/data":
                self._handle_aggregate_data(payload)
            elif topic.startswith("servo/") and topic.endswith("/data"):
                # Extract servo ID from topic: servo/{id}/data
                servo_id = int(topic.split('/')[1])
                self._handle_individual_servo_data(servo_id, payload)
            
            # Call user-defined callback if set
            if self.data_callback:
                self.data_callback(topic, payload)
                
        except Exception as e:
            print(f"Error processing message on topic {msg.topic}: {e}")

    def _handle_aggregate_data(self, data):
        """Handle aggregate data from all servos."""
        timestamp = data.get('timestamp', 'N/A')
        servos_data = data.get('servos', [])
        
        print(f"\n=== Aggregate Servo Data ({timestamp}) ===")
        for servo_data in servos_data:
            servo_id = servo_data.get('servo_id', 'Unknown')
            position = servo_data.get('position', 'N/A')
            voltage = servo_data.get('voltage', 'N/A')
            temperature = servo_data.get('temperature', 'N/A')
            current = servo_data.get('current', 'N/A')
            
            print(f"Servo {servo_id}: Pos={position}, V={voltage}V, T={temperature}°C, I={current}mA")

    def _handle_individual_servo_data(self, servo_id, data):
        """Handle data from individual servo."""
        timestamp = data.get('timestamp', 'N/A')
        position = data.get('position', 'N/A')
        voltage = data.get('voltage', 'N/A')
        temperature = data.get('temperature', 'N/A')
        current = data.get('current', 'N/A')
        load = data.get('load', 'N/A')
        mode = data.get('mode', 'N/A')
        status = data.get('status', 'N/A')
        moving = data.get('moving', 'N/A')
        
        print(f"\n--- Servo {servo_id} Data ({timestamp}) ---")
        print(f"Position: {position}")
        print(f"Voltage: {voltage}V")
        print(f"Temperature: {temperature}°C")
        print(f"Current: {current}mA")
        print(f"Load: {load}")
        print(f"Mode: {mode}")
        print(f"Status: {status}")
        print(f"Moving: {moving}")

    def _subscribe_to_topics(self):
        """Subscribe to relevant MQTT topics."""
        try:
            # Subscribe to aggregate data
            self.mqtt_client.subscribe("servo/all/data")
            print("Subscribed to: servo/all/data")
            
            # Subscribe to individual servo topics if specific servos are specified
            if self.servo_ids:
                for servo_id in self.servo_ids:
                    topic = f"servo/{servo_id}/data"
                    self.mqtt_client.subscribe(topic)
                    print(f"Subscribed to: {topic}")
            else:
                # Subscribe to all individual servo topics using wildcard
                self.mqtt_client.subscribe("servo/+/data")
                print("Subscribed to: servo/+/data (all individual servos)")
                
        except Exception as e:
            print(f"Error subscribing to topics: {e}")

    def set_data_callback(self, callback):
        """Set a custom callback function to handle received data.
        
        Callback function should accept (topic, payload) parameters.
        """
        self.data_callback = callback

    def start(self):
        """Start the subscriber."""
        if self.running:
            print("Subscriber is already running")
            return
        
        print("Starting servo MQTT subscriber...")
        
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
            self.mqtt_client.on_message = self._on_mqtt_message
            
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            
            self.running = True
            print(f"Subscriber started. Connected to {self.mqtt_broker}:{self.mqtt_port}")
            if self.servo_ids:
                print(f"Monitoring specific servos: {self.servo_ids}")
            else:
                print("Monitoring all servos")
            print("Press Ctrl+C to stop...")
            
            return True
            
        except Exception as e:
            print(f"Failed to start subscriber: {e}")
            return False

    def stop(self):
        """Stop the subscriber."""
        if not self.running:
            return
        
        print("Stopping subscriber...")
        self.running = False
        
        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
        
        print("Subscriber stopped")

    def run_forever(self):
        """Run the subscriber until interrupted."""
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
    
    parser = argparse.ArgumentParser(description='ST3215 Servo MQTT Subscriber')
    parser.add_argument('--broker', default='localhost', help='MQTT broker address')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--servos', type=str, help='Comma-separated list of servo IDs to monitor (monitor all if not specified)')
    
    args = parser.parse_args()
    
    # Parse servo IDs
    servo_ids = []
    if args.servos:
        try:
            servo_ids = [int(x.strip()) for x in args.servos.split(',')]
        except ValueError:
            print("Error: Invalid servo IDs format. Use comma-separated integers.")
            sys.exit(1)
    
    # Create and run subscriber
    subscriber = ServoMQTTSubscriber(
        mqtt_broker=args.broker,
        mqtt_port=args.port,
        servo_ids=servo_ids
    )
    
    subscriber.run_forever()


if __name__ == "__main__":
    main()