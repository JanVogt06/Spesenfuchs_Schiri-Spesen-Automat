"""
Liest die Spielberichte der eigenen Spiele - ausschliesslich lesend.

Zwei DFBnet-Teile sind beteiligt:

1. "Spielberichte -> Einsatzplan" (/spielplus/mod_sbo) ist ein altes
   Server-Formular wie die Beobachtungsmodule. Es listet je Saison alle
   Spiele, in denen man angesetzt war, mit einem Link auf den Bericht. Die
   Saison wird ueber eine Auswahlliste gewechselt, die die Seite neu
   abschickt. Die Liste zeigt alle Treffer auf einer Seite.

2. Der Bericht selbst ist eine eigene Angular-App (/sbo-mobile/v2), die
   alles aus einer JSON-Schnittstelle laedt. Diese App ist EDITIERBAR -
   Torschuetzen, Dokumente, Kontrollen haben Knoepfe. Deshalb wird in ihr
   nichts angeklickt. Gelesen wird direkt ueber dieselben GET-Abrufe, die die
   App beim Oeffnen macht.

Die Schnittstelle authentisiert ueber ein Cookie, das erst entsteht, wenn
die App einmal geladen wurde. Vorher antwortet sie mit 410. Deshalb wird sie
einmal ueber den Bericht eines Spiels geoeffnet - genau so, wie es ein Klick
auf das Symbol im Einsatzplan tut.

Sicherheitsnetz: Jeder Abruf geht durch _pruefe_pfad. Erlaubt sind nur die
drei Lese-Pfade und der Dokument-Download, und nur als GET. Alles, was die
App zum Speichern, Bestaetigen, Zurueckziehen oder Loeschen benutzt, ist ein
POST auf andere Pfade und kann hier gar nicht entstehen.

Gelesen werden nur Berichte von Spielen, die vorbei sind UND deren Bericht
laut Einsatzplan schon freigegeben ist. Der Abruf .../report/<Spiel>/create
liefert die Berichts-ID; die App ruft ihn bei jedem Oeffnen auf und er gibt
fuer ein Spiel mit Bericht nur den vorhandenen zurueck. Fuer ein Spiel ohne
Bericht wird er nie aufgerufen.
"""
import base64
import re
from datetime import date, datetime
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page

from utils.logger import setup_logger

logger = setup_logger("spielberichte")

_ZEITLIMIT_MS = 45000

_BASIS = "https://www.dfbnet.org"
_EINSATZPLAN_URL = f"{_BASIS}/spielplus/mod_sbo/webflow.do?event=SEARCH_REFEREE_MATCHES"
_APP_URL = f"{_BASIS}/sbo-mobile/v2/#/match-report/report/{{}}?dmg_company=DFBNET"
_API = "/sbo-mobile/v2/oauth/"

# Die einzigen Pfade, die abgerufen werden duerfen (relativ zu _API).
_ID = r"[A-Za-z0-9]{10,64}"
_ERLAUBT = [
    re.compile(rf"report/{_ID}/create"),
    re.compile(rf"report/{_ID}/matches"),
    re.compile(rf"match/{_ID}/details"),
    re.compile(rf"match/{_ID}/documents/{_ID}"),
]

# Status-Symbole im Einsatzplan, die einen fertigen Bericht anzeigen:
# "Spiel ist freigegeben", "Schiedsrichterfreigabe", "Prueferfreigabe".
# "Spiel ist erfolgt" allein heisst: der Bericht wird noch ausgefuellt.
_FREIGEGEBEN = {"spiel_anerkannt", "staffel_view", "staffel_wettbewerb"}
# Geplant, Schiri geplant, verlegt - dazu gibt es (noch) keinen Bericht.
_NICHT_LESEN = {"spiel_geplant", "spiel_schiri", "spiel_historisch"}

# Ereignistypen der Bericht-App (aus deren Quelltext, *_TYPE_ID)
EREIGNIS_TYPEN = {
    1: "wechsel",
    2: "gelb",
    3: "rot",
    4: "gelbrot",
    7: "tor",
    8: "eigentor",
    9: "elfmetertor",
    10: "elfmeterschiessen",
    11: "unsportlichkeit",
    13: "zeitstrafe",
}

# Kurzzeichen der Schiedsrichter-Rollen nach rolePosition
_ROLLEN = {1: "SR", 2: "SRA1", 3: "SRA2", 4: "4OF"}


