#!/bin/bash

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
SCRIPT_PATH="$(realpath "$0")"
STATE_FILE="${XDG_RUNTIME_DIR:-/tmp}/rofi-menu-state"
CACHE_FILE="${XDG_RUNTIME_DIR:-/tmp}/rofi-desktop-cache"
CACHE_MAX_AGE=120
OTHER_FOLDER="Programs"
PACKAGES_FOLDER="Packages"
MENU_JSON_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/rofi/menu.json"

if [ -f "$MENU_JSON_FILE" ]; then
    MENU_JSON="$(cat "$MENU_JSON_FILE")"
else
    MENU_JSON='{"1 System":{}, "2 Work":{}, "3 Utilities":{}, "4 Games":{}, "5 Multimedia":{}, "6 Settings":{}, "7 Social":{}}'
fi

# ─────────────────────────────────────────────────────────────
# DESKTOP ENTRIES CACHE
# ─────────────────────────────────────────────────────────────
is_cache_valid() {
    [ -f "$CACHE_FILE" ] || return 1
    local now mod age
    now=$(date +%s)
    mod=$(stat -c %Y "$CACHE_FILE" 2>/dev/null) || return 1
    age=$((now - mod))
    [ "$age" -lt "$CACHE_MAX_AGE" ]
}

build_desktop_cache() {
    local desktop_dirs=(
        "/usr/share/applications"
        "$HOME/.local/share/applications"
        "/usr/local/share/applications"
    )
    local tmp="${CACHE_FILE}.tmp"
    : > "$tmp"
    for dir in "${desktop_dirs[@]}"; do
        [ -d "$dir" ] || continue
        while IFS= read -r desktop; do
            grep -qE '^(NoDisplay|Hidden)=true' "$desktop" && continue
            name=$(grep -m1 '^Name=' "$desktop" | cut -d= -f2-)
            exec_cmd=$(grep -m1 '^Exec=' "$desktop" | cut -d= -f2- | sed 's/%[a-zA-Z]//g;s/^[[:space:]]*//;s/[[:space:]]*$//')
            icon=$(grep -m1 '^Icon=' "$desktop" | cut -d= -f2-)
            [ -z "$name" ] || [ -z "$exec_cmd" ] && continue
            name="${name//[$'\t\n\0']/ }"
            exec_cmd="${exec_cmd//[$'\t\n\0']/ }"
            printf "%s\t%s\t%s\n" "$name" "$exec_cmd" "$icon"
        done < <(find "$dir" -name "*.desktop" -type f 2>/dev/null)
    done | sort -u > "$tmp"
    mv "$tmp" "$CACHE_FILE"
}

get_desktop_entries() {
    if ! is_cache_valid; then build_desktop_cache; fi
    cat "$CACHE_FILE"
}

if [ -z "$ROFI_RETV" ] && ! is_cache_valid; then
    build_desktop_cache &
fi

# ─────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────
get_path() { [ -f "$STATE_FILE" ] && cat "$STATE_FILE" || echo "."; }
set_path() { echo "$1" > "$STATE_FILE"; }

is_in_static_menu() {
    local name="$1"
    local exec_cmd="$2"
    if echo "$MENU_JSON" | jq -r '.. | objects | to_entries[] | select(.value | type=="string") | "\(.key)\t\(.value)"' | \
        grep -qi "^$name	\|	$exec_cmd$"; then
        return 0
    fi
    return 1
}

