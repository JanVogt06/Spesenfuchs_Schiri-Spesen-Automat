"""
Reads the user's own observations (Beobachtungen) from two classic DFBnet
modules.

- "Schiri-Beobachtung -> Beobachtung" holds the observations at state
  association level (Landesverband, men's league levels). Every referee has
  this module.
- "Schiri-Portal -> Beobachtung" holds the observations in the DFB youth
  leagues (U19 Bundesliga/Nachwuchsliga). Only few people have this module;
  whoever does not have it is missing the menu item entirely.

Both modules are the same old server-side form (not Angular like the
Schiriansetzung): set season, date from/to and function (Funktion), "Suchen"
(search) submits the page and reloads it with the result list.

Four things you need to know:

1. The function filters on the user's OWN role. "1. Assistent" returns exactly
   the matches in which the user was SRA1 themselves. The user's own grade is
   assigned via that - matching by name would go wrong as soon as two people
   with the same surname are in the same crew.

2. The grade column is a sub-table whose rows match 1:1 the rows of the crew
   (Gespann) sub-table (SR, SRA1, SRA2, in the portal also 4OF). The user's
   own grade is therefore in the row in which the crew lists the user's own
   role.

3. The form values are set via JavaScript, without change events: the season
   selection has an onchange attached that immediately resubmits the page.
   Submitting, on the other hand, is done with a real click - a click
   triggered by script produced an invalid Webflow page in testing
   ("moeglicherweise haben Sie die Browser-Back Funktion benutzt" - "you may
   have used the browser back function").

4. A search without hits shows, in the men's module, the box "Fehlermeldungen
   / Hinweise" (error messages / notes) with "Ihre Suchanfrage ergab keine
   Treffer!" (your search returned no hits). That is not an error but the
   normal case for every role in which the user was never assigned in a
   season.
"""
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page

from utils.logger import setup_logger
from utils.saison_utils import saison_zeitraum

logger = setup_logger("beobachtungen")

# Roles for which an own grade is read: (form value, abbreviation in the crew
# table). The values of the function selection are the same in both modules;
# the fourth official only exists in the portal.
QUELLEN = {
    "herren": {
        "menue": "Schiri-Beobachtung",
        "rollen": [("1", "SR"), ("2", "SRA1"), ("3", "SRA2")],
    },
    "portal": {
        "menue": "Schiri-Portal",
        "rollen": [("1", "SR"), ("2", "SRA1"), ("3", "SRA2"), ("4", "4OF")],
    },
}

_ZEITLIMIT_MS = 45000

_MENUE_JS = """
    (namen) => {
        const gefunden = {};
        for (const a of document.querySelectorAll('a[href]')) {
            const text = a.textContent.trim();
            if (namen.includes(text) && !gefunden[text]) gefunden[text] = a.href;
        }
        return gefunden;
    }
"""

# The "Beobachtung" menu item of a module - recognised by the module's path and
# by the event, not by the text: "Beobachtung" is also part of
# "Schiri-Beobachtung".
_LISTEN_LINK_JS = """
    (modulpfad) => {
        for (const a of document.querySelectorAll('a[href]')) {
            const url = new URL(a.href, location.href);
            if (url.pathname === modulpfad + '/webflow.do'
                    && url.searchParams.get('event') === 'OBSERVATION') {
                return url.href;
            }
        }
        return null;
    }
"""

_FORMULAR_SETZEN_JS = """
    ([saison, von, bis, rolle]) => {
        const f = document.forms.actionForm;
        if (!f) return 'Suchformular fehlt';

        const auswahl = f.elements['kontext.searchPanel.seasonId'];
        if (![...auswahl.options].some((o) => o.value === saison)) {
            return 'Saison ' + saison + ' wird nicht angeboten';
        }
        const funktion = f.elements['kontext.searchPanel.refereeRoleId'];
        if (![...funktion.options].some((o) => o.value === rolle)) {
            return 'Funktion ' + rolle + ' wird nicht angeboten';
        }

        auswahl.value = saison;
        funktion.value = rolle;
        f.elements['kontext.searchPanel.matchDay'].value = '';
        f.elements['kontext.searchPanel.kickoffFrom'].value = von;
        f.elements['kontext.searchPanel.kickoffTo'].value = bis;
        return '';
    }
"""

