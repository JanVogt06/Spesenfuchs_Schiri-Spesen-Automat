"""
Observations from Schiri-Beobachtung and Schiri-Portal - without a browser.

The old DFBnet form pages are imitated by FormularSeite: it remembers the
form values that were set, runs the search on "Suchen" and delivers the
result list the way _LISTE_JS would return it in the browser.
"""
from contextlib import contextmanager

import pytest

from scraper import beobachtungen as b
from scraper.beobachtungen import (
    eigene_beobachtung,
    finde_module,
    lies_quelle,
    lies_saison,
    oeffne_liste,
    parse_note,
    suche,
)

MODUL_URL = "https://www.dfbnet.org/spielplus/mod_sr_beob/webflow.do?event=START"
LISTEN_URL = "https://www.dfbnet.org/spielplus/mod_sr_beob/webflow.do?event=OBSERVATION"


def liste(zeilen=(), treffer=None, seiten=None, weiter=False, fehler="", keine_treffer=False):
    """A result of _LISTE_JS."""
    zeilen = list(zeilen)
    if treffer is None:
        treffer = len(zeilen)
    return {
        "seite": 1 if treffer else None,
        "seiten": seiten if seiten is not None else (1 if treffer else None),
        "treffer": treffer,
        "zeilen": zeilen,
        "weiter": weiter,
        "keine_treffer": keine_treffer,
        "fehler": fehler,
    }


def zeile(datum="14.09.2025", heim="FC Beispielstadt", gast="SV Musterdorf",
          gespann=(("SR", "Muster, Max"), ("SRA1", "Beispiel, Erika"), ("SRA2", "Probe, Paul"),
                   ("BEO", "Pruefer, Hans")),
          noten=("8,4", "8,5", "8,3", ""), status=("freigegeben", "20.09.2025", "18:30")):
    """A row of the result list, as _LISTE_JS delivers it."""
    return {
        "datum": datum,
        "uhrzeit": "15:00",
        "spieltag": "5",
        "staffel": "Verbandsliga",
        "mannschaften": [heim, gast],
        "ergebnis": "2:1",
        "gespann": [{"rolle": r, "name": n} for r, n in gespann],
        "noten": list(noten),
        "status": list(status),
    }


class FormLocator:
    def __init__(self, seite, selektor):
        self.seite = seite
        self.selektor = selektor

    @property
    def first(self):
        return self

    def click(self):
        self.seite.klicks.append(self.selektor)
        if self.selektor == 'input[name="SEARCH"]':
            self.seite.aktiv = list(self.seite.gesetzt)
            self.seite.seite_nr = 0
        elif self.selektor == "input.naviNext":
            self.seite.seite_nr += 1

    def wait_for(self, state=None, timeout=None):
        if not self.seite.formular_da:
            raise TimeoutError("Timeout 5000ms exceeded")

    def inner_text(self):
        return self.seite.text


class FormularSeite:
    """The old DFBnet search form including the result list."""

    def __init__(self, ergebnisse=None, saisons=("26/27", "25/26", "24/25"),
                 listen_link=LISTEN_URL, menue=None):
        # (saison, rolle) -> [Seite 1, Seite 2, ...]
        self.ergebnisse = ergebnisse or {}
        self.saisons = list(saisons)
        self.listen_link = listen_link
        self.menue = menue or {}
        self.gesetzt = None
        self.aktiv = None
        self.seite_nr = 0
        self.klicks = []
        self.gotos = []
        self.suchen = []
        self.formular_da = True
        self.formular_echo = None
        self.text = "Startseite"
        self.url = "about:blank"
        self.bei_goto = None

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append(url)
        self.url = url
        if self.bei_goto:
            self.bei_goto(self, url)

    @contextmanager
    def expect_navigation(self, wait_until=None, timeout=None):
        yield

    def locator(self, selektor):
        return FormLocator(self, selektor)

    def evaluate(self, js, arg=None):
        if js is b._MENUE_JS:
            assert arg == ["Schiri-Beobachtung", "Schiri-Portal"]
            return self.menue
        if js is b._LISTEN_LINK_JS:
            assert arg == "/spielplus/mod_sr_beob"
            return self.listen_link
        if js is b._SAISONS_JS:
            return list(self.saisons)
        if js is b._FORMULAR_SETZEN_JS:
            saison, von, bis, rolle = arg
            if saison not in self.saisons:
                return f"Saison {saison} wird nicht angeboten"
            self.gesetzt = list(arg)
            return ""
        if js is b._FORMULAR_LESEN_JS:
            return self.formular_echo or self.aktiv
        if js is b._LISTE_JS:
            saison, rolle = self.aktiv[0], self.aktiv[3]
            if self.seite_nr == 0:
                self.suchen.append((saison, rolle))
            seiten = self.ergebnisse.get((saison, rolle), [liste(keine_treffer=True)])
            return seiten[self.seite_nr]
        raise AssertionError(f"Unerwartetes Skript: {js[:60]}")