# ─────────────────────────────────────────────────────────────
# NAVIGATION & SEARCH
# ─────────────────────────────────────────────────────────────
get_nav_entries() {
    local path="$1"

    printf "✕ Schließen\0icon\x1fwindow-close\x1finfo\x1fquit:\n"

    if [[ "$path" == SEARCH:* ]]; then
        local query="${path#SEARCH:}"
        echo "$MENU_JSON" | jq -r '.. | objects | to_entries[] | select(.value | type=="string") | "\(.key)\t\(.value)"' \
            | grep -i "$query" | while IFS=$'\t' read -r s_name s_cmd; do
            printf "%s\0icon\x1fsearch\x1finfo\x1fcmd:%s\n" "[Menu] $s_name" "$s_cmd"
        done
        get_desktop_entries | grep -i "$query" | while IFS=$'\t' read -r d_name d_cmd d_icon; do
            printf "%s\0icon\x1f%s\x1finfo\x1fcmd:%s\n" "[App] $d_name" "$d_icon" "$d_cmd"
        done
        compgen -c | grep -i "^$query" | sort -u | while read -r b_cmd; do
            printf "%s\0icon\x1fsystem-run\x1finfo\x1fcmd:%s\n" "[Exec] $b_cmd" "$b_cmd"
        done
        return
    fi

    if [ "$path" = "." ]; then
        echo "$MENU_JSON" | jq -r 'keys[]' | while read -r folder; do
            printf "%s\0icon\x1ffolder\x1finfo\x1fdir:%s\n" "$folder" "$folder"
        done
        printf "%s\0icon\x1ffolder-blue\x1finfo\x1fdir:%s\n" "$OTHER_FOLDER" "$OTHER_FOLDER"
        printf "%s\0icon\x1fpackage-x-generic\x1finfo\x1fdir:%s\n" "$PACKAGES_FOLDER" "$PACKAGES_FOLDER"
        return
    fi

    if [ "$path" = "$OTHER_FOLDER" ]; then
        get_desktop_entries | while IFS=$'\t' read -r name exec_cmd icon; do
            if ! is_in_static_menu "$name" "$exec_cmd"; then
                printf "%s\0icon\x1f%s\x1finfo\x1fcmd:%s\n" "$name" "$icon" "$exec_cmd"
            fi
        done
        return
    fi

    if [ "$path" = "$PACKAGES_FOLDER" ]; then
        declare -A exclude
        while IFS=$'\t' read -r s_name s_cmd; do exclude["${s_cmd%% *}"]=1; done < <(echo "$MENU_JSON" | jq -r '.. | objects | to_entries[] | select(.value | type=="string") | "\(.key)\t\(.value)"')
        while IFS=$'\t' read -r _ d_cmd _; do exclude["${d_cmd%% *}"]=1; done < <(get_desktop_entries)
        compgen -c | sort -u | while read -r cmd; do
            [ -z "${exclude[$cmd]}" ] && printf "%s\0icon\x1fapplication-x-executable\x1finfo\x1fcmd:%s\n" "$cmd" "$cmd"
        done
        return
    fi

    echo "$MENU_JSON" | jq -r --arg p "$path" '
        (if $p == "." then . else getpath($p | split(".")) end) | to_entries[]
        | "\(.key)\t\(if (.value|type)=="object" then "dir" else "cmd" end)\t\(if (.value|type)=="object" then "" else .value end)"
    ' | while IFS=$'\t' read -r name type value; do
        if [ "$type" = "dir" ]; then
            new_path="${path}.${name}"
            [ "$path" = "." ] && new_path="$name"
            printf "%s\0icon\x1ffolder\x1finfo\x1fdir:%s\n" "$name" "$new_path"
        else
            icon_name="${name,,}"
            case "$name" in
                "VLC Player")       icon_name="vlc" ;;
                "Firefox")          icon_name="firefox" ;;
                "Kitty")            icon_name="kitty" ;;
                "Thunar")           icon_name="system-file-manager" ;;
                "Htop")             icon_name="htop" ;;
                "Fastfetch")        icon_name="utilities-terminal" ;;
                *)                  icon_name="${name,,}" ;;
            esac
            printf "%s\0icon\x1f%s\x1finfo\x1fcmd:%s\n" "$name" "$icon_name" "$value"
        fi
    done
}

run_mode() {
    local selection="$1"
    local info="$ROFI_INFO"
    local path
    path=$(get_path)

    if [ "$ROFI_RETV" -gt 0 ]; then
        if [ -n "$info" ]; then
            local type="${info%%:*}"
            local value="${info#*:}"
            case "$type" in
                cmd)
                    rm -f "$STATE_FILE"
                    setsid bash -c "$value" >/dev/null 2>&1 &
                    exit 0
                    ;;
                quit)
                    rm -f "$STATE_FILE"
                    exit 0
                    ;;
                dir)
                    set_path "$value"
                    ;;
                back)
                    if [[ "$path" == SEARCH:* ]]; then set_path "."
                    elif [[ "$path" == *.* ]]; then set_path "${path%.*}"
                    else set_path "."; fi
                    ;;
            esac
        elif [ -n "$selection" ]; then
            set_path "SEARCH:$selection"
        fi
    fi

    path=$(get_path)

    if [ "$path" = "." ]; then printf "\0prompt\x1fMenu\n"
    elif [[ "$path" == SEARCH:* ]]; then printf "\0prompt\x1fSearch: %s\n" "${path#SEARCH:}"
    else printf "\0prompt\x1f%s\n" "$path"
    fi
    printf "\0no-custom\x1ffalse\n"

    if [ "$path" != "." ]; then
        printf "← Zurück\0icon\x1fgo-previous\x1finfo\x1fback:\n"
    fi

    get_nav_entries "$path"
}

start() {
    rm -f "$STATE_FILE"

    rofi -show menu -modi "menu:$SCRIPT_PATH" -show-icons -theme-str 'configuration { icon-theme: "Clay"; }' -theme-str 'element { padding: 45px 0px; }'
}

if [ "$1" = "--clear-cache" ]; then
    rm -f "$CACHE_FILE"
    echo "Cache gelöscht."
    exit 0
fi

if [ -n "$ROFI_RETV" ]; then
    run_mode "$1"
else
    start
fi