_FORMULAR_LESEN_JS = """
    () => {
        const f = document.forms.actionForm;
        if (!f) return null;
        return [
            f.elements['kontext.searchPanel.seasonId'].value,
            f.elements['kontext.searchPanel.kickoffFrom'].value,
            f.elements['kontext.searchPanel.kickoffTo'].value,
            f.elements['kontext.searchPanel.refereeRoleId'].value,
        ];
    }
"""

_SAISONS_JS = """
    () => {
        const f = document.forms.actionForm;
        if (!f) return [];
        return [...f.elements['kontext.searchPanel.seasonId'].options].map((o) => o.value);
    }
"""

# The result list. Columns: symbol | date+time | matchday | division (Staffel) |
# home+away | result | crew (sub-table) | grades (sub-table) |
# status+release time. An empty list has neither rows nor the paging bar
# "Seite x/y (n Treffer insgesamt)" (page x/y (n hits in total)).
_LISTE_JS = """
    () => {
        const text = document.body.innerText;
        const seite = /Seite\\s+(\\d+)\\s*\\/\\s*(\\d+)\\s*\\((\\d+)\\s+Treffer/.exec(text);
        const spans = (el) => [...el.querySelectorAll('span')].map((s) => s.textContent.trim());
        const unterzeilen = (el) => [...el.querySelectorAll('tr')].map(
            (tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent.trim())
        );

        const zeilen = [];
        for (const tr of document.querySelectorAll('tr')) {
            const zellen = [...tr.children].filter((c) => c.tagName === 'TD');
            if (zellen.length < 9 || !zellen[1].classList.contains('listtext')) continue;

            const termin = spans(zellen[1]);
            if (!/^\\d{2}\\.\\d{2}\\.\\d{4}$/.test(termin[0] || '')) continue;

            zeilen.push({
                datum: termin[0],
                uhrzeit: termin[1] || '',
                spieltag: zellen[2].textContent.trim(),
                staffel: zellen[3].textContent.trim(),
                mannschaften: spans(zellen[4]),
                ergebnis: zellen[5].textContent.trim(),
                gespann: unterzeilen(zellen[6]).map((z) => ({rolle: z[0] || '', name: z[1] || ''})),
                noten: unterzeilen(zellen[7]).map((z) => z.join(' ').trim()),
                status: spans(zellen[8]),
            });
        }

        // The men's module reports an empty search in the box "Fehlermeldungen /
        // Hinweise" ("Ihre Suchanfrage ergab keine Treffer!"); the portal
        // then simply shows nothing. Only what is OTHERWISE in there is an error.
        const kasten = /Fehlermeldungen[^\\n]*\\n([^\\n]*)/.exec(text);
        const keineTreffer = /ergab keine Treffer/.test(text);

        return {
            seite: seite ? Number(seite[1]) : null,
            seiten: seite ? Number(seite[2]) : null,
            treffer: seite ? Number(seite[3]) : 0,
            zeilen,
            weiter: !!document.querySelector('input.naviNext'),
            keine_treffer: keineTreffer,
            fehler: kasten && !keineTreffer ? (kasten[1] || 'Fehlermeldung ohne Text').trim() : '',
        };
    }
"""


def finde_module(page: Page) -> Dict[str, str]:
    """
    The entry links of the observation modules from the DFBnet main menu.

    Returns source -> URL only for the modules that the account has.
    """
    namen = [cfg["menue"] for cfg in QUELLEN.values()]
    gefunden = page.evaluate(_MENUE_JS, namen) or {}
    return {
        quelle: gefunden[cfg["menue"]]
        for quelle, cfg in QUELLEN.items()
        if gefunden.get(cfg["menue"])
    }


