"""
Spesenfuchs - Main Entry Point
Starts the FastAPI backend application
"""
import os
from datetime import date, timedelta
from typing import Callable, Optional, List

# Load .env before importing modules that read secrets at import time
from core.config import load_environment

load_environment()

from scraper.dfb_scraper import DFBScraper
from generator.docx_generator import KM_SATZ_EURO
from generator.spesen_calculator import calculate_spesen
from db.database import dfb_login_angenommen
from db.matches import upsert_match, mark_missing_matches, setze_spielnummern
from db.stammdaten import upsert_stammdaten, get_stammdaten
from db.beobachtungen import (
    replace_beobachtungs_saison, count_beobachtungen, get_fertige_beobachtungs_saisons,
)
from db.season import replace_saison, get_komplette_saisons, count_saison_spiele
from db.spielberichte import (
    speichere_bericht, setze_saison, get_fertige_saisons as get_fertige_bericht_saisons,
    get_gespeicherte as get_gespeicherte_berichte, get_dokument_ids,
)
from scraper.spielberichte import ist_lesbar, spielkennung, wartet_auf_freigabe
from utils.logger import setup_logger
from utils.match_utils import extract_iso_date_from_anpfiff, parse_saison_datum
from utils.saison_utils import saison_start_jahr, saison_fuer_datum, parse_deutsches_datum, saison_zeitraum

logger = setup_logger("main")


def persist_matches(user_id: int, matches_data: List[dict], vollstaendig: bool = True) -> int:
    """
    Writes a scrape result to the database.

    The expense rates and the km rate are frozen here: they apply from the
    first time a match is seen and are not touched again by later scrapes, so
    that a change to the expense regulations does not retroactively rewrite a
    statement that has already been submitted.

    Matches that are no longer in the assignment list are marked instead of
    deleted - otherwise the entered kilometres would disappear with them.

    Args:
        vollstaendig: Whether the scrape captured all assignments. Only then
            may "not in the result" be taken to mean "no longer assigned". The
            scraper skips individual matches whose data cannot be processed;
            without this distinction the user would see perfectly valid
            assignments displayed as withdrawn.

    Returns:
        Number of saved matches.
    """
    seen_ids = []
    saved = 0

    for match_data in matches_data:
        try:
            spiel_info = match_data.get('spiel_info', {}) or {}
            datum = extract_iso_date_from_anpfiff(spiel_info.get('anpfiff', ''))

            sr_spesen, sra_spesen = calculate_spesen(
                spiel_info.get('spielklasse', ''),
                spiel_info.get('mannschaftsart', ''),
                spiel_info.get('staffel', ''),
                spiel_info.get('heim_team', ''),
                spiel_info.get('gast_team', '')
            )

            seen_ids.append(
                upsert_match(user_id, match_data, datum, sr_spesen, sra_spesen, KM_SATZ_EURO)
            )
            saved += 1

        except Exception as e:
            logger.error(f"Spiel konnte nicht gespeichert werden: {e}")
            continue

    if seen_ids and vollstaendig:
        markiert = mark_missing_matches(user_id, [], seen_ids=seen_ids)
        if markiert:
            logger.info(f"{markiert} Spiele nicht mehr in der Ansetzung - markiert")
    elif seen_ids:
        logger.warning(
            "Scrape war unvollstaendig - es wird kein Spiel als zurueckgezogen markiert"
        )

    logger.info(f"{saved}/{len(matches_data)} Spiele in der Datenbank")
    return saved


def persist_stammdaten(user_id: int, stammdaten: dict) -> None:
    """
    Writes a user's own master data (Stammdaten) to the database.

    Errors are only logged: the assignments are the product, the master data
    is a side feature. They must not make a run fail after the matches have
    already been written successfully.

    An empty result is skipped instead of saved. Otherwise the upsert would
    create a row of nothing but empty strings, and the tab would show the user
    an empty table instead of the hint that nothing has been fetched yet.
    """
    if not any(stammdaten.values()):
        logger.warning("Keine Stammdaten gelesen - nichts zu speichern")
        return

    try:
        upsert_stammdaten(user_id, stammdaten)
        gefuellt = sum(1 for wert in stammdaten.values() if wert)
        logger.info(f"Stammdaten gespeichert ({gefuellt} Felder)")
    except Exception as e:
        logger.error(f"Stammdaten konnten nicht gespeichert werden: {e}")


