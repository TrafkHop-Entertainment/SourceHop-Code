#!/bin/bash
# TrafkHop Popup Toggle
# Verwendung: popup-toggle.sh volume|calendar|network|bluetooth

POPUP="$1"
SCRIPT_DIR="$(dirname "$(realpath "$0")")"

case "$POPUP" in
    volume)    SCRIPT="$SCRIPT_DIR/volume-popup.py" ;;
    brightness) SCRIPT="$SCRIPT_DIR/brightness-popup.py" ;;
    calendar)  SCRIPT="$SCRIPT_DIR/calendar-popup.py" ;;
    network)   SCRIPT="$SCRIPT_DIR/network-popup.py" ;;
    bluetooth) SCRIPT="$SCRIPT_DIR/bluetooth-popup.py" ;;
    *) echo "Unbekanntes Popup: $POPUP"; exit 1 ;;
esac

# Kill if running (toggle off)
if pkill -f "$SCRIPT" 2>/dev/null; then
    exit 0
fi

# Start popup
exec python3 "$SCRIPT"
