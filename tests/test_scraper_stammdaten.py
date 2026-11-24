"""
Master data and QMax from the interface - without a browser (data invented).

The texts must look exactly as the app's cards showed them:
that is how they are stored in the database.
"""
from datetime import date

import pytest

from scraper.stammdaten import ausweis, kontakt_und_meldedaten, lies_stammdaten, qmax, zusatzausbildungen
from test_scraper_ansetzungen import Seite, ok

HEUTE = date(2026, 11, 23)

SCHIRI = {
    "id": "SCHIRI42", "title": None, "firstName": "Erika", "lastName": "Pfeife",
    "phoneNumberMobile": "0151 000", "phoneNumberPrivate": None, "phoneNumberBusiness": None,
    "email": "erika@example.org", "street": "Musterweg 1", "zipCode": "99999", "city": "Beispielstadt",
    "dateOfBirth": "2006-06-11", "coreArea": {"name": "Kreis Mittelthüringen"},
    "coreClub": {"name": "FC Beispiel e.V."}, "status": "ACTIVE", "refereeSince": "2019-01-26",
    "absentMonths": 0, "suppressPublicationOfMatches": False, "mentoringFinishedAt": None,
    "subjectToVat": False, "debitorNumber": None, "creditorNumber": "4711", "comment": None,
}

KARTE = {"cardNumber": "A123", "photoStatus": "APPROVED",
         "photoValidUntil": "2029-02-25", "validUntil": "2027-06-30"}

QUALIFIKATION = {
    "maxQualificationAsReferee": {"id": "71", "name": "Oberliga"},
    "maxQualificationAsAssistant1": {"id": "70", "name": "Regionalliga Nordost"},
    "maxQualificationAsAssistant2": {"id": "70", "name": "Regionalliga Nordost"},
    "maxQualificationAsObserver": None,
    "qualifications": [],
}


class TestKontaktUndMeldedaten:
    def test_wie_auf_der_karte(self):
        assert kontakt_und_meldedaten(SCHIRI) == {
            "name_vorname": "Pfeife, Erika",
            "strasse": "Musterweg 1",
            "plz_ort": "99999 Beispielstadt",
            "geburtsdatum": "11.06.2006",
            "email": "erika@example.org",
            "telefon_privat": "-",
            "telefon_geschaeftlich": "-",
            "telefon_mobil": "0151 000",
            "sr_gebiet": "Kreis Mittelthüringen",
            "schiedsrichter_seit": "26.01.2019",
            "verein": "FC Beispiel e.V.",
            "fehlmonate": "-",
            "patensystem_am": "-",
            "kreditor_nr": "4711",
            "debitor_nr": "-",
            "status": "aktiv",
            "umsatzsteuerpflichtig": "Nein",
            "bemerkung": "-",
            "fussball_de_hinweis": "Einsätze werden auf FUSSBALL.DE veröffentlicht.",
        }

    def test_andere_werte(self):
        daten = kontakt_und_meldedaten({**SCHIRI, "absentMonths": 2, "status": "PASSIVE",
                                        "subjectToVat": True, "mentoringFinishedAt": "2021-03-04",
                                        "suppressPublicationOfMatches": True})
        assert daten["fehlmonate"] == "2"
        assert daten["status"] == "passiv"
        assert daten["umsatzsteuerpflichtig"] == "Ja"
        assert daten["patensystem_am"] == "04.03.2021"
        assert daten["fussball_de_hinweis"] == "Einsätze werden auf FUSSBALL.DE nicht veröffentlicht."

    def test_unbekannter_status_bleibt_lesbar(self):
        assert kontakt_und_meldedaten({**SCHIRI, "status": "NEU"})["status"] == "NEU"


class TestAusweis:
    def test_genehmigtes_foto(self):
        assert ausweis(KARTE, HEUTE) == {
            "ausweisnummer": "A123",
            "foto_status": "genehmigt",
            "ausweisgueltigkeit": "gültig bis 30.06.2027",
            "foto_gueltigkeit": "noch 825 Tage",
        }

    @pytest.mark.parametrize("status, text", [
        ("PENDING", "ungeprüft"), ("REJECTED", "abgelehnt"), ("EXPIRED", "veraltet"),
    ])
    def test_ohne_genehmigtes_foto_laufzeit(self, status, text):
        daten = ausweis({**KARTE, "photoStatus": status}, HEUTE)
        assert daten["foto_status"] == text
        assert daten["ausweisgueltigkeit"] == "Laufzeit bis 30.06.2027"

    def test_abgelaufen(self):
        daten = ausweis({**KARTE, "validUntil": "2026-06-30", "photoValidUntil": "2026-11-23"}, HEUTE)
        assert daten["ausweisgueltigkeit"] == "abgelaufen am 30.06.2026"
        assert daten["foto_gueltigkeit"] == "abgelaufen am 23.11.2026"

    def test_ohne_angaben(self):
        assert ausweis({}, HEUTE) == {"ausweisnummer": "-", "foto_status": "-",
                                      "ausweisgueltigkeit": "-", "foto_gueltigkeit": "-"}


class TestZusatzUndQmax:
    @pytest.mark.parametrize("liste, text", [
        (["MENTOR", "FUTSAL"], "Futsal, Pate"), (["FUTSAL"], "Futsal"), ([], "-"),
    ])
    def test_zusatzausbildungen(self, liste, text):
        assert zusatzausbildungen({"additionalQualifications": liste}) == {"zusatzausbildungen": text}

    def test_qmax(self):
        assert qmax(QUALIFIKATION) == {"qmax_sr": "Oberliga", "qmax_sra1": "Regionalliga Nordost",
                                       "qmax_sra2": "Regionalliga Nordost", "qmax_beobachter": ""}


class TestLiesStammdaten:
    def test_alles_zusammen(self):
        seite = Seite({
            "referee/SCHIRI42": ok(SCHIRI),
            "referee-id-card/SCHIRI42": ok(KARTE),
            "referee/SCHIRI42/additional-qualification": ok({"additionalQualifications": ["FUTSAL"]}),
            "referee/SCHIRI42/qualification": ok(QUALIFIKATION),
        })

        daten = lies_stammdaten(seite, "SCHIRI42", heute=HEUTE)

        assert daten["name_vorname"] == "Pfeife, Erika"
        assert daten["foto_gueltigkeit"] == "noch 825 Tage"
        assert daten["zusatzausbildungen"] == "Futsal"
        assert daten["qmax_sr"] == "Oberliga"

    def test_ein_teil_faellt_aus(self):
        seite = Seite({
            "referee/SCHIRI42": ok(SCHIRI),
            "referee-id-card/SCHIRI42": {"status": 404},
            "referee/SCHIRI42/additional-qualification": ok({}),
            "referee/SCHIRI42/qualification": ok(QUALIFIKATION),
        })

        daten = lies_stammdaten(seite, "SCHIRI42", heute=HEUTE)

        # What was not read is missing - the upsert keeps the old value
        assert "ausweisgueltigkeit" not in daten
        assert daten["verein"] == "FC Beispiel e.V."
