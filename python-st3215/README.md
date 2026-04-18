
# ST3215 Servo Controller

A Python library and CLI tools for controlling ST3215 servos with real-time MQTT data publishing capabilities.

## Features

- **ST3215 Servo Control**: Complete Python library for ST3215 servo communication
- **Command Line Interface**: Easy-to-use CLI for servo operations  
- **Real-time MQTT Publisher**: Publish servo data to MQTT broker with automatic conflict resolution
- **Process Monitoring**: Automatically handles conflicts between CLI operations and real-time monitoring

## Installation

1. Clone or download the repository
2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Hardware Requirements

- ST3215 servo(s)
- USB to TTL serial adapter (typically `/dev/ttyUSB0`)
- MQTT broker (optional, for data publishing)

## Quick Start

### Basic Servo Control

```bash
# Move servo ID 1 to position 2048
python3 servo_control.py --device /dev/ttyUSB0 move 1 2048

# Check servo status
python3 servo_control.py --device /dev/ttyUSB0 status 1

# List all connected servos
python3 servo_control.py --device /dev/ttyUSB0 list
```

### Real-time MQTT Publishing

```bash
# Start publisher with auto-discovered servos
python3 servo_pub.py --device /dev/ttyUSB0

# Publish specific servos to remote broker
python3 servo_pub.py --device /dev/ttyUSB0 --broker 192.168.1.100 --servos 1,2,3

# High-frequency publishing (50ms intervals)
python3 servo_pub.py --interval 0.05
```

## servo_control.py - CLI Interface

The command-line interface provides full servo control capabilities:

### Commands

#### Move Command
```bash
python3 servo_control.py --device /dev/ttyUSB0 move <servo_id> <position> [speed]
```
- `servo_id`: Servo ID (0-253)
- `position`: Target position (0-4095)
- `speed`: Movement speed (optional, default: 1000)

#### Rotate Command
```bash
python3 servo_control.py --device /dev/ttyUSB0 rotate <servo_id> <speed>
```
- `speed`: Rotation speed (-1000 to 1000, negative for reverse)

#### Stop Command
```bash
python3 servo_control.py --device /dev/ttyUSB0 stop <servo_id>
```

#### Mode Command
```bash
python3 servo_control.py --device /dev/ttyUSB0 mode <servo_id> <mode>
```
- `mode`: 0=position, 1=rotation, 2=PWM, 3=step

#### Status Command
```bash
python3 servo_control.py --device /dev/ttyUSB0 status <servo_id>
```

#### List Command
```bash
python3 servo_control.py --device /dev/ttyUSB0 list
```

#### Check Command (Comprehensive Status)
```bash
python3 servo_control.py --device /dev/ttyUSB0 check <servo_id>
```

### Examples

```bash
# Move servo 1 to center position at speed 2000
python3 servo_control.py --device /dev/ttyUSB0 move 1 2048 2000

# Rotate servo 2 clockwise at speed 500
python3 servo_control.py --device /dev/ttyUSB0 rotate 2 500

# Get comprehensive status of servo 1
python3 servo_control.py --device /dev/ttyUSB0 check 1
```

## servo_pub.py - Real-time MQTT Publisher

The MQTT publisher provides real-time servo data streaming with smart conflict resolution.

### Features

- **Real-time Data**: Publishes servo sensor data at configurable intervals
- **Smart Monitoring**: Automatically detects when `servo_control.py` is running
- **Conflict Resolution**: Pauses publishing during CLI operations, resumes after 3 seconds
- **Auto-discovery**: Automatically finds servos on the bus
- **Robust Reconnection**: Handles connection failures gracefully

### Command Line Options

```bash
python3 servo_pub.py [options]
```

- `--device`: Serial device path (default: `/dev/ttyUSB0`)
- `--broker`: MQTT broker address (default: `localhost`)
- `--port`: MQTT broker port (default: `1883`)
- `--interval`: Publishing interval in seconds (default: `0.1`)
- `--servos`: Comma-separated servo IDs (auto-discover if not specified)

### MQTT Topics

- **Individual servo**: `servo/{servo_id}/data`
- **All servos**: `servo/all/data`

### Data Format

