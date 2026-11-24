"""
Die Persistenz-Schicht in main.py: was ein Scrape in die Datenbank schreibt,
und was er bewusst stehen laesst. scrape_matches laeuft gegen einen falschen
DFBScraper - Playwright startet hier nie.
"""
from datetime import date, timedelta

import pytest

import db.database as database
import main
from db import matches as db_matches
from db import spielberichte as db_spielberichte
from db.beobachtungen import count_beobachtungen, get_beobachtungen, replace_beobachtungs_saison
from db.matches import get_matches_for_user
from db.season import count_saison_spiele, get_komplette_saisons, get_saison
from db.spielberichte import get_fertige_saisons, get_gespeicherte
from db.stammdaten import get_stammdaten
from db_helpers import feste_uhr, spiel


@pytest.fixture
def uhr(monkeypatch):
    """Heute ist der 23.11.2026 - auch fuer mark_missing_matches."""
    return feste_uhr(monkeypatch, db_matches)


@pytest.fixture
def datenordner(tmp_path, monkeypatch):
    ordner = tmp_path / "daten"
    ordner.mkdir()
    monkeypatch.setattr(db_spielberichte, "get_data_dir", lambda: ordner)
    return ordner


def _nach_heim(uid):
    return {m["heim_team"]: m for m in get_matches_for_user(uid)}


# ---------------------------------------------------------- persist_matches


class TestPersistMatches:
    def test_schreibt_mit_eingefrorenen_saetzen(self, user, uhr):
        assert main.persist_matches(user["id"], [spiel(), spiel(heim="Zwei", spielklasse="Verbandsliga")]) == 2
        spiele = _nach_heim(user["id"])
        assert (spiele["FC Heim"]["sr_spesen"], spiele["FC Heim"]["sra_spesen"]) == (30.0, 25.0)
        assert (spiele["Zwei"]["sr_spesen"], spiele["Zwei"]["sra_spesen"]) == (50.0, 40.0)
        assert spiele["FC Heim"]["km_satz"] == main.KM_SATZ_EURO
        assert spiele["FC Heim"]["datum"] == "2026-12-05"

    def test_saetze_aendern_sich_beim_naechsten_scrape_nicht(self, user, uhr, monkeypatch):
        main.persist_matches(user["id"], [spiel()])
        monkeypatch.setattr(main, "calculate_spesen", lambda *a: (99.0, 88.0))
        main.persist_matches(user["id"], [spiel()])
        assert _nach_heim(user["id"])["FC Heim"]["sr_spesen"] == 30.0

    def test_mannschaften_gehen_an_den_rechner(self, user, uhr, monkeypatch):
        aufrufe = []
        monkeypatch.setattr(main, "calculate_spesen", lambda *a: aufrufe.append(a) or (None, None))
        main.persist_matches(user["id"], [spiel(staffel="St")])
        assert aufrufe == [("Kreisoberliga", "Herren", "St", "FC Heim", "SV Gast")]

    def test_kaputtes_spiel_kippt_den_lauf_nicht(self, user, uhr):
        assert main.persist_matches(user["id"], [None, spiel(), {"spiel_info": "kein dict"}]) == 1
        assert list(_nach_heim(user["id"])) == ["FC Heim"]

    def test_verschwundenes_kuenftiges_spiel_wird_markiert(self, user, uhr):
        main.persist_matches(user["id"], [spiel(heim="Bleibt"), spiel(heim="Weg"),
                                          spiel(heim="Gespielt", tag="2026-11-01")])
        main.persist_matches(user["id"], [spiel(heim="Bleibt")])

        spiele = _nach_heim(user["id"])
        assert len(spiele) == 3
        assert spiele["Bleibt"]["missing_since"] is None
        assert spiele["Weg"]["missing_since"] == "2026-11-23T12:00:00+00:00"
        assert spiele["Gespielt"]["missing_since"] is None

    def test_unvollstaendiger_scrape_markiert_nichts(self, user, uhr):
        main.persist_matches(user["id"], [spiel(heim="Bleibt"), spiel(heim="Weg")])
        main.persist_matches(user["id"], [spiel(heim="Bleibt")], vollstaendig=False)
        assert all(m["missing_since"] is None for m in get_matches_for_user(user["id"]))

    def test_leerer_scrape_markiert_nichts(self, user, uhr):
        main.persist_matches(user["id"], [spiel(heim="Bleibt")])
        assert main.persist_matches(user["id"], []) == 0
        assert get_matches_for_user(user["id"])[0]["missing_since"] is None

    def test_kilometer_ueberleben_das_markieren(self, user, uhr):
        from db.matches import get_match, set_official_expenses

        main.persist_matches(user["id"], [spiel(heim="Weg"), spiel(heim="Bleibt")])
        mid = _nach_heim(user["id"])["Weg"]["id"]
        set_official_expenses(mid, {"sr_km": 42.0})
        main.persist_matches(user["id"], [spiel(heim="Bleibt")])

        m = get_match(mid)
        assert m["missing_since"] is not None
        assert m["expenses"]["sr_km"] == 42.0

    def test_turnier_ohne_teams(self, user, uhr):
        turnier = spiel(heim="", gast="", staette="Halle")
        assert main.persist_matches(user["id"], [turnier]) == 1
        assert get_matches_for_user(user["id"])[0]["match_key"].startswith("turnier|Halle|")


