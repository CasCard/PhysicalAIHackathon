#!/usr/bin/env python3
"""
Persistent MQTT bridge for ST3215 serial-bus servos.

The bridge keeps the UART open, executes commands from MQTT, and publishes
continuous telemetry so Klipper macros and Grafito services do not need to
re-initialize the servo stack on every action.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import paho.mqtt.client as mqtt

from st3215 import ST3215


DEFAULT_DEVICE = (
    "/dev/serial/by-id/"
    "usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
)


class TelemetryYield(Exception):
    """Raised when telemetry work should back off for a pending command."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BridgeConfig:
    device: str
    broker: str
    port: int
    servo_ids: List[int] = field(default_factory=list)
    telemetry_interval: float = 0.5
    reconnect_delay: float = 2.0
    discover_interval: float = 0.0
    temperature_warn: float = 55.0
    load_warn: float = 75.0
    current_warn: float = 1200.0
    command_quiet_period: float = 0.15
    servo_cache_file: str = ".servo_ids.json"
    command_topic: str = "grafito/servo/command"
    telemetry_topic: str = "grafito/servo/telemetry"
    per_servo_topic_template: str = "grafito/servo/{servo_id}/telemetry"
    event_topic: str = "grafito/servo/event"
    status_topic: str = "grafito/servo/bridge/status"


