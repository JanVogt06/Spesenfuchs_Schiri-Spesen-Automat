"""
Spielberichte: Speichern samt Dokumentdateien, Lesen nur fuer den Besitzer,
und die Zuordnung eines Berichts zu einem Spiel ueber Mannschaften und Anstoss.
"""
import pytest

import db.database as database
from db import spielberichte as sb
from db.spielberichte import (
    Zuordnung,
    _gleiches_team,
    delete_spielberichte,
    get_bericht,
    get_dokument,
    get_dokument_ids,
    get_fertige_saisons,
    get_gespeicherte,
    get_index,
    kurzinfo,
    normalisiere_team,
    setze_saison,
    speichere_bericht,
    team_kern,
    uhrzeit_aus,
)
from db_helpers import nutzer_anlegen


@pytest.fixture
def datenordner(tmp_path, monkeypatch):
    ordner = tmp_path / "daten"
    ordner.mkdir()
    monkeypatch.setattr(sb, "get_data_dir", lambda: ordner)
    return ordner


@pytest.fixture
def zweiter(db):
    conn = database.get_connection()
    try:
        return nutzer_anlegen(conn, "kollege@example.org")
    finally:
        conn.close()


def _zeile(spiel_id="S123", **extra):
    return {"dfb_spiel_id": spiel_id, "datum": "2026-11-22", "uhrzeit": "13:30", "gruppe": "KOL",
            "nummer": "123", "heim": "FC Heim", "gast": "SV Gast", "ergebnis": "2:1", **extra}


def _dok(dfb_id="d1", dateiname="Bericht.pdf", kategorie_id=1, zeit="2026-11-22 18:00"):
    return {"dfb_id": dfb_id, "dateiname": dateiname, "kategorie_id": kategorie_id,
            "beschreibung": "Sonderbericht", "hochgeladen": {"name": "Ich", "zeit": zeit}}


def _daten(*dokumente, **extra):
    return {"kosten": {"fahrtkosten": 12.5, "spesen": 50.0}, "spielkennung": "KOL-123",
            "kategorien": {1: "Spielbericht", "2": "Sonderbericht"},
            "dokumente": list(dokumente), "ereignisse": [{"minute": 12, "art": "Tor"}], **extra}


def _dokumente_in_db():
    conn = database.get_connection()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM spielbericht_dokumente ORDER BY id")]
    finally:
        conn.close()


# ---------------------------------------------------------------- Namen


class TestNamen:
    def test_normalisiere_team(self):
        assert normalisiere_team("FC Rot-Weiß­Erfurt e.V.") == "fcrotweisserfurtev"
        assert normalisiere_team(None) == ""

    @pytest.mark.parametrize("a, b", [
        ("SG Dynamo Dresden U19", "SG Dynamo Dresden"),
        ("Hertha BSC II", "Hertha BSC U23"),
        ("SV 09 Arnstadt 2.", "SV 09 Arnstadt"),
        ("FC Heim e.V.", "FC Heim"),
    ])
    def test_team_kern_ohne_zusaetze(self, a, b):
        assert team_kern(a) == team_kern(b)

    def test_enthalten_ab_acht_zeichen(self):
        assert _gleiches_team("Arminia Bielefeld", "DSC Arminia Bielefeld")

    def test_kurzer_kern_passt_nicht_ueberall(self):
        assert not _gleiches_team("SV", "SV Musterstadt")

    def test_leer_passt_nie(self):
        assert not _gleiches_team("", "")
        assert not _gleiches_team("U19", "FC Heim")

    @pytest.mark.parametrize("text, erwartet", [
        ("So., 22.11.2026 13:30", "13:30"),
        ("9:05", "09:05"),
        ("Samstag · 22.11.2026 · 13:30 Uhr", "13:30"),
        ("", ""),
        (None, ""),
    ])
    def test_uhrzeit_aus(self, text, erwartet):
        assert uhrzeit_aus(text) == erwartet


# ------------------------------------------------------------ Zuordnung


def _eintrag(id_, heim, gast, datum="2026-11-22", uhrzeit="13:30"):
    return {"id": id_, "datum": datum, "uhrzeit": uhrzeit, "heim": heim, "gast": gast,
            "fahrtkosten": None, "spesen": None, "dokumente": 0}