# -------------------------------------------------------- persist_stammdaten


class TestPersistStammdaten:
    def test_leeres_ergebnis_wird_nicht_gespeichert(self, user):
        main.persist_stammdaten(user["id"], {"name_vorname": "", "verein": ""})
        assert get_stammdaten(user["id"]) is None

    def test_speichert(self, user):
        main.persist_stammdaten(user["id"], {"name_vorname": "Pfeife, Erika", "verein": "FC Heim"})
        assert get_stammdaten(user["id"])["name_vorname"] == "Pfeife, Erika"

    def test_fehler_wird_nur_geloggt(self, user, monkeypatch):
        def kaputt(*a, **kw):
            raise RuntimeError("DB weg")

        monkeypatch.setattr(main, "upsert_stammdaten", kaputt)
        main.persist_stammdaten(user["id"], {"verein": "FC Heim"})  # wirft nicht


# ----------------------------------------------------------- persist_saisons


def _roh_spiel(datum_text="20.09.25, 15:00", heim="FC Heim", **extra):
    return {"datum_text": datum_text, "liga": "KOL", "heim": heim, "gast": "SV Gast", "ergebnis": "1:0",
            "heim_gelb": "2", "gast_rot": "-",
            "gespann": [{"rolle": "SRA", "name": "Ich", "selbst": True}, {"rolle": "SR", "name": "Chef"}],
            **extra}


def _saison(spiele=None, vollstaendig=True, **extra):
    return {"vollstaendig": vollstaendig, "spiele": spiele if spiele is not None else [_roh_spiel()],
            "einsaetze": [{"rolle": "SR", "geleitet": "3"}],
            "lehrgaenge": {"lehrabend": "4"}, **extra}


class TestPersistSaisons:
    def test_schreibt_und_rechnet_um(self, user):
        assert main.persist_saisons(user["id"], {"25/26": _saison(erwartet=1)}) == 1
        [s] = get_saison(user["id"], "25/26")["spiele"]
        assert (s["datum"], s["uhrzeit"]) == ("2025-09-20", "15:00")
        assert s["eigene_rolle"] == "SRA"
        assert (s["heim_gelb"], s["gast_rot"]) == (2, None)
        assert get_komplette_saisons(user["id"]) == {"25/26"}

    def test_unvollstaendig_bleibt_unveraendert(self, user):
        main.persist_saisons(user["id"], {"25/26": _saison([_roh_spiel(heim="Bestand")])})
        assert main.persist_saisons(user["id"], {"25/26": _saison([_roh_spiel(heim="Halb")], vollstaendig=False)}) == 0
        assert get_saison(user["id"], "25/26")["spiele"][0]["heim"] == "Bestand"

    def test_leer_gelesen_ersetzt_keinen_bestand(self, user):
        main.persist_saisons(user["id"], {"25/26": _saison()})
        assert main.persist_saisons(user["id"], {"25/26": _saison([])}) == 0
        assert count_saison_spiele(user["id"], "25/26") == 1

    def test_leere_saison_ohne_bestand_wird_geschrieben(self, user):
        assert main.persist_saisons(user["id"], {"26/27": _saison([])}) == 1
        assert get_saison(user["id"], "26/27")["lehrgaenge"]["lehrabend"] == "4"

    def test_eine_kaputte_saison_kippt_die_anderen_nicht(self, user):
        ergebnis = {"24/25": _saison(["kein dict"]), "25/26": _saison()}
        assert main.persist_saisons(user["id"], ergebnis) == 1
        assert count_saison_spiele(user["id"], "25/26") == 1
        assert get_saison(user["id"], "24/25") is None