def oeffne_liste(page: Page, modul_url: str) -> str:
    """
    Opens the observation list of a module and returns its URL.

    With the URL the list can be opened afresh after an error - the Webflow
    pages after a search cannot be opened again.
    """
    page.goto(modul_url, wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS)

    teile = urlparse(modul_url)
    modulpfad = teile.path.rsplit("/", 1)[0]
    listen_url = page.evaluate(_LISTEN_LINK_JS, modulpfad)

    # If the menu item is not on the entry page, the list is opened directly -
    # the OBSERVATION event can also be opened without first clicking into the
    # module.
    if not listen_url:
        listen_url = f"{teile.scheme}://{teile.netloc}{modulpfad}/webflow.do?event=OBSERVATION"
        logger.info(f"Menuepunkt 'Beobachtung' in {modulpfad} nicht gefunden - rufe die Liste direkt auf")

    lade_liste(page, listen_url)
    return listen_url


def _warte_auf_formular(page: Page) -> None:
    """
    Waits for the search form - and, in case of failure, says what is there
    instead.

    The pages are rendered on the server; after domcontentloaded the form is
    either there or it will not come anymore. Instead of watching an error
    page for 45 seconds, we wait briefly and write the top of the page to the
    log ("Die aufgerufene Seite ist ungueltig ..." (the requested page is
    invalid) or similar).
    """
    try:
        page.locator('select[name="kontext.searchPanel.seasonId"]').wait_for(
            state="attached", timeout=5000
        )
    except Exception:
        try:
            anfang = " ".join(page.locator("main, body").first.inner_text().split())[:300]
        except Exception:
            anfang = "?"
        raise RuntimeError(f"Kein Suchformular auf {urlparse(page.url).path}: {anfang}")


def lade_liste(page: Page, listen_url: str) -> None:
    page.goto(listen_url, wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS)
    _warte_auf_formular(page)


def angebotene_saisons(page: Page) -> List[str]:
    """The seasons of the selection, as DFBnet lists them: newest first."""
    return page.evaluate(_SAISONS_JS) or []


def _abschicken(page: Page, ausloeser: str) -> dict:
    with page.expect_navigation(wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS):
        page.locator(ausloeser).first.click()
    _warte_auf_formular(page)
    ergebnis = page.evaluate(_LISTE_JS)
    if ergebnis.get("fehler"):
        raise RuntimeError(f"DFBnet meldet: {ergebnis['fehler']}")
    return ergebnis


def suche(page: Page, saison: str, rolle: str) -> dict:
    """
    Searches all observations of a season in one function (rolle "" = all).

    Pages through if DFBnet returns more than one page (20 per page).

    Returns:
        {"zeilen": [...], "treffer": n, "vollstaendig": bool}
    """
    zeitraum = saison_zeitraum(saison)
    if not zeitraum:
        raise ValueError(f"Unbekanntes Saisonformat: {saison}")
    von, bis = (tag.strftime("%d.%m.%Y") for tag in zeitraum)

    problem = page.evaluate(_FORMULAR_SETZEN_JS, [saison, von, bis, rolle])
    if problem:
        raise RuntimeError(problem)

    ergebnis = _abschicken(page, 'input[name="SEARCH"]')

    # Did DFBnet really run the search with our values? An empty list
    # otherwise looks exactly like one that never searched.
    if page.evaluate(_FORMULAR_LESEN_JS) != [saison, von, bis, rolle]:
        raise RuntimeError(f"Suche {saison}/{rolle or 'alle'} nicht mit den gesetzten Werten ausgefuehrt")

    zeilen = list(ergebnis["zeilen"])
    treffer = ergebnis["treffer"]
    seiten = ergebnis.get("seiten") or 1

    for _ in range(seiten - 1):
        if not ergebnis.get("weiter"):
            break
        ergebnis = _abschicken(page, "input.naviNext")
        zeilen.extend(ergebnis["zeilen"])

    vollstaendig = len(zeilen) == treffer
    if not vollstaendig:
        logger.warning(f"{saison}/{rolle or 'alle'}: {len(zeilen)} von {treffer} Zeilen gelesen")

    return {"zeilen": zeilen, "treffer": treffer, "vollstaendig": vollstaendig}


def parse_note(text: str) -> Optional[float]:
    """'244' -> 244.0, '8,4' -> 8.4, '' -> None."""
    text = (text or "").strip().replace(",", ".")
    try:
        return float(text) if text else None
    except ValueError:
        return None


