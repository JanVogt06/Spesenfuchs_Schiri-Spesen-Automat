#!/bin/sh
# Exportiert die Instagram-Slides (frontend/src/instagram) als PNG, 1080 x 1440.
# Voraussetzung: der Vite-Dev-Server laeuft (npm run dev in frontend).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASIS="${BASIS:-http://localhost:5173/instagram.html}"
NAMEN="01-ankuendigung 02-problem 03-ablauf 04-funktionen 05-aufruf"
i=1
for name in $NAMEN; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
        --window-size=540,720 --virtual-time-budget=4000 \
        --screenshot="$PWD/$name.png" "$BASIS?s=$i" >/dev/null 2>&1
    echo "$name.png"
    i=$((i + 1))
done