# ----------------------------------------------------- Beobachtungs-Saisons


class TestWaehleBeobachtungsSaisons:
    ANGEBOTEN = ["26/27", "25/26", "20/21", "19/20"]

    def test_ab_schiedsrichter_seit(self):
        assert main.waehle_beobachtungs_saisons(self.ANGEBOTEN, "15.08.2020", set()) == \
            ["26/27", "25/26", "20/21"]

    def test_seit_im_fruehjahr_zaehlt_zur_laufenden_saison(self):
        assert main.waehle_beobachtungs_saisons(self.ANGEBOTEN, "15.03.2020", set()) == self.ANGEBOTEN

    def test_fertige_fallen_weg(self):
        assert main.waehle_beobachtungs_saisons(self.ANGEBOTEN, "15.08.2020", {"20/21", "25/26"}) == ["26/27"]

    def test_ohne_datum_alle(self):
        assert main.waehle_beobachtungs_saisons(self.ANGEBOTEN, "", set()) == self.ANGEBOTEN
        assert main.waehle_beobachtungs_saisons(self.ANGEBOTEN, "unbekannt", {"19/20"}) == self.ANGEBOTEN[:3]


class TestPersistBeobachtungen:
    def _b(self, heim="FC Heim"):
        return {"datum": "2025-09-20", "heim": heim, "gast": "SV Gast", "rolle": "SR", "note": 8.5}

    def test_schreibt_je_quelle_und_saison(self, user):
        n = main.persist_beobachtungen(user["id"], {
            "herren": {"25/26": {"vollstaendig": True, "beobachtungen": [self._b()]},
                       "24/25": {"vollstaendig": True, "beobachtungen": []}},
            "portal": {"25/26": {"vollstaendig": True, "beobachtungen": [self._b(), self._b("X")]}},
        })
        assert n == 3
        assert count_beobachtungen(user["id"], "portal", "25/26") == 2
        assert len(get_beobachtungen(user["id"])["saisons"]) == 3

    def test_unvollstaendig_bleibt_liegen(self, user):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [self._b("Bestand")])
        n = main.persist_beobachtungen(user["id"], {
            "herren": {"25/26": {"vollstaendig": False, "beobachtungen": [self._b("Neu")]}},
        })
        assert n == 0
        assert get_beobachtungen(user["id"])["beobachtungen"][0]["heim"] == "Bestand"

    def test_leer_ersetzt_keinen_bestand(self, user):
        replace_beobachtungs_saison(user["id"], "herren", "25/26", [self._b()])
        assert main.persist_beobachtungen(user["id"], {
            "herren": {"25/26": {"vollstaendig": True, "beobachtungen": []}},
        }) == 0
        assert count_beobachtungen(user["id"], "herren", "25/26") == 1

    def test_fehler_wird_geloggt(self, user):
        assert main.persist_beobachtungen(user["id"], {
            "herren": {"25/26": {"vollstaendig": True, "beobachtungen": [{"note": 1}]},
                       "24/25": {"vollstaendig": True, "beobachtungen": [self._b()]}},
        }) == 1


# ------------------------------------------------------------ Spielberichte


