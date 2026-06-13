#!/bin/bash

# Aktives Fenster für "Close" ermitteln
last_active=$(hyprctl activewindow -j 2>/dev/null | jq -r '.address // empty')

# ─────────────────────────────────────────────────────────────
# ICON PFADE
# Rofi sucht Icons zuerst im angegebenen Pfad, dann im Theme.
# Absolute Pfade für eigene PNGs, Theme-Namen für System-Icons.
# ─────────────────────────────────────────────────────────────
ICON_CLOSE="$HOME/.config/rofi/EXIT2.png"

# System-Icons (funktionieren mit fast jedem Icon-Theme):
ICON_SHUTDOWN="system-shutdown"
ICON_REBOOT="system-reboot"
ICON_LOGOUT="system-log-out"
ICON_SUSPEND="system-suspend"
ICON_LOCK="system-lock-screen"

# ─────────────────────────────────────────────────────────────
# CLOSE-BUTTON nur anzeigen wenn ein Fenster aktiv ist
# ─────────────────────────────────────────────────────────────
options=""
if [[ -n "$last_active" ]]; then
    options+="Close\0icon\x1f${ICON_CLOSE}\n"
fi
options+="Shutdown\0icon\x1f${ICON_SHUTDOWN}\n"
options+="Reboot\0icon\x1f${ICON_REBOOT}\n"
options+="Logout\0icon\x1f${ICON_LOGOUT}\n"
options+="Suspend\0icon\x1f${ICON_SUSPEND}\n"
options+="Lock\0icon\x1f${ICON_LOCK}"

# ─────────────────────────────────────────────────────────────
# ROFI AUFRUFEN
# ─────────────────────────────────────────────────────────────
chosen=$(echo -e "$options" | rofi \
    -dmenu \
    -show-icons \
    -p "Power" \
    -theme-str 'inputbar { enabled: false; }' \
    -theme-str 'element-icon { size: 165px; }' \
    -theme-str 'listview { columns: 3; lines: 2; }')

[ -z "$chosen" ] && exit 0

case "$chosen" in
    Close)
        hyprctl dispatch closewindow address:"$last_active"
        ;;
    Shutdown)
        systemctl poweroff
        ;;
    Reboot)
        systemctl reboot
        ;;
    Logout)
        hyprctl dispatch exit
        ;;
    Suspend)
        systemctl suspend
        ;;
    Lock)
        if command -v hyprlock &>/dev/null; then
            hyprlock
        else
            loginctl lock-session
        fi
        ;;
esac