**Individual Servo Data** (`servo/1/data`):
```json
{
  "servo_id": 1,
  "timestamp": "2025-08-25T10:30:45.123456",
  "position": 2048,
  "voltage": 12.5,
  "temperature": 35,
  "current": 150.5,
  "load": 45.2,
  "mode": 0,
  "status": {
    "Voltage": true,
    "Sensor": true,
    "Temperature": true,
    "Current": true,
    "Angle": true,
    "Overload": true
  },
  "moving": false
}
```

**Aggregate Data** (`servo/all/data`):
```json
{
  "timestamp": "2025-08-25T10:30:45.123456",
  "servos": [
    {
      "servo_id": 1,
      "position": 2048,
      "voltage": 12.5,
      ...
    },
    {
      "servo_id": 2,
      "position": 1024,
      "voltage": 12.4,
      ...
    }
  ]
}
```

### Data Fields Explanation

- **position**: Current servo position (0-4095)
- **voltage**: Supply voltage (V)
- **temperature**: Internal temperature (°C)
- **current**: Current consumption (mA)
- **load**: Load percentage (0-100%)
- **mode**: Operation mode (0=position, 1=rotation, 2=PWM, 3=step)
- **status**: Error flags (true=OK, false=error/alarm)
  - `Voltage`: true=voltage OK, false=voltage error
  - `Sensor`: true=sensor OK, false=sensor error
  - `Temperature`: true=temperature OK, false=overheating
  - `Current`: true=current OK, false=overcurrent
  - `Angle`: true=angle OK, false=angle error
  - `Overload`: true=no overload, false=overloaded
- **moving**: Whether servo is currently moving

## Subscribing to MQTT Data

### Using mosquitto_sub

```bash
# Subscribe to all servo data
mosquitto_sub -h localhost -t "servo/all/data"

# Subscribe to specific servo
mosquitto_sub -h localhost -t "servo/1/data"

# Subscribe with wildcards
mosquitto_sub -h localhost -t "servo/+/data"
```

### Using Python

```python
import paho.mqtt.client as mqtt
import json

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe("servo/all/data")

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())
    print(f"Received: {json.dumps(data, indent=2)}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("localhost", 1883, 60)
client.loop_forever()
```

## ST3215 Library

The core `st3215` library provides low-level servo control:

### Key Methods

- `PingServo(id)`: Check servo presence
- `ListServos()`: Find all servos on bus
- `MoveTo(id, position, speed, acc, wait)`: Move to position
- `Rotate(id, speed)`: Continuous rotation
- `ReadPosition(id)`: Get current position
- `ReadVoltage(id)`: Get voltage
- `ReadTemperature(id)`: Get temperature
- `ReadCurrent(id)`: Get current
- `ReadLoad(id)`: Get load percentage
- `SetMode(id, mode)`: Set operation mode
- `TareServo(id)`: Calibrate servo range

### Usage Example

```python
from st3215 import ST3215

# Connect to servo
servo = ST3215('/dev/ttyUSB0')

# Find all servos
servos = servo.ListServos()
print(f"Found servos: {servos}")

# Move servo 1 to center
servo.MoveTo(1, 2048, speed=2000, wait=True)

# Read current position
position = servo.ReadPosition(1)
print(f"Current position: {position}")
```

## Troubleshooting

### Serial Port Issues
- Ensure correct device path (usually `/dev/ttyUSB0`)
- Check user permissions: `sudo usermod -a -G dialout $USER`
- Verify servo connections and power

### MQTT Issues
- Ensure MQTT broker is running: `mosquitto -v`
- Check network connectivity to broker
- Verify topic subscriptions

### Servo Communication
- Check baud rate and serial settings
- Verify servo power supply
- Use `list` command to detect servos

## Files Structure

- `servo_control.py`: Command-line interface
- `servo_pub.py`: Real-time MQTT publisher
- `st3215/`: Core servo library
- `requirements.txt`: Python dependencies
- `servo.cfg`: Configuration file (if present)

## Dependencies

- `pyserial`: Serial communication
- `paho-mqtt`: MQTT client
- `psutil`: Process monitoring

## License

See LICENSE file for details.

---

## ST3215 Library API Documentation

### `PingServo(sts_id)`
Check if the servo is responding.

- **Parameters**: `sts_id` (int) – Servo ID
- **Returns**: `True` if successful, `False` otherwise
- **Example**:
```python
servo.PingServo(1)
```