HEUTE = date(2026, 11, 23)


class TestBrauchtBericht:
    def test_neu(self):
        assert main.braucht_bericht({"dfb_spiel_id": "A", "datum": "2020-01-01"}, {}, HEUTE)

    def test_frisch_gespeichert_wird_nachgelesen(self):
        grenze = (HEUTE - timedelta(days=main.BERICHT_NACHLAUF_TAGE)).isoformat()
        assert main.braucht_bericht({"dfb_spiel_id": "A", "datum": grenze}, {"A": "t"}, HEUTE)

    def test_alt_gespeichert_nicht_mehr(self):
        alt = (HEUTE - timedelta(days=main.BERICHT_NACHLAUF_TAGE + 1)).isoformat()
        assert not main.braucht_bericht({"dfb_spiel_id": "A", "datum": alt}, {"A": "t"}, HEUTE)

    def test_kaputtes_datum(self):
        assert not main.braucht_bericht({"dfb_spiel_id": "A", "datum": "kaputt"}, {"A": "t"}, HEUTE)
        assert not main.braucht_bericht({"dfb_spiel_id": "A"}, {"A": "t"}, HEUTE)


def _bzeile(spiel_id, datum, status=("spiel_anerkannt",)):
    return {"dfb_spiel_id": spiel_id, "datum": datum, "uhrzeit": "13:30", "heim": "FC Heim",
            "gast": "SV Gast", "status": list(status)}


def _bericht(zeile):
    return {"zeile": zeile, "daten": {"kosten": {"fahrtkosten": 10.0}}, "dateien": {}}


def _fertig_vermerkt(uid, saison):
    conn = database.get_connection()
    try:
        row = conn.execute(
            "SELECT anzahl, fertig FROM spielbericht_saisons WHERE user_id = ? AND saison = ?", (uid, saison)
        ).fetchone()
        return tuple(row) if row else None
    finally:
        conn.close()


class TestPersistSpielnummern:
    def test_aus_einsatzplan_und_bericht(self, user):
        mit_id = spiel(tag="2026-11-14")
        mit_id["spiel_info"]["dfb_spiel_id"] = "SPIEL1"
        main.persist_matches(user["id"], [mit_id, spiel(heim="Kuenftig", tag="2026-12-05")])
        gruppe = "Herren, Kreisoberliga, Kreis Mittelthüringen 659000 - Meisterschaft, KOL"

        n = main.persist_spielnummern(user["id"], {
            "saisons": {"26/27": {"zeilen": [
                {**_bzeile(None, "2026-12-05"), "heim": "Kuenftig", "gruppe": gruppe, "nummer": "091"},
            ]}},
            "berichte": {"SPIEL1": {"zeile": {}, "daten": {"spielkennung": "659000082"}}},
        })

        assert n == 2
        nummern = {s["heim_team"]: s["spielnummer"] for s in get_matches_for_user(user["id"])}
        assert nummern == {"FC Heim": "659000082", "Kuenftig": "659000091"}

    def test_fehler_wird_nur_geloggt(self, user, monkeypatch):
        def kaputt(*a):
            raise RuntimeError("DB weg")
        monkeypatch.setattr(main, "setze_spielnummern", kaputt)
        assert main.persist_spielnummern(user["id"], {"saisons": {}, "berichte": {}}) == 0