class ServoBridge:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.running = False
        self.servo: Optional[ST3215] = None
        self.servo_ids = list(config.servo_ids) or self._load_cached_servo_ids()
        self.mqtt_client: Optional[mqtt.Client] = None
        self.servo_lock = threading.RLock()
        self.command_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.telemetry_thread: Optional[threading.Thread] = None
        self.command_thread: Optional[threading.Thread] = None
        self.last_discovery_at = 0.0
        self.last_command_completed_at = 0.0
        self.client_id = f"st3215-bridge-{int(time.time())}"
        self.command_pending = threading.Event()

    def start(self) -> None:
        self.running = True
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self._setup_mqtt()
        self._ensure_servo()

        self.command_thread = threading.Thread(
            target=self._command_loop,
            name="st3215-command-loop",
            daemon=True,
        )
        self.command_thread.start()

        self.telemetry_thread = threading.Thread(
            target=self._telemetry_loop,
            name="st3215-telemetry-loop",
            daemon=True,
        )
        self.telemetry_thread.start()

        self._publish_bridge_status("online")

        try:
            while self.running:
                time.sleep(1.0)
        finally:
            self.stop()

    def stop(self) -> None:
        if not self.running and self.servo is None and self.mqtt_client is None:
            return

        self.running = False
        self._close_servo()
        self._publish_bridge_status("offline")

        if self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except Exception:
                pass
            self.mqtt_client = None

    def _handle_signal(self, signum: int, _frame: Any) -> None:
        print(f"Received signal {signum}, stopping bridge...", flush=True)
        self.stop()
        sys.exit(0)

    def _setup_mqtt(self) -> None:
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
        )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(
            min_delay=1,
            max_delay=max(2, int(self.config.reconnect_delay * 5)),
        )
        client.connect(self.config.broker, self.config.port, keepalive=60)
        client.loop_start()
        self.mqtt_client = client

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if reason_code == 0:
            print(
                f"Connected to MQTT broker at {self.config.broker}:{self.config.port}",
                flush=True,
            )
            client.subscribe(self.config.command_topic, qos=0)
            self._publish_bridge_status("online")
        else:
            print(f"MQTT connection failed: {reason_code}", flush=True)

    def _on_disconnect(self, _client, _userdata, _disconnect_flags, reason_code, _properties) -> None:
        print(f"Disconnected from MQTT broker: {reason_code}", flush=True)

    def _on_message(self, _client, _userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode())
            if not isinstance(payload, dict):
                raise ValueError("command payload must be a JSON object")
            self.command_pending.set()
            self.command_queue.put(payload)
        except Exception as exc:
            self._publish_event(
                {
                    "timestamp": utc_now(),
                    "status": "error",
                    "error": f"invalid command payload: {exc}",
                    "raw_topic": message.topic,
                }
            )

    def _ensure_servo(self) -> bool:
        with self.servo_lock:
            if self.servo is not None:
                return True

            try:
                self.servo = ST3215(self.config.device)
                print(f"Connected to servo bus on {self.config.device}", flush=True)

                if not self.servo_ids:
                    discovered = self.servo.ListServos()
                    self.last_discovery_at = time.time()
                    if discovered:
                        self.servo_ids = discovered
                        self._save_cached_servo_ids()
                        print(f"Discovered servos: {self.servo_ids}", flush=True)

                return True
            except Exception as exc:
                print(f"Failed to open servo bus: {exc}", flush=True)
                self._close_servo()
                return False

    def _close_servo(self) -> None:
        with self.servo_lock:
            if not self.servo:
                return

            try:
                self.servo.portHandler.closePort()
            except Exception:
                pass
            self.servo = None

    def _should_refresh_discovery(self) -> bool:
        if self.config.servo_ids:
            return False
        if self.config.discover_interval <= 0:
            return False
        if not self.servo_ids:
            return True
        return (time.time() - self.last_discovery_at) >= self.config.discover_interval

    def _telemetry_should_yield(self) -> bool:
        if self.command_pending.is_set():
            return True
        if (time.time() - self.last_command_completed_at) < self.config.command_quiet_period:
            return True
        return False

    def _telemetry_loop(self) -> None:
        while self.running:
            if self._telemetry_should_yield():
                time.sleep(0.02)
                continue

            if not self._ensure_servo():
                self._publish_bridge_status("degraded")
                time.sleep(self.config.reconnect_delay)
                continue

            if self._should_refresh_discovery():
                try:
                    with self.servo_lock:
                        discovered = self.servo.ListServos() if self.servo else []
                    if discovered:
                        self.servo_ids = discovered
                    self.last_discovery_at = time.time()
                except Exception:
                    self._close_servo()
                    time.sleep(self.config.reconnect_delay)
                    continue

            snapshots = []
            for servo_id in self.servo_ids:
                if self._telemetry_should_yield():
                    break
                snapshot = self._read_servo_snapshot(servo_id)
                if snapshot is not None:
                    snapshots.append(snapshot)
                    self._publish_json(
                        self.config.per_servo_topic_template.format(servo_id=servo_id),
                        snapshot,
                    )

            aggregate = {
                "timestamp": utc_now(),
                "bridge": "st3215_bridge",
                "device": self.config.device,
                "connected": self.servo is not None,
                "servo_ids": self.servo_ids,
                "servos": snapshots,
            }
            self._publish_json(self.config.telemetry_topic, aggregate)
            self._publish_bridge_status("online" if self.servo is not None else "degraded")
            time.sleep(self.config.telemetry_interval)

    def _command_loop(self) -> None:
        while self.running:
            try:
                command = self.command_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            result = self._execute_command(command)
            self._publish_event(result)
            self.last_command_completed_at = time.time()
            if self.command_queue.empty():
                self.command_pending.clear()
            self.command_queue.task_done()

    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        request_id = command.get("request_id")
        action = str(command.get("action", "")).strip().lower()
        servo_id = command.get("servo_id")

        result: Dict[str, Any] = {
            "timestamp": utc_now(),
            "request_id": request_id,
            "action": action,
            "servo_id": servo_id,
            "status": "ok",
        }

        if not action:
            result["status"] = "error"
            result["error"] = "missing action"
            return result

        if action not in {"discover", "list", "stop_all"} and servo_id is None:
            result["status"] = "error"
            result["error"] = "missing servo_id"
            return result

        if not self._ensure_servo():
            result["status"] = "error"
            result["error"] = "servo bus unavailable"
            return result

        try:
            with self.servo_lock:
                assert self.servo is not None

                if action in {"discover", "list"}:
                    self.servo_ids = self.servo.ListServos()
                    self.last_discovery_at = time.time()
                    self._save_cached_servo_ids()
                    result["servo_ids"] = self.servo_ids
                    result["count"] = len(self.servo_ids)
                    return result

                if action == "stop_all":
                    stopped = []
                    for discovered_servo_id in self.servo_ids:
                        self.servo.StopServo(discovered_servo_id)
                        stopped.append(discovered_servo_id)
                    result["servo_ids"] = stopped
                    result["count"] = len(stopped)
                    return result

                servo_id = int(servo_id)
                result["servo_id"] = servo_id

                if action == "move":
                    position = int(command["position"])
                    speed = int(command.get("speed", 1000))
                    self.servo.SetMode(servo_id, 0)
                    self.servo.StartServo(servo_id)
                    self.servo.MoveTo(servo_id, position, speed=speed)
                    result.update({"position": position, "speed": speed})
                elif action == "rotate":
                    speed = int(command["speed"])
                    self.servo.SetMode(servo_id, 1)
                    self.servo.StartServo(servo_id)
                    self.servo.Rotate(servo_id, speed)
                    result["speed"] = speed
                elif action == "stop":
                    self.servo.StopServo(servo_id)
                elif action == "start":
                    self.servo.StartServo(servo_id)
                elif action == "mode":
                    mode = int(command["mode"])
                    self.servo.SetMode(servo_id, mode)
                    result["mode"] = mode
                elif action == "status":
                    snapshot = self._read_servo_snapshot(servo_id)
                    result["telemetry"] = snapshot
                elif action == "set_speed":
                    speed = int(command["speed"])
                    self.servo.SetSpeed(servo_id, speed)
                    result["speed"] = speed
                else:
                    result["status"] = "error"
                    result["error"] = f"unsupported action: {action}"
                    return result
        except Exception as exc:
            self._close_servo()
            result["status"] = "error"
            result["error"] = str(exc)

        return result

    def _read_servo_snapshot(self, servo_id: int) -> Optional[Dict[str, Any]]:
        if not self.servo and not self._ensure_servo():
            return None

        try:
            status = self._read_with_priority(lambda servo: servo.ReadStatus(servo_id))
            snapshot = {
                "timestamp": utc_now(),
                "servo_id": servo_id,
                "position": self._read_with_priority(lambda servo: servo.ReadPosition(servo_id)),
                "voltage": self._read_with_priority(lambda servo: servo.ReadVoltage(servo_id)),
                "temperature": self._read_with_priority(lambda servo: servo.ReadTemperature(servo_id)),
                "current": self._read_with_priority(lambda servo: servo.ReadCurrent(servo_id)),
                "load": self._read_with_priority(lambda servo: servo.ReadLoad(servo_id)),
                "mode": self._read_with_priority(lambda servo: servo.ReadMode(servo_id)),
                "moving": self._read_with_priority(lambda servo: servo.IsMoving(servo_id)),
                "status": status,
            }
        except TelemetryYield:
            return None
        except Exception as exc:
            self._close_servo()
            return {
                "timestamp": utc_now(),
                "servo_id": servo_id,
                "health": "error",
                "error": str(exc),
            }

        alerts: List[str] = []
        temperature = snapshot.get("temperature")
        current = snapshot.get("current")
        load = snapshot.get("load")
        status_flags = snapshot.get("status") or {}

        if isinstance(temperature, (int, float)) and temperature >= self.config.temperature_warn:
            alerts.append("high_temperature")
        if isinstance(current, (int, float)) and current >= self.config.current_warn:
            alerts.append("high_current")
        if isinstance(load, (int, float)) and load >= self.config.load_warn:
            alerts.append("high_load")
        for key, value in status_flags.items():
            if value is False:
                alerts.append(f"fault_{key.lower()}")

        snapshot["alerts"] = alerts
        snapshot["health"] = "warn" if alerts else "ok"
        return snapshot

    def _read_with_priority(self, read_fn):
        if self._telemetry_should_yield():
            raise TelemetryYield()
        with self.servo_lock:
            assert self.servo is not None
            return read_fn(self.servo)

    def _publish_event(self, payload: Dict[str, Any]) -> None:
        self._publish_json(self.config.event_topic, payload)

    def _publish_bridge_status(self, state: str) -> None:
        payload = {
            "timestamp": utc_now(),
            "state": state,
            "connected": self.servo is not None,
            "device": self.config.device,
            "servo_ids": self.servo_ids,
        }
        self._publish_json(self.config.status_topic, payload, retain=True)

    def _publish_json(self, topic: str, payload: Dict[str, Any], retain: bool = False) -> None:
        if not self.mqtt_client:
            return
        try:
            self.mqtt_client.publish(
                topic,
                json.dumps(payload, separators=(",", ":")),
                qos=0,
                retain=retain,
            )
        except Exception:
            pass

    def _load_cached_servo_ids(self) -> List[int]:
        cache_path = self.config.servo_cache_file
        if not cache_path or not os.path.exists(cache_path):
            return []

        try:
            with open(cache_path, "r", encoding="ascii") as handle:
                data = json.load(handle)
            servo_ids = data.get("servo_ids", [])
            if not isinstance(servo_ids, list):
                return []
            return [int(servo_id) for servo_id in servo_ids]
        except Exception:
            return []

    def _save_cached_servo_ids(self) -> None:
        cache_path = self.config.servo_cache_file
        if not cache_path:
            return

        payload = {
            "timestamp": utc_now(),
            "servo_ids": self.servo_ids,
        }
        try:
            with open(cache_path, "w", encoding="ascii") as handle:
                json.dump(payload, handle, separators=(",", ":"))
        except Exception:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persistent ST3215 MQTT bridge")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Serial device path")
    parser.add_argument("--broker", default="192.168.1.10", help="MQTT broker hostname")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument(
        "--servos",
        type=str,
        default="",
        help="Comma-separated servo IDs. If omitted, the bridge auto-discovers them.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Telemetry publish interval in seconds",
    )
    parser.add_argument(
        "--discover-interval",
        type=float,
        default=0.0,
        help="How often to rescan the bus when servo IDs are not fixed. 0 disables periodic rescans.",
    )
    parser.add_argument("--temperature-warn", type=float, default=55.0)
    parser.add_argument("--load-warn", type=float, default=75.0)
    parser.add_argument("--current-warn", type=float, default=1200.0)
    parser.add_argument(
        "--servo-cache-file",
        default=".servo_ids.json",
        help="Local file used to persist discovered servo IDs on the Biqu host",
    )
    return parser.parse_args()


def parse_servo_ids(raw: str) -> List[int]:
    if not raw:
        return []
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> int:
    args = parse_args()
    config = BridgeConfig(
        device=args.device,
        broker=args.broker,
        port=args.port,
        servo_ids=parse_servo_ids(args.servos),
        telemetry_interval=args.interval,
        discover_interval=args.discover_interval,
        temperature_warn=args.temperature_warn,
        load_warn=args.load_warn,
        current_warn=args.current_warn,
        servo_cache_file=args.servo_cache_file,
    )
    bridge = ServoBridge(config)
    bridge.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