class TestZuordnung:
    def test_beide_mannschaften(self):
        z = Zuordnung([_eintrag(1, "SG Dynamo Dresden", "Hertha BSC")])
        assert z.finde("2026-11-22", "SG Dynamo Dresden U19", "Hertha BSC II")["id"] == 1

    def test_anderer_tag(self):
        z = Zuordnung([_eintrag(1, "FC Heim", "SV Gast")])
        assert z.finde("2026-11-23", "FC Heim", "SV Gast") is None

    def test_eine_mannschaft_plus_anstoss(self):
        z = Zuordnung([_eintrag(1, "FC Heim", "Ganz Anders")])
        assert z.finde("2026-11-22", "FC Heim", "SV Gast", "Sonntag · 22.11.2026 · 13:30 Uhr")["id"] == 1

    def test_eine_mannschaft_ohne_anstoss_reicht_nicht(self):
        z = Zuordnung([_eintrag(1, "FC Heim", "Ganz Anders")])
        assert z.finde("2026-11-22", "FC Heim", "SV Gast") is None

    def test_eine_mannschaft_falscher_anstoss(self):
        z = Zuordnung([_eintrag(1, "FC Heim", "Ganz Anders", uhrzeit="10:00")])
        assert z.finde("2026-11-22", "FC Heim", "SV Gast", "13:30") is None

    def test_zurueckgezogenes_spiel_bekommt_nicht_den_einzigen_bericht_des_tages(self):
        """Stattdessen gepfiffen: anderer Gegner, gleiche Zeit - kein Treffer."""
        z = Zuordnung([_eintrag(1, "TSV Ersatz", "SC Woanders")])
        assert z.finde("2026-11-22", "FC Heim", "SV Gast", "13:30") is None

    def test_zwei_treffer_zeit_entscheidet(self):
        z = Zuordnung([
            _eintrag(1, "FC Heim", "SV Gast", uhrzeit="10:00"),
            _eintrag(2, "FC Heim", "SV Gast", uhrzeit="14:00"),
        ])
        assert z.finde("2026-11-22", "FC Heim", "SV Gast", "14:00")["id"] == 2
        assert z.finde("2026-11-22", "FC Heim", "SV Gast")["id"] == 1

    def test_eine_mannschaft_mehrdeutig(self):
        z = Zuordnung([
            _eintrag(1, "FC Heim", "A Team Eins"),
            _eintrag(2, "B Team Zwei", "SV Gast"),
        ])
        assert z.finde("2026-11-22", "FC Heim", "SV Gast", "13:30") is None

    def test_kurzinfo(self):
        assert kurzinfo(None) is None
        assert kurzinfo({**_eintrag(7, "A", "B"), "dokumente": 2}) == {
            "id": 7, "fahrtkosten": None, "spesen": None, "dokumente": 2,
        }


# --------------------------------------------------------------- Schreiben


