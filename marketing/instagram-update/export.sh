#!/bin/sh
# Exportiert die Update-Story (frontend/src/instagram/Update.tsx) als PNG in
# 9:16 (1080 x 1920) hierher. Voraussetzung: der Vite-Dev-Server laeuft
# (npm run dev in frontend).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASIS="${BASIS:-http://localhost:5173/instagram-update.html}"
NAMEN="01-update 02-beobachtungen 03-app 04-feinschliff 05-aufruf"

# Ohne Server fotografiert Chrome sonst still die Fehlerseite ab
curl -fsS -o /dev/null "$BASIS" || { echo "Dev-Server unter $BASIS nicht erreichbar" >&2; exit 1; }

i=1
for name in $NAMEN; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
        --window-size=540,960 --virtual-time-budget=4000 \
        --screenshot="$PWD/$name.png" "$BASIS?s=$i&f=story" >/dev/null 2>&1
    echo "$name.png"
    i=$((i + 1))
done