# ===== Grades =====

class TestParseNote:
    @pytest.mark.parametrize("text, note", [
        ("244", 244.0),
        ("8,4", 8.4),
        (" 8,5 ", 8.5),
        ("8.3", 8.3),
        ("", None),
        (None, None),
        ("   ", None),
        ("k.A.", None),
    ])
    def test_parse(self, text, note):
        assert parse_note(text) == note


class TestEigeneBeobachtung:
    def test_note_der_eigenen_rolle(self):
        ergebnis = eigene_beobachtung(zeile(), "SRA1")

        assert ergebnis == {
            "datum": "2025-09-14",
            "uhrzeit": "15:00",
            "spieltag": "5",
            "staffel": "Verbandsliga",
            "heim": "FC Beispielstadt",
            "gast": "SV Musterdorf",
            "ergebnis": "2:1",
            "rolle": "SRA1",
            "note": 8.5,
            "note_text": "8,5",
            "beobachter": "Pruefer, Hans",
            "freigegeben_am": "20.09.2025 18:30",
        }

    def test_zuordnung_ueber_position_nicht_ueber_namen(self):
        # Two people of the same name in the crew: the role is what matters
        z = zeile(gespann=(("SR", "Muster, Max"), ("SRA1", "Muster, Max"), ("SRA2", "Probe, Paul")),
                  noten=("8,1", "8,6", "8,2"))
        assert eigene_beobachtung(z, "SR")["note"] == 8.1
        assert eigene_beobachtung(z, "SRA1")["note"] == 8.6

    @pytest.mark.parametrize("status", [
        ("in Bearbeitung",),
        (),
        ("",),
    ])
    def test_nicht_freigegeben(self, status):
        assert eigene_beobachtung(zeile(status=status), "SR") is None

    def test_freigegeben_unabhaengig_von_schreibweise(self):
        assert eigene_beobachtung(zeile(status=(" Freigegeben ",)), "SR")["freigegeben_am"] == ""

    def test_rolle_nicht_im_gespann(self):
        assert eigene_beobachtung(zeile(), "4OF") is None

    def test_ohne_note(self):
        assert eigene_beobachtung(zeile(noten=("8,4", "", "8,3")), "SRA1") is None
        assert eigene_beobachtung(zeile(noten=("8,4",)), "SRA2") is None

    def test_ohne_beobachter_und_gast(self):
        z = zeile(gespann=(("SR", "Muster, Max"),), noten=("244",))
        z["mannschaften"] = ["FC Turnier"]
        ergebnis = eigene_beobachtung(z, "SR")
        assert ergebnis["beobachter"] == ""
        assert ergebnis["gast"] == ""
        assert ergebnis["note"] == 244.0


# ===== Modules and list =====

class TestFindeModule:
    def test_nur_vorhandene_module(self):
        seite = FormularSeite(menue={"Schiri-Beobachtung": MODUL_URL})
        assert finde_module(seite) == {"herren": MODUL_URL}

    def test_beide_module(self):
        seite = FormularSeite(menue={"Schiri-Beobachtung": MODUL_URL, "Schiri-Portal": "https://x/portal"})
        assert finde_module(seite) == {"herren": MODUL_URL, "portal": "https://x/portal"}

    @pytest.mark.parametrize("menue", [{}, None, {"Schiri-Portal": ""}])
    def test_keine_module(self, menue):
        seite = FormularSeite()
        seite.menue = menue
        assert finde_module(seite) == {}


