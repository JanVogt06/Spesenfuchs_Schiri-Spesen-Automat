#!/usr/bin/env bash
#
# Synct data/app.db vom Server auf das lokale Repo.
# Richtung: Server -> Lokal (die lokale Datenbank wird dabei überschrieben,
# damit sie exakt dem Server-Stand entspricht).
#
# Die Datenbank enthaelt inzwischen alles: Spiele, Unparteiische und
# Fahrtkosten. Dokumente entstehen beim Download und liegen nirgends.
#
# data/.env wird absichtlich NICHT gesynct - die Secrets bleiben auf dem Server.
#
set -euo pipefail

SSH_HOST="jan-server"
# Verzeichnisname auf dem Server - beim Umbenennen des Server-Ordners
# (Projekt heisst inzwischen "spesenfuchs") hier mitziehen.
REMOTE_DIR="/home/janvogt/dockercontainer/dfb-spesen-generator/data"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/data"

mkdir -p "${LOCAL_DIR}"

echo "Synce app.db von ${SSH_HOST}..."
rsync -avz --progress \
    "${SSH_HOST}:${REMOTE_DIR}/app.db" \
    "${LOCAL_DIR}/app.db"

echo "Fertig."
