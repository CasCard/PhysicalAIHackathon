# Servo G-code Commands Testing Documentation

## Overview
This document provides comprehensive testing procedures for the servo control G-code commands configured in your Klipper setup. The configuration includes shell commands that interface with a Python servo control script and G-code macros for easy servo manipulation.

## Prerequisites
- Klipper firmware running with the configuration loaded
- `servo_control.sh` script located at `/home/grafito/Grafito-Edge-Services/python-st3215/`
- Servo hardware properly connected and configured
- Access to Klipper console (via OctoPrint, Mainsail, Fluidd, or direct terminal)

## Command Structure Overview

### Shell Commands (Backend)
- `servo_move` - Move servo to specific position
- `servo_rotate` - Continuous rotation
- `servo_stop` - Stop servo movement
- `servo_mode` - Set servo operating mode
- `servo_status` - Read servo status

### G-code Macros (User Interface)
- `SERVO_MOVE` - Position control (0-4095 range)
- `SERVO_ANGLE` - Angle control (0-360 degrees)
- `SERVO_ROTATE` - Continuous rotation
- `SERVO_STOP` - Stop movement
- `SERVO_HOME` - Return to center position
- `SERVO_STATUS` - Check servo status
- `SERVO_MODE` - Set operating mode

## Testing Procedures

### 1. Basic Connectivity Test

**Test servo status first to ensure communication:**
```gcode
SERVO_STATUS
SERVO_STATUS SERVO_ID=1
```

**Expected Result:** Status information should display without errors

**Troubleshooting:**
- If command fails, check that `servo_control.sh` is executable
- Verify servo hardware connections
- Check that the Python script dependencies are installed

### 2. Position Control Tests

#### Test 2.1: Home Position
```gcode
SERVO_HOME
SERVO_HOME SERVO_ID=1
SERVO_HOME SERVO_ID=1 SPEED=500
```

**Expected Result:** Servo moves to center position (2048)

#### Test 2.2: Position Range Test
```gcode
# Minimum position
SERVO_MOVE POSITION=0 SPEED=1000

# Quarter position
SERVO_MOVE POSITION=1024 SPEED=1000

# Center position
SERVO_MOVE POSITION=2048 SPEED=1000

# Three-quarter position
SERVO_MOVE POSITION=3072 SPEED=1000

# Maximum position
SERVO_MOVE POSITION=4095 SPEED=1000
```

**Expected Result:** Servo should move smoothly to each position

#### Test 2.3: Speed Variation Test
```gcode
# Slow movement
SERVO_MOVE POSITION=0 SPEED=100
G4 P2  # Wait 2 seconds
SERVO_MOVE POSITION=4095 SPEED=100

# Fast movement
SERVO_MOVE POSITION=0 SPEED=2000
G4 P1
SERVO_MOVE POSITION=4095 SPEED=2000
```

**Expected Result:** Noticeable difference in movement speed

### 3. Angle Control Tests

#### Test 3.1: Basic Angle Movement
```gcode
# 0 degrees
SERVO_ANGLE ANGLE=0

# 90 degrees
SERVO_ANGLE ANGLE=90

# 180 degrees
SERVO_ANGLE ANGLE=180

# 270 degrees
SERVO_ANGLE ANGLE=270

# 360 degrees
SERVO_ANGLE ANGLE=360
```

**Expected Result:** Servo moves to corresponding angular positions

#### Test 3.2: Angle Boundary Test
```gcode
# Test negative angle (should clamp to 0)
SERVO_ANGLE ANGLE=-45

# Test over-range angle (should clamp to 360)
SERVO_ANGLE ANGLE=450
```

**Expected Result:** Angles should be clamped to valid range (0-360)

### 4. Continuous Rotation Tests

#### Test 4.1: Basic Rotation
```gcode
# Set to continuous mode and start rotation
SERVO_ROTATE SPEED=500

# Wait and observe rotation
G4 P5

# Stop rotation
SERVO_STOP
```

