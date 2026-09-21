# Spesenfuchs

**Schiri-Spesen-Automat.** Erstellt Schiedsrichter-Spesenabrechnungen automatisch aus den eigenen
DFB.net-Ansetzungen. Einmal die DFB.net-Zugangsdaten hinterlegen, danach holt
die Anwendung jede Nacht die aktuellen Ansetzungen in die Datenbank. Die
Abrechnung als DOCX oder PDF entsteht beim Download — inklusive Fahrtkosten,
wenn die Kilometer im Rechner eingetragen sind. Beim selben Abruf liest die
Anwendung auch die eigenen Stammdaten aus DFB.net und zeigt sie im Reiter
*Stammdaten*; die persönlichen Angaben darunter liegen verschlüsselt in der
Datenbank. Der Reiter *Saison* zeigt alle geleiteten Spiele je Saison mit
Ergebnis, Kartenstatistik und Gespann, dazu Einsatzbilanz und Lehrabende.
Abgeschlossene Saisons werden nur einmal gelesen — erneut geholt werden die
laufende Saison und jede, deren Bestand unvollständig ist. Bei den Fahrtkosten
eines Spiels liegt eine Karte, die die Anschriften der angesetzten
Unparteiischen und die Spielstätte zeigt — so ist beim Eintragen der Kilometer
sichtbar, wer wie weit fährt.

Die Oberfläche hat vier Reiter: *Dashboard* mit der Übersicht, *Spesen* mit den
Abrechnungen zum Herunterladen, *Saison* und *Stammdaten*.

Self-hosted: ein Container, eine `docker-compose.yml`, ein `data`-Ordner.

## Schnellstart

### Auf einem Server, ohne Checkout

Der Quellcode wird nicht gebraucht — eine Datei und ein Ordner genügen. Die
`docker-compose.yml` dieses Repositories ist unverändert server-tauglich, sie
enthält absichtlich keine Build-Anweisung:

```bash
mkdir -p spesenfuchs/data && cd spesenfuchs
curl -fO https://raw.githubusercontent.com/JanVogt06/dfb-spesen-generator/main/docker-compose.yml
docker compose pull && docker compose up -d
```

Danach ist die Oberfläche unter http://localhost:8001 erreichbar, von anderen
Geräten im Netzwerk über die Adresse des Hosts, zum Beispiel
`http://192.168.1.20:8001`.

Die Datei zieht `latest`. Wer selbst entscheiden möchte, wann aktualisiert wird,
nagelt die Version fest — entweder von Hand oder gleich beim Einrichten:

```bash
sed -i 's/:latest/:1.2.1/' docker-compose.yml
```

### Aus einem Checkout

```bash
docker compose up -d --build
```

Im Checkout liegt neben der Compose-Datei eine
[`docker-compose.override.yml`](docker-compose.override.yml), die Docker Compose
automatisch dazulädt und die `build: .` ergänzt. Deshalb baut derselbe Befehl
hier aus dem Quellcode, während auf dem Server ohne diese Datei das fertige
Image benutzt wird — eine Konfiguration, zwei Verwendungen.

### Port ändern

Ohne die Compose-Datei anzufassen:

```bash
SPESEN_PORT=9000 docker compose up -d
```

Soll die Oberfläche nur vom Host selbst erreichbar sein (etwa weil ein
Reverse-Proxy davor liegt), das Port-Mapping auf
`"127.0.0.1:${SPESEN_PORT:-8001}:8001"` ändern.

## Daten und Secrets

Alles Veränderliche liegt im Container unter `/data` und damit im Ordner `data`
neben der Compose-Datei — es übersteht Neustarts und Updates:

| Pfad | Inhalt |
| --- | --- |
| `data/.env` | `JWT_SECRET_KEY` und `ENCRYPTION_KEY` |
| `data/app.db` | Nutzer, eigene Stammdaten, Spiele, Unparteiische, Fahrtkosten, geleitete Spiele je Saison, aufgelöste Adressen der Karte, Abruf-Protokoll, Login- und Download-Log |

Erzeugte Dokumente werden nicht gespeichert: sie entstehen bei jedem Download
neu aus den Daten in `app.db`. Ein Backup der Datenbank ist damit ein
vollständiges Backup.

Fehlt `data/.env` beim Start, erzeugt die Anwendung beide Schlüssel selbst und
schreibt sie dorthin. Eine vorhandene Datei wird nie verändert.

