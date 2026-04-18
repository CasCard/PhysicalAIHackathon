# ST3215 Bridge Setup

## Network layout

- Dev machine where you edit code: `192.168.1.2`
- Biqu / Klipper / ST3215 USB-UART host: `192.168.1.20`
- Raspberry Pi / MQTT broker / Grafito orchestration host: `192.168.1.10`

## What changed

The recommended path is now:

1. Klipper macro on `192.168.1.20` publishes JSON to `grafito/servo/command`
2. `st3215_bridge.py` on `192.168.1.20` keeps the ST3215 UART open
3. The bridge publishes telemetry to the MQTT broker on `192.168.1.10`
4. `graftio_services` `servo_node` on `192.168.1.10` subscribes to that telemetry and republishes it into the internal Grafito message bus

This removes the repeated serial initialization that was happening with `servo_control.py` on every macro call.

## Files that matter

### Biqu host `192.168.1.20`

- `python-st3215/st3215_bridge.py`
- `python-st3215/st3215_bridge.service`
- `python-st3215/servo.cfg`
- `python-st3215/requirements.txt`

On the Biqu machine these files should live under:

- `/home/biqu/python-st3215`

### Raspberry Pi `192.168.1.10`

- `graftio_services/src/services/nodes/servo_node.py`
- `graftio_services/src/services/communication/messages.py`
- `graftio_services/src/services/grafting_system_launcher.py`
- `graftio_services/src/services/autonomous_grafting/node_integration_manager.py`
- `graftio_services/start_grafting_system.sh`
- `graftio_services/grafito_listener.py`

## MQTT topics

- Command in: `grafito/servo/command`
- Aggregate telemetry: `grafito/servo/telemetry`
- Per-servo telemetry: `grafito/servo/<id>/telemetry`
- Command results: `grafito/servo/event`
- Bridge health: `grafito/servo/bridge/status`

## Example command payloads

```json
{"action":"move","servo_id":1,"position":2048,"speed":1000}
{"action":"rotate","servo_id":1,"speed":500}
{"action":"stop","servo_id":1}
{"action":"stop_all"}
{"action":"status","servo_id":1}
{"action":"discover"}
```

## Step 1: Push changes from `192.168.1.2`

Run these commands from your dev machine at `192.168.1.2`.

### Copy Biqu-side files

```bash
rsync -avz \
  /home/grafito/Grafito-Edge-Services/python-st3215/st3215_bridge.py \
  /home/grafito/Grafito-Edge-Services/python-st3215/st3215_bridge.service \
  /home/grafito/Grafito-Edge-Services/python-st3215/servo.cfg \
  /home/grafito/Grafito-Edge-Services/python-st3215/requirements.txt \
  biqu@192.168.1.20:/home/biqu/python-st3215/
```

### Copy Pi-side files

```bash
rsync -avz \
  /home/grafito/Grafito-Edge-Services/graftio_services/src/services/nodes/servo_node.py \
  /home/grafito/Grafito-Edge-Services/graftio_services/src/services/communication/messages.py \
  /home/grafito/Grafito-Edge-Services/graftio_services/src/services/grafting_system_launcher.py \
  /home/grafito/Grafito-Edge-Services/graftio_services/src/services/autonomous_grafting/node_integration_manager.py \
  /home/grafito/Grafito-Edge-Services/graftio_services/start_grafting_system.sh \
  /home/grafito/Grafito-Edge-Services/graftio_services/grafito_listener.py \
  grafito@192.168.1.10:/home/grafito/Grafito-Edge-Services/graftio_services/
```

If your Pi repo has the same full tree and you want exact paths preserved, use this instead:

```bash
rsync -avz /home/grafito/Grafito-Edge-Services/graftio_services/ \
  grafito@192.168.1.10:/home/grafito/Grafito-Edge-Services/graftio_services/
```

## Step 2: Set up the Biqu host `192.168.1.20`

SSH in:

```bash
ssh biqu@192.168.1.20
```

Create a local virtualenv and install dependencies for the servo bridge:

```bash
cd /home/biqu/python-st3215
sudo apt update
sudo apt install -y python3-venv
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

This avoids the `externally-managed-environment` error from the system Python.

Test the bridge manually:

```bash
cd /home/biqu/python-st3215
. .venv/bin/activate
python st3215_bridge.py \
  --device /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0 \
  --broker 192.168.1.10 \
  --interval 0.5