**Expected Result:** Servo rotates continuously, then stops

#### Test 4.2: Speed Variation in Rotation
```gcode
# Slow rotation
SERVO_ROTATE SPEED=100
G4 P3
SERVO_STOP

# Medium rotation
SERVO_ROTATE SPEED=500
G4 P3
SERVO_STOP

# Fast rotation
SERVO_ROTATE SPEED=1000
G4 P3
SERVO_STOP
```

**Expected Result:** Different rotation speeds should be observable

### 5. Mode Control Tests

#### Test 5.1: Mode Switching
```gcode
# Set to position mode
SERVO_MODE MODE=0
SERVO_MOVE POSITION=2048

# Set to continuous mode
SERVO_MODE MODE=1
SERVO_ROTATE SPEED=500
G4 P2
SERVO_STOP

# Return to position mode
SERVO_MODE MODE=0
SERVO_HOME
```

**Expected Result:** Servo behavior changes between position and continuous modes

### 6. Multi-Servo Position Control

#### Important Configuration Note
Your current configuration should work for multiple servos, but there's a potential issue with parameter spacing in the PARAMS field. If you encounter issues, update your macros to use this format:

```ini
# Fixed parameter passing (note the spaces around braces)
RUN_SHELL_COMMAND CMD=servo_move PARAMS="{ sid } { pos } { spd }"
```

#### Test 6.1: Individual Servo Control
```gcode
# Control servo ID 1
SERVO_STATUS SERVO_ID=1
SERVO_HOME SERVO_ID=1
SERVO_MOVE SERVO_ID=1 POSITION=1000 SPEED=1000

# Control servo ID 2  
SERVO_STATUS SERVO_ID=2
SERVO_HOME SERVO_ID=2
SERVO_MOVE SERVO_ID=2 POSITION=3000 SPEED=1000

# Control servo ID 3
SERVO_STATUS SERVO_ID=3
SERVO_HOME SERVO_ID=3  
SERVO_MOVE SERVO_ID=3 POSITION=2048 SPEED=500
```

**Expected Result:** Each servo responds independently to its specific ID

#### Test 6.2: Position Control by Servo ID
```gcode
# Move different servos to different positions
SERVO_MOVE SERVO_ID=1 POSITION=0     # Servo 1 to minimum
SERVO_MOVE SERVO_ID=2 POSITION=2048  # Servo 2 to center  
SERVO_MOVE SERVO_ID=3 POSITION=4095  # Servo 3 to maximum

# Wait and then move to new positions
G4 P3
SERVO_MOVE SERVO_ID=1 POSITION=4095  # Servo 1 to maximum
SERVO_MOVE SERVO_ID=2 POSITION=0     # Servo 2 to minimum
SERVO_MOVE SERVO_ID=3 POSITION=2048  # Servo 3 to center
```

#### Test 6.3: Angle Control by Servo ID
```gcode
# Set different angles for different servos
SERVO_ANGLE SERVO_ID=1 ANGLE=0     # Servo 1 to 0 degrees
SERVO_ANGLE SERVO_ID=2 ANGLE=90    # Servo 2 to 90 degrees  
SERVO_ANGLE SERVO_ID=3 ANGLE=180   # Servo 3 to 180 degrees
SERVO_ANGLE SERVO_ID=4 ANGLE=270   # Servo 4 to 270 degrees

# Create a sweep pattern
G4 P2
SERVO_ANGLE SERVO_ID=1 ANGLE=180
SERVO_ANGLE SERVO_ID=2 ANGLE=270  
SERVO_ANGLE SERVO_ID=3 ANGLE=0
SERVO_ANGLE SERVO_ID=4 ANGLE=90
```

