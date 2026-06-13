#!/bin/bash

# KONFIGURATION
SINGLE_WORKSPACES="1 2"

is_single_ws() {
    for ws in $SINGLE_WORKSPACES; do
        [[ "$1" == "$ws" ]] && return 0
    done
    return 1
}

_LOCK=false

manage_window() {
    local event_type="$1"
    local event_data="$2"
    local target_addr=""

    if [[ "$event_type" == "openwindow" ]]; then
        target_addr="${event_data%%,*}"
    elif [[ "$event_type" == "activewindowv2" ]]; then
        target_addr="$event_data"
    else
        local active_addr
        active_addr=$(hyprctl activewindow -j | jq -r '.address // empty')
        [[ -z "$active_addr" ]] && return
        target_addr="$active_addr"
    fi

    [[ -z "$target_addr" ]] && return

    local clients_json
    clients_json=$(hyprctl clients -j)

    local clean_addr="${target_addr#0x}"
    local win_data
    win_data=$(echo "$clients_json" | jq ".[] | select(.address | endswith(\"$clean_addr\"))")

    [[ -z "$win_data" ]] && return

    local is_floating
    is_floating=$(echo "$win_data" | jq -r '.floating')
    local fs_mode
    fs_mode=$(echo "$win_data" | jq -r '.fullscreen')
    local win_ws
    win_ws=$(echo "$win_data" | jq -r '.workspace.name')
    local exact_addr
    exact_addr=$(echo "$win_data" | jq -r '.address')

    if ! is_single_ws "$win_ws"; then
        return
    fi

    if [[ "$is_floating" == "true" ]]; then
        return
    fi

    if [[ "$fs_mode" != "0" ]]; then
        return
    fi


    hyprctl --batch "dispatch focuswindow address:$exact_addr; dispatch fullscreen 1" >/dev/null
}

socat -U - "UNIX-CONNECT:$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket2.sock" | while read -r line; do
    event="${line%%>>*}"
    data="${line#*>>}"

    case "$event" in
        openwindow)
            ( sleep 0.08; manage_window "$event" "$data" ) &
            ;;
        workspace|workspacev2)
            manage_window "$event" "$data" &
            ;;
    esac
done