class TestPersistSpielberichte:
    def test_alles_gelesen_saison_fertig(self, user, datenordner):
        z = _bzeile("A", "2025-05-01")
        n = main.persist_spielberichte(user["id"], {
            "saisons": {"24/25": {"zeilen": [z]}}, "berichte": {"A": _bericht(z)},
        }, heute=HEUTE)
        assert n == 1
        assert _fertig_vermerkt(user["id"], "24/25") == (1, 1)
        assert get_fertige_saisons(user["id"]) == {"24/25"}

    def test_fehlender_bericht_haelt_saison_offen(self, user, datenordner):
        main.persist_spielberichte(user["id"], {
            "saisons": {"24/25": {"zeilen": [_bzeile("A", "2025-05-01")]}}, "berichte": {},
        }, heute=HEUTE)
        assert _fertig_vermerkt(user["id"], "24/25") == (1, 0)

    def test_frueher_gespeicherter_bericht_zaehlt(self, user, datenordner):
        z = _bzeile("A", "2025-05-01")
        main.persist_spielberichte(user["id"], {"saisons": {}, "berichte": {"A": _bericht(z)}}, heute=HEUTE)
        main.persist_spielberichte(user["id"], {"saisons": {"24/25": {"zeilen": [z]}}, "berichte": {}},
                                   heute=HEUTE)
        assert _fertig_vermerkt(user["id"], "24/25") == (1, 1)

    def test_laufende_saison_nie_fertig(self, user, datenordner):
        z = _bzeile("A", "2026-09-01")
        main.persist_spielberichte(user["id"], {
            "saisons": {"26/27": {"zeilen": [z]}}, "berichte": {"A": _bericht(z)},
        }, heute=HEUTE)
        assert _fertig_vermerkt(user["id"], "26/27") == (1, 0)

    def test_nachlauf_nach_saisonende(self, user, datenordner):
        z = _bzeile("A", "2026-05-01")
        daten = {"saisons": {"25/26": {"zeilen": [z]}}, "berichte": {"A": _bericht(z)}}
        main.persist_spielberichte(user["id"], daten, heute=date(2026, 7, 30))
        assert _fertig_vermerkt(user["id"], "25/26")[1] == 0
        main.persist_spielberichte(user["id"], daten, heute=date(2026, 7, 31))
        assert _fertig_vermerkt(user["id"], "25/26")[1] == 1

    def test_wartet_auf_freigabe_haelt_saison_offen(self, user, datenordner):
        """Vergangenes Spiel ohne Freigabe, juenger als 60 Tage: Saison bleibt offen."""
        heute = date(2026, 8, 15)
        z = _bzeile("B", "2026-06-20", status=())
        main.persist_spielberichte(user["id"], {"saisons": {"25/26": {"zeilen": [z]}}, "berichte": {}},
                                   heute=heute)
        assert _fertig_vermerkt(user["id"], "25/26") == (0, 0)

    def test_nach_sechzig_tagen_gilt_bericht_als_nie_freigegeben(self, user, datenordner):
        heute = date(2026, 8, 25)
        z = _bzeile("B", "2026-06-20", status=())
        main.persist_spielberichte(user["id"], {"saisons": {"25/26": {"zeilen": [z]}}, "berichte": {}},
                                   heute=heute)
        assert _fertig_vermerkt(user["id"], "25/26") == (0, 1)

    @pytest.mark.parametrize("tage, fertig", [
        (main.FREIGABE_WARTEN_TAGE, 0),
        (main.FREIGABE_WARTEN_TAGE + 1, 1),
    ])
    def test_sechzig_tage_grenze(self, user, datenordner, tage, fertig):
        heute = date(2026, 9, 30)
        z = _bzeile("B", (heute - timedelta(days=tage)).isoformat(), status=())
        main.persist_spielberichte(user["id"], {"saisons": {"25/26": {"zeilen": [z]}}, "berichte": {}},
                                   heute=heute)
        assert _fertig_vermerkt(user["id"], "25/26")[1] == fertig

    def test_historisches_spiel_wartet_nicht(self, user, datenordner):
        heute = date(2026, 8, 15)
        z = _bzeile("B", "2026-06-20", status=("spiel_historisch",))
        main.persist_spielberichte(user["id"], {"saisons": {"25/26": {"zeilen": [z]}}, "berichte": {}},
                                   heute=heute)
        assert _fertig_vermerkt(user["id"], "25/26") == (0, 1)

    def test_saison_aus_zeile_sonst_aus_datum(self, user, datenordner):
        a = _bzeile("A", "2025-05-01")
        b = _bzeile("B", "2024-03-01")
        main.persist_spielberichte(user["id"], {
            # A steht in der Liste von 25/26 (etwa ein Nachholspiel) - die Liste gewinnt
            "saisons": {"25/26": {"zeilen": [a]}},
            "berichte": {"A": _bericht(a), "B": _bericht(b)},
        }, heute=HEUTE)
        conn = database.get_connection()
        try:
            saisons = dict(conn.execute("SELECT dfb_spiel_id, saison FROM spielberichte").fetchall())
        finally:
            conn.close()
        assert saisons == {"A": "25/26", "B": "23/24"}

    def test_kaputter_bericht_kippt_die_anderen_nicht(self, user, datenordner):
        gut = _bzeile("A", "2025-05-01")
        kaputt = {"datum": "2025-05-02", "status": []}
        n = main.persist_spielberichte(user["id"], {
            "saisons": {}, "berichte": {"X": _bericht(kaputt), "A": _bericht(gut)},
        }, heute=HEUTE)
        assert n == 1
        assert list(get_gespeicherte(user["id"])) == ["A"]