def persist_saisons(user_id: int, saisons: dict) -> int:
    """
    Writes the seasons that were read to the database - each one replacing
    its previous contents.

    A season that was read incompletely is NOT written. The tables are emptied
    and refilled per season; with a partial result the good stored data would
    be destroyed. It is better to leave the old state in place until the next
    run reads the season cleanly.

    Returns:
        Number of replaced seasons.
    """
    ersetzt = 0

    for saison, daten in saisons.items():
        if not daten.get("vollstaendig"):
            logger.warning(f"Saison {saison} unvollstaendig gelesen - bleibt unveraendert")
            continue

        # A stored season with matches is never replaced by an empty one. That
        # would be a display glitch in DFBnet and not a withdrawal of all
        # matches - the stored data would be lost.
        if not daten.get("spiele") and count_saison_spiele(user_id, saison):
            logger.warning(f"Saison {saison} leer gelesen, gespeichert sind Spiele - bleibt unveraendert")
            continue

        try:
            spiele = []
            for roh in daten.get("spiele", []):
                datum, uhrzeit = parse_saison_datum(roh.get("datum_text", ""))
                gespann = roh.get("gespann") or []
                eigene = next((p.get("rolle", "") for p in gespann if p.get("selbst")), "")

                spiele.append({
                    "datum": datum,
                    "uhrzeit": uhrzeit,
                    "liga": roh.get("liga", ""),
                    "heim": roh.get("heim", ""),
                    "gast": roh.get("gast", ""),
                    "ergebnis": roh.get("ergebnis", ""),
                    "heim_gelb": roh.get("heim_gelb"),
                    "heim_gelbrot": roh.get("heim_gelbrot"),
                    "heim_rot": roh.get("heim_rot"),
                    "gast_gelb": roh.get("gast_gelb"),
                    "gast_gelbrot": roh.get("gast_gelbrot"),
                    "gast_rot": roh.get("gast_rot"),
                    "eigene_rolle": eigene,
                    "gespann": gespann,
                })

            geschrieben = replace_saison(
                user_id,
                saison,
                spiele=spiele,
                einsaetze=daten.get("einsaetze", []),
                lehrgaenge=daten.get("lehrgaenge", {}),
                erwartet=daten.get("erwartet"),
                vollstaendig=True,
            )
            ersetzt += 1
            logger.info(f"Saison {saison}: {geschrieben} Spiele gespeichert")

        except Exception as e:
            logger.error(f"Saison {saison} konnte nicht gespeichert werden: {e}")
            continue

    logger.info(f"{ersetzt}/{len(saisons)} Saisons in der Datenbank")
    return ersetzt


def waehle_beobachtungs_saisons(angebotene: List[str], schiedsrichter_seit: str, fertig: set) -> List[str]:
    """
    The seasons whose observations (Beobachtungen) need to be read.

    From the season in which the person became a referee onwards - before
    that there cannot be any observation. If the date is still unknown (first
    fetch, the master data is only read later in the run), all offered seasons
    are read; this happens exactly once, after which the completed ones count
    as done.
    """
    seit = parse_deutsches_datum(schiedsrichter_seit)
    erste = saison_start_jahr(saison_fuer_datum(seit)) if seit else None

    return [
        saison for saison in angebotene
        if saison not in fertig
        and (erste is None or (saison_start_jahr(saison) or 0) >= erste)
    ]


def persist_beobachtungen(user_id: int, beobachtungen: dict) -> int:
    """
    Writes the observations that were read - replacing per source and season.

    As with the seasons: anything read incompletely is left untouched, and a
    stored season with grades is never replaced by an empty one. Either would
    be a display glitch in DFBnet, not a disappearance of the observations.

    Returns:
        Number of replaced seasons.
    """
    ersetzt = 0

    for quelle, saisons in beobachtungen.items():
        for saison, daten in saisons.items():
            if not daten.get("vollstaendig"):
                logger.warning(f"Beobachtungen {quelle} {saison} unvollstaendig - bleiben unveraendert")
                continue

            liste = daten.get("beobachtungen") or []
            if not liste and count_beobachtungen(user_id, quelle, saison):
                logger.warning(
                    f"Beobachtungen {quelle} {saison} leer gelesen, gespeichert sind welche - "
                    "bleiben unveraendert"
                )
                continue

            try:
                replace_beobachtungs_saison(user_id, quelle, saison, liste)
                ersetzt += 1
            except Exception as e:
                logger.error(f"Beobachtungen {quelle} {saison} nicht gespeichert: {e}")

    logger.info(f"{ersetzt} Beobachtungs-Saisons in der Datenbank")
    return ersetzt


