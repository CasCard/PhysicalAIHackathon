#!/bin/bash
# This script serves as a bridge between Klipper and your servo control script

PYTHON_PATH=python3
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMAND=$1
SERVO_ID=$2
VALUE=$3
SPEED=$4

SERIAL_DEVICE='/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0'
LOG_FILE="$SCRIPT_DIR/servo_control.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

log "Command received: $COMMAND, ServoID: $SERVO_ID, Value: $VALUE, Speed: $SPEED"

case "$COMMAND" in
    "move")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" move "$SERVO_ID" "$VALUE" "$SPEED"
        ;;
    "rotate")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" rotate "$SERVO_ID" "$VALUE"
        ;;
    "stop")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" stop "$SERVO_ID"
        ;;
    "mode")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" mode "$SERVO_ID" "$VALUE"
        ;;
    "status")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" status "$SERVO_ID"
        ;;
    "list")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" list
        ;;
    "check")
        $PYTHON_PATH "$SCRIPT_DIR/servo_control.py" --device "$SERIAL_DEVICE" check "$SERVO_ID"
        ;;
    "help")
        echo "Usage: ./servo_control.sh <command> [args...]"
        echo ""
        echo "Commands:"
        echo "  move   <ID> <position> <speed>   - Move servo to position"
        echo "  rotate <ID> <speed>              - Rotate servo continuously"
        echo "  stop   <ID>                      - Stop the servo"
        echo "  mode   <ID> <mode>               - Set mode: 0=position, 1=rotation"
        echo "  status <ID>                      - Show status"
        echo "  list                             - List connected servos"
        echo "  check  <ID>                      - Show detailed info"
        echo "  help                             - Show this help message"
        exit 0
        ;;
    *)
        log "Unknown command: $COMMAND"
        echo "Unknown command: $COMMAND" >&2
        exit 1
        ;;
esac

EXIT_CODE=$?
log "Command completed with exit code: $EXIT_CODE"
exit $EXIT_CODE