def eigene_beobachtung(zeile: dict, rolle: str) -> Optional[dict]:
    """
    Turns a list row into the user's own observation in the given role.

    None if the observation is not released (freigegeben), the role does not
    appear in the crew, or no grade is entered for the role.
    """
    status = zeile.get("status") or []
    if not status or status[0].strip().lower() != "freigegeben":
        return None

    gespann = zeile.get("gespann") or []
    position = next((i for i, p in enumerate(gespann) if p.get("rolle") == rolle), None)
    if position is None:
        return None

    noten = zeile.get("noten") or []
    note_text = noten[position].strip() if position < len(noten) else ""
    note = parse_note(note_text)
    if note is None:
        return None

    tag, monat, jahr = zeile["datum"].split(".")
    mannschaften = list(zeile.get("mannschaften") or []) + ["", ""]

    return {
        "datum": f"{jahr}-{monat}-{tag}",
        "uhrzeit": zeile.get("uhrzeit", ""),
        "spieltag": zeile.get("spieltag", ""),
        "staffel": zeile.get("staffel", ""),
        "heim": mannschaften[0],
        "gast": mannschaften[1],
        "ergebnis": zeile.get("ergebnis", ""),
        "rolle": rolle,
        "note": note,
        "note_text": note_text,
        "beobachter": next((p.get("name", "") for p in gespann if p.get("rolle") == "BEO"), ""),
        "freigegeben_am": " ".join(status[1:3]).strip(),
    }


def lies_saison(page: Page, quelle: str, saison: str) -> dict:
    """
    All of the user's own released observations of a season in one module.

    First a search across all functions: most seasons are empty (especially in
    the portal), and then it stays with this one search. Only if there are
    hits is each role searched individually.
    """
    alle = suche(page, saison, "")
    if alle["treffer"] == 0 and not alle["zeilen"]:
        return {"beobachtungen": [], "vollstaendig": True}

    beobachtungen = []
    vollstaendig = alle["vollstaendig"]

    for formularwert, rolle in QUELLEN[quelle]["rollen"]:
        ergebnis = suche(page, saison, formularwert)
        vollstaendig = vollstaendig and ergebnis["vollstaendig"]

        for zeile in ergebnis["zeilen"]:
            beobachtung = eigene_beobachtung(zeile, rolle)
            if beobachtung:
                beobachtungen.append(beobachtung)

    return {"beobachtungen": beobachtungen, "vollstaendig": vollstaendig}


def lies_quelle(
    page: Page,
    quelle: str,
    modul_url: str,
    saisons_fuer: Callable[[str, List[str]], List[str]],
    progress_callback=None,
) -> Dict[str, dict]:
    """
    Reads the required seasons of a module.

    Args:
        saisons_fuer: (source, offered seasons) -> seasons to read

    Returns:
        season -> {"beobachtungen": [...], "vollstaendig": bool}. A season for
        which something went wrong is missing from the result and is read
        again on the next run.
    """
    listen_url = oeffne_liste(page, modul_url)
    zu_lesen = saisons_fuer(quelle, angebotene_saisons(page))
    logger.info(f"Beobachtungen {quelle}: lese {zu_lesen}")

    ergebnis = {}
    for nummer, saison in enumerate(zu_lesen, start=1):
        if progress_callback:
            progress_callback(
                nummer, len(zu_lesen),
                f"Beobachtungen {QUELLEN[quelle]['menue']} {saison} ({nummer}/{len(zu_lesen)})",
            )

        try:
            ergebnis[saison] = lies_saison(page, quelle, saison)
            logger.info(
                f"✓ Beobachtungen {quelle} {saison}: "
                f"{len(ergebnis[saison]['beobachtungen'])} eigene Noten"
            )
        except Exception as e:
            logger.warning(f"Beobachtungen {quelle} {saison} nicht gelesen: {e}")
            # After an error the page is somewhere unknown - start afresh.
            try:
                lade_liste(page, listen_url)
            except Exception as neu_laden:
                logger.warning(f"Beobachtungsliste {quelle} nicht wieder geoeffnet: {neu_laden}")
                break

    return ergebnis