# ---------------------------------------------------------------- Einsatzplan

_EINSATZPLAN_LINK_JS = """
    () => {
        for (const a of document.querySelectorAll('a[href]')) {
            const url = new URL(a.href, location.href);
            if (url.pathname.endsWith('/mod_sbo/webflow.do')
                    && url.searchParams.get('event') === 'SEARCH_REFEREE_MATCHES') {
                return url.href;
            }
        }
        return null;
    }
"""

_SAISONS_JS = """
    () => {
        const auswahl = document.querySelector('select.dfb-Dropdown-nativeSelect');
        if (!auswahl) return null;
        return [...auswahl.options].map((o) => o.value).filter((v) => v);
    }
"""

_GEWAEHLTE_SAISON_JS = """
    () => {
        const feld = document.querySelector('input[name="kontext.seasonId"]');
        return feld ? feld.value : null;
    }
"""

# Die Liste: Gruppenzeilen (eine Zelle, "Herren, Regionalliga ...") stehen
# vor ihren Spielen. Eine Spielzeile hat: Symbol mit Link | leer | Nr. |
# "So. 22.11.2026 13:30" | Spieltag | Heim | - | Gast | Ergebnis | Status.
_LISTE_JS = """
    () => {
        const zeilen = [];
        let gruppe = '';
        const text = (el) => (el ? el.textContent.replace(/\\s+/g, ' ').trim() : '');
        const symbol = (img) => img.src.split('/').pop().replace(/\\.gif$/, '');

        for (const tr of document.querySelectorAll('tr[data-index]')) {
            const zellen = [...tr.children].filter((c) => c.tagName === 'TD');
            if (zellen.length === 1) {
                gruppe = text(zellen[0]);
                continue;
            }
            if (zellen.length < 10) continue;

            const termin = /(\\d{2})\\.(\\d{2})\\.(\\d{4})\\s*(\\d{1,2}:\\d{2})?/.exec(text(zellen[3]));
            if (!termin) continue;

            const link = tr.querySelector('a[href*="#/match-report/report/"]');
            const id = link
                ? (/#\\/match-report\\/report\\/([A-Za-z0-9]+)/.exec(link.getAttribute('href')) || [])[1]
                : null;

            zeilen.push({
                gruppe,
                nummer: text(zellen[2]),
                datum: `${termin[3]}-${termin[2]}-${termin[1]}`,
                uhrzeit: termin[4] || '',
                spieltag: text(zellen[4]),
                heim: text(zellen[5]),
                gast: text(zellen[7]),
                ergebnis: text(zellen[8]).replace(/\\s+/g, ''),
                status: [...zellen[zellen.length - 1].querySelectorAll('img')].map(symbol),
                dfb_spiel_id: id || null,
            });
        }
        return zeilen;
    }
"""


def finde_einsatzplan(page: Page) -> str:
    """Der Link auf den Einsatzplan aus dem DFBnet-Menue, sonst die bekannte URL."""
    try:
        url = page.evaluate(_EINSATZPLAN_LINK_JS)
    except Exception:
        url = None
    return url or _EINSATZPLAN_URL


def oeffne_einsatzplan(page: Page, url: str) -> List[str]:
    """Oeffnet den Einsatzplan und gibt die angebotenen Saisons zurueck (neueste zuerst)."""
    page.goto(url, wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS)
    page.locator("select.dfb-Dropdown-nativeSelect").wait_for(state="attached", timeout=15000)
    saisons = page.evaluate(_SAISONS_JS)
    if saisons is None:
        raise RuntimeError(f"Keine Saisonauswahl auf {urlparse(page.url).path}")
    return saisons


def waehle_saison(page: Page, saison: str) -> None:
    """
    Waehlt eine Saison wie ein Mensch: Auswahl aufklappen, Eintrag anklicken.

    Die Auswahl ist ein eigenes Dropdown-Bauteil ueber einem versteckten
    <select>; der Klick auf den Eintrag schickt das Formular ab und laedt die
    Seite neu. Danach muss das versteckte Feld die Saison tragen - sonst
    zeigte die Liste womoeglich noch die vorige.
    """
    if page.evaluate(_GEWAEHLTE_SAISON_JS) == saison:
        return

    page.locator("input.dfb-Dropdown-combobox").first.click()
    eintrag = page.locator(f'li[role="option"][data-value="{saison}"]').first
    eintrag.wait_for(state="visible", timeout=10000)

    with page.expect_navigation(wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS):
        eintrag.click()

    page.locator("select.dfb-Dropdown-nativeSelect").wait_for(state="attached", timeout=15000)
    gewaehlt = page.evaluate(_GEWAEHLTE_SAISON_JS)
    if gewaehlt != saison:
        raise RuntimeError(f"Saison {saison} gewaehlt, angezeigt wird {gewaehlt!r}")