---

### `ListServos()`
Scan and return a list of all responsive servos. Return `None` in case of error.

- **Returns**: `List[int]` of servo IDs
- **Example**:
```python
servo.ListServos()
```

---

### `ReadLoad(sts_id)`
Get the motor load in %. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `float` or `None`
- **Example**:
```python
servo.ReadLoad(1)
```

---

### `ReadVoltage(sts_id)`
Read voltage in volts. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `float` or `None`
- **Example**:
```python
servo.ReadVoltage(1)
```

---

### `ReadCurrent(sts_id)`
Get current in mA. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `float` or `None`
- **Example**:
```python
servo.ReadCurrent(1)
```

---

### `ReadTemperature(sts_id)`
Read current temperature °C. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `int` or `None`
- **Example**:
```python
servo.ReadTemperature(1)
```

---

### `ReadAccelaration(sts_id)`
Read current acceleration value in step/s². Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `int` or `None`
- **Example**:
```python
servo.ReadAccelaration(1)
```

---

### `ReadMode(sts_id)`
Get current mode. Return `None` in case of error.

0: position servo mode 
1: motor constant speed mode
2: PWM open-loop speed regulation mode
3: step servo mode

- **Parameters**: `sts_id` (int)
- **Returns**: `int` or `None`
- **Example**:
```python
servo.ReadMode(1)
```

---

### `ReadCorrection(sts_id)`
Read position position correction value. Return `None` in case of error.

Add a position correction in steps.

- **Parameters**: `sts_id` (int)
- **Returns**: `int` or `None`
- **Example**:
```python
servo.ReadCorrection(1)
```

---

### `ReadStatus(sts_id)`
Read the sensors status of the servo. Return a dict with sensor status or `None` in case of error

`{'Voltage': True, 'Sensor': True, 'Temperature': True, 'Current': True, 'Angle': True, 'Overload': True}`

- **Parameters**: `sts_id` (int)
- **Returns**: `dict` or `None`
- **Example**:
```python
servo.ReadStatus(1)
```


---

### `IsMoving(sts_id)`
Check if the servo is moving. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `bool` or `None`
- **Example**:
```python
servo.IsMoving(1)
```

---

### `SetAcceleration(sts_id, acc)`
Set acceleration value in step/s². Return `None` in case of error.

- **Parameters**:
  - `sts_id` (int)
  - `acc` (int, 0–254)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.SetAcceleration(1, 100)
```

---

### `SetSpeed(sts_id, speed)`
Set servo speed in step/s. Return `None` in case of error.

- **Parameters**:
  - `sts_id` (int)
  - `speed` (int)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.SetSpeed(1, 3000)
```

---

### `StopServo(sts_id)`
Disable torque. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.StopServo(1)
```

---

### `StartServo(sts_id)`
Enable torque. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.StartServo(1)
```

---

### `SetMode(sts_id, mode)`
Set operational mode. Return `None` in case of error.

0: position servo mode 
1: motor constant speed mode
2: PWM open-loop speed regulation mode
3: step servo mode

- **Parameters**:
  - `sts_id` (int)
  - `mode` (0–3)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.SetMode(1, 0)
```

---

### `CorrectPosition(sts_id, correction)`
Apply a position correction. Return `None` in case of error.

- **Parameters**:
  - `sts_id` (int)
  - `correction` (int, can be negative)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.CorrectPosition(1, -100)
```

---

### `Rotate(sts_id, speed)`
Rotate in continuous mode. Return `None` in case of error.

- **Parameters**:
  - `sts_id` (int)
  - `speed` (int, can be negative)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.Rotate(1, 250)
```

---

### `MoveTo(sts_id, position, speed=2400, acc=50, wait=False)`
Move to a defined position.
Set wait to `True` if you want to wait the end of the move before the function returning

- **Parameters**:
  - `sts_id` (int)
  - `position` (int)
  - `speed` (int)
  - `acc` (int)
  - `wait` (bool)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.MoveTo(1, 2048)
```

---

### `WritePosition(sts_id, position)`
Direct position write. Return `None` in case of error.

- **Parameters**:
  - `sts_id` (int)
  - `position` (int)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.WritePosition(1, 2048)
