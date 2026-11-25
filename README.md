# Spesenfuchs

**Referee expense automat.** Automatically creates referee expense claims from
your own DFB.net assignments. Store your DFB.net credentials once, and from then
on the application fetches your current assignments into the database every
night. The claim as DOCX or PDF is generated on download — including travel
costs, if the kilometres have been entered in the calculator. On the same
fetch, the application also reads your own master data from DFB.net and shows
it in the *Stammdaten* (master data) tab; the personal details below it are
stored encrypted in the database. The *Saison* (season) tab shows all matches
you officiated per season with result, card statistics and crew, plus
assignment balance and training evenings. The *Statistik* (statistics) tab
shows your own expenses and travel costs per season (missing travel costs are
estimated and marked as estimated) and a map of all venues where you have
already officiated. It counts the matches DFBnet lists as officiated – the
same as the *Saison* tab – and takes rates, entered kilometres and venues from
the stored appointments; for matches before your first fetch the rate follows
from the league.
The *Beobachtungen* (observations) tab shows your own grades from referee
observations (men's football, from the season of "Schiedsrichter seit", i.e.
referee since) and — for those who have it — from the Schiri-Portal (DFB
youth talent programme): per season an average as referee, as assistant and as
fourth official, and for men's football additionally per league level.
Completed seasons are read only once — the current season and any season whose
data is incomplete are fetched again. Next to the travel costs of a match
there is a map showing the addresses of the assigned officials and the venue —
so when entering the kilometres you can see who travels how far.

For cup and friendly matches, the rate does not depend on the league level of
the match itself but on that of the clubs involved — which the assignment does
not state. For men's football, the application therefore fetches the tables of
the Thüringenliga and the three Landesklasse groups from FUSSBALL.DE every
night; the *Ligen* (leagues) tab shows them. If a team cannot be matched
unambiguously, or a team playing at supra-regional level is involved, the
expense field stays empty rather than guessed.

The interface has five main tabs: *Übersicht* (overview), *Spiele* (matches)
with all assignments – upcoming and past, searchable, each match with a claim
to download –, *Saison*, *Statistik* and *Beobachtungen*. Behind *Mehr* (more) are *Ligen*,
*Stammdaten*, *Einstellungen* (settings) and *Fehler melden* (report a bug).
Next to the *Aktualisieren* (refresh) button at the top right it shows when
DFB.net was last read.

Self-hosted: one container, one `docker-compose.yml`, one `data` folder.

## Quick start

### On a server, without a checkout

The source code is not needed — one file and one folder are enough. The
`docker-compose.yml` of this repository is server-ready as it is; it
intentionally contains no build instruction:

```bash
mkdir -p spesenfuchs/data && cd spesenfuchs
curl -fO https://raw.githubusercontent.com/JanVogt06/dfb-spesen-generator/main/docker-compose.yml
docker compose pull && docker compose up -d
```

Afterwards the interface is reachable at http://localhost:8001, and from other
devices on the network via the host's address, for example
`http://192.168.1.20:8001`.

The file pulls `latest`. If you want to decide yourself when to update, pin the
version — either by hand or right when setting up:

```bash
sed -i 's/:latest/:1.2.1/' docker-compose.yml
```

### From a checkout

```bash
docker compose up -d --build
```

In a checkout, next to the Compose file there is a
[`docker-compose.override.yml`](docker-compose.override.yml) that Docker Compose
loads automatically and that adds `build: .`. That is why the same command
builds from source here, while on the server, without this file, the finished
image is used — one configuration, two uses.

### Changing the port

Without touching the Compose file:

```bash
SPESEN_PORT=9000 docker compose up -d
```

If the interface should only be reachable from the host itself (for example
because a reverse proxy sits in front of it), change the port mapping to
`"127.0.0.1:${SPESEN_PORT:-8001}:8001"`.

## Data and secrets

Everything mutable lives in the container under `/data` and thus in the `data`
folder next to the Compose file — it survives restarts and updates:

| Path | Contents |
| --- | --- |
| `data/.env` | `JWT_SECRET_KEY` and `ENCRYPTION_KEY` |
| `data/app.db` | Users, own master data, matches, officials, travel costs, matches officiated per season, own observation grades, resolved map addresses, league tables, fetch log, login and download log |
| `data/logs/spesenfuchs.log` | Log of the application and the nightly fetches, rotated at 5 MB (four older files are kept) |

Generated documents are not stored: they are created anew on every download
from the data in `app.db`. A backup of the database is therefore a complete
backup.