def lies_einsatzplan(page: Page) -> List[Dict]:
    """Alle Spielzeilen der angezeigten Saison."""
    return page.evaluate(_LISTE_JS) or []


def ist_lesbar(zeile: Dict, heute: Optional[date] = None) -> bool:
    """
    Ob zu einer Zeile ein Bericht gelesen werden darf.

    Nur Einzelspielberichte (Sammelberichte von Turnieren haben einen anderen
    Link), nur vergangene Spiele, nur mit freigegebenem Bericht.
    """
    if not zeile.get("dfb_spiel_id"):
        return False

    heute = heute or date.today()
    try:
        if date.fromisoformat(zeile.get("datum") or "") >= heute:
            return False
    except ValueError:
        return False

    status = set(zeile.get("status") or [])
    return bool(status & _FREIGEGEBEN) and not (status & _NICHT_LESEN)


def wartet_auf_freigabe(zeile: Dict, heute: Optional[date] = None) -> bool:
    """
    Ein vergangenes Spiel, dessen Bericht kommen wird, aber noch nicht freigegeben ist.

    Solange es so eines gibt, ist die Saison nicht fertig gelesen.
    """
    if not zeile.get("dfb_spiel_id") or ist_lesbar(zeile, heute):
        return False
    status = set(zeile.get("status") or [])
    return "spiel_historisch" not in status


# ----------------------------------------------------------- Bericht-App (JSON)

def _pruefe_pfad(pfad: str) -> str:
    if not any(muster.fullmatch(pfad) for muster in _ERLAUBT):
        raise ValueError(f"Abruf {pfad!r} ist nicht freigegeben")
    return _API + pfad


# Laeuft im Kontext der Bericht-App. Ausdruecklich method GET, kein Body.
_HOLE_JSON_JS = """
    async (url) => {
        const antwort = await fetch(url, {method: 'GET', credentials: 'include',
                                          headers: {Accept: 'application/json'}});
        if (!antwort.ok) return {status: antwort.status};
        return {status: antwort.status, daten: await antwort.json()};
    }
"""

_HOLE_DATEI_JS = """
    async (url) => {
        const antwort = await fetch(url, {method: 'GET', credentials: 'include',
                                          headers: {Accept: 'application/octet-stream'}});
        if (!antwort.ok) return {status: antwort.status};
        const puffer = new Uint8Array(await antwort.arrayBuffer());
        let binaer = '';
        for (let i = 0; i < puffer.length; i += 0x8000) {
            binaer += String.fromCharCode.apply(null, puffer.subarray(i, i + 0x8000));
        }
        return {
            status: antwort.status,
            typ: antwort.headers.get('content-type') || '',
            inhalt: btoa(binaer),
        };
    }
"""


class SitzungAbgelaufen(RuntimeError):
    """Die Schnittstelle will eine neu geladene App (410/401/403)."""


def _hole_json(page: Page, pfad: str):
    ergebnis = page.evaluate(_HOLE_JSON_JS, _pruefe_pfad(pfad))
    status = ergebnis.get("status")
    if status in (401, 403, 410):
        raise SitzungAbgelaufen(f"{status} auf {pfad.split('/')[0]}")
    if status != 200:
        raise RuntimeError(f"HTTP {status} auf {pfad.split('/')[0]}/…/{pfad.rsplit('/', 1)[-1]}")
    return ergebnis.get("daten")


def hole_dokument(page: Page, bericht_spiel_id: str, dokument_id: str) -> bytes:
    """Laedt ein angehaengtes Dokument (meist PDF) herunter."""
    ergebnis = page.evaluate(
        _HOLE_DATEI_JS, _pruefe_pfad(f"match/{bericht_spiel_id}/documents/{dokument_id}")
    )
    status = ergebnis.get("status")
    if status in (401, 403, 410):
        raise SitzungAbgelaufen(f"{status} beim Dokument")
    if status != 200:
        raise RuntimeError(f"Dokument nicht geladen: HTTP {status}")
    return base64.b64decode(ergebnis.get("inhalt") or "")