#### Test 6.4: Speed Control by Servo ID
```gcode
# Different speeds for different servos
SERVO_MOVE SERVO_ID=1 POSITION=0 SPEED=100      # Slow
SERVO_MOVE SERVO_ID=2 POSITION=0 SPEED=500      # Medium
SERVO_MOVE SERVO_ID=3 POSITION=0 SPEED=1000     # Fast
SERVO_MOVE SERVO_ID=4 POSITION=0 SPEED=2000     # Very fast

G4 P5  # Wait for slow servo to complete

# Return all to center at same speed
SERVO_MOVE SERVO_ID=1 POSITION=2048 SPEED=1000
SERVO_MOVE SERVO_ID=2 POSITION=2048 SPEED=1000
SERVO_MOVE SERVO_ID=3 POSITION=2048 SPEED=1000
SERVO_MOVE SERVO_ID=4 POSITION=2048 SPEED=1000
```

#### Test 6.5: Sequential vs Simultaneous Control
```gcode
# Sequential control (one after another)
RESPOND MSG="Sequential movement..."
SERVO_MOVE SERVO_ID=1 POSITION=1000
G4 P1
SERVO_MOVE SERVO_ID=2 POSITION=1000  
G4 P1
SERVO_MOVE SERVO_ID=3 POSITION=1000
G4 P1

# Simultaneous control (all at once)
RESPOND MSG="Simultaneous movement..."
SERVO_MOVE SERVO_ID=1 POSITION=3000
SERVO_MOVE SERVO_ID=2 POSITION=3000
SERVO_MOVE SERVO_ID=3 POSITION=3000
```

#### Test 6.6: Mixed Mode Operation
```gcode
# Set different servos to different modes
SERVO_MODE SERVO_ID=1 MODE=0  # Position mode
SERVO_MODE SERVO_ID=2 MODE=1  # Continuous mode

# Control position servo
SERVO_MOVE SERVO_ID=1 POSITION=1500

# Control continuous servo  
SERVO_ROTATE SERVO_ID=2 SPEED=300

# Wait and stop continuous servo
G4 P5
SERVO_STOP SERVO_ID=2

# Return continuous servo to position mode
SERVO_MODE SERVO_ID=2 MODE=0
SERVO_HOME SERVO_ID=2
```

### 7. Error Handling Tests

#### Test 7.1: Invalid Parameters
```gcode
# Test invalid position (should be handled gracefully)
SERVO_MOVE POSITION=5000

# Test invalid servo ID
SERVO_STATUS SERVO_ID=99

# Test invalid mode
SERVO_MODE MODE=5
```

**Expected Result:** Commands should fail gracefully with appropriate error messages

### 8. Stress Tests

#### Test 8.1: Rapid Commands
```gcode
# Rapid position changes
SERVO_MOVE POSITION=0 SPEED=2000
SERVO_MOVE POSITION=4095 SPEED=2000
SERVO_MOVE POSITION=2048 SPEED=2000
SERVO_MOVE POSITION=1024 SPEED=2000
SERVO_MOVE POSITION=3072 SPEED=2000
```

**Expected Result:** Servo should handle rapid command changes

#### Test 8.2: Continuous Operation
```gcode
# Extended continuous rotation
SERVO_ROTATE SPEED=300
G4 P30  # Run for 30 seconds
SERVO_STOP
```

**Expected Result:** Servo operates continuously without overheating

## Multi-Servo Test Sequence Template

Use this template for systematic multi-servo testing:

```gcode
# ========================================
# Multi-Servo Test Sequence - [Date/Time]  
# ========================================

# Define your servo IDs here (adjust as needed)
# SERVO_IDS: 1, 2, 3, 4

# 1. Initial Status Check - All Servos
RESPOND MSG="Starting multi-servo tests..."
SERVO_STATUS SERVO_ID=1
SERVO_STATUS SERVO_ID=2  
SERVO_STATUS SERVO_ID=3
SERVO_STATUS SERVO_ID=4

# 2. Home All Servos
RESPOND MSG="Homing all servos..."
SERVO_HOME SERVO_ID=1
SERVO_HOME SERVO_ID=2
SERVO_HOME SERVO_ID=3  
SERVO_HOME SERVO_ID=4
G4 P3

# 3. Individual Position Test
RESPOND MSG="Testing individual positions..."
SERVO_MOVE SERVO_ID=1 POSITION=1000
G4 P1
SERVO_MOVE SERVO_ID=2 POSITION=2000
G4 P1
SERVO_MOVE SERVO_ID=3 POSITION=3000
G4 P1
SERVO_MOVE SERVO_ID=4 POSITION=4000
G4 P2

# 4. Simultaneous Movement Test
RESPOND MSG="Testing simultaneous movement..."
SERVO_MOVE SERVO_ID=1 POSITION=0
SERVO_MOVE SERVO_ID=2 POSITION=1365    # 120 degrees
SERVO_MOVE SERVO_ID=3 POSITION=2730    # 240 degrees  
SERVO_MOVE SERVO_ID=4 POSITION=4095    # 360 degrees
G4 P3

# 5. Angle Control Test
RESPOND MSG="Testing angle control..."
SERVO_ANGLE SERVO_ID=1 ANGLE=45
SERVO_ANGLE SERVO_ID=2 ANGLE=135
SERVO_ANGLE SERVO_ID=3 ANGLE=225
SERVO_ANGLE SERVO_ID=4 ANGLE=315
G4 P3

# 6. Speed Variation Test
RESPOND MSG="Testing different speeds..."
SERVO_MOVE SERVO_ID=1 POSITION=2048 SPEED=200   # Slow
SERVO_MOVE SERVO_ID=2 POSITION=2048 SPEED=600   # Medium
SERVO_MOVE SERVO_ID=3 POSITION=2048 SPEED=1200  # Fast
SERVO_MOVE SERVO_ID=4 POSITION=2048 SPEED=2000  # Very fast
G4 P5

# 7. Continuous Rotation Test (one servo)
RESPOND MSG="Testing continuous rotation..."
SERVO_ROTATE SERVO_ID=1 SPEED=400
G4 P5
SERVO_STOP SERVO_ID=1
SERVO_HOME SERVO_ID=1
G4 P2

# 8. Final Status Check
RESPOND MSG="Multi-servo tests completed"
SERVO_STATUS SERVO_ID=1
SERVO_STATUS SERVO_ID=2
SERVO_STATUS SERVO_ID=3
SERVO_STATUS SERVO_ID=4
```

## Single Servo Test Template

For testing individual servos:

```gcode
# ========================================
# Single Servo Test - Servo ID: [X]
# ========================================

# Replace [X] with your servo ID
{% set test_servo_id = 1 %}

RESPOND MSG="Testing Servo ID { test_servo_id }"

# Status check
SERVO_STATUS SERVO_ID={test_servo_id}

# Home position
SERVO_HOME SERVO_ID={test_servo_id}
G4 P2

# Position range test
SERVO_MOVE SERVO_ID={test_servo_id} POSITION=0
G4 P2
SERVO_MOVE SERVO_ID={test_servo_id} POSITION=4095  
G4 P2
SERVO_HOME SERVO_ID={test_servo_id}
G4 P2

# Angle test
SERVO_ANGLE SERVO_ID={test_servo_id} ANGLE=90
G4 P2
SERVO_ANGLE SERVO_ID={test_servo_id} ANGLE=270
G4 P2
SERVO_HOME SERVO_ID={test_servo_id}

RESPOND MSG="Servo { test_servo_id } test completed"
```

## Quick Reference for Multi-Servo Commands

### Basic Syntax
All commands support the `SERVO_ID` parameter to specify which servo to control:

```gcode
# Command format:
COMMAND_NAME SERVO_ID=X [other parameters]

# Examples:
SERVO_MOVE SERVO_ID=1 POSITION=2048 SPEED=1000
SERVO_ANGLE SERVO_ID=2 ANGLE=90 SPEED=500  
SERVO_ROTATE SERVO_ID=3 SPEED=600
SERVO_STOP SERVO_ID=4
SERVO_HOME SERVO_ID=1 SPEED=800
SERVO_STATUS SERVO_ID=2
SERVO_MODE SERVO_ID=3 MODE=1
```

### Default Values
If you don't specify `SERVO_ID`, it defaults to servo ID 1:
```gcode
SERVO_MOVE POSITION=2048    # Same as SERVO_MOVE SERVO_ID=1 POSITION=2048
```

### Common Multi-Servo Patterns

**Control multiple servos to same position:**
```gcode
SERVO_MOVE SERVO_ID=1 POSITION=2048
SERVO_MOVE SERVO_ID=2 POSITION=2048  
SERVO_MOVE SERVO_ID=3 POSITION=2048
```

**Control multiple servos to different positions:**
```gcode
SERVO_MOVE SERVO_ID=1 POSITION=1000
SERVO_MOVE SERVO_ID=2 POSITION=2000
SERVO_MOVE SERVO_ID=3 POSITION=3000
```

**Create servo formations:**
```gcode
# Triangle formation (3 servos at 120° intervals)
SERVO_ANGLE SERVO_ID=1 ANGLE=0
SERVO_ANGLE SERVO_ID=2 ANGLE=120  
SERVO_ANGLE SERVO_ID=3 ANGLE=240

# Square formation (4 servos at 90° intervals)  
SERVO_ANGLE SERVO_ID=1 ANGLE=0
SERVO_ANGLE SERVO_ID=2 ANGLE=90
SERVO_ANGLE SERVO_ID=3 ANGLE=180
SERVO_ANGLE SERVO_ID=4 ANGLE=270
```

### Common Issues and Solutions

**Command Not Found Error:**
- Verify configuration is loaded in Klipper
- Check for syntax errors in configuration
- Restart Klipper firmware

**Shell Script Execution Errors:**
- Check script permissions: `chmod +x /home/grafito/Grafito-Edge-Services/python-st3215/servo_control.sh`
- Verify script path is correct
- Test script manually: `bash /home/grafito/Grafito-Edge-Services/python-st3215/servo_control.sh status`

**Servo Not Responding:**
- Check hardware connections
- Verify power supply to servos
- Test with direct script commands
- Check servo ID configuration

**Timeout Errors:**
- Increase timeout value in shell command definitions
- Check for hardware communication issues
- Verify servo is not mechanically stuck

**Parameter Errors:**
- Ensure parameters are within valid ranges
- Check parameter spelling and case sensitivity
- Verify Jinja template syntax

## Logging and Monitoring

Enable verbose logging to monitor command execution:
- The configuration already has `verbose: True` enabled
- Monitor Klipper logs for detailed command output
- Use `RESPOND` commands to add custom logging

## Safety Considerations

- Always test with safe servo positions first
- Monitor servo temperature during extended operation
- Have emergency stop procedures ready
- Test individual servos before simultaneous operation
- Verify mechanical clearances before full range testing

## Performance Metrics

Track these metrics during testing:
- Command response time
- Position accuracy
- Speed consistency
- Error frequency
- Temperature stability

## Configuration Backup

Before making changes, backup your configuration:
```bash
cp printer.cfg printer.cfg.backup.$(date +%Y%m%d_%H%M%S)
```

This ensures you can revert if issues arise during testing.

## Test Commands

```gcode
SERVO_ANGLE SERVO_ID=4 ANGLE=200
SERVO_ANGLE SERVO_ID=4 ANGLE=240
```

```gcode
SERVO_MOVE SERVO_ID=1 ANGLE=200
SERVO_MOVE SERVO_ID=1 ANGLE=200
```