class TestSpeichern:
    def test_bericht_und_dokument(self, user, datenordner):
        bid = speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok()), {"d1": b"%PDF-1"},
                                scraped_at="2026-11-23T00:00:00")
        bericht = get_bericht(user["id"], bid)
        assert bericht["dfb_spiel_id"] == "S123"
        assert (bericht["saison"], bericht["spielnummer"], bericht["spielkennung"]) == ("26/27", "123", "KOL-123")
        assert (bericht["fahrtkosten"], bericht["spesen"]) == (12.5, 50.0)
        assert bericht["daten"]["ereignisse"] == [{"minute": 12, "art": "Tor"}]

        [dok] = bericht["dokumente"]
        assert dok["kategorie"] == "Spielbericht"
        assert dok["dateiname"] == "Bericht.pdf"
        assert dok["groesse"] == 6
        assert dok["hochgeladen_von"] == "Ich"

        datei = datenordner / "spielberichte" / str(user["id"]) / "S123" / "d1.pdf"
        assert datei.read_bytes() == b"%PDF-1"
        assert _dokumente_in_db()[0]["pfad"] == f"spielberichte/{user['id']}/S123/d1.pdf"

    def test_fehlende_kopfdaten_aus_dem_bericht(self, user, datenordner):
        zeile = _zeile(heim="", gast=None, ergebnis="", datum="")
        daten = _daten(heim="Heim lt. Bericht", gast="Gast lt. Bericht", ergebnis={"endstand": "0:3"})
        bid = speichere_bericht(user["id"], "26/27", zeile, daten, {})
        b = get_bericht(user["id"], bid)
        assert (b["heim"], b["gast"], b["ergebnis"], b["datum"]) == \
            ("Heim lt. Bericht", "Gast lt. Bericht", "0:3", "1900-01-01")

    def test_erneut_speichern_aktualisiert(self, user, datenordner):
        a = speichere_bericht(user["id"], "26/27", _zeile(), _daten(), {})
        b = speichere_bericht(user["id"], "26/27", _zeile(ergebnis="3:3"),
                              {**_daten(), "kosten": {"fahrtkosten": 20.0}}, {})
        assert a == b
        bericht = get_bericht(user["id"], a)
        assert bericht["ergebnis"] == "3:3"
        assert (bericht["fahrtkosten"], bericht["spesen"]) == (20.0, None)
        assert len(get_gespeicherte(user["id"])) == 1

    def test_nicht_geladenes_dokument_wird_uebersprungen(self, user, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok("d1"), _dok("d2")), {"d1": b"x"})
        assert [d["dfb_dokument_id"] for d in _dokumente_in_db()] == ["d1"]

    def test_dokument_ohne_id_wird_ignoriert(self, user, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile(), _daten({"dateiname": "x.pdf"}), {})
        assert _dokumente_in_db() == []

    def test_gespeichertes_dokument_bleibt_ohne_neuen_download(self, user, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok()), {"d1": b"alt"})
        speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok()), {})
        datei = datenordner / "spielberichte" / str(user["id"]) / "S123" / "d1.pdf"
        assert datei.read_bytes() == b"alt"
        assert len(_dokumente_in_db()) == 1

    def test_bei_dfbnet_geloeschtes_dokument_verschwindet(self, user, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok("d1"), _dok("d2")),
                          {"d1": b"eins", "d2": b"zwei"})
        speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok("d1")), {})

        assert [d["dfb_dokument_id"] for d in _dokumente_in_db()] == ["d1"]
        ordner = datenordner / "spielberichte" / str(user["id"]) / "S123"
        assert sorted(p.name for p in ordner.iterdir()) == ["d1.pdf"]

    @pytest.mark.parametrize("spiel_id, dok_id, dateiname, erwartet", [
        ("../../S1", "../d1", "Bericht.PDF", "S1/d1.pdf"),
        ("S1", "d1", "ohne_endung", "S1/d1.bin"),
        ("S1", "d1", "x.verylongext", "S1/d1.veryl"),
        ("S1", "d1", "x.p/../hp", "S1/d1.bin"),
        ("S1", "d1", None, "S1/d1.bin"),
    ])
    def test_dateiname_nur_aus_ids(self, user, datenordner, spiel_id, dok_id, dateiname, erwartet):
        speichere_bericht(user["id"], "26/27", _zeile(spiel_id), _daten(_dok(dok_id, dateiname)),
                          {dok_id: b"x"})
        pfad = _dokumente_in_db()[0]["pfad"]
        assert pfad == f"spielberichte/{user['id']}/{erwartet}"
        assert (datenordner / pfad).is_file()

    def test_fehler_rollt_zurueck_und_raeumt_dateien_weg(self, user, datenordner):
        # Die zweite Datei ist kein bytes-Objekt - write_bytes scheitert nach der ersten
        with pytest.raises(TypeError):
            speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok("d1"), _dok("d2")),
                              {"d1": b"eins", "d2": "kein bytes"})
        assert get_gespeicherte(user["id"]) == {}
        assert _dokumente_in_db() == []
        ordner = datenordner / "spielberichte" / str(user["id"]) / "S123"
        assert not ordner.exists() or not any(ordner.iterdir())


class TestSaisons:
    def test_setzen_und_fertige(self, user):
        setze_saison(user["id"], "24/25", 10, True)
        setze_saison(user["id"], "25/26", 3, False)
        assert get_fertige_saisons(user["id"]) == {"24/25"}

    def test_upsert(self, user):
        setze_saison(user["id"], "25/26", 3, True)
        setze_saison(user["id"], "25/26", 4, False)
        assert get_fertige_saisons(user["id"]) == set()
        conn = database.get_connection()
        try:
            assert conn.execute("SELECT anzahl FROM spielbericht_saisons").fetchone()[0] == 4
        finally:
            conn.close()

    def test_nutzer_getrennt(self, user, zweiter):
        setze_saison(user["id"], "24/25", 10, True)
        assert get_fertige_saisons(zweiter) == set()


