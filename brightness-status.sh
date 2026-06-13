#!/bin/bash
# TrafkHop brightness-status.sh
# Wird von waybar custom/brightness als "exec"-Skript aufgerufen.
# Gibt Icon + Prozentwert aus – funktioniert mit echter Hardware UND in VMs.
#
# Aufruf:
#   brightness-status.sh          → aktuellen Wert ausgeben (für waybar interval)
#   brightness-status.sh up       → Helligkeit +5 % (Scroll-Up)
#   brightness-status.sh down     → Helligkeit -5 % (Scroll-Down)

STATE_FILE="/tmp/trafkhop_brightness"
ACTION="${1:-}"

# ─── Backend ermitteln ────────────────────────────────────────────────────────

has_brightnessctl() {
    command -v brightnessctl &>/dev/null && \
    brightnessctl -m 2>/dev/null | grep -q '%'
}

# ─── Helligkeitswert lesen ────────────────────────────────────────────────────

get_value() {
    if has_brightnessctl; then
        brightnessctl -m 2>/dev/null | cut -d',' -f4 | tr -d '%'
    else
        # VM-Fallback: gespeicherten Wert aus State-File lesen
        cat "$STATE_FILE" 2>/dev/null || echo "100"
    fi
}

# ─── Helligkeitswert setzen ───────────────────────────────────────────────────

set_value() {
    local val="$1"
    (( val < 1  )) && val=1
    (( val > 100 )) && val=100

    if has_brightnessctl; then
        brightnessctl set "${val}%" &>/dev/null
    else
        # VM-Fallback mit Gammastep (Software-Dimming)
        echo "$val" > "$STATE_FILE"
        if command -v gammastep &>/dev/null; then
            killall gammastep 2>/dev/null
            # Umrechnen von 1-100 auf 0.1 bis 1.0
            local float_val=$(awk "BEGIN {print $val/100}")
            # Lade den aktuellen Nachtlicht-Wert (oder Standard 6500)
            local temp=$(cat /tmp/trafkhop_night_temp 2>/dev/null || echo 6500)
            # Gammastep wendet Temperatur und Software-Helligkeit gleichzeitig an
            gammastep -P -O "$temp" -b "$float_val" >/dev/null 2>&1 &
        fi
    fi
}

# ─── Icon wählen ─────────────────────────────────────────────────────────────

get_icon() {
    local v="$1"
    if   (( v < 34 )); then echo "󰃞"
    elif (( v < 67 )); then echo "󰃟"
    else                    echo "󰃠"
    fi
}

# ─── Aktionen ─────────────────────────────────────────────────────────────────

current=$(get_value)

case "$ACTION" in
    up)
        set_value $(( current + 5 ))
        current=$(get_value)
        ;;
    down)
        set_value $(( current - 5 ))
        current=$(get_value)
        ;;
esac

icon=$(get_icon "$current")
echo "${icon} ${current}%"