If `data/.env` is missing at startup, the application generates both keys itself
and writes them there. An existing file is never modified.

> **Back up these two keys.** The `ENCRYPTION_KEY` decrypts the DFB credentials
> stored in `app.db`, and the `JWT_SECRET_KEY` keeps existing logins valid. If
> they are lost, every user has to re-enter their DFB credentials — the rest of
> the data is kept.

A backup is thus just a copy of the folder:

```bash
docker compose stop
tar -czf spesenfuchs-backup-$(date +%F).tar.gz data
docker compose start
```

Individual paths can be relocated via environment variable (`DATA_DIR`,
`ENV_FILE`, `DATABASE_PATH`, `OUTPUT_DIR`, `LOG_FILE`); normally this is not
necessary. `OUTPUT_DIR` only points to the old session folders and is used
exclusively for the one-time migration on the version jump.

`ALLOW_SCHEDULER_TRIGGER=1` enables the manual bulk fetch via
`POST /api/scheduler/trigger`. It is blocked by default because it starts the
nightly run for **all** accounts and the project has no roles.

Two tuning knobs for the download path: `PDF_MAX_CONCURRENCY` (default 2)
limits how many LibreOffice processes may run at the same time — each takes
150–300 MB. `MAX_BULK_DOWNLOAD` (default 50) limits how many matches may go
into one ZIP.

## Installing as an app

The interface can be put on the home screen as an app (PWA). On Android and in
Chrome or Edge on desktop, there is an "App installieren" (install app) button
for this on the overview and in the *Einstellungen*. On the iPhone, Apple does
not allow an install dialog; there the same button unfolds the steps in Safari
(*Teilen* (share) → *Zum Home-Bildschirm* (add to home screen)).

**HTTPS** is required: over `http://192.168.x.x:8001` no browser offers
installation, but it does over a reverse proxy or Cloudflare Tunnel with a
certificate. Only `localhost` is exempt.

The service worker (`frontend/public/sw.js`) caches only the shell of the
interface, so the app also starts without a network. API responses never end up
in its cache — they contain addresses and phone numbers. Page requests always go
to the network first, so an update reaches the installed app on its next open
by itself. The backend serves `sw.js` and the manifest with
`Cache-Control: no-cache`, so that even a CDN in front does not hold on to an
old worker.

## Map

The maps need coordinates, but DFBnet only delivers addresses as plain text.
They are resolved once when a map is first opened and then kept permanently in
`app.db` — the same venue and the same colleagues show up again and again over
a season, so it stays at a handful of queries overall. If no map is ever
opened, no address is ever sent.

For travel costs, the application suggests kilometres: for each person the
round trip alone and, where it saves kilometres, carpools – who drives, whom
they pick up on the way, passengers with 0 km. Next to that comes the best
meeting point on the driver's way: the others drive there in their own cars
and continue together, each claiming what they drove themselves. In kilometres
a pick-up is never shorter, but the driver stays on the main road; the meeting
point is named after the nearest village (one reverse lookup at the geocoder,
cached in `app.db`) and links to OpenStreetMap. One click transfers the values
into the fields; saving works as usual. To do this, it asks a route planner for
the road kilometres between the places of residence and the venue; only
coordinates are transmitted. The venue's coordinate is supplied by DFBnet
itself, which is more accurate than an address search. The statistics in the
*Statistik* tab use the same planning to estimate travel costs where none have
been entered: per match the suggestion with the fewest total kilometres for
the whole crew, and from it your own share – the whole trip as driver, 0 km as
passenger, otherwise the round trip alone. Matches without a stored
appointment (no crew known) are estimated as a trip alone. Each route, too,
is only asked for once and then kept in `app.db`; evaluations over many matches
only query for a few seconds per call and fetch the rest on the next one.

The public OpenStreetMap services are preconfigured. All of them can be
switched to your own instance:

| Variable | Default | Purpose |
| --- | --- | --- |
| `NOMINATIM_URL` | `https://nominatim.openstreetmap.org` | Address → coordinate |
| `GEOCODER_MIN_INTERVAL` | `1.0` | Minimum interval between two queries in seconds |
| `ROUTING_URL` | `https://routing.openstreetmap.de/routed-car` | Road kilometres (OSRM, matrix query) |
| `ROUTING_MIN_INTERVAL` | `1.0` | Minimum interval between two route queries in seconds |
| `MAP_TILE_URL` | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | Map tiles, loaded by the browser |
| `MAP_TILE_ATTRIBUTION` | OpenStreetMap contributors | Attribution shown in the map |

