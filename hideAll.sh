#!/bin/bash
HIDDEN_WS="special:hidden"
CURRENT_WS=$(hyprctl monitors -j | jq -r '.[] | select(.focused == true) | .activeWorkspace.id')

BATCH_CMD=""

if hyprctl clients -j | jq -e ".[] | select(.workspace.name == \"$HIDDEN_WS\")" >/dev/null 2>&1; then
    # Wiederherstellen
    for addr in $(hyprctl clients -j | jq -r ".[] | select(.workspace.name == \"$HIDDEN_WS\") | .address"); do
        BATCH_CMD+="dispatch movetoworkspacesilent $CURRENT_WS,address:$addr; "
    done
else
    # Verstecken
    for addr in $(hyprctl clients -j | jq -r ".[] | select(.workspace.id == $CURRENT_WS and .pinned == false) | .address"); do
        BATCH_CMD+="dispatch movetoworkspacesilent $HIDDEN_WS,address:$addr; "
    done
fi

# Alles auf einmal abschicken
[[ -n "$BATCH_CMD" ]] && hyprctl --batch "$BATCH_CMD"