class TestOeffneListe:
    def test_ueber_menuepunkt(self):
        seite = FormularSeite(listen_link=LISTEN_URL + "&x=1")
        assert oeffne_liste(seite, MODUL_URL) == LISTEN_URL + "&x=1"
        assert seite.gotos == [MODUL_URL, LISTEN_URL + "&x=1"]

    def test_ohne_menuepunkt_direkt(self):
        seite = FormularSeite(listen_link=None)
        assert oeffne_liste(seite, MODUL_URL) == LISTEN_URL
        assert seite.gotos[-1] == LISTEN_URL

    def test_fehlerseite_statt_formular(self):
        seite = FormularSeite()
        seite.formular_da = False
        seite.text = "Die aufgerufene   Seite ist\nungueltig " + "x" * 400

        with pytest.raises(RuntimeError) as fehler:
            oeffne_liste(seite, MODUL_URL)

        meldung = str(fehler.value)
        assert "Kein Suchformular auf /spielplus/mod_sr_beob/webflow.do" in meldung
        assert "Die aufgerufene Seite ist ungueltig" in meldung
        # No query string (session data) and not the whole page in the log
        assert "event=" not in meldung
        assert len(meldung) < 400


# ===== Search =====

class TestSuche:
    def test_setzt_saisonzeitraum_und_rolle(self):
        seite = FormularSeite({("25/26", "2"): [liste([zeile()])]})

        ergebnis = suche(seite, "25/26", "2")

        assert seite.gesetzt == ["25/26", "01.07.2025", "30.06.2026", "2"]
        assert seite.klicks == ['input[name="SEARCH"]']
        assert ergebnis == {"zeilen": [zeile()], "treffer": 1, "vollstaendig": True}

    def test_keine_treffer_ist_kein_fehler(self):
        seite = FormularSeite({("25/26", ""): [liste(keine_treffer=True)]})

        assert suche(seite, "25/26", "") == {"zeilen": [], "treffer": 0, "vollstaendig": True}

    def test_blaettert(self):
        seite1 = [zeile(datum=f"{t:02d}.09.2025") for t in range(1, 21)]
        seite2 = [zeile(datum="21.09.2025"), zeile(datum="22.09.2025")]
        seite = FormularSeite({("25/26", ""): [
            liste(seite1, treffer=22, seiten=2, weiter=True),
            liste(seite2, treffer=22, seiten=2, weiter=False),
        ]})

        ergebnis = suche(seite, "25/26", "")

        assert len(ergebnis["zeilen"]) == 22
        assert ergebnis["vollstaendig"] is True
        assert seite.klicks == ['input[name="SEARCH"]', "input.naviNext"]

    def test_ohne_weiter_knopf_unvollstaendig(self):
        seite = FormularSeite({("25/26", ""): [
            liste([zeile()] * 20, treffer=25, seiten=2, weiter=False),
        ]})

        ergebnis = suche(seite, "25/26", "")

        assert ergebnis["vollstaendig"] is False
        assert seite.klicks == ['input[name="SEARCH"]']

    def test_saison_nicht_angeboten(self):
        seite = FormularSeite(saisons=("26/27",))

        with pytest.raises(RuntimeError, match="nicht angeboten"):
            suche(seite, "25/26", "")
        assert seite.klicks == []

    def test_unbekanntes_saisonformat(self):
        with pytest.raises(ValueError):
            suche(FormularSeite(), "2025", "")

    def test_suche_nicht_mit_gesetzten_werten(self):
        # An empty list that never searched must not count as "no hits"
        seite = FormularSeite()
        seite.formular_echo = ["26/27", "01.07.2026", "30.06.2027", ""]

        with pytest.raises(RuntimeError, match="nicht mit den gesetzten Werten"):
            suche(seite, "25/26", "")

    def test_fehlermeldung_von_dfbnet(self):
        seite = FormularSeite({("25/26", ""): [liste(fehler="Datum bis liegt vor Datum von")]})

        with pytest.raises(RuntimeError, match="DFBnet meldet: Datum bis liegt vor Datum von"):
            suche(seite, "25/26", "")


# ===== One season =====

