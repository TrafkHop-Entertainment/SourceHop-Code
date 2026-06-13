#!/bin/bash

DIR="$HOME/.config/wallpapers"

# Zufälliges Bild auswählen (ohne den Symlink selbst)
RANDOM_PIC=$(find "$DIR" -type f -not -name "current_wallpaper" | shuf -n 1)

# Abbruch, falls kein Bild gefunden wurde
if [ -z "$RANDOM_PIC" ]; then
    echo "Fehler: Kein Bild in $DIR gefunden."
    exit 1
fi

# Symlink aktualisieren (nur wichtig für den nächsten Systemstart)
ln -sf "$RANDOM_PIC" "$DIR/current_wallpaper"

# Prüfen, ob Hyprpaper läuft
if pgrep -x "hyprpaper" > /dev/null; then
    # NEU: preload und unload wurden aus Hyprpaper entfernt.
    # Wir rufen direkt den wallpaper-Request auf, den Rest macht Hyprpaper selbst.
    hyprctl hyprpaper wallpaper ",$RANDOM_PIC"
else
    # Sicherheitsfall: hyprpaper läuft doch nicht – dann starte es
    hyprpaper &
fi