> **Diese beiden Schlüssel sichern.** Der `ENCRYPTION_KEY` entschlüsselt die in
> `app.db` gespeicherten DFB-Zugangsdaten, der `JWT_SECRET_KEY` hält bestehende
> Logins gültig. Gehen sie verloren, muss jeder Nutzer seine DFB-Zugangsdaten
> neu eintragen — die restlichen Daten bleiben erhalten.

Ein Backup ist damit ein Kopieren des Ordners:

```bash
docker compose stop
tar -czf spesenfuchs-backup-$(date +%F).tar.gz data
docker compose start
```

Einzelne Pfade lassen sich per Umgebungsvariable verlegen (`DATA_DIR`,
`ENV_FILE`, `DATABASE_PATH`, `OUTPUT_DIR`); nötig ist das im Normalfall nicht.
`OUTPUT_DIR` zeigt nur noch auf die alten Session-Ordner und wird ausschließlich
für die einmalige Übernahme beim Versionssprung gebraucht.

`ALLOW_SCHEDULER_TRIGGER=1` gibt den manuellen Sammel-Abruf über
`POST /api/scheduler/trigger` frei. Er ist standardmäßig gesperrt, weil er den
nächtlichen Lauf für **alle** Konten startet und das Projekt keine Rollen kennt.

Zwei Stellschrauben für den Download-Pfad: `PDF_MAX_CONCURRENCY` (Standard 2)
begrenzt, wie viele LibreOffice-Prozesse gleichzeitig laufen dürfen — jeder
belegt 150–300 MB. `MAX_BULK_DOWNLOAD` (Standard 50) begrenzt, wie viele Spiele
in einem ZIP stecken dürfen.

## Karte

Die Karte bei den Fahrtkosten braucht Koordinaten, DFBnet liefert aber nur
Anschriften im Klartext. Sie werden beim ersten Öffnen einer Karte einmalig
aufgelöst und danach dauerhaft in `app.db` behalten — dieselbe Spielstätte und
dieselben Kollegen tauchen über eine Saison hinweg immer wieder auf, sodass es
insgesamt bei einer Handvoll Abfragen bleibt. Wird nie eine Karte geöffnet,
wird auch nie eine Adresse verschickt.

Voreingestellt sind die öffentlichen Dienste von OpenStreetMap. Beide lassen
sich auf eine eigene Instanz umstellen:

| Variable | Standard | Zweck |
| --- | --- | --- |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Adresse → Koordinate |
| `GEOCODER_MIN_INTERVAL` | `1.0` | Mindestabstand zwischen zwei Abfragen in Sekunden |
| `MAP_TILE_URL` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Kartenbilder, vom Browser geladen |
| `MAP_TILE_ATTRIBUTION` | OpenStreetMap-Mitwirkende | Quellenangabe in der Karte |

Der Mindestabstand hält die Nutzungsbedingungen des öffentlichen Nominatim ein
(eine Abfrage pro Sekunde aus einem einzelnen Strang). Wer selbst hostet, darf
ihn herunterdrehen.

Ein eigener Geocoder lohnt sich für diese Datenmenge kaum: ein Nominatim mit
ganz Deutschland belegt 50–108 GB und importiert stundenlang, ein
Photon-Index für Deutschland sind 9 GB Download. Dem stehen geschätzt hundert
Abfragen über die Lebensdauer eines Kontos gegenüber. Wer es dennoch will,
setzt `NOMINATIM_URL` auf den eigenen Dienst — im Code ändert sich nichts, und
zu einem anderen Dienst aufgelöste Adressen werden getrennt gespeichert.

## Aktualisieren

```bash
docker compose pull && docker compose up -d
```

Schemaänderungen laufen beim Start automatisch. Vor dem ersten Schritt legt die
Anwendung eine Kopie von `app.db` daneben (`app.db.v<version>.<zeit>.bak`).
Beim Sprung auf die datenbankgestützte Version werden die Spiele aus den alten
`data/output/`-Ordnern einmalig übernommen; danach wird das Verzeichnis nicht
mehr gebraucht und kann nach einer Sicherung gelöscht werden.

Der `data`-Ordner wird dabei nicht angefasst.

## Umstieg vom alten Setup

Das Projekt hieß früher *DFB Spesen Generator*; Image, Service und Container
heißen jetzt `spesenfuchs`. Eine laufende Installation zieht weiter das alte
Image, bis ihre `docker-compose.yml` auf
`ghcr.io/janvogt06/spesenfuchs` umgestellt ist. Der alte Container muss dabei
einmal weichen, weil sich der `container_name` geändert hat:

```bash
docker compose down          # entfernt den Container "dfb-spesen-generator"
curl -fO https://raw.githubusercontent.com/JanVogt06/dfb-spesen-generator/main/docker-compose.yml
docker compose pull && docker compose up -d
```

Der `data`-Ordner bleibt davon unberührt — Datenbank, Secrets und erzeugte
Dokumente überleben die Umbenennung.

Früher lief die Anwendung aus einem Checkout mit `docker compose up -d --build`
und drei einzelnen Bind-Mounts (`./app.db`, `./.env`, `./output`). Die
vorhandenen Daten wandern einmalig in den `data`-Ordner:

```bash
cd /pfad/zum/alten/verzeichnis

# 1. Sicherung, bevor irgendetwas bewegt wird
tar -czf ~/spesenfuchs-backup-$(date +%F).tar.gz app.db .env output

# 2. Alten Container stoppen (das Image bleibt vorerst liegen)
docker compose down

# 3. Daten in den neuen Ordner verschieben
mkdir -p data
mv app.db .env output data/

# 4. Neue docker-compose.yml einsetzen (siehe oben), dann
docker compose pull && docker compose up -d
```

Sollte `data/app.db` einmal fehlen, während `app.db` noch daneben liegt, benutzt
die Anwendung weiterhin die alte Datei und schreibt eine Warnung ins Log — ein
halb migriertes Verzeichnis startet also nicht mit leerer Datenbank.

## Releases

Ein Tag, der mit `v` beginnt, baut ein Multi-Architektur-Image (`linux/amd64`
und `linux/arm64`), veröffentlicht es unter
`ghcr.io/janvogt06/spesenfuchs` als `<version>`, `<major>.<minor>` und
`latest` und legt daraus ein GitHub-Release an:

```bash
git tag v1.2.0 && git push origin v1.2.0
```

Der Workflow lässt sich unter *Actions* auch ohne Tag starten (`workflow_dispatch`),
etwa um nur den Image-Bau zu prüfen; das Ergebnis landet dann als `edge` und ohne
Release. Der arm64-Teil wird auf dem Runner emuliert und dauert deutlich länger
als amd64 — bei einem Testlauf lohnt es, in der Eingabe `linux/amd64` zu setzen.

## Entwicklung

Backend und Frontend getrennt, ohne Docker:

```bash
pip install -r requirements.txt
playwright install chromium
python src/main.py                    # API auf :8001

cd frontend && npm install && npm run dev   # Oberfläche auf :5173
```

Ohne gesetzte Umgebungsvariablen liegt `DATA_DIR` auf `./data` im Projekt — die
lokale Entwicklung benutzt also dieselbe Struktur wie der Server. `data/` ist in
`.gitignore`, für die Vorlage der Secrets siehe [.env.example](.env.example).

Die DOCX→PDF-Konvertierung braucht LibreOffice; im Container ist
`libreoffice-writer` enthalten, lokal muss es installiert sein — ohne
LibreOffice funktioniert nur der DOCX-Download.

Das DOCX entsteht in rund 25 ms, die PDF-Konvertierung kostet 2–6 Sekunden.
Der Kaltstart von LibreOffice dominiert dabei, deshalb ist ein Sammel-Download
mehrerer Spiele kaum teurer als ein einzelner.

## Layout

| Pfad | Zweck |
| --- | --- |
| `src/main.py` | Einstiegspunkt und Scraping-Ablauf |
| `src/api/` | FastAPI-Endpunkte und Authentifizierung |
| `src/core/config.py` | Pfade und Secrets (`DATA_DIR` und Ableitungen) |
| `src/scraper/` | DFB.net-Scraper (Playwright) |
| `src/generator/` | DOCX-Erzeugung (im Speicher) und Spesenberechnung |
| `src/scheduler/` | Nächtlicher Abruf um 3:00 (Europe/Berlin) |
| `src/db/` | SQLite-Zugriff; `migrations.py` führt das Schema über `PRAGMA user_version` nach |
| `frontend/` | React-Oberfläche (Vite), wird ins Image gebaut |
| `Dockerfile` | Image mit Frontend-Build, Playwright und LibreOffice |
| `docker-compose.yml` | Service, Port, Volume und Health Check — ohne Build, direkt server-tauglich |
| `docker-compose.override.yml` | Ergänzt lokal `build: .`, wird von Compose automatisch geladen |
| `.github/workflows/release.yml` | Image-Bau und Release beim Tag-Push |

## Lizenz

MIT — siehe [LICENSE](LICENSE).