The minimum interval complies with the terms of use of the public Nominatim
(one query per second from a single thread). If you self-host, you may turn it
down.

Your own geocoder is hardly worthwhile for this amount of data: a Nominatim
with all of Germany takes up 50–108 GB and imports for hours, and a Photon
index for Germany is a 9 GB download. Against that stand an estimated hundred
queries over the lifetime of an account. If you still want it, set
`NOMINATIM_URL` to your own service — nothing changes in the code, and
addresses resolved by a different service are stored separately.

## Leagues and the expenses of cup and friendly matches

The TFV expense regulations tie the rate for cup matches to the highest-ranked
team involved (§2 para. 3) and for friendly matches to the league level of the
host (§2 para. 4). But in the assignment, DFBnet only states "Kreispokal"
(district cup) or "Kreisfreundschaftsspiele" (district friendlies) — the clubs'
league is not there.

That is why the application fetches the FUSSBALL.DE tables every night before
the DFBnet fetch: Thüringenliga and Landesklasse as the basis for the rates,
plus Regionalliga Nordost and NOFV-Oberliga, to **detect** supra-regional
involvement. Nothing is billed from supra-regional leagues — if such a team is
involved, the field stays empty.

FUSSBALL.DE's group identifiers change with every season and are therefore
nowhere in the code. They are looked up starting from a club that your own
assignments already know to play in the league in question. Anyone who has never
had a match in the Verbandsliga or Landesklasse gets no tables — and no rates
for cup and friendly matches.

Matching is done via club names and **team number**. The number is not
negotiable: the third team of FC Saalfeld plays Kreisliga, the first the
Verbandsliga. If a match remains ambiguous or yields nothing, the expense field
stays empty. An empty field is filled in by the referee in the dressing room; a
plausible-looking wrong amount goes unnoticed.

This covers **men's football**. For girls' youth football there is nothing to
look up (€20 in all match and age classes), nor for veterans (Alte Herren) at
district level (one rate for all district groups). For boys' youth football and
women, cup and friendly matches remain without a rate: that would require the
league tables of the same team type, and a club without a men's team would not
appear in any of them.

## Login and credentials

After **five wrong passwords** in a row, login for that account is locked for
15 minutes, even with the correct password. From the third failed attempt on,
the login says how many attempts remain. Counting is per email address, not per
IP: behind a Cloudflare Tunnel all requests come from the same address.
Addresses without an account are counted the same way, so that the lock does not
reveal who is registered. The counters live in `app.db` and survive a restart.

If DFBnet rejects the stored credentials, usually because DFBnet has demanded a
new password, the application records this with the date. Until new credentials
are saved or a fetch succeeds again, a red notice appears on every page, and
*Mehr* as well as *Einstellungen* within it carry a red dot.

## Reporting bugs

The entry of the same name under *Mehr* (*Fehler melden*) sends a report by
email. Without an outgoing mail server the form is visible but says that nothing
can be sent — no report is silently discarded.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | – | Outgoing mail server; without it sending is off |
| `SMTP_PORT` | `587` | `465` speaks TLS immediately, otherwise STARTTLS |
| `SMTP_USER` / `SMTP_PASSWORD` | – | Mailbox credentials |
| `SMTP_FROM` | `SMTP_USER` | Sender address |
| `BUGREPORT_EMPFAENGER` | `spesen-generator@jan-vogt.dev` | Recipient of the reports |

The mail's sender is the outgoing mail server's address, and the reporter's
address goes in `Reply-To` — the other way round, every recipient with SPF or
DMARC checks would reject the message.

## Updating

```bash
docker compose pull && docker compose up -d
```

Schema changes run automatically at startup. Before the first step, the
application places a copy of `app.db` next to it (`app.db.v<version>.<time>.bak`).
On the jump to the database-backed version, the matches from the old
`data/output/` folders are taken over once; after that the directory is no
longer needed and can be deleted after a backup.

The `data` folder is not touched in the process.

## Migrating from the old setup

The project used to be called *DFB Spesen Generator*; image, service and
container are now called `spesenfuchs`. A running installation keeps pulling the
old image until its `docker-compose.yml` is switched to
`ghcr.io/janvogt06/spesenfuchs`. The old container has to make way once,
because the `container_name` has changed:

```bash
docker compose down          # removes the container "dfb-spesen-generator"
curl -fO https://raw.githubusercontent.com/JanVogt06/dfb-spesen-generator/main/docker-compose.yml
docker compose pull && docker compose up -d
```