# How long after the match a stored report is still re-read.
# Special reports, expense documents and corrections often arrive days later.
BERICHT_NACHLAUF_TAGE = 30

# How long to wait for a report to be released (Freigabe). Indoor tournaments
# and some friendlies never get a released report; without this limit their
# season would never count as finished and would be read every night.
FREIGABE_WARTEN_TAGE = 60


def braucht_bericht(zeile: dict, gespeichert: dict, heute: Optional[date] = None) -> bool:
    """New, or still so recent that DFBnet may have added something."""
    if zeile.get("dfb_spiel_id") not in gespeichert:
        return True
    heute = heute or date.today()
    try:
        return date.fromisoformat(zeile.get("datum") or "") >= heute - timedelta(days=BERICHT_NACHLAUF_TAGE)
    except ValueError:
        return False


def persist_spielberichte(user_id: int, ergebnis: dict, heute: Optional[date] = None) -> int:
    """
    Writes the match reports (Spielberichte) that were read and remembers
    finished seasons.

    A season is finished when it is over (plus the follow-up period), every
    released report is stored and none is still waiting for its release. Then
    its assignment schedule (Einsatzplan) is no longer read.

    Returns:
        Number of saved reports.
    """
    heute = heute or date.today()
    saisons = ergebnis.get("saisons") or {}
    berichte = ergebnis.get("berichte") or {}

    saison_von = {}
    for saison, daten in saisons.items():
        for zeile in daten.get("zeilen") or []:
            if zeile.get("dfb_spiel_id"):
                saison_von.setdefault(zeile["dfb_spiel_id"], saison)

    gespeichert = 0
    for spiel_id, bericht in berichte.items():
        zeile = bericht["zeile"]
        try:
            saison = saison_von.get(spiel_id) or saison_fuer_datum(date.fromisoformat(zeile["datum"]))
            speichere_bericht(user_id, saison, zeile, bericht["daten"], bericht.get("dateien") or {})
            gespeichert += 1
        except Exception as e:
            logger.error(f"Spielbericht {zeile.get('datum')} {zeile.get('heim')} nicht gespeichert: {e}")

    vorhanden = set(get_gespeicherte_berichte(user_id))
    for saison, daten in saisons.items():
        zeilen = daten.get("zeilen") or []
        lesbar = [z for z in zeilen if ist_lesbar(z, heute)]
        fehlend = [z for z in lesbar if z["dfb_spiel_id"] not in vorhanden]
        wartend = [
            z for z in zeilen
            if wartet_auf_freigabe(z, heute)
            and (z.get("datum") or "") >= (heute - timedelta(days=FREIGABE_WARTEN_TAGE)).isoformat()
        ]

        zeitraum = saison_zeitraum(saison)
        vorbei = bool(zeitraum) and zeitraum[1] + timedelta(days=BERICHT_NACHLAUF_TAGE) < heute

        try:
            setze_saison(user_id, saison, len(lesbar), vorbei and not fehlend and not wartend)
        except Exception as e:
            logger.error(f"Spielbericht-Saison {saison} nicht vermerkt: {e}")

        if fehlend or wartend:
            logger.info(
                f"Spielberichte {saison}: {len(fehlend)} nicht gelesen, {len(wartend)} ohne Freigabe"
            )

    logger.info(f"{gespeichert}/{len(berichte)} Spielberichte in der Datenbank")
    return gespeichert