```

You should see it connect to the broker and either discover servos or report bus errors clearly.

Install the systemd service:

```bash
sudo cp /home/biqu/python-st3215/st3215_bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now st3215_bridge.service
sudo systemctl status st3215_bridge.service
```

If your servo IDs are fixed, edit the service and add `--servos 1,2,3` to `ExecStart` for the most deterministic startup.

The bridge now avoids periodic bus rescans by default to reduce latency spikes. If you do not pass `--servos`, it will discover once, store the IDs locally in `/home/biqu/python-st3215/.servo_ids.json`, and reuse them on restart. If IDs change later, use `SERVO_LIST` or publish `{"action":"discover"}` manually.

### Update Klipper config on Biqu

Make sure the new MQTT-based `servo.cfg` is included by your printer config, then restart Klipper / Moonraker so the macros reload.

If you use an absolute include path, point it at:

```ini
[include /home/biqu/python-st3215/servo.cfg]
```

If your config already includes it, a restart is enough. Example:

```bash
sudo systemctl restart klipper
sudo systemctl restart moonraker
```

Important:

- These macros now use `publish_mqtt_topic`
- That means Moonraker MQTT support must be configured on the Biqu host

## Step 3: Set up the Raspberry Pi `192.168.1.10`

SSH in:

```bash
ssh grafito@192.168.1.10
```

Check that Mosquitto is running:

```bash
systemctl status mosquitto
```

Install service dependencies if needed:

```bash
cd /home/grafito/Grafito-Edge-Services/graftio_services
./venv/bin/pip install -r requirements.txt
```

Restart the Grafito listener and the main node launcher path:

```bash
cd /home/grafito/Grafito-Edge-Services/graftio_services
pkill -f grafito_listener.py || true
./venv/bin/python3 grafito_listener.py &
```

If you normally run the main system through your existing launcher flow, restart that flow the same way you already do. The updated launcher now starts `servo_node` automatically.

You can also start the service stack manually:

```bash
cd /home/grafito/Grafito-Edge-Services/graftio_services/src/services
python3 grafting_system_launcher.py --nodes-only
```

## Step 4: Validate end to end

### On the Pi, watch telemetry

```bash
mosquitto_sub -h 192.168.1.10 -t grafito/servo/telemetry
mosquitto_sub -h 192.168.1.10 -t grafito/servo/event
mosquitto_sub -h 192.168.1.10 -t grafito/servo/bridge/status
```

### On the Biqu, issue a Klipper macro

Examples:

```gcode
SERVO_LIST
SERVO_STATUS SERVO_ID=1
SERVO_MOVE SERVO_ID=1 POSITION=2048 SPEED=800
SERVO_STOP SERVO_ID=1
SERVO_STOP_ALL
```

You should see:

- command result messages on `grafito/servo/event`
- aggregate telemetry on `grafito/servo/telemetry`
- continuous health updates from the bridge

## Step 5: Jam recovery workflow

When a servo jams:

1. Remove the obstruction first
2. Publish or call `SERVO_STOP_ALL`
3. Watch `grafito/servo/telemetry`
4. Check `alerts`, `load`, `current`, `temperature`, and `health`
5. Reissue motion only after the affected servo returns to a stable state

## Notes and constraints

- The bridge must run only on `192.168.1.20` because that machine owns the USB-UART device
- The broker should remain on `192.168.1.10`
- `servo_node` should run on `192.168.1.10` alongside the rest of `graftio_services`
- Do not keep using the old one-shot `servo_control.py` path in parallel with the new bridge for normal operation

## Quick troubleshooting

### No telemetry on the Pi

- Confirm `st3215_bridge.py` is running on `192.168.1.20`
- Confirm it points to broker `192.168.1.10`
- Confirm Mosquitto is running on `192.168.1.10`

### Macros do nothing on Biqu

- Confirm Moonraker MQTT is configured
- Confirm the new `servo.cfg` is loaded
- Confirm `grafito/servo/command` messages are reaching the broker

### Bridge starts but cannot open the serial bus

- Confirm the device path is correct
- Confirm `pyserial` is installed on `192.168.1.20`
- Confirm no other long-lived process is still holding the ST3215 USB-UART device
