#!/bin/bash

HIDDEN=false
trap "HIDDEN=false" USR2

SCREEN_H=$(hyprctl monitors -j | jq -r '.[] | select(.focused == true) | .height')
if [ -z "$SCREEN_H" ]; then
    SCREEN_H=$(hyprctl monitors | grep -A 12 "focused: yes" | grep "res" | awk '{print $2}' | cut -d'x' -f2 | cut -d'@' -f1)
fi

THRESHOLD=$((SCREEN_H - 165))
THRESHOLD2=$((SCREEN_H - 15))

MOUSE_Y=0

while sleep 0.1; do
    pos=$(hyprctl cursorpos)

    if [[ "$pos" =~ ^[0-9]+,\ ([0-9]+)$ ]]; then
        MOUSE_Y="${BASH_REMATCH[1]}"
    else
        continue
    fi


    if [ "$MOUSE_Y" -ge "$THRESHOLD2" ] && [ "$HIDDEN" = true ]; then
        pkill -SIGUSR1 waybar
        HIDDEN=false
    elif [ "$MOUSE_Y" -lt "$THRESHOLD" ] && [ "$HIDDEN" = false ]; then
        pkill -SIGUSR1 waybar
        HIDDEN=true
    fi
done
