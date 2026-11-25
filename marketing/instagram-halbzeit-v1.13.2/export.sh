#!/bin/sh
# Exports the half-time post (frontend/src/instagram/Halbzeit.tsx) as PNG:
# the post in 3:4 (1080 x 1440) into this folder, the story in 9:16
# (1080 x 1920) into story/. Prerequisite: the Vite dev server is running
# (npm run dev in frontend).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASIS="${BASIS:-http://localhost:5173/instagram-halbzeit.html}"
NAMEN="01-halbzeit 02-november 03-spiele 04-fahrten 05-statistik 06-spielberichte 07-ausserdem 08-aufruf"

# Without a server, Chrome would silently screenshot the error page
curl -fsS -o /dev/null "$BASIS" || { echo "Dev-Server unter $BASIS nicht erreichbar" >&2; exit 1; }

aufnehmen() { # target, height, extra parameters
    mkdir -p "$1"
    i=1
    for name in $NAMEN; do
        "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
            --window-size=540,"$2" --virtual-time-budget=4000 \
            --screenshot="$PWD/$1/$name.png" "$BASIS?s=$i$3" >/dev/null 2>&1
        echo "$1/$name.png"
        i=$((i + 1))
    done
}

aufnehmen . 720 ""
aufnehmen story 960 "&f=story"