def oeffne_bericht_app(page: Page, dfb_spiel_id: str) -> None:
    """
    Laedt die Bericht-App einmal ueber den Bericht eines (freigegebenen) Spiels.

    Gewartet wird auf deren ersten Datenabruf - erst danach ist das Cookie
    gesetzt, mit dem die Schnittstelle antwortet. Angeklickt wird nichts.
    """
    with page.expect_response(
        lambda antwort: _API in antwort.url and antwort.url.endswith("/info"),
        timeout=_ZEITLIMIT_MS,
    ):
        page.goto(_APP_URL.format(dfb_spiel_id), wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS)


def hole_bericht(page: Page, dfb_spiel_id: str) -> List[Dict]:
    """
    Die Rohdaten eines Berichts: je Spiel des Berichts (praktisch immer eins)
    die Kopfdaten aus /matches und der komplette Spielverlauf aus /details.
    """
    bericht_id = _hole_json(page, f"report/{dfb_spiel_id}/create")
    if not isinstance(bericht_id, str) or not re.fullmatch(_ID, bericht_id):
        raise RuntimeError("Keine Berichts-ID erhalten")

    spiele = _hole_json(page, f"report/{bericht_id}/matches") or []
    ergebnis = []
    for spiel in spiele:
        details = _hole_json(page, f"match/{spiel['id']}/details")
        ergebnis.append({"spiel": spiel, "details": details})
    return ergebnis


# ------------------------------------------------------------- Aufbereitung

def _name(person: Optional[Dict]) -> str:
    if not person:
        return ""
    nachname = (person.get("lastName") or "").strip()
    vorname = (person.get("firstName") or "").strip()
    return ", ".join(teil for teil in (nachname, vorname) if teil)


def _ohne_trennstriche(text: Optional[str]) -> str:
    """DFBnet setzt weiche Trennstriche in Vereinsnamen ("BFC \\u00adPreussen")."""
    return re.sub(r"\s+", " ", (text or "").replace("­", "")).strip()


def _tore(ergebnis: Optional[Dict]) -> Optional[str]:
    if not ergebnis:
        return None
    heim, gast = ergebnis.get("homeTeamGoals"), ergebnis.get("awayTeamGoals")
    if heim is None or gast is None:
        return None
    return f"{heim}:{gast}"


def _zeitpunkt(info: Optional[Dict]) -> Optional[Dict]:
    """Name und Zeitstempel einer Bestaetigung/eines Uploads - ohne Telefon und Mail."""
    if not info:
        return None
    return {"name": info.get("userName") or "", "zeit": info.get("timestamp") or ""}


def _spieler(spieler: Dict) -> Dict:
    """Nur was auf dem Spielbericht steht - kein Geburtsdatum, keine Passnummer."""
    status = spieler.get("playerStatusShort") or spieler.get("playerStatus") or {}
    return {
        "id": spieler.get("id"),
        "nummer": spieler.get("jerseyNumber"),
        "name": _name(spieler),
        "kapitaen": bool(spieler.get("captain")),
        "torwart": bool(spieler.get("goalkeeper")),
        "ersatz": bool(spieler.get("reserve")),
        "status": status.get("shortName") or status.get("name") or "",
    }


def _offizieller(person: Dict) -> Dict:
    funktionen = [t.get("name") for t in (person.get("types") or []) if t.get("name")]
    return {"id": person.get("id"), "name": _name(person), "funktion": ", ".join(funktionen)}