# ------------------------------------------------------------------ Lesen


class TestLesen:
    def test_gespeicherte(self, user, zweiter, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile("A"), _daten(), {}, scraped_at="t1")
        speichere_bericht(zweiter, "26/27", _zeile("B"), _daten(), {}, scraped_at="t2")
        assert get_gespeicherte(user["id"]) == {"A": "t1"}

    def test_dokument_ids_nur_mit_datei(self, user, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok("d1"), _dok("d2")),
                          {"d1": b"1", "d2": b"2"})
        (datenordner / "spielberichte" / str(user["id"]) / "S123" / "d2.pdf").unlink()
        assert get_dokument_ids(user["id"]) == {"d1"}

    def test_index_mit_dokumentzahl(self, user, datenordner):
        a = speichere_bericht(user["id"], "26/27", _zeile("A"), _daten(_dok("d1"), _dok("d2")),
                              {"d1": b"1", "d2": b"2"})
        b = speichere_bericht(user["id"], "26/27", _zeile("B", heim="X"), _daten(), {})
        index = {e["id"]: e for e in get_index(user["id"])}
        assert index[a]["dokumente"] == 2
        assert index[b]["dokumente"] == 0
        assert index[a]["fahrtkosten"] == 12.5
        assert "daten" not in index[a]

    def test_bericht_nur_fuer_besitzer(self, user, zweiter, datenordner):
        bid = speichere_bericht(user["id"], "26/27", _zeile(), _daten(), {})
        assert get_bericht(zweiter, bid) is None
        assert get_bericht(user["id"], 999) is None

    def test_dokumente_nach_hochladezeit(self, user, datenordner):
        bid = speichere_bericht(user["id"], "26/27", _zeile(), _daten(
            _dok("spaet", zeit="2026-11-23 10:00"), _dok("frueh", zeit="2026-11-22 10:00"),
        ), {"spaet": b"1", "frueh": b"2"})
        assert [d["dfb_dokument_id"] for d in get_bericht(user["id"], bid)["dokumente"]] == ["frueh", "spaet"]

    def test_dokument_mit_absolutem_pfad(self, user, datenordner):
        bid = speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok()), {"d1": b"inhalt"})
        dok_id = _dokumente_in_db()[0]["id"]
        dok = get_dokument(user["id"], bid, dok_id)
        assert dok["absolut"].read_bytes() == b"inhalt"

    def test_dokument_fremder_nutzer_oder_bericht(self, user, zweiter, datenordner):
        bid = speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok()), {"d1": b"x"})
        anderer = speichere_bericht(user["id"], "26/27", _zeile("S2"), _daten(), {})
        dok_id = _dokumente_in_db()[0]["id"]
        assert get_dokument(zweiter, bid, dok_id) is None
        assert get_dokument(user["id"], anderer, dok_id) is None

    def test_pfad_ausserhalb_des_datenordners_abgelehnt(self, user, datenordner):
        bid = speichere_bericht(user["id"], "26/27", _zeile(), _daten(_dok()), {"d1": b"x"})
        dok_id = _dokumente_in_db()[0]["id"]
        conn = database.get_connection()
        conn.execute("UPDATE spielbericht_dokumente SET pfad = '../../etc/passwd' WHERE id = ?", (dok_id,))
        conn.commit()
        conn.close()
        assert get_dokument(user["id"], bid, dok_id) is None


class TestLoeschen:
    def test_loescht_berichte_saisons_und_ordner(self, user, zweiter, datenordner):
        speichere_bericht(user["id"], "26/27", _zeile("A"), _daten(_dok()), {"d1": b"x"})
        speichere_bericht(user["id"], "26/27", _zeile("B"), _daten(), {})
        speichere_bericht(zweiter, "26/27", _zeile("C"), _daten(_dok()), {"d1": b"y"})
        setze_saison(user["id"], "25/26", 1, True)

        assert delete_spielberichte(user["id"]) == 2

        assert get_gespeicherte(user["id"]) == {}
        assert get_fertige_saisons(user["id"]) == set()
        assert not (datenordner / "spielberichte" / str(user["id"])).exists()
        assert get_gespeicherte(zweiter) == {"C": get_gespeicherte(zweiter)["C"]}
        assert get_dokument_ids(zweiter) == {"d1"}

    def test_nichts_da(self, user, datenordner):
        assert delete_spielberichte(user["id"]) == 0