```

---

### `ReadPosition(sts_id)`
Read current position. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `int` or `None`
- **Example**:
```python
servo.ReadPosition(1)
```

---

### `ReadSpeed(sts_id)`
Get current speed. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `(int, int, int)`
- **Example**:
```python
speed, comm, error = servo.ReadSpeed(1)
```

---

### `LockEprom(sts_id)`
Lock the EEPROM. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `int`
- **Example**:
```python
servo.LockEprom(1)
```

---

### `UnLockEprom(sts_id)`
Unlock the EEPROM. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `int`
- **Example**:
```python
servo.UnLockEprom(1)
```

---

### `ChangeId(sts_id, new_id)`
Change the servo ID. Return `None` in case of error.

- **Parameters**:
  - `sts_id` (int)
  - `new_id` (int)
- **Returns**: `None` or `str`
- **Example**:
```python
servo.ChangeId(1, 2)
```

---

### `DefineMiddle(sts_id)`
Define current position as center (2048). Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `True` or `None`
- **Example**:
```python
servo.DefineMiddle(1)
```

---

### `TareServo(sts_id)`
Calibrate min/max and redefine middle. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `(min_position, max_position)` or `None`
- **Example**:
```python
min_pos, max_pos = servo.TareServo(1)
```

---

### `getBlockPosition(sts_id)`
Move to physical limit and return position. Return `None` in case of error.

- **Parameters**: `sts_id` (int)
- **Returns**: `int` or `None`
- **Example**:
```python
position = servo.getBlockPosition(1)
```

---



## ST3215 registers

> Bytes are little-endian


| Memory First Address   | Function                                       |   Number of Bytes |   Initial Value | Storage Area   | Permission   | Minimum Value   | Maximum Value   | Unit         | Value Parsing                                                                                                                                                                                                                                                                                                                                                                                   |
|:-----------------------|:-----------------------------------------------|------------------:|----------------:|:---------------|:-------------|:----------------|:----------------|:-------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0x0                    | Firmware major version number                  |                 1 |               3 | EPROM          | read only    | -1              | -1              | nan          | nan                                                                                                                                                                                                                                                                                                                                                                                             |
| 0x1                    | Firmware minor version number                  |                 1 |               7 | EPROM          | read only    | -1              | -1              | nan          | nan                                                                                                                                                                                                                                                                                                                                                                                             |
| 0x3                    | Servo major version number                     |                 1 |               9 | EPROM          | read only    | -1              | -1              | nan          | nan                                                                                                                                                                                                                                                                                                                                                                                             |
| 0x4                    | Servo minor version number                     |                 1 |               3 | EPROM          | read only    | -1              | -1              | nan          | nan                                                                                                                                                                                                                                                                                                                                                                                             |
| 0x5                    | ID                                             |                 1 |               1 | EPROM          | read/write   | 0               | 253             | Baud         | A unique identification code on the bus, with no duplicate ID numbers allowed on the same bus. ID number 254 (0xFE) is the broadcast ID, and broadcasts do not receive response packets.                                                                                                                                                                                                        |
| 0x6                    | Baudrate                                       |                 1 |               0 | EPROM          | read/write   | 0               | 7               | None         | 0-7 respectively represent baud rates as follows:                                                                                                                                                                                                                                                                                                                                               |
|                        |                                                |                   |                 |                |              |                 |                 |              | 1000000, 500000, 250000, 128000, 115200, 76800, 57600, 38400                                                                                                                                                                                                                                                                                                                                    |
| 0x7                    | Return delay                                   |                 1 |               0 | EPROM          | read/write   | 0               | 254             | 2us          | The minimum unit is 2us, and the maximum allowable setting for response delay is 254*2=508us                                                                                                                                                                                                                                                                                                    |
| 0x8                    | Response status level                          |                 1 |               1 | EPROM          | read/write   | 0               | 1               | None         | 0: Except for read and PING instructions, other instructions do not return response packets.                                                                                                                                                                                                                                                                                                    |
|                        |                                                |                   |                 |                |              |                 |                 |              | 1: Return response packets for all instructions                                                                                                                                                                                                                                                                                                                                                 |
| 0x9                    | Minimum angle                                  |                 2 |               0 | EPROM          | read/write   | -32766          | --              | Step         | Set the minimum value limit for the motion range, which should be smaller than the maximum angle limit. When performing multi-turn absolute position control, this value is set to 0.                                                                                                                                                                                                           |
| 0xB                    | Maximum angle                                  |                 2 |            4095 | EPROM          | read/write   | --              | 32767           | Step         | Set the maximum value limit for the motion range, which should be greater than the minimum angle limit. When performing multi-turn absolute position control, this value is set to 0.                                                                                                                                                                                                           |
| 0xD                    | Maximum temperature                            |                 1 |              70 | EPROM          | read/write   | 0               | 100             | °C           | The maximum operating temperature limit, when set to 70, means the maximum temperature is 70 degrees Celsius, with a precision setting of 1 degree Celsius.                                                                                                                                                                                                                                     |
| 0xE                    | Maximum input voltage                          |                 1 |              80 | EPROM          | read/write   | 0               | 254             | 0.1V         | If the maximum input voltage is set to 80, then the maximum operating voltage limit is 8.0V, with a precision setting of 0.1V.                                                                                                                                                                                                                                                                  |
| 0xF                    | Minimum input voltage                          |                 1 |              40 | EPROM          | read/write   | 0               | 254             | 0.1V         | If the minimum input voltage is set to 40, then the minimum operating voltage limit is 4.0V, with a precision setting of 0.1V.                                                                                                                                                                                                                                                                  |
| 0x10                   | Maximum torque                                 |                 2 |            1000 | EPROM          | read/write   | 0               | 1000            | nan          | Set the maximum output torque limit for the servo motor, where 1000 corresponds to 100% of the locked-rotor torque. Assign this value to address 48 upon power-up as the torque limit.                                                                                                                                                                                                          |
| 0x12                   | Phase                                          |                 1 |              12 | EPROM          | read/write   | 0               | 254             | None         | Special function byte, do not modify unless there are specific requirements. Please refer to the special byte bit analysis for further details.                                                                                                                                                                                                                                                 |
| 0x13                   | Unloading conditions                           |                 1 |              44 | EPROM          | read/write   | 0               | 254             | None         | Bit0  Bit1  Bit2 Bit3 Bit4 Bit5 set corresponding bit to 1 to enable the corresponding protection.                                                                                                                                                                                                                                                                                              |
|                        |                                                |                   |                 |                |              |                 |                 |              | Voltage Sensor Temperature Current Angle Overload set corresponding bit to 0 to disable the corresponding protection                                                                                                                                                                                                                                                                            |
| 0x14                   | LED alarm conditions                           |                 1 |              47 | EPROM          | read/write   | 0               | 254             | None         | Bit0  Bit1  Bit2 Bit3 Bit4 Bit5 set the corresponding bit to 1 to enable flashing  LED.                                                                                                                                                                                                                                                                                                         |
|                        |                                                |                   |                 |                |              |                 |                 |              | Voltage Sensor Temperature Current Angle Overload set corresponding bit to 0 to disable the corresponding protection                                                                                                                                                                                                                                                                            |
| 0x15                   | Position loop P (Proportional) coefficient     |                 1 |              32 | EPROM          | read/write   | 0               | 254             | None         | Proportional coefficient of control motor                                                                                                                                                                                                                                                                                                                                                       |
| 0x16                   | Position loop D (Differential) coefficient     |                 1 |              32 | EPROM          | read/write   | 0               | 254             | None         | Differential coefficient of control motor                                                                                                                                                                                                                                                                                                                                                       |
| 0x17                   | Position loop I (Integral) coefficient         |                 1 |               0 | EPROM          | read/write   | 0               | 254             | None         | Integral coefficient of the control motor                                                                                                                                                                                                                                                                                                                                                       |
| 0x18                   | Minimum starting force                         |                 2 |              16 | EPROM          | read/write   | 0               | 1000            | nan          | Set the minimum output startup torque for the servo, where 1000 corresponds to 100% of the locked-rotor torque.                                                                                                                                                                                                                                                                                 |
| 0x1A                   | Clockwise insensitive zone                     |                 1 |               1 | EPROM          | read/write   | 0               | 32              | Step         | The minimum unit is one minimum resolution angle.                                                                                                                                                                                                                                                                                                                                               |
| 0x1B                   | Anti-clockwise insensitive zone                |                 1 |               1 | EPROM          | read/write   | 0               | 32              | Step         | The minimum unit is a minimum resolution angle.                                                                                                                                                                                                                                                                                                                                                 |
| 0x1C                   | Protection current                             |                 2 |             500 | EPROM          | read/write   | 0               | 511             | 6.5mA        | The maximum settable current is 500 * 6.5mA= 3250mA.                                                                                                                                                                                                                                                                                                                                            |
| 0x1E                   | Angle resolution                               |                 1 |               1 | EPROM          | read/write   | 1               | 3               | None         | For the amplification factor of the minimum resolution angle (degree/step) of the sensor, modifying this value can expand the number of control range. When performing the multi-turn control, you need to modify the parameter at address 0x12 by setting BIT4 to 1. This modification will result in the current position feedback value being adjusted to reflect the larger angle feedback. |
| 0x1F                   | Position correction                            |                 2 |               0 | EPROM          | read/write   | -2047           | 2047            | Step         | BIT11 is the direction bit, indicating the positive and negative direction, and other bits can indicate the range of 0-2047 steps.                                                                                                                                                                                                                                                              |
| 0x21                   | Operation mode                                 |                 1 |               0 | EPROM          | read/write   | 0               | 3               | None         | 0: position servo mode                                                                                                                                                                                                                                                                                                                                                                          |
|                        |                                                |                   |                 |                |              |                 |                 |              | 1: motor constant speed mode, controlled by parameter 0x2E running speed parameter, the highest bit BIT15 is direction bit.                                                                                                                                                                                                                                                                     |
|                        |                                                |                   |                 |                |              |                 |                 |              | 2: PWM open-loop speed regulation mode, controlled by parameter 0x2Cthe  running time parameter, BIT10 is direction bit                                                                                                                                                                                                                                                                         |
|                        |                                                |                   |                 |                |              |                 |                 |              | 3: step servo mode, and the target position of parameter 0x2A is used to indicate the number of steps, and the highest bit BIT15 is the direction bit. When working                                                                                                                                                                                                                             |
|                        |                                                |                   |                 |                |              |                 |                 |              | In mode 3, the minimum and maximum angle limits of 0x9 and 0xB must be set to 0. Otherwise, it is impossible to step indefinitely.                                                                                                                                                                                                                                                              |
| 0x22                   | Protection torque                              |                 1 |              20 | EPROM          | read/write   | 0               | 100             | nan          | Output torque after entering overload protection. If 20 is set, it means 20% of the maximum torque.                                                                                                                                                                                                                                                                                             |
| 0x23                   | Protection time                                |                 1 |             200 | EPROM          | read/write   | 0               | 254             | 10ms         | The duration for which the current load output exceeds the overload torque and remains is represented by a value, such as 200, which indicates 2 seconds. The maximum value that can be set is 2.5 seconds.                                                                                                                                                                                     |
| 0x24                   | Overload torque                                |                 1 |              80 | EPROM          | read/write   | 0               | 100             | nan          | The maximum torque threshold for starting the overload protection time countdown can be represented by a value, such as 80, indicating 80% of the maximum torque.                                                                                                                                                                                                                               |
| 0x25                   | Speed closed-loop proportional (P) coefficient |                 1 |              10 | EPROM          | read/write   | 0               | 100             | None         | Proportional coefficient of speed loop in motor constant speed mode (mode 1)                                                                                                                                                                                                                                                                                                                    |
| 0x26                   | Overcurrent protection time                    |                 1 |             200 | EPROM          | read/write   | 0               | 254             | 10ms         | The maximum setting is 254 * 10ms = 2540ms.                                                                                                                                                                                                                                                                                                                                                     |
| 0x27                   | Velocity closed-loop integral (I) coefficient  |                 1 |              10 | EPROM          | read/write   | 0               | 254             | 1/10         | In the motor constant speed mode (mode 1), the speed loop integral coefficient (change note: the speed closed loop I integral coefficient is reduced by 10 times compared with version 3.6).                                                                                                                                                                                                    |
| 0x28                   | Torque switch                                  |                 1 |               0 | SRAM           | read/write   | 0               | 128             | None         | Write 0: disable the torque output; Write 1: enable the torque output; Write 128: Arbitrary current position correction to 2048.                                                                                                                                                                                                                                                                |
| 0x29                   | Acceleration                                   |                 1 |               0 | SRAM           | read/write   | 0               | 254             | 100 step/s^2 | If set to 10, it corresponds to an acceleration and deceleration rate of 1000 steps per second squared.                                                                                                                                                                                                                                                                                         |
| 0x2A                   | Target location                                |                 2 |               0 | SRAM           | read/write   | -30719          | 30719           | Step         | Each step corresponds to the minimum resolution angle, and it is used in absolute position control mode. The maximum number of steps corresponds to the maximum effective angle.                                                                                                                                                                                                                |
| 0x2C                   | Operation time                                 |                 2 |               0 | SRAM           | read/write   | 0               | 1000            | nan          | In the PWM open-loop speed control mode, the value range is from 50 to 1000, and BIT10 serves as the direction bit.                                                                                                                                                                                                                                                                             |
| 0x2E                   | Operation speed                                |                 2 |               0 | SRAM           | read/write   | 0               | 3400            | step/s       | Number of steps per unit time (per second), 50 steps per second = 0.732 RPM (revolutions per minute)                                                                                                                                                                                                                                                                                            |
| 0x30                   | Torque limit                                   |                 2 |            1000 | SRAM           | read/write   | 0               | 1000            | nan          | The initial value of power-on will be assigned by the maximum torque (0x10), which can be modified by the user to control the output of the maximum torque.                                                                                                                                                                                                                                     |
| 0x37                   | Lock flag                                      |                 1 |               0 | SRAM           | read/write   | 0               | 1               | None         | Writing 0: Disables the write lock, allowing values written to the EPROM address to be saved even after power loss.                                                                                                                                                                                                                                                                             |
|                        |                                                |                   |                 |                |              |                 |                 |              | Writing 1: Enables the write lock, preventing values written to the EPROM address from being saved after power loss.                                                                                                                                                                                                                                                                            |
| 0x38                   | Current location                               |                 2 |               0 | SRAM           | read only    | -1              | -1              | Step         | Feedback the number of steps in the current position, each step is a minimum resolution angle; Absolute position control mode, the maximum value corresponds to the maximum effective angle.                                                                                                                                                                                                    |
| 0x3A                   | Current speed                                  |                 2 |               0 | SRAM           | read only    | -1              | -1              | step/s       | Feedback the current speed of motor rotation and the number of steps in unit time (per second).                                                                                                                                                                                                                                                                                                 |
| 0x3C                   | Current load                                   |                 2 |               0 | SRAM           | read only    | -1              | -1              | nan          | The voltage duty cycle of the current control output driving motor.                                                                                                                                                                                                                                                                                                                             |
| 0x3E                   | Current voltage                                |                 1 |               0 | SRAM           | read only    | -1              | -1              | 0.1V         | Current servo operation voltage                                                                                                                                                                                                                                                                                                                                                                 |
| 0x3F                   | Current temperature                            |                 1 |               0 | SRAM           | read only    | -1              | -1              | °C           | Current servo internal operating temperature                                                                                                                                                                                                                                                                                                                                                    |
| 0x40                   | Asynchronous write flag                        |                 1 |               0 | SRAM           | read only    | -1              | -1              | None         | The flag bit for using asynchronous write instructions                                                                                                                                                                                                                                                                                                                                          |
| 0x41                   | Servo status                                   |                 1 |               0 | SRAM           | read only    | -1              | -1              | None         | Bit0  Bit1  Bit2 Bit3 Bit4 Bit5 the corresponding bit is set to 1 to indicate that the corresponding error occurs,                                                                                                                                                                                                                                                                              |
|                        |                                                |                   |                 |                |              |                 |                 |              | Voltage Sensor Temperature Current Angle Overload the corresponding bit is set to 0 to indicate that there is no corresponding error.                                                                                                                                                                                                                                                           |
| 0x42                   | Move flag                                      |                 1 |               0 | SRAM           | read only    | -1              | -1              | None         | The sign of the servo is 1 when it is moving, and 0 when it is stopped.                                                                                                                                                                                                                                                                                                                         |
| 0x45                   | Current current                                |                 2 |               0 | SRAM           | read only    | -1              | -1              | 6.5mA        | The maximum measurable current is 500 * 6.5mA= 3250mA.                                                                                                                                                                                                                                                                                                                                          |