def aufbereiten(spiel: Dict, details: Dict) -> Dict:
    """
    Macht aus den Rohdaten der Bericht-App das, was der Spesenfuchs anzeigt.

    Bewusst eine Auswahl: Personen nur mit Name, Rueckennummer und Funktion.
    Geburtsdaten, Passnummern, Fotos, Telefonnummern und Mailadressen bleiben
    bei DFBnet.
    """
    info = details.get("matchInfo") or {}
    heim_id = (info.get("homeTeam") or {}).get("id")
    gast_id = (info.get("awayTeam") or {}).get("id")

    heim_spieler = [_spieler(s) for s in details.get("homeTeamPlayers") or []]
    gast_spieler = [_spieler(s) for s in details.get("awayTeamPlayers") or []]
    heim_offizielle = [_offizieller(p) for p in details.get("homeTeamOfficials") or []]
    gast_offizielle = [_offizieller(p) for p in details.get("awayTeamOfficials") or []]

    personen = {}
    for liste in (heim_spieler, gast_spieler):
        for s in liste:
            personen[s["id"]] = {"name": s["name"], "nummer": s["nummer"]}
    for liste in (heim_offizielle, gast_offizielle):
        for p in liste:
            personen[p["id"]] = {"name": p["name"], "funktion": p["funktion"]}

    def seite(team_id: Optional[str]) -> str:
        if team_id == heim_id:
            return "heim"
        if team_id == gast_id:
            return "gast"
        return ""

    ereignisse = []
    quellen = [
        ("goalEvents", False),
        ("substitutionEvents", False),
        ("playerPenaltyEvents", False),
        ("teamOfficialPenaltyEvents", True),
    ]
    for feld, offizieller in quellen:
        for e in details.get(feld) or []:
            typ = EREIGNIS_TYPEN.get(e.get("typeId"), f"typ{e.get('typeId')}")
            person = personen.get(e.get("teamPersonId1")) or {}
            eintrag = {
                "minute": e.get("matchMinute"),
                "nachspielzeit": e.get("additionalMinute"),
                "typ": typ,
                "seite": seite(e.get("teamId")),
                "person": person.get("name", ""),
                "nummer": person.get("nummer"),
                "funktion": person.get("funktion") if offizieller else None,
                "grund": (e.get("description") or "").strip(),
                "sonderbericht": bool(e.get("extraReportAttached")),
            }
            if typ == "wechsel":
                # teamPersonId1 kommt rein (Ersatzspieler), teamPersonId2 geht raus
                raus = personen.get(e.get("teamPersonId2")) or {}
                eintrag["person_raus"] = raus.get("name", "")
                eintrag["nummer_raus"] = raus.get("nummer")
            ereignisse.append(eintrag)

    ereignisse.sort(key=lambda e: (e["minute"] or 0, e["nachspielzeit"] or 0))

    # Gespann: angesetzte Personen und, wer welche Rolle tatsaechlich hatte
    angesetzt = {p.get("id"): p for p in details.get("appointedOfficials") or []}
    gespann = []
    for rolle in details.get("matchOfficials") or []:
        person = angesetzt.get(rolle.get("appointedOfficialId"))
        if not person:
            continue
        gespann.append({
            "rolle": _ROLLEN.get(rolle.get("roleId"), rolle.get("roleName") or ""),
            "rolle_name": rolle.get("roleName") or "",
            "name": _name(person),
            "verein": person.get("clubName") or "",
            "nicht_angetreten": bool(person.get("notAppeared")),
        })
    if not gespann:
        for person in sorted(angesetzt.values(), key=lambda p: p.get("rolePosition") or 9):
            gespann.append({
                "rolle": _ROLLEN.get(person.get("rolePosition"), ""),
                "rolle_name": "",
                "name": _name(person),
                "verein": person.get("clubName") or "",
                "nicht_angetreten": bool(person.get("notAppeared")),
            })

    ergebnis = details.get("matchResult") or {}
    kosten = details.get("matchRefereeExpensesInfo") or {}
    bestaetigung = details.get("matchConfirmationInfo") or {}
    vorkommnisse = details.get("matchIncidents") or {}
    bemerkungen = details.get("matchCommentsInfo") or {}

    kontrollen = []
    for pruefung in details.get("matchCheckInfos") or []:
        auswahl = {a.get("id"): a.get("name") for a in pruefung.get("availableSelections") or []}
        kontrollen.append({
            "name": (pruefung.get("checkType") or {}).get("name") or "",
            "wert": auswahl.get(pruefung.get("selectedValue")) or "",
            "bemerkung": pruefung.get("remarkValue") or "",
        })

    runde = spiel.get("round") or {}
    staette = spiel.get("venue") or info.get("venue") or {}

    return {
        "spielkennung": spiel.get("identifier") or info.get("identifier") or "",
        "heim": _ohne_trennstriche((spiel.get("homeTeam") or {}).get("teamName")),
        "gast": _ohne_trennstriche((spiel.get("awayTeam") or {}).get("teamName")),
        "runde": runde.get("name") or "",
        "anstoss_geplant": spiel.get("kickOff") or info.get("kickOff") or "",
        "beginn": details.get("actualKickoff") or "",
        "ende": details.get("actualEnd") or "",
        "nachspielzeit": {
            "h1": details.get("additionalTimeHalf1"),
            "h2": details.get("additionalTimeHalf2"),
            "v1": details.get("additionalTimeExtra1"),
            "v2": details.get("additionalTimeExtra2"),
        },
        "spielstaette": {
            "name": staette.get("name") or "",
            "ort": " ".join(t for t in (staette.get("zipCode"), staette.get("town")) if t),
            "strasse": staette.get("street") or "",
            "belag": staette.get("typeName") or "",
        },
        "ergebnis": {
            "halbzeit": _tore(ergebnis.get("resultAtHalfTime")),
            "regulaer": _tore(ergebnis.get("resultAfterRegularTime")),
            "verlaengerung": _tore(ergebnis.get("resultAfterExtraTime")),
            "endstand": _tore(ergebnis.get("finalResult")),
            "wertung": ergebnis.get("cancellationReasonName") or "",
            "abbruch_minute": ergebnis.get("abortionMinute"),
        },
        "zuschauer": (details.get("matchSpectatorsInfo") or {}).get("spectators"),
        "kosten": {
            "fahrtkosten": kosten.get("refereeTravelExpenses"),
            "spesen": kosten.get("refereeRsRsaExpenses"),
        },
        "gespann": gespann,
        "ereignisse": ereignisse,
        "aufstellung": {
            "heim": {"spieler": heim_spieler, "offizielle": heim_offizielle},
            "gast": {"spieler": gast_spieler, "offizielle": gast_offizielle},
        },
        "kontrollen": kontrollen,
        "bemerkungen": (bemerkungen.get("otherComments") or "").strip(),
        "fairplay": bool(bemerkungen.get("especiallyFairPlay")),
        "vorkommnisse": {
            "gemeldet": bool(vorkommnisse.get("incidentsSpecified")),
            "gewalt": vorkommnisse.get("violence"),
            "diskriminierung": vorkommnisse.get("discrimination"),
            "spielabbruch": vorkommnisse.get("matchAbandoned"),
            "beschuldigte": [k for k, feld in (
                ("Spieler", "offenderPlayer"), ("Teamoffizielle", "offenderTeamOfficial"),
                ("Vereinsoffizielle", "offenderClubOfficial"), ("Schiedsrichter", "offenderReferee"),
                ("Zuschauer", "offenderSpectator"),
            ) if vorkommnisse.get(feld)],
            "geschaedigte": [k for k, feld in (
                ("Spieler", "victimPlayer"), ("Teamoffizielle", "victimTeamOfficial"),
                ("Vereinsoffizielle", "victimClubOfficial"), ("Schiedsrichter", "victimReferee"),
                ("Zuschauer", "victimSpectator"),
            ) if vorkommnisse.get(feld)],
        },
        "bestaetigung": {
            "heim": _zeitpunkt(bestaetigung.get("homeConfirmInfo")) if bestaetigung.get("homeConfirmed") else None,
            "gast": _zeitpunkt(bestaetigung.get("awayConfirmInfo")) if bestaetigung.get("awayConfirmed") else None,
            "schiedsrichter": _zeitpunkt(bestaetigung.get("refereeConfirmInfo")),
        },
        "dokumente": [
            {
                "dfb_id": d.get("id"),
                "kategorie_id": d.get("categoryId"),
                "dateiname": d.get("fileName") or "",
                "beschreibung": (d.get("description") or "").strip(),
                "hochgeladen": _zeitpunkt(d.get("uploadInfo")),
            }
            for d in details.get("matchDocuments") or []
            if d.get("authorizedToView", True)
        ],
        "kategorien": {
            k.get("id"): k.get("name") for k in details.get("documentCategories") or []
        },
        "bericht_spiel_id": info.get("id") or spiel.get("id"),
    }


