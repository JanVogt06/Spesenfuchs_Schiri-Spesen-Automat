"""
Liest die eigenen Beobachtungen aus zwei klassischen DFBnet-Modulen.

- "Schiri-Beobachtung -> Beobachtung" fuehrt die Beobachtungen im
  Landesverband (Herren-Spielklassen). Das Modul hat jeder Schiedsrichter.
- "Schiri-Portal -> Beobachtung" fuehrt die Beobachtungen im DFB-Nachwuchs
  (U19-Bundesliga/Nachwuchsliga). Das Modul haben nur wenige; wer es nicht
  hat, dem fehlt der Menuepunkt komplett.

Beide Module sind dasselbe alte Server-Formular (kein Angular wie die
Schiriansetzung): Saison, Datum von/bis und Funktion setzen, "Suchen" schickt
die Seite ab und laedt sie mit der Ergebnisliste neu.

Drei Dinge, die man wissen muss:

1. Die Funktion filtert auf die EIGENE Rolle. "1. Assistent" liefert genau
   die Spiele, in denen man selbst SRA1 war. Darueber wird die eigene Note
   zugeordnet - ein Abgleich ueber den Namen ginge schief, sobald zwei
   Personen gleichen Nachnamens im selben Gespann stehen.

2. Die Notenspalte ist eine Untertabelle, deren Zeilen 1:1 zu den Zeilen
   der Gespann-Untertabelle passen (SR, SRA1, SRA2, im Portal auch 4OF). Die
   eigene Note steht also in der Zeile, in der im Gespann die eigene Rolle
   steht.

3. Die Formularwerte werden per JavaScript gesetzt, ohne Change-Events: der
   Saison-Auswahl haengt ein onchange an, das die Seite sofort neu abschickt.
   Abgeschickt wird dagegen mit einem echten Klick - ein per Skript
   ausgeloester Klick erzeugte im Test eine ungueltige Webflow-Seite
   ("moeglicherweise haben Sie die Browser-Back Funktion benutzt").

4. Eine Suche ohne Treffer zeigt im Herren-Modul den Kasten "Fehlermeldungen
   / Hinweise" mit "Ihre Suchanfrage ergab keine Treffer!". Das ist kein
   Fehler, sondern der Normalfall fuer jede Rolle, in der man in einer Saison
   nie eingesetzt war.
"""
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page

from utils.logger import setup_logger
from utils.saison_utils import saison_zeitraum

logger = setup_logger("beobachtungen")

# Rollen, zu denen eine eigene Note gelesen wird: (Formularwert, Kuerzel in
# der Gespann-Tabelle). Die Werte der Funktion-Auswahl sind in beiden Modulen
# gleich; den 4. Offiziellen gibt es nur im Portal.
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

# Der Menuepunkt "Beobachtung" eines Moduls - erkannt am Pfad des Moduls und
# am Ereignis, nicht am Text: "Beobachtung" steckt auch in
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

# Die Ergebnisliste. Spalten: Symbol | Datum+Zeit | Spieltag | Staffel |
# Heim+Gast | Ergebnis | Gespann (Untertabelle) | Noten (Untertabelle) |
# Status+Freigabezeitpunkt. Eine leere Liste hat weder Zeilen noch die
# Blaetterleiste "Seite x/y (n Treffer insgesamt)".
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

        // Das Herren-Modul meldet eine leere Suche im Kasten "Fehlermeldungen /
        // Hinweise" ("Ihre Suchanfrage ergab keine Treffer!"); das Portal
        // zeigt dann einfach nichts. Nur was dort SONST steht, ist ein Fehler.
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
    Die Einstiegs-Links der Beobachtungsmodule aus dem DFBnet-Hauptmenue.

    Liefert quelle -> URL nur fuer die Module, die der Account hat.
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
    Oeffnet die Beobachtungsliste eines Moduls und gibt ihre URL zurueck.

    Mit der URL laesst sich die Liste nach einem Fehler frisch aufrufen - die
    Webflow-Seiten nach einer Suche sind nicht wieder aufrufbar.
    """
    page.goto(modul_url, wait_until="domcontentloaded", timeout=_ZEITLIMIT_MS)

    teile = urlparse(modul_url)
    modulpfad = teile.path.rsplit("/", 1)[0]
    listen_url = page.evaluate(_LISTEN_LINK_JS, modulpfad)

    # Steht der Menuepunkt nicht auf der Einstiegsseite, wird die Liste direkt
    # aufgerufen - das Ereignis OBSERVATION laesst sich auch ohne vorherigen
    # Klick ins Modul oeffnen.
    if not listen_url:
        listen_url = f"{teile.scheme}://{teile.netloc}{modulpfad}/webflow.do?event=OBSERVATION"
        logger.info(f"Menuepunkt 'Beobachtung' in {modulpfad} nicht gefunden - rufe die Liste direkt auf")

    lade_liste(page, listen_url)
    return listen_url


def _warte_auf_formular(page: Page) -> None:
    """
    Wartet auf das Suchformular - und sagt im Fehlerfall, was stattdessen da
    steht.

    Die Seiten werden auf dem Server gerendert; nach domcontentloaded ist das
    Formular da oder es kommt nicht mehr. Statt einer Fehlerseite 45 Sekunden
    lang zuzusehen, wird kurz gewartet und der Seitenanfang ins Protokoll
    geschrieben ("Die aufgerufene Seite ist ungueltig ..." o.ae.).
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
    """Die Saisons der Auswahl, wie DFBnet sie listet: neueste zuerst."""
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
    Sucht alle Beobachtungen einer Saison in einer Funktion (rolle "" = alle).

    Blaettert durch, falls DFBnet mehr als eine Seite liefert (20 je Seite).

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

    # Hat DFBnet die Suche wirklich mit unseren Werten ausgefuehrt? Eine leere
    # Liste sieht sonst genauso aus wie eine, die nie gesucht hat.
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
    Macht aus einer Listenzeile die eigene Beobachtung in der gegebenen Rolle.

    None, wenn die Beobachtung nicht freigegeben ist, die Rolle im Gespann
    nicht vorkommt oder zur Rolle keine Note eingetragen ist.
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
    Alle eigenen, freigegebenen Beobachtungen einer Saison in einem Modul.

    Erst eine Suche ueber alle Funktionen: die meisten Saisons sind leer (vor
    allem im Portal), und dann bleibt es bei dieser einen Suche. Nur wenn es
    Treffer gibt, wird je Rolle einzeln gesucht.
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
    Liest die noetigen Saisons eines Moduls.

    Args:
        saisons_fuer: (quelle, angebotene Saisons) -> zu lesende Saisons

    Returns:
        saison -> {"beobachtungen": [...], "vollstaendig": bool}. Eine Saison,
        bei der etwas schiefging, fehlt im Ergebnis und wird beim naechsten
        Lauf erneut gelesen.
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
            # Nach einem Fehler steht die Seite irgendwo - frisch einsteigen.
            try:
                lade_liste(page, listen_url)
            except Exception as neu_laden:
                logger.warning(f"Beobachtungsliste {quelle} nicht wieder geoeffnet: {neu_laden}")
                break

    return ergebnis