The `data` folder remains untouched by this — database, secrets and generated
documents survive the renaming.

Previously the application ran from a checkout with `docker compose up -d --build`
and three individual bind mounts (`./app.db`, `./.env`, `./output`). The
existing data moves into the `data` folder once:

```bash
cd /path/to/old/directory

# 1. Backup before anything is moved
tar -czf ~/spesenfuchs-backup-$(date +%F).tar.gz app.db .env output

# 2. Stop the old container (the image stays around for now)
docker compose down

# 3. Move the data into the new folder
mkdir -p data
mv app.db .env output data/

# 4. Put the new docker-compose.yml in place (see above), then
docker compose pull && docker compose up -d
```

If `data/app.db` should ever be missing while `app.db` still sits next to it,
the application keeps using the old file and writes a warning to the log — so a
half-migrated directory does not start with an empty database.

## Releases

A tag beginning with `v` builds a multi-architecture image (`linux/amd64` and
`linux/arm64`), publishes it at `ghcr.io/janvogt06/spesenfuchs` as `<version>`,
`<major>.<minor>` and `latest`, and creates a GitHub release from it:

```bash
git tag v1.2.0 && git push origin v1.2.0
```

The version number in the code does **not** have to be bumped along: the
workflow passes the tag into the image as the build argument `APP_VERSION`, and
the health endpoint, the subject of the bug reports and the User-Agent towards
FUSSBALL.DE and Nominatim report exactly this value. A run from source falls
back to the constant in [`src/core/config.py`](src/core/config.py) — a manual
build is not a release.

The workflow can also be started without a tag under *Actions*
(`workflow_dispatch`), for example to only check the image build; the result
then lands as `edge` and without a release. The arm64 part is emulated on the
runner and takes considerably longer than amd64 — for a test run it is worth
setting `linux/amd64` in the input.

## Development

Backend and frontend separately, without Docker:

```bash
pip install -r requirements.txt
playwright install chromium
python src/main.py                    # API on :8001

cd frontend && npm install && npm run dev   # interface on :5173
```

Without any environment variables set, `DATA_DIR` points to `./data` in the
project — local development thus uses the same structure as the server. `data/`
is in `.gitignore`; for the template of the secrets see
[.env.example](.env.example).

### Tests

```bash
pip install -r requirements-dev.txt
python -m pytest                      # backend

cd frontend && npm test               # frontend (Vitest)
npm run lint && npx tsc -b
```

The backend tests run against a throwaway database in a temporary folder (see
[`tests/conftest.py`](tests/conftest.py)) and never touch `data/`. DFBnet,
FUSSBALL.DE, Nominatim, SMTP and LibreOffice are mocked, so nothing goes out to
the network and no browser starts. Suspected, not yet fixed bugs are marked as
`xfail(strict=True)` in the tests. As soon as one is fixed, the test fails until
the marker is removed.

The workflow [`tests.yml`](.github/workflows/tests.yml) runs both on every push
and pull request. The release workflow calls it beforehand and builds no image
as long as a test is red.

The DOCX→PDF conversion needs LibreOffice; the container includes
`libreoffice-writer`, locally it has to be installed — without LibreOffice only
the DOCX download works.

The DOCX is created in about 25 ms, the PDF conversion costs 2–6 seconds.
LibreOffice's cold start dominates, which is why a bulk download of several
matches costs hardly more than a single one.

## Layout

| Path | Purpose |
| --- | --- |
| `src/main.py` | Entry point and scraping flow |
| `src/api/` | FastAPI endpoints and authentication |
| `src/core/config.py` | Paths and secrets (`DATA_DIR` and derivatives) |
| `src/scraper/` | DFB.net scraper (Playwright) |
| `src/generator/` | DOCX generation (in memory) and expense calculation |
| `src/scheduler/` | Nightly fetch at 3:00 (Europe/Berlin) |
| `src/db/` | SQLite access; `migrations.py` migrates the schema via `PRAGMA user_version` |
| `frontend/` | React interface (Vite), built into the image |
| `Dockerfile` | Image with frontend build, Playwright and LibreOffice |
| `docker-compose.yml` | Service, port, volume and health check — without build, directly server-ready |
| `docker-compose.override.yml` | Adds `build: .` locally, loaded automatically by Compose |
| `.github/workflows/release.yml` | Image build and release on tag push |
| `.github/workflows/tests.yml` | pytest, ESLint, TypeScript and Vitest on every push |
| `tests/` | Backend tests (pytest) |

## License

MIT — see [LICENSE](LICENSE).