# ------------------------------------------------------------------ Ablauf

def lies_saisons(
    page: Page,
    einsatzplan_url: str,
    saisons_fuer: Callable[[List[str]], List[str]],
    progress_callback=None,
) -> Dict[str, Dict]:
    """
    Liest den Einsatzplan der noetigen Saisons.

    Returns:
        saison -> {"zeilen": [...]}. Eine Saison, bei der etwas schiefging,
        fehlt und wird beim naechsten Lauf erneut gelesen.
    """
    angebotene = oeffne_einsatzplan(page, einsatzplan_url)
    zu_lesen = saisons_fuer(angebotene)
    logger.info(f"Spielberichte: lese Einsatzplan {zu_lesen}")

    ergebnis = {}
    for nummer, saison in enumerate(zu_lesen, start=1):
        if progress_callback:
            progress_callback(nummer, len(zu_lesen), f"Einsatzplan {saison} ({nummer}/{len(zu_lesen)})")
        try:
            waehle_saison(page, saison)
            ergebnis[saison] = {"zeilen": lies_einsatzplan(page)}
            logger.info(f"✓ Einsatzplan {saison}: {len(ergebnis[saison]['zeilen'])} Spiele")
        except Exception as e:
            logger.warning(f"Einsatzplan {saison} nicht gelesen: {e}")
            try:
                oeffne_einsatzplan(page, einsatzplan_url)
            except Exception as neu:
                logger.warning(f"Einsatzplan nicht wieder geoeffnet: {neu}")
                break

    return ergebnis


