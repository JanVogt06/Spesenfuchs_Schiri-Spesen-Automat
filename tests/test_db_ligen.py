"""Ligatabellen: vollstaendiger Austausch je Staffel und die misstrauische Zuordnung."""
import pytest

import db.database as database
from db import ligen
from db.ligen import (
    RANG_UEBERREGIONAL,
    alle_staffeln,
    bestand,
    ersetze_staffel,
    finde_mannschaft,
    suche_mannschaft,
    kennt_ueberregionale_ligen,
    rang,
    tabelle,
)
from db_helpers import feste_uhr
from scraper.fussball_de import Staffel, Tabellenplatz


def _staffel(staffel_id="vl", spielklasse="verbandsliga", anzeigename="Thüringenliga", pfad=None):
    return Staffel(staffel_id, pfad or f"/{staffel_id}", staffel_id, spielklasse, "thueringen", anzeigename)


def _platz(n, name, team_id=None, punkte=None):
    return Tabellenplatz(n, name, team_id or name, 10, 5, 3, 2, 20, 10, punkte if punkte is not None else 30 - n)


class TestRang:
    def test_bekannte_klassen(self):
        assert rang("regionalliga") < rang("oberliga") < rang("verbandsliga") < rang("landesklasse")

    def test_unbekannt_ganz_unten(self):
        assert rang("kreisliga") == 99
        assert rang("") == 99