class TestLiesSaison:
    def test_leere_saison_braucht_nur_eine_suche(self):
        seite = FormularSeite()

        assert lies_saison(seite, "herren", "25/26") == {"beobachtungen": [], "vollstaendig": True}
        assert seite.suchen == [("25/26", "")]

    def test_je_rolle_die_eigene_note(self):
        sr_spiel = zeile(datum="01.09.2025")
        sra_spiel = zeile(datum="08.09.2025")
        offen = zeile(datum="15.09.2025", status=("in Bearbeitung",))
        seite = FormularSeite({
            ("25/26", ""): [liste([sr_spiel, sra_spiel, offen])],
            ("25/26", "1"): [liste([sr_spiel])],
            ("25/26", "2"): [liste([sra_spiel, offen])],
        })

        ergebnis = lies_saison(seite, "herren", "25/26")

        assert seite.suchen == [("25/26", ""), ("25/26", "1"), ("25/26", "2"), ("25/26", "3")]
        assert [(e["datum"], e["rolle"], e["note"]) for e in ergebnis["beobachtungen"]] == [
            ("2025-09-01", "SR", 8.4),
            ("2025-09-08", "SRA1", 8.5),
        ]
        assert ergebnis["vollstaendig"] is True

    def test_portal_kennt_vierten_offiziellen(self):
        spiel = zeile(gespann=(("SR", "A, B"), ("SRA1", "C, D"), ("SRA2", "E, F"), ("4OF", "Muster, Max")),
                      noten=("", "", "", "8,7"))
        seite = FormularSeite({
            ("25/26", ""): [liste([spiel])],
            ("25/26", "4"): [liste([spiel])],
        })

        ergebnis = lies_saison(seite, "portal", "25/26")

        assert seite.suchen[-1] == ("25/26", "4")
        assert [(e["rolle"], e["note"]) for e in ergebnis["beobachtungen"]] == [("4OF", 8.7)]

    def test_unvollstaendige_rollensuche(self):
        seite = FormularSeite({
            ("25/26", ""): [liste([zeile()])],
            ("25/26", "1"): [liste([zeile()], treffer=2)],
        })

        assert lies_saison(seite, "herren", "25/26")["vollstaendig"] is False


# ===== One module =====

class TestLiesQuelle:
    def test_liest_die_gewuenschten_saisons(self):
        seite = FormularSeite({("25/26", ""): [liste([zeile()])], ("25/26", "1"): [liste([zeile()])]})
        gefragt = []
        fortschritt = []

        def saisons_fuer(quelle, angebotene):
            gefragt.append((quelle, angebotene))
            return ["25/26", "24/25"]

        ergebnis = lies_quelle(seite, "herren", MODUL_URL, saisons_fuer,
                               lambda *a: fortschritt.append(a))

        assert gefragt == [("herren", ["26/27", "25/26", "24/25"])]
        assert set(ergebnis) == {"25/26", "24/25"}
        assert len(ergebnis["25/26"]["beobachtungen"]) == 1
        assert ergebnis["24/25"] == {"beobachtungen": [], "vollstaendig": True}
        assert fortschritt == [
            (1, 2, "Beobachtungen Schiri-Beobachtung 25/26 (1/2)"),
            (2, 2, "Beobachtungen Schiri-Beobachtung 24/25 (2/2)"),
        ]

    def test_fehlerhafte_saison_fehlt_und_liste_wird_neu_geladen(self):
        seite = FormularSeite(saisons=("26/27", "24/25"))

        ergebnis = lies_quelle(seite, "herren", MODUL_URL, lambda q, a: ["25/26", "24/25"])

        assert list(ergebnis) == ["24/25"]
        assert seite.gotos == [MODUL_URL, LISTEN_URL, LISTEN_URL]

    def test_bricht_ab_wenn_liste_nicht_wieder_aufgeht(self):
        seite = FormularSeite(saisons=("26/27", "24/25"))

        def nach_fehler_kaputt(s, url):
            if len(s.gotos) > 2:
                s.formular_da = False

        seite.bei_goto = nach_fehler_kaputt

        ergebnis = lies_quelle(seite, "herren", MODUL_URL, lambda q, a: ["25/26", "24/25", "26/27"])

        assert ergebnis == {}
        assert len(seite.gotos) == 3