def lies_berichte(
    page: Page,
    zeilen: List[Dict],
    dokument_vorhanden: Callable[[str], bool],
    progress_callback=None,
) -> Dict[str, Dict]:
    """
    Liest die Berichte zu den uebergebenen Einsatzplan-Zeilen.

    Args:
        zeilen: nur lesbare Zeilen (ist_lesbar)
        dokument_vorhanden: dfb_dokument_id -> schon gespeichert? Solche
            Dokumente werden nicht noch einmal geladen.

    Returns:
        dfb_spiel_id -> {"zeile", "daten", "dateien": {dfb_dokument_id: bytes}}
    """
    if not zeilen:
        return {}

    oeffne_bericht_app(page, zeilen[0]["dfb_spiel_id"])

    ergebnis = {}
    neu_geoeffnet = False

    for nummer, zeile in enumerate(zeilen, start=1):
        spiel_id = zeile["dfb_spiel_id"]
        if progress_callback:
            progress_callback(
                nummer, len(zeilen),
                f"Spielbericht {zeile.get('datum', '')} {zeile.get('heim', '')} ({nummer}/{len(zeilen)})",
            )

        for versuch in (1, 2):
            try:
                roh = hole_bericht(page, spiel_id)
                if not roh:
                    raise RuntimeError("Bericht ohne Spiel")

                # Ein Einzelspielbericht hat genau ein Spiel
                daten = aufbereiten(roh[0]["spiel"], roh[0]["details"])

                dateien = {}
                for dokument in daten["dokumente"]:
                    if dokument_vorhanden(dokument["dfb_id"]):
                        continue
                    try:
                        dateien[dokument["dfb_id"]] = hole_dokument(
                            page, daten["bericht_spiel_id"], dokument["dfb_id"]
                        )
                    except SitzungAbgelaufen:
                        raise
                    except Exception as e:
                        logger.warning(f"Dokument zu {zeile['datum']} nicht geladen: {e}")

                ergebnis[spiel_id] = {"zeile": zeile, "daten": daten, "dateien": dateien}
                break

            except SitzungAbgelaufen as e:
                # Einmal pro Lauf die App neu laden, dann aufgeben
                if versuch == 1 and not neu_geoeffnet:
                    logger.info(f"Bericht-App neu laden ({e})")
                    neu_geoeffnet = True
                    try:
                        oeffne_bericht_app(page, spiel_id)
                    except Exception as fehler:
                        # Das Gelesene behalten - sonst ginge mit einem
                        # haengenden Neuladen der ganze Lauf verloren.
                        logger.warning(f"Spielberichte abgebrochen, App laedt nicht neu: {fehler}")
                        return ergebnis
                    continue
                logger.warning(f"Spielberichte abgebrochen: {e}")
                return ergebnis

            except Exception as e:
                logger.warning(f"Spielbericht {zeile.get('datum')} {zeile.get('heim')} nicht gelesen: {e}")
                break

    return ergebnis
