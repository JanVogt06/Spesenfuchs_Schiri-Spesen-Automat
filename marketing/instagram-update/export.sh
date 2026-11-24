#!/bin/sh
# Exports the update story (frontend/src/instagram/Update.tsx) as PNG in
# 9:16 (1080 x 1920) into this folder. Prerequisite: the Vite dev server is
# running (npm run dev in frontend).
set -e
cd "$(dirname "$0")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASIS="${BASIS:-http://localhost:5173/instagram-update.html}"
NAMEN="01-update 02-beobachtungen 03-app 04-feinschliff 05-aufruf"

# Without a server, Chrome would silently screenshot the error page
curl -fsS -o /dev/null "$BASIS" || { echo "Dev-Server unter $BASIS nicht erreichbar" >&2; exit 1; }

i=1
for name in $NAMEN; do
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
        --window-size=540,960 --virtual-time-budget=4000 \
        --screenshot="$PWD/$name.png" "$BASIS?s=$i&f=story" >/dev/null 2>&1
    echo "$name.png"
    i=$((i + 1))
done