def persist_spielnummern(user_id: int, ergebnis: dict) -> int:
    """
    Enters the match identifiers (Spielkennungen) from the assignment
    schedule (Einsatzplan) into the assignments - they appear on the expense
    receipts (TFV and NOFV).

    Runs after persist_matches so that matches that were only just created
    also get their identifier. Errors are only logged, as with all side
    features.
    """
    eintraege = []
    for daten in (ergebnis.get("saisons") or {}).values():
        for zeile in daten.get("zeilen") or []:
            eintraege.append({
                "spielkennung": spielkennung(zeile),
                "dfb_spiel_id": zeile.get("dfb_spiel_id"),
                "datum": zeile.get("datum"),
                "uhrzeit": zeile.get("uhrzeit"),
                "heim": zeile.get("heim"),
                "gast": zeile.get("gast"),
            })
    # The report that was read is the most accurate source
    for spiel_id, bericht in (ergebnis.get("berichte") or {}).items():
        eintraege.append({
            "spielkennung": (bericht.get("daten") or {}).get("spielkennung"),
            "dfb_spiel_id": spiel_id,
        })

    try:
        gesetzt = setze_spielnummern(user_id, eintraege)
        if gesetzt:
            logger.info(f"Spielkennung bei {gesetzt} Spielen eingetragen")
        return gesetzt
    except Exception as e:
        logger.error(f"Spielkennungen konnten nicht eingetragen werden: {e}")
        return 0


