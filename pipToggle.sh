    #!/bin/bash

PIP_FILE="/tmp/hypr_pip_window"

create_pip() {
    local active
    active=$(hyprctl activewindow -j) || exit 1
    local addr
    addr=$(echo "$active" | jq -r '.address')
    local ws
    ws=$(echo "$active" | jq -r '.workspace.id')

    if [[ "$addr" == "null" || -z "$addr" ]]; then
        echo "❌ Kein aktives Fenster"
        exit 1
    fi

    # Zustand speichern
    echo "$addr $ws" > "$PIP_FILE"

    # Fenster ins PiP verwandeln (ohne sleep, als Batch)
    hyprctl --batch "dispatch togglefloating address:$addr; dispatch pin address:$addr; dispatch resizewindowpixel exact 400 225,address:$addr; dispatch movewindowpixel exact 20 20,address:$addr; dispatch focuswindow address:$addr"
    hyprctl dispatch pin address:"$addr"
    hyprctl dispatch resizewindowpixel exact 400 225,address:"$addr"
    hyprctl dispatch movewindowpixel exact 20 20,address:"$addr"
    hyprctl dispatch focuswindow address:"$addr"
}

restore_pip() {
    local addr ws
    read -r addr ws < "$PIP_FILE"
    if [[ -z "$addr" ]]; then
        echo "❌ Ungültige PiP-Datei"
        rm -f "$PIP_FILE"
        exit 1
    fi

    # Prüfen, ob das Fenster noch existiert
    if ! hyprctl clients -j | jq -e ".[] | select(.address == \"$addr\")" >/dev/null; then
        echo "⚠️  Fenster existiert nicht mehr"
        rm -f "$PIP_FILE"
        exit 1
    fi

    # Falls der gespeicherte Workspace ein special oder negativ ist → aktuellen nehmen
    if [[ "$ws" == "special"* ]] || [[ "$ws" =~ ^-?[0-9]+$ && "$ws" -lt 0 ]]; then
        ws=$(hyprctl monitors -j | jq -r '.[] | select(.focused == true) | .activeWorkspace.id')
    fi

    # PiP rückgängig machen
    hyprctl dispatch pin address:"$addr"         # entpinnt (toggle)
    sleep 0.05
    hyprctl dispatch togglefloating address:"$addr"  # zurück ins Tiling
    hyprctl dispatch movetoworkspacesilent "$ws,address:$addr"
    hyprctl dispatch focuswindow address:"$addr"

    rm -f "$PIP_FILE"
}

if [[ -f "$PIP_FILE" ]]; then
    restore_pip
else
    create_pip
fi
