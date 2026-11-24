"""
Eigene Stammdaten und QMax-Werte ueber die Schnittstelle der Ansetzungs-App.

Frueher wurden dafuer zwei Reiter angeklickt und deren Karten ausgelesen.
Die Karten zeigen aber nur, was die App aus wenigen Abrufen formatiert:

- referee/<id>                     - Kontakt- und Meldedaten, Status
- referee-id-card/<id>             - Ausweis und Foto
- referee/<id>/additional-qualification - Zusatzausbildungen
- referee/<id>/qualification       - die QMax-Werte je Rolle

Die Texte ("gueltig bis ...", "noch 825 Tage", "genehmigt", "aktiv", der
FUSSBALL.DE-Satz) und die Regeln dafuer stammen aus dem Quelltext der App
(24.11.2026), damit die gespeicherten Werte gleich bleiben. "-" steht wie
auf der Karte fuer "wirklich leer"; ein Feld, das nicht gelesen werden
konnte, bleibt dagegen weg - der Upsert behaelt dann den alten Wert.
"""
from datetime import date
from typing import Dict, Optional

from playwright.sync_api import Page

from scraper.sria_api import abruf, datum_de, text
from utils.logger import setup_logger

logger = setup_logger("stammdaten")

_FOTO_STATUS = {
    "EXPIRED": "veraltet",
    "REJECTED": "abgelehnt",
    "APPROVED": "genehmigt",
    "PENDING": "ungeprüft",
    "NOT_AVAILABLE": "nicht vorhanden",
}

_SR_STATUS = {
    "ACTIVE": "aktiv",
    "LEFT": "ausgeschieden",
    "LAID_OFF": "entlassen",
    "DECEASED": "verstorben",
    "NEWCOMER": "Neuzugang",
    "PASSIVE": "passiv",
}

_ZUSATZ = {"FUTSAL": "Futsal", "MENTOR": "Pate"}

_FUSSBALL_DE = {
    True: "Einsätze werden auf FUSSBALL.DE nicht veröffentlicht.",
    False: "Einsätze werden auf FUSSBALL.DE veröffentlicht.",
}

_QMAX = {
    "qmax_sr": "maxQualificationAsReferee",
    "qmax_sra1": "maxQualificationAsAssistant1",
    "qmax_sra2": "maxQualificationAsAssistant2",
    "qmax_beobachter": "maxQualificationAsObserver",
}


def _oder_strich(wert) -> str:
    return text(wert) or "-"


def _plz_ort(plz, ort) -> str:
    return " ".join(t for t in (text(plz), text(ort)) if t)


def kontakt_und_meldedaten(schiri: Dict) -> Dict:
    nachname, vorname = text(schiri.get("lastName")), text(schiri.get("firstName"))
    return {
        "name_vorname": ", ".join(t for t in (nachname, vorname) if t),
        "strasse": _oder_strich(schiri.get("street")),
        "plz_ort": _oder_strich(_plz_ort(schiri.get("zipCode"), schiri.get("city"))),
        "geburtsdatum": _oder_strich(datum_de(schiri.get("dateOfBirth"))),
        "email": _oder_strich(schiri.get("email")),
        "telefon_privat": _oder_strich(schiri.get("phoneNumberPrivate")),
        "telefon_geschaeftlich": _oder_strich(schiri.get("phoneNumberBusiness")),
        "telefon_mobil": _oder_strich(schiri.get("phoneNumberMobile")),
        "sr_gebiet": _oder_strich((schiri.get("coreArea") or {}).get("name")),
        "schiedsrichter_seit": _oder_strich(datum_de(schiri.get("refereeSince"))),
        "verein": _oder_strich((schiri.get("coreClub") or {}).get("name")),
        # Wie die Karte: 0 Fehlmonate erscheinen als "-"
        "fehlmonate": str(schiri["absentMonths"]) if schiri.get("absentMonths") else "-",
        "patensystem_am": _oder_strich(datum_de(schiri.get("mentoringFinishedAt"))),
        "kreditor_nr": _oder_strich(schiri.get("creditorNumber")),
        "debitor_nr": _oder_strich(schiri.get("debitorNumber")),
        "status": _SR_STATUS.get(schiri.get("status"), text(schiri.get("status"))),
        "umsatzsteuerpflichtig": "Ja" if schiri.get("subjectToVat") else "Nein",
        "bemerkung": _oder_strich(schiri.get("comment")),
        "fussball_de_hinweis": _FUSSBALL_DE[bool(schiri.get("suppressPublicationOfMatches"))],
    }


def ausweis(karte: Dict, heute: date) -> Dict:
    """
    Wie getValidUntil/getPhotoValidUntil der App: "gueltig bis" nur bei
    genehmigtem Foto, sonst "Laufzeit bis"; nach Ablauf "abgelaufen am".
    """
    status = karte.get("photoStatus")
    gueltig = karte.get("validUntil")
    foto_gueltig = karte.get("photoValidUntil")

    ergebnis = {
        "ausweisnummer": _oder_strich(karte.get("cardNumber")),
        "foto_status": _FOTO_STATUS.get(status, text(status)) or "-",
    }

    if gueltig and status:
        if date.fromisoformat(gueltig[:10]) > heute:
            vorlage = "gültig bis {}" if status == "APPROVED" else "Laufzeit bis {}"
        else:
            vorlage = "abgelaufen am {}"
        ergebnis["ausweisgueltigkeit"] = vorlage.format(datum_de(gueltig))
    else:
        ergebnis["ausweisgueltigkeit"] = "-"

    if foto_gueltig:
        ende = date.fromisoformat(foto_gueltig[:10])
        ergebnis["foto_gueltigkeit"] = (
            f"noch {(ende - heute).days} Tage" if ende > heute else f"abgelaufen am {datum_de(foto_gueltig)}"
        )
    else:
        ergebnis["foto_gueltigkeit"] = "-"

    return ergebnis


def zusatzausbildungen(daten: Dict) -> Dict:
    vorhanden = set((daten or {}).get("additionalQualifications") or [])
    namen = [name for schluessel, name in _ZUSATZ.items() if schluessel in vorhanden]
    return {"zusatzausbildungen": ", ".join(namen) or "-"}


def qmax(daten: Dict) -> Dict:
    daten = daten or {}
    return {feld: text((daten.get(quelle) or {}).get("name")) for feld, quelle in _QMAX.items()}


def lies_stammdaten(page: Page, schiri_id: str, heute: Optional[date] = None) -> Dict:
    """
    Stammdaten samt QMax in den Schluesseln von db/stammdaten.py.

    Jeder Teil wird fuer sich gelesen: faellt einer aus, fehlen nur seine
    Felder.
    """
    heute = heute or date.today()
    teile = [
        (f"referee/{schiri_id}", kontakt_und_meldedaten),
        (f"referee-id-card/{schiri_id}", lambda d: ausweis(d, heute)),
        (f"referee/{schiri_id}/additional-qualification", zusatzausbildungen),
        (f"referee/{schiri_id}/qualification", qmax),
    ]

    stammdaten = {}
    for pfad, aufbereiten in teile:
        try:
            stammdaten.update(aufbereiten(abruf(page, "GET", pfad) or {}))
        except Exception as e:
            logger.warning(f"Stammdaten aus {pfad.split('/')[0]} nicht gelesen: {e}")

    gefuellt = sum(1 for wert in stammdaten.values() if wert)
    logger.info(f"Stammdaten: {gefuellt}/{len(stammdaten)} Felder")
    return stammdaten
