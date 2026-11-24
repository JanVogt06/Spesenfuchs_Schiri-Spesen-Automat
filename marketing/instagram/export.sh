#!/bin/sh
# Exports the Instagram slides (frontend/src/instagram) as PNG:
# the post in 3:4 (1080 x 1440) into this folder, the story in 9:16
# (1080 x 1920) into story/. Prerequisite: the Vite dev server is running
# (npm run dev in frontend).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASIS="${BASIS:-http://localhost:5173/instagram.html}"
NAMEN="01-ankuendigung 02-problem 03-ablauf 04-funktionen 05-aufruf"

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