# ------------------------------------------------------------ scrape_matches


class FakeScraper:
    """Spielt DFBScraper nach - jede Methode protokolliert sich selbst."""

    spiele: list = []
    erwartet = None
    stammdaten = {"name_vorname": "Pfeife, Erika", "schiedsrichter_seit": "01.08.2010"}
    stammdaten_fehler = False
    saisons: dict = {}
    beobachtungen: dict = {}
    spielberichte: dict = {}
    letzter = None

    def __init__(self, headless, username, password):
        self.kwargs = {"headless": headless, "username": username, "password": password}
        self.aufrufe = []
        self.ueberspringen = None
        type(self).letzter = self
        if self.erwartet is not None:
            self.erwartete_spiele = self.erwartet

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.aufrufe.append("exit")
        return False

    _SCHRITTE = {"open_dfbnet", "accept_cookies", "click_login", "login", "open_menu_if_needed",
                 "navigate_to_schiriansetzung"}

    def __getattr__(self, name):
        # Die reinen Navigationsschritte werden nur mitgeschrieben. Alles andere
        # fehlt wirklich - sonst faende getattr(scraper, "erwartete_spiele", ...)
        # eine Funktion statt des Defaults.
        if name not in self._SCHRITTE:
            raise AttributeError(name)

        def schritt(*a, **kw):
            self.aufrufe.append(name)
        return schritt

    def scrape_all_matches(self, progress_callback=None):
        if progress_callback:
            progress_callback(1, len(self.spiele), "Spiel 1")
        return list(self.spiele)

    def lies_stammdaten(self):
        if self.stammdaten_fehler:
            raise RuntimeError("Schnittstelle geaendert")
        return {**self.stammdaten, "qmax_sr": "Verbandsliga"}

    def scrape_saisons(self, progress_callback=None, ueberspringen=None):
        self.ueberspringen = ueberspringen
        return self.saisons

    def scrape_beobachtungen(self, saisons_fuer, progress_callback=None):
        self.beobachtungen_auswahl = saisons_fuer("herren", ["26/27", "05/06"])
        return self.beobachtungen

    def scrape_spielberichte(self, saisons_fuer, braucht_bericht, dokument_vorhanden, progress_callback=None):
        return self.spielberichte


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(main, "DFBScraper", FakeScraper)
    for name, wert in {"spiele": [], "erwartet": None, "stammdaten_fehler": False, "saisons": {},
                       "beobachtungen": {}, "spielberichte": {}, "letzter": None}.items():
        monkeypatch.setattr(FakeScraper, name, wert)
    monkeypatch.setattr(FakeScraper, "stammdaten",
                        {"name_vorname": "Pfeife, Erika", "schiedsrichter_seit": "01.08.2010"})
    return FakeScraper