def scrape_matches(
    username: Optional[str] = None,
    password: Optional[str] = None,
    user_id: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[dict]:
    """
    Scrapes all assignments of the user and writes them to the database.

    The result used to be additionally placed as spesen_data.json in a session
    folder, and a DOCX and a PDF were generated from it right away. Both are
    gone: the database is the source of truth, documents are only generated on
    download.

    Args:
        username: DFB.net username (otherwise from ENV - for development only)
        password: DFB.net password (otherwise from ENV - for development only)
        user_id: User who owns the matches
        progress_callback: called as (current, total, step)

    Returns:
        The scraped matches (may be empty, e.g. during the winter break).
    """
    logger.info("=== DFB Scraper: Sammle alle Spieldaten ===")

    dfb_username = username or os.getenv("DFB_USERNAME")
    dfb_password = password or os.getenv("DFB_PASSWORD")

    if not dfb_username or not dfb_password:
        logger.error("DFB Credentials fehlen - weder als Parameter noch in ENV")
        return []

    def melde(current: int, total: int, step: str) -> None:
        if progress_callback:
            progress_callback(current, total, step)

    with DFBScraper(headless=True, username=dfb_username, password=dfb_password) as scraper:
        melde(0, 0, "Login und Navigation...")

        scraper.open_dfbnet()
        scraper.accept_cookies()
        scraper.click_login()
        scraper.accept_cookies()
        scraper.click_login()
        scraper.login()

        # login() raises on rejected credentials; at this point DFBnet has
        # accepted them. If the fetch fails afterwards for another reason, the
        # credentials are still fine.
        if user_id is not None:
            dfb_login_angenommen(user_id)

        scraper.open_menu_if_needed()

        def fortschritt(current, total, step):
            melde(current, total, step)
            logger.info(f"Progress: {current}/{total} - {step}")

        scraper.navigate_to_schiriansetzung()

        all_matches = scraper.scrape_all_matches(progress_callback=fortschritt)

        # If the scraper skipped individual matches, the result is incomplete
        # and is no basis for "no longer assigned"
        erwartet = getattr(scraper, "erwartete_spiele", len(all_matches))
        vollstaendig = len(all_matches) >= erwartet

        if not vollstaendig:
            logger.warning(
                f"Nur {len(all_matches)} von {erwartet} Ansetzungen gelesen - "
                "unvollstaendiger Scrape"
            )

        # Master data and seasons come, like the assignments, through the
        # interface of the assignment app, in the same logged-in tab.
        #
        # The separate try/except that only warns is load-bearing:
        # persist_matches only runs after the with block. An exception here
        # would escape from scrape_matches, and not a single match would be
        # saved - a whole nightly run lost because DFBnet moved a master data
        # field.
        stammdaten = {}

        try:
            melde(len(all_matches), erwartet, "Lese Stammdaten...")

            stammdaten = scraper.lies_stammdaten()

        except Exception as e:
            logger.warning(f"Stammdaten konnten nicht gelesen werden: {e}")

        # And the season summary. It also gets its own try/except: it runs
        # over all seasons, but the assignments are the product and must not
        # fail because of it.
        saisons = {}

        try:
            melde(len(all_matches), erwartet, "Lese Saisonzusammenfassung...")

            # Completed seasons no longer change - whatever is stored completely
            # in the database is not read again. The scraper itself takes the
            # current season back out of the list.
            fertig = get_komplette_saisons(user_id) if user_id is not None else set()

            saisons = scraper.scrape_saisons(
                progress_callback=fortschritt, ueberspringen=fertig
            )

        except Exception as e:
            logger.warning(f"Saisonzusammenfassung konnte nicht gelesen werden: {e}")

        # Last of all, the observations from the old DFBnet modules
        # (Schiri-Beobachtung, Schiri-Portal). Deliberately the last step:
        # these modules keep their state in the session, and when they ran
        # before the Schiriansetzung, its menu no longer opened afterwards -
        # the entire fetch was lost. Like everything after the assignments,
        # with its own try/except.
        beobachtungen = {}

        try:
            melde(len(all_matches), erwartet, "Lese Beobachtungen...")

            # Freshly read, otherwise the state from the last fetch
            schiedsrichter_seit = stammdaten.get("schiedsrichter_seit") or ""
            if not schiedsrichter_seit and user_id is not None:
                schiedsrichter_seit = (get_stammdaten(user_id) or {}).get("schiedsrichter_seit") or ""

            def saisons_fuer(quelle, angebotene):
                fertig = (
                    get_fertige_beobachtungs_saisons(user_id, quelle)
                    if user_id is not None else set()
                )
                return waehle_beobachtungs_saisons(angebotene, schiedsrichter_seit, fertig)

            beobachtungen = scraper.scrape_beobachtungen(
                saisons_fuer=saisons_fuer, progress_callback=fortschritt
            )

        except Exception as e:
            logger.warning(f"Beobachtungen konnten nicht gelesen werden: {e}")

        # Then the match reports - they too go through the old form modules and
        # therefore come after the Schiriansetzung. They are only ever read;
        # anything that could change something in DFBnet cannot even be called
        # by the scraper.
        spielberichte = {}

        try:
            melde(len(all_matches), erwartet, "Lese Spielberichte...")

            gespeicherte_berichte = get_gespeicherte_berichte(user_id) if user_id is not None else {}
            vorhandene_dokumente = get_dokument_ids(user_id) if user_id is not None else set()
            fertige_bericht_saisons = get_fertige_bericht_saisons(user_id) if user_id is not None else set()

            seit = stammdaten.get("schiedsrichter_seit") or ""
            if not seit and user_id is not None:
                seit = (get_stammdaten(user_id) or {}).get("schiedsrichter_seit") or ""

            spielberichte = scraper.scrape_spielberichte(
                saisons_fuer=lambda angebotene: waehle_beobachtungs_saisons(
                    angebotene, seit, fertige_bericht_saisons
                ),
                braucht_bericht=lambda zeile: braucht_bericht(zeile, gespeicherte_berichte),
                dokument_vorhanden=lambda dok_id: dok_id in vorhandene_dokumente,
                progress_callback=fortschritt,
            )

        except Exception as e:
            logger.warning(f"Spielberichte konnten nicht gelesen werden: {e}")

    if user_id is not None:
        persist_matches(user_id, all_matches, vollstaendig=vollstaendig)
        persist_stammdaten(user_id, stammdaten)
        persist_saisons(user_id, saisons)
        persist_beobachtungen(user_id, beobachtungen)
        if spielberichte:
            persist_spielberichte(user_id, spielberichte)
            persist_spielnummern(user_id, spielberichte)

    logger.info(f"Erfolgreich {len(all_matches)} Spiele gescrapt")
    return all_matches


def main():
    """
    Starts the FastAPI backend application.
    The frontend runs separately with the Vite dev server.
    """
    import uvicorn

    # Load port and host from environment variables
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8001"))  # Default: 8001 instead of 8000

    logger.info("Starte Spesenfuchs API...")
    logger.info("==============================================")
    logger.info(f"API läuft auf: http://{API_HOST}:{API_PORT}")
    logger.info("==============================================")

    # Start the API
    uvicorn.run(
        "api.main_api:app",
        host=API_HOST,
        port=API_PORT,
        reload=False  # reload=False in Docker!
    )


if __name__ == "__main__":
    main()