class TestErsetzeStaffel:
    def test_schreibt_staffel_und_tabelle(self, db):
        ersetze_staffel(_staffel(), [_platz(2, "SV Zwei 2."), _platz(1, "FC Eins")])
        [s] = alle_staffeln()
        assert (s["staffel_id"], s["spielklasse"], s["rang"], s["mannschaften"]) == ("vl", "verbandsliga", 4, 2)

        zeilen = tabelle("vl")
        assert [z["mannschaft"] for z in zeilen] == ["FC Eins", "SV Zwei 2."]
        assert (zeilen[1]["kern"], zeilen[1]["nummer"]) == ("sv zwei", 2)

    def test_austausch_entfernt_absteiger(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Eins"), _platz(2, "Absteiger")])
        ersetze_staffel(_staffel(anzeigename="Neuer Name"), [_platz(1, "FC Eins"), _platz(2, "Aufsteiger")])
        assert [z["mannschaft"] for z in tabelle("vl")] == ["FC Eins", "Aufsteiger"]
        assert alle_staffeln()[0]["anzeigename"] == "Neuer Name"

    def test_umbenennung_ersetzt_statt_zu_verdoppeln(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Alt", team_id="t1")])
        ersetze_staffel(_staffel(), [_platz(1, "FC Neu", team_id="t1")])
        assert [z["mannschaft"] for z in tabelle("vl")] == ["FC Neu"]

    def test_leere_tabelle_laesst_bestand_stehen(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Eins")])
        ersetze_staffel(_staffel(anzeigename="Egal"), [])
        assert [z["mannschaft"] for z in tabelle("vl")] == ["FC Eins"]
        assert alle_staffeln()[0]["anzeigename"] == "Thüringenliga"

    def test_staffeln_getrennt(self, db):
        ersetze_staffel(_staffel("a"), [_platz(1, "FC A")])
        ersetze_staffel(_staffel("b", "landesklasse"), [_platz(1, "FC B")])
        ersetze_staffel(_staffel("a"), [_platz(1, "FC A2")])
        assert [z["mannschaft"] for z in tabelle("b")] == ["FC B"]

    def test_fehler_rollt_zurueck(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Eins")])
        with pytest.raises(Exception):
            # Zweimal dieselbe team_id verletzt den Primaerschluessel
            ersetze_staffel(_staffel(), [_platz(1, "X", team_id="t"), _platz(2, "Y", team_id="t")])
        assert [z["mannschaft"] for z in tabelle("vl")] == ["FC Eins"]

    def test_aktualisiert_at(self, db, monkeypatch):
        feste_uhr(monkeypatch, ligen)
        ersetze_staffel(_staffel(), [_platz(1, "FC Eins")])
        assert alle_staffeln()[0]["aktualisiert_at"] == "2026-11-23T12:00:00+00:00"

    def test_reihenfolge_hoechste_zuerst(self, db):
        ersetze_staffel(_staffel("lk", "landesklasse", "Landesklasse 1"), [_platz(1, "A")])
        ersetze_staffel(_staffel("ol", "oberliga", "NOFV-Oberliga"), [_platz(1, "B")])
        ersetze_staffel(_staffel("vl", "verbandsliga", "Thüringenliga"), [_platz(1, "C")])
        ersetze_staffel(_staffel("lk0", "landesklasse", "Landesklasse 0"), [_platz(1, "D")])
        assert [s["staffel_id"] for s in alle_staffeln()] == ["ol", "vl", "lk0", "lk"]

    def test_unbekannte_staffel_leer(self, db):
        assert tabelle("gibtsnicht") == []


class TestFindeMannschaft:
    def test_eindeutiger_treffer(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Saalfeld")])
        treffer = finde_mannschaft("SG FC Saalfeld I")
        assert treffer["mannschaft"] == "FC Saalfeld"
        assert (treffer["spielklasse"], treffer["rang"]) == ("verbandsliga", 4)

    def test_nummer_muss_passen(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Saalfeld")])
        assert finde_mannschaft("FC Saalfeld 3.") is None
        assert finde_mannschaft("FC Saalfeld II") is None

    def test_zweite_mannschaft(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Saalfeld"), _platz(2, "FC Saalfeld 2.")])
        assert finde_mannschaft("FC Saalfeld II")["mannschaft"] == "FC Saalfeld 2."

    def test_mehrdeutig_gibt_none(self, db):
        ersetze_staffel(_staffel("a"), [_platz(1, "FC Saalfeld", team_id="t1")])
        ersetze_staffel(_staffel("b", "landesklasse"), [_platz(1, "FC Saalfeld", team_id="t2")])
        assert finde_mannschaft("FC Saalfeld") is None

    def test_suche_unterscheidet_mehrdeutig_von_unbekannt(self, db):
        ersetze_staffel(_staffel("a"), [_platz(1, "FC Saalfeld", team_id="t1")])
        ersetze_staffel(_staffel("b", "landesklasse"), [_platz(1, "FC Saalfeld", team_id="t2")])
        assert len(suche_mannschaft("FC Saalfeld")) == 2
        assert suche_mannschaft("FC Nirgendwo") == []
        assert suche_mannschaft("") == []

    def test_leerer_name(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "FC Saalfeld")])
        assert finde_mannschaft("") is None
        assert finde_mannschaft("SG") is None

    def test_unbekannt(self, db):
        assert finde_mannschaft("FC Nirgendwo") is None


class TestUeberblick:
    def test_ueberregional_erst_mit_oberliga(self, db):
        assert kennt_ueberregionale_ligen() is False
        ersetze_staffel(_staffel("vl", "verbandsliga"), [_platz(1, "A")])
        assert kennt_ueberregionale_ligen() is False
        ersetze_staffel(_staffel("ol", "oberliga"), [_platz(1, "B")])
        assert kennt_ueberregionale_ligen() is True
        assert RANG_UEBERREGIONAL == rang("oberliga")

    def test_bestand_leer(self, db):
        assert bestand() == {"staffeln": 0, "mannschaften": 0, "aktualisiert_at": None}

    def test_bestand(self, db, monkeypatch):
        uhr = feste_uhr(monkeypatch, ligen)
        ersetze_staffel(_staffel("a"), [_platz(1, "A"), _platz(2, "B")])
        uhr.weiter(hours=1)
        ersetze_staffel(_staffel("b", "landesklasse"), [_platz(1, "C")])
        assert bestand() == {"staffeln": 2, "mannschaften": 3, "aktualisiert_at": "2026-11-23T13:00:00+00:00"}

    def test_tabelle_kaskadiert_mit_staffel(self, db):
        ersetze_staffel(_staffel(), [_platz(1, "A")])
        conn = database.get_connection()
        try:
            conn.execute("DELETE FROM liga_staffeln WHERE staffel_id = 'vl'")
            conn.commit()
            assert conn.execute("SELECT COUNT(*) FROM liga_tabellen").fetchone()[0] == 0
        finally:
            conn.close()