class TestScrapeMatches:
    def test_ohne_zugangsdaten(self, db, fake, monkeypatch):
        monkeypatch.delenv("DFB_USERNAME", raising=False)
        monkeypatch.delenv("DFB_PASSWORD", raising=False)
        assert main.scrape_matches(user_id=1) == []
        assert fake.letzter is None

    def test_voller_lauf_schreibt_alles(self, user, fake, uhr, datenordner):
        fake.spiele = [spiel(), spiel(heim="Zwei")]
        fake.saisons = {"25/26": _saison(erwartet=1)}
        fake.beobachtungen = {"herren": {"25/26": {"vollstaendig": True, "beobachtungen": [
            {"datum": "2025-09-20", "heim": "A", "gast": "B", "rolle": "SR", "note": 8.4}]}}}
        z = _bzeile("A", "2025-05-01")
        fake.spielberichte = {"saisons": {"24/25": {"zeilen": [z]}}, "berichte": {"A": _bericht(z)}}

        schritte = []
        ergebnis = main.scrape_matches("nutzer", "geheim", user["id"],
                                       progress_callback=lambda c, t, s: schritte.append(s))

        assert len(ergebnis) == 2
        assert fake.letzter.kwargs == {"headless": True, "username": "nutzer", "password": "geheim"}
        assert fake.letzter.aufrufe[0] == "open_dfbnet"
        assert "login" in fake.letzter.aufrufe
        assert set(_nach_heim(user["id"])) == {"FC Heim", "Zwei"}
        stammdaten = get_stammdaten(user["id"])
        assert stammdaten["name_vorname"] == "Pfeife, Erika"
        assert stammdaten["qmax_sr"] == "Verbandsliga"
        assert count_saison_spiele(user["id"], "25/26") == 1
        assert count_beobachtungen(user["id"], "herren", "25/26") == 1
        assert list(get_gespeicherte(user["id"])) == ["A"]
        assert schritte[0] == "Login und Navigation..."
        assert "Spiel 1" in schritte
        assert "Lese Spielberichte..." in schritte

    def test_zugangsdaten_aus_umgebung(self, db, fake, monkeypatch):
        monkeypatch.setenv("DFB_USERNAME", "env-nutzer")
        monkeypatch.setenv("DFB_PASSWORD", "env-pass")
        main.scrape_matches()
        assert fake.letzter.kwargs["username"] == "env-nutzer"

    def test_ohne_user_id_wird_nichts_gespeichert(self, db, fake):
        fake.spiele = [spiel()]
        assert len(main.scrape_matches("n", "p")) == 1
        assert database.get_all_users() == []
        conn = database.get_connection()
        try:
            assert conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 0
        finally:
            conn.close()

    def test_stammdatenfehler_kostet_keine_spiele(self, user, fake, uhr):
        fake.spiele = [spiel()]
        fake.stammdaten_fehler = True
        main.scrape_matches("n", "p", user["id"])
        assert len(get_matches_for_user(user["id"])) == 1
        assert get_stammdaten(user["id"]) is None

    def test_unvollstaendiger_scrape_markiert_nichts(self, user, fake, uhr):
        main.persist_matches(user["id"], [spiel(heim="Bleibt"), spiel(heim="Weg")])
        fake.spiele = [spiel(heim="Bleibt")]
        fake.erwartet = 2
        main.scrape_matches("n", "p", user["id"])
        assert _nach_heim(user["id"])["Weg"]["missing_since"] is None

    def test_vollstaendiger_scrape_markiert(self, user, fake, uhr):
        main.persist_matches(user["id"], [spiel(heim="Bleibt"), spiel(heim="Weg")])
        fake.spiele = [spiel(heim="Bleibt")]
        fake.erwartet = 1
        main.scrape_matches("n", "p", user["id"])
        assert _nach_heim(user["id"])["Weg"]["missing_since"] is not None

    def test_komplette_saisons_werden_uebersprungen(self, user, fake, uhr):
        main.persist_saisons(user["id"], {"24/25": _saison(erwartet=1)})
        main.scrape_matches("n", "p", user["id"])
        assert fake.letzter.ueberspringen == {"24/25"}

    def test_beobachtungen_ab_schiedsrichter_seit(self, user, fake, uhr):
        main.scrape_matches("n", "p", user["id"])
        # Seit 2010 - "05/06" kann es nicht geben
        assert fake.letzter.beobachtungen_auswahl == ["26/27"]
