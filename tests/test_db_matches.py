"""
Assignments: keys, upsert with frozen rates, marking instead of deleting,
travel costs and the separation between users.
"""
import pytest

import db.database as database
from db import matches
from db.matches import (
    build_match_key,
    count_distinct_matches,
    ergaenze_offene_saetze,
    get_match,
    get_matches_for_user,
    mark_missing_matches,
    set_official_expenses,
    setze_spielnummern,
    upsert_match,
)
from db_helpers import feste_uhr, nutzer_anlegen, spiel


@pytest.fixture
def zweiter(db):
    conn = database.get_connection()
    try:
        return nutzer_anlegen(conn, "kollege@example.org")
    finally:
        conn.close()


def _upsert(user_id, daten, datum=None, sr=30.0, sra=25.0, km=0.30, **kw):
    datum = datum or _datum(daten)
    return upsert_match(user_id, daten, datum, sr, sra, km, **kw)


def _datum(daten):
    from utils.match_utils import extract_iso_date_from_anpfiff
    return extract_iso_date_from_anpfiff(daten["spiel_info"]["anpfiff"])


def _zeile(match_id):
    conn = database.get_connection()
    try:
        return dict(conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone())
    finally:
        conn.close()


def _anzahl(tabelle):
    conn = database.get_connection()
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0]
    finally:
        conn.close()


# --------------------------------------------------------------------- Keys


class TestBuildMatchKey:
    def test_mit_teams(self):
        info = {"heim_team": " FC Heim ", "gast_team": "SV Gast", "mannschaftsart": "Herren",
                "spielklasse": " Kreisliga", "anpfiff": "egal"}
        assert build_match_key(info, {"name": "Platz"}, "2026-12-05") == \
            "FC Heim|SV Gast|2026-12-05|Herren|Kreisliga"

    def test_anpfiff_gehoert_nicht_dazu(self):
        a = spiel(zeit="13:00")
        b = spiel(zeit="15:30")
        assert build_match_key(a["spiel_info"], a["spielstaette"], "2026-12-05") == \
            build_match_key(b["spiel_info"], b["spielstaette"], "2026-12-05")

    def test_mannschaftsart_trennt(self):
        a = spiel(mannschaftsart="G-Junioren")
        b = spiel(mannschaftsart="C-Junioren")
        assert build_match_key(a["spiel_info"], {}, "2026-12-05") != \
            build_match_key(b["spiel_info"], {}, "2026-12-05")

    def test_turnier_ohne_teams(self):
        info = {"heim_team": "", "gast_team": None, "anpfiff": "Sonntag · 06.12.2026 · 10:00 Uhr"}
        assert build_match_key(info, {"name": " Halle "}, "2026-12-06") == \
            "turnier|Halle|Sonntag · 06.12.2026 · 10:00 Uhr"

    def test_turnier_ohne_anpfiff_nimmt_datum(self):
        assert build_match_key({}, {}, "2026-12-06") == "turnier||2026-12-06"

    def test_nur_ein_team_gilt_als_turnier(self):
        assert build_match_key({"heim_team": "FC Heim"}, {"name": "Halle"}, "2026-12-06").startswith("turnier|")


# ------------------------------------------------------------------- Upsert


class TestUpsert:
    def test_legt_an_und_liefert_id(self, user):
        mid = _upsert(user["id"], spiel())
        zeile = _zeile(mid)
        assert zeile["user_id"] == user["id"]
        assert zeile["match_key"] == "FC Heim|SV Gast|2026-12-05|Herren|Kreisoberliga"
        assert zeile["datum"] == "2026-12-05"
        assert zeile["staette_name"] == "Sportplatz Am Wald"
        assert (zeile["sr_spesen"], zeile["sra_spesen"], zeile["km_satz"]) == (30.0, 25.0, 0.30)
        assert zeile["missing_since"] is None

    def test_zweiter_upsert_dieselbe_zeile(self, user):
        a = _upsert(user["id"], spiel())
        b = _upsert(user["id"], spiel())
        assert a == b
        assert _anzahl("matches") == 1

    def test_saetze_bleiben_eingefroren(self, user):
        mid = _upsert(user["id"], spiel(), sr=30.0, sra=25.0, km=0.30)
        _upsert(user["id"], spiel(), sr=99.0, sra=88.0, km=0.50)
        zeile = _zeile(mid)
        assert (zeile["sr_spesen"], zeile["sra_spesen"], zeile["km_satz"]) == (30.0, 25.0, 0.30)

    def test_leere_felder_ueberschreiben_nichts(self, user):
        mid = _upsert(user["id"], spiel())
        teilfehler = spiel(staette="", adresse="", platz_typ="", staffel="", spieltag="")
        _upsert(user["id"], teilfehler)
        zeile = _zeile(mid)
        assert zeile["staette_name"] == "Sportplatz Am Wald"
        assert zeile["staette_adresse"] == "Waldweg 1, 99999 Irgendwo"
        assert zeile["staffel"] == "Kreisoberliga Mittelthueringen"
        assert zeile["spieltag"] == "12"

    def test_dfb_spiel_id_wird_gespeichert_und_bleibt(self, user):
        mit_id = spiel()
        mit_id["spiel_info"]["dfb_spiel_id"] = "031E47FI74000000VS5489BUVUR5FS5A"

        mid = _upsert(user["id"], spiel())
        assert _zeile(mid)["dfb_spiel_id"] is None

        assert _upsert(user["id"], mit_id) == mid
        assert _zeile(mid)["dfb_spiel_id"] == "031E47FI74000000VS5489BUVUR5FS5A"

        # A later retrieval without an ID does not delete it
        _upsert(user["id"], spiel())
        assert _zeile(mid)["dfb_spiel_id"] == "031E47FI74000000VS5489BUVUR5FS5A"
        assert get_match(mid)["spiel_info"]["dfb_spiel_id"] == "031E47FI74000000VS5489BUVUR5FS5A"

    def test_koordinaten_der_spielstaette_bleiben_bei_einem_abruf_ohne(self, user):
        mit_ort = spiel()
        mit_ort["spielstaette"].update(lat=50.65, lon=11.37)

        mid = _upsert(user["id"], mit_ort)
        assert (_zeile(mid)["staette_lat"], _zeile(mid)["staette_lon"]) == (50.65, 11.37)

        _upsert(user["id"], spiel())
        assert get_match(mid)["staette_lat"] == 50.65

    def test_eigene_person_im_gespann(self, user):
        daten = spiel()
        daten["schiedsrichter"][1]["selbst"] = True

        mid = _upsert(user["id"], daten)

        assert get_match(mid)["selbst"] == {"rolle": "SRA 1", "seq": 0}
        # The marker is not on the people - the frontend shows that field by field
        assert all("selbst" not in p for p in get_match(mid)["schiedsrichter"])

    def test_ohne_markierung_keine_eigene_person(self, user):
        assert get_match(_upsert(user["id"], spiel()))["selbst"] is None

    def test_verlegung_aktualisiert_anpfiff(self, user):
        mid = _upsert(user["id"], spiel(zeit="13:00"))
        _upsert(user["id"], spiel(zeit="15:00", adresse="Neue Str. 2"))
        zeile = _zeile(mid)
        assert "15:00" in zeile["anpfiff"]
        assert zeile["staette_adresse"] == "Neue Str. 2"

    def test_first_seen_bleibt_scraped_at_wandert(self, user):
        mid = _upsert(user["id"], spiel(), scraped_at="2026-11-01T00:00:00+00:00")
        _upsert(user["id"], spiel(), scraped_at="2026-11-20T00:00:00+00:00")
        zeile = _zeile(mid)
        assert zeile["first_seen_at"] == "2026-11-01T00:00:00+00:00"
        assert zeile["scraped_at"] == "2026-11-20T00:00:00+00:00"

    def test_scraped_at_default_ist_jetzt(self, user, monkeypatch):
        feste_uhr(monkeypatch, matches)
        mid = _upsert(user["id"], spiel())
        assert _zeile(mid)["scraped_at"] == "2026-11-23T12:00:00+00:00"

    def test_team_namen_werden_getrimmt(self, user):
        mid = _upsert(user["id"], spiel(heim="  FC Heim ", gast=" SV Gast"))
        zeile = _zeile(mid)
        assert (zeile["heim_team"], zeile["gast_team"]) == ("FC Heim", "SV Gast")

    def test_unparteiische_mit_seq_je_rolle(self, user):
        daten = spiel(schiedsrichter=[
            {"rolle": "SR", "name": "A"},
            {"rolle": "SR", "name": "B"},
            {"rolle": "", "name": "C"},
            {"rolle": "SRA 1", "name": "D"},
        ])
        mid = _upsert(user["id"], daten)
        conn = database.get_connection()
        try:
            reihen = [
                (r["rolle"], r["seq"], r["name"])
                for r in conn.execute(
                    "SELECT rolle, seq, name FROM match_officials WHERE match_id = ? ORDER BY rolle, seq",
                    (mid,),
                )
            ]
        finally:
            conn.close()
        assert reihen == [("SR", 0, "A"), ("SR", 1, "B"), ("SR", 2, "C"), ("SRA 1", 0, "D")]

    def test_unparteiische_werden_ersetzt(self, user):
        mid = _upsert(user["id"], spiel())
        _upsert(user["id"], spiel(schiedsrichter=[{"rolle": "SR", "name": "Neu"}]))
        assert [o["name"] for o in get_match(mid)["schiedsrichter"]] == ["Neu"]

    def test_leere_liste_laesst_unparteiische_stehen(self, user):
        mid = _upsert(user["id"], spiel())
        _upsert(user["id"], spiel(schiedsrichter=[]))
        assert len(get_match(mid)["schiedsrichter"]) == 3

    def test_wieder_aufgetaucht_raeumt_markierung(self, user):
        mid = _upsert(user["id"], spiel(tag="2026-12-05"))
        _upsert(user["id"], spiel(heim="Anderer", tag="2026-12-06"))
        mark_missing_matches(user["id"], ["nicht-dabei"], now="2026-11-23T12:00:00+00:00")
        assert _zeile(mid)["missing_since"] is not None

        _upsert(user["id"], spiel(tag="2026-12-05"))
        assert _zeile(mid)["missing_since"] is None

    def test_fremde_verbindung_ohne_commit(self, user):
        conn = database.get_connection()
        try:
            upsert_match(user["id"], spiel(), "2026-12-05", 30.0, 25.0, 0.30, conn=conn)
            conn.rollback()
        finally:
            conn.close()
        assert _anzahl("matches") == 0

    def test_fremde_verbindung_bleibt_offen(self, user):
        conn = database.get_connection()
        try:
            mid = upsert_match(user["id"], spiel(), "2026-12-05", 30.0, 25.0, 0.30, conn=conn)
            # The connection is still usable and sees its own row
            assert conn.execute("SELECT id FROM matches").fetchone()["id"] == mid
            conn.commit()
        finally:
            conn.close()
        assert _anzahl("matches") == 1


# -------------------------------------------------------- User separation


class TestNutzertrennung:
    def test_gleiches_spiel_zwei_nutzer_zwei_zeilen(self, user, zweiter):
        a = _upsert(user["id"], spiel())
        b = _upsert(zweiter, spiel())
        assert a != b
        assert [m["id"] for m in get_matches_for_user(user["id"])] == [a]
        assert [m["id"] for m in get_matches_for_user(zweiter)] == [b]

    def test_saetze_je_nutzer_eingefroren(self, user, zweiter):
        a = _upsert(user["id"], spiel(), sr=30.0)
        b = _upsert(zweiter, spiel(), sr=50.0)
        assert _zeile(a)["sr_spesen"] == 30.0
        assert _zeile(b)["sr_spesen"] == 50.0

    def test_markieren_trifft_nur_eigenen_nutzer(self, user, zweiter):
        _upsert(user["id"], spiel())
        fremd = _upsert(zweiter, spiel())
        _upsert(user["id"], spiel(heim="Anderer"))
        mark_missing_matches(user["id"], ["nicht-dabei"], now="2026-11-23T12:00:00+00:00")
        assert _zeile(fremd)["missing_since"] is None

    def test_unbekannter_nutzer_hat_keine_spiele(self, db):
        assert get_matches_for_user(4711) == []


# ---------------------------------------------------------- DFBnet ID as identity


def mit_id(dfb_spiel_id, **kw):
    daten = spiel(**kw)
    daten["spiel_info"]["dfb_spiel_id"] = dfb_spiel_id
    return daten


class TestIdentitaetUeberId:
    def test_alte_zeile_wird_ueber_den_schluessel_uebernommen(self, user):
        alt = _upsert(user["id"], spiel())
        set_official_expenses(alt, {"sr_km": 42.0})

        assert _upsert(user["id"], mit_id("SPIEL1")) == alt
        assert _zeile(alt)["dfb_spiel_id"] == "SPIEL1"
        assert _anzahl("matches") == 1

    def test_verlegung_auf_anderen_tag_bleibt_in_der_zeile(self, user):
        mid = _upsert(user["id"], mit_id("SPIEL1", tag="2026-12-05"))
        set_official_expenses(mid, {"sr_km": 42.0, "sr_oevm": 3.0})

        assert _upsert(user["id"], mit_id("SPIEL1", tag="2026-12-12", zeit="15:00")) == mid

        zeile = _zeile(mid)
        assert _anzahl("matches") == 1
        assert zeile["datum"] == "2026-12-12"
        assert zeile["match_key"] == "FC Heim|SV Gast|2026-12-12|Herren|Kreisoberliga"
        assert get_match(mid)["expenses"]["sr_km"] == 42.0

    def test_zeile_mit_anderer_id_wird_nicht_uebernommen(self, user):
        erstes = _upsert(user["id"], mit_id("SPIEL1"))
        zweites = _upsert(user["id"], mit_id("SPIEL2"))

        assert erstes != zweites
        assert _zeile(erstes)["match_key"] == "FC Heim|SV Gast|2026-12-05|Herren|Kreisoberliga"
        assert _zeile(zweites)["match_key"] == "FC Heim|SV Gast|2026-12-05|Herren|Kreisoberliga|SPIEL2"

    def test_verlegung_auf_belegten_schluessel(self, user):
        # Legacy: the same match is already present under its new date as a
        # row with a different ID - the uniqueness must not break
        _upsert(user["id"], mit_id("ALT", tag="2026-12-12"))
        mid = _upsert(user["id"], mit_id("SPIEL1", tag="2026-12-05"))

        _upsert(user["id"], mit_id("SPIEL1", tag="2026-12-12"))

        assert _zeile(mid)["match_key"] == "FC Heim|SV Gast|2026-12-12|Herren|Kreisoberliga|SPIEL1"
        assert _zeile(mid)["datum"] == "2026-12-12"

    def test_leere_felder_ueberschreiben_nichts(self, user):
        mid = _upsert(user["id"], mit_id("SPIEL1"))
        _upsert(user["id"], mit_id("SPIEL1", staette="", spieltag=""))
        assert _zeile(mid)["staette_name"] == "Sportplatz Am Wald"
        assert _zeile(mid)["spieltag"] == "12"

    def test_saetze_bleiben_eingefroren_und_markierung_geht(self, user):
        mid = _upsert(user["id"], mit_id("SPIEL1"), sr=30.0)
        mark_missing_matches(user["id"], ["x"], now="2026-11-23T12:00:00+00:00")

        _upsert(user["id"], mit_id("SPIEL1"), sr=99.0)

        assert _zeile(mid)["sr_spesen"] == 30.0
        assert _zeile(mid)["missing_since"] is None

    def test_nutzer_sind_getrennt(self, user, zweiter):
        assert _upsert(user["id"], mit_id("SPIEL1")) != _upsert(zweiter, mit_id("SPIEL1"))


class TestSpielnummern:
    def test_ueber_id_und_ueber_teams(self, user):
        mit = _upsert(user["id"], mit_id("SPIEL1", heim="Hertha BSC U23", gast="FSV Zwickau"))
        ohne = _upsert(user["id"], spiel(heim="SG Dynamo Dresden U19", gast="RB Leipzig U19",
                                         tag="2026-12-06", zeit="11:00"))

        n = setze_spielnummern(user["id"], [
            {"spielkennung": "690047011", "dfb_spiel_id": "SPIEL1"},
            # Future, without link: names as in the duty roster
            {"spielkennung": "890201022", "dfb_spiel_id": None, "datum": "2026-12-06",
             "uhrzeit": "11:00", "heim": "SG Dynamo Dresden", "gast": "RB Leipzig"},
            {"spielkennung": "", "dfb_spiel_id": "SPIEL1"},
        ])

        assert n == 2
        assert _zeile(mit)["spielnummer"] == "690047011"
        assert get_match(ohne)["spielnummer"] == "890201022"
        # Unchanged does not count
        assert setze_spielnummern(user["id"], [{"spielkennung": "690047011", "dfb_spiel_id": "SPIEL1"}]) == 0

    def test_kein_treffer_und_fremde_id(self, user, zweiter):
        mid = _upsert(user["id"], mit_id("SPIEL1"))
        _upsert(zweiter, mit_id("SPIEL9"))

        assert setze_spielnummern(user["id"], [
            # Different day
            {"spielkennung": "1", "datum": "2026-12-06", "heim": "FC Heim", "gast": "SV Gast"},
            # Same teams, but a different DFBnet ID
            {"spielkennung": "2", "dfb_spiel_id": "SPIEL2", "datum": "2026-12-05",
             "heim": "FC Heim", "gast": "SV Gast"},
            # Another user's ID
            {"spielkennung": "3", "dfb_spiel_id": "SPIEL9"},
        ]) == 0
        assert _zeile(mid)["spielnummer"] is None


# -------------------------------------------------------- Missing matches


class TestMarkMissing:
    JETZT = "2026-11-23T12:00:00+00:00"

    def _drei(self, uid):
        vergangen = _upsert(uid, spiel(heim="Vergangen", tag="2026-11-15"))
        heute = _upsert(uid, spiel(heim="Heute", tag="2026-11-23"))
        kuenftig = _upsert(uid, spiel(heim="Kuenftig", tag="2026-12-05"))
        return vergangen, heute, kuenftig

    def test_leerer_scrape_markiert_nichts(self, user):
        self._drei(user["id"])
        assert mark_missing_matches(user["id"], [], now=self.JETZT) == 0
        assert all(m["missing_since"] is None for m in get_matches_for_user(user["id"]))

    def test_nur_kuenftige_und_heutige_werden_markiert(self, user):
        vergangen, heute, kuenftig = self._drei(user["id"])
        assert mark_missing_matches(user["id"], ["anderer-key"], now=self.JETZT) == 2
        assert _zeile(vergangen)["missing_since"] is None
        assert _zeile(heute)["missing_since"] == self.JETZT
        assert _zeile(kuenftig)["missing_since"] == self.JETZT

    def test_im_gelesenen_zeitraum_auch_vergangene(self, user):
        # The whole season was read: a past match missing from it was given back
        alt = _upsert(user["id"], spiel(heim="Vorsaison", tag="2026-06-20"))
        vergangen, heute, kuenftig = self._drei(user["id"])

        assert mark_missing_matches(user["id"], ["x"], now=self.JETZT, ab="2026-07-01") == 3
        assert _zeile(vergangen)["missing_since"] == self.JETZT
        assert _zeile(kuenftig)["missing_since"] == self.JETZT
        # Before the read period nothing can be judged
        assert _zeile(alt)["missing_since"] is None

    def test_spaeterer_beginn_als_heute_aendert_nichts(self, user):
        vergangen, _, _ = self._drei(user["id"])
        assert mark_missing_matches(user["id"], ["x"], now=self.JETZT, ab="2026-12-01") == 2
        assert _zeile(vergangen)["missing_since"] is None

    def test_gesehene_bleiben_unmarkiert(self, user):
        _, _, kuenftig = self._drei(user["id"])
        gesehen = _zeile(kuenftig)["match_key"]
        assert mark_missing_matches(user["id"], [gesehen], now=self.JETZT) == 1
        assert _zeile(kuenftig)["missing_since"] is None

    def test_markierung_wird_nicht_erneuert(self, user):
        _, _, kuenftig = self._drei(user["id"])
        mark_missing_matches(user["id"], ["x"], now=self.JETZT)
        assert mark_missing_matches(user["id"], ["x"], now="2026-11-24T12:00:00+00:00") == 0
        assert _zeile(kuenftig)["missing_since"] == self.JETZT

    def test_nichts_wird_geloescht_kilometer_bleiben(self, user):
        _, _, kuenftig = self._drei(user["id"])
        set_official_expenses(kuenftig, {"sr_km": 42.0, "sr_oevm": 3.0})
        mark_missing_matches(user["id"], ["x"], now=self.JETZT)

        assert _anzahl("matches") == 3
        spiel_ = get_match(kuenftig)
        assert spiel_["missing_since"] == self.JETZT
        assert spiel_["expenses"]["sr_km"] == 42.0

    def test_default_now_ist_jetzt(self, user, monkeypatch):
        feste_uhr(monkeypatch, matches)
        _, _, kuenftig = self._drei(user["id"])
        mark_missing_matches(user["id"], ["x"])
        assert _zeile(kuenftig)["missing_since"] == "2026-11-23T12:00:00+00:00"

    def test_gesehene_ids(self, user):
        vergangen, heute, kuenftig = self._drei(user["id"])
        assert mark_missing_matches(user["id"], [], now=self.JETZT, seen_ids=[kuenftig]) == 1
        assert _zeile(heute)["missing_since"] == self.JETZT
        assert _zeile(kuenftig)["missing_since"] is None

    def test_include_missing(self, user):
        _, _, kuenftig = self._drei(user["id"])
        mark_missing_matches(user["id"], ["x"], now=self.JETZT)
        alle = {m["id"] for m in get_matches_for_user(user["id"])}
        aktiv = {m["id"] for m in get_matches_for_user(user["id"], include_missing=False)}
        assert kuenftig in alle
        assert kuenftig not in aktiv
        assert len(alle) == 3 and len(aktiv) == 1


# -------------------------------------------------------------- Reading


class TestLesen:
    def test_neueste_zuerst(self, user):
        _upsert(user["id"], spiel(heim="A", tag="2026-10-01"))
        _upsert(user["id"], spiel(heim="B", tag="2026-12-01"))
        _upsert(user["id"], spiel(heim="C", tag="2026-11-01"))
        assert [m["heim_team"] for m in get_matches_for_user(user["id"])] == ["B", "C", "A"]

    def test_struktur_wie_scraper(self, user):
        mid = _upsert(user["id"], spiel())
        m = get_match(mid)
        assert m["spiel_info"]["heim_team"] == "FC Heim"
        assert m["spiel_info"]["spielklasse"] == "Kreisoberliga"
        assert m["spielstaette"] == {
            "name": "Sportplatz Am Wald", "adresse": "Waldweg 1, 99999 Irgendwo", "platz_typ": "Rasen",
        }
        assert [o["rolle"] for o in m["schiedsrichter"]] == ["SR", "SRA 1", "SRA 2"]
        assert m["expenses"] is None

    def test_unbekanntes_spiel(self, db):
        assert get_match(999) is None


# ------------------------------------------------------------ Travel costs


class TestFahrtkosten:
    def test_setzen_und_lesen(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"sr_km": 42.0, "sr_oevm": 1.5, "sra1_km": 10.0, "sra2_oevm": 2.0})
        assert get_match(mid)["expenses"] == {
            "sr_km": 42.0, "sr_oevm": 1.5,
            "sra1_km": 10.0, "sra1_oevm": None,
            "sra2_km": None, "sra2_oevm": 2.0,
        }

    def test_teilupdate_laesst_andere_stehen(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"sr_km": 42.0, "sr_oevm": 1.5, "sra1_km": 10.0})
        set_official_expenses(mid, {"sr_km": 50.0})
        e = get_match(mid)["expenses"]
        assert (e["sr_km"], e["sr_oevm"], e["sra1_km"]) == (50.0, 1.5, 10.0)

    def test_none_fuer_beide_loescht(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"sr_km": 42.0, "sra1_km": 10.0})
        set_official_expenses(mid, {"sr_km": None, "sr_oevm": None})
        e = get_match(mid)["expenses"]
        assert "sr_km" not in e
        assert e["sra1_km"] == 10.0

    def test_none_fuer_einen_wert_behaelt_den_anderen(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"sr_km": 42.0, "sr_oevm": 3.0})
        set_official_expenses(mid, {"sr_km": None})
        e = get_match(mid)["expenses"]
        assert (e["sr_km"], e["sr_oevm"]) == (None, 3.0)

    def test_unbekannte_schluessel_werden_ignoriert(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"vierter_km": 99.0})
        assert get_match(mid)["expenses"] is None
        assert _anzahl("official_expenses") == 0

    def test_ueberleben_neuen_scrape(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"sr_km": 42.0, "sra1_km": 10.0})
        _upsert(user["id"], spiel(zeit="15:00"))
        assert get_match(mid)["expenses"]["sr_km"] == 42.0

    def test_unbesetzte_rolle_ausgeblendet_aber_nicht_geloescht(self, user):
        mid = _upsert(user["id"], spiel())
        set_official_expenses(mid, {"sr_km": 42.0, "sra2_km": 17.0})

        # Assistant 2 drops out in the next scrape
        _upsert(user["id"], spiel(schiedsrichter=[
            {"rolle": "SR", "name": "Erika Pfeife"}, {"rolle": "SRA 1", "name": "Max Fahne"},
        ]))
        e = get_match(mid)["expenses"]
        assert "sra2_km" not in e
        assert _anzahl("official_expenses") == 2

        # ... and comes back - the value is there again
        _upsert(user["id"], spiel())
        assert get_match(mid)["expenses"]["sra2_km"] == 17.0

    def test_rolle_ohne_namen_gilt_als_unbesetzt(self, user):
        mid = _upsert(user["id"], spiel(schiedsrichter=[
            {"rolle": "SR", "name": "Erika"}, {"rolle": "SRA 1", "name": ""},
        ]))
        set_official_expenses(mid, {"sr_km": 1.0, "sra1_km": 2.0})
        assert get_match(mid)["expenses"] == {"sr_km": 1.0, "sr_oevm": None}

    def test_spiel_ohne_kosten_hat_none(self, user):
        mid = _upsert(user["id"], spiel())
        assert get_matches_for_user(user["id"])[0]["expenses"] is None
        assert get_match(mid)["expenses"] is None


# --------------------------------------------------------------- Counting


class TestCountDistinct:
    def test_leer(self, db):
        assert count_distinct_matches() == 0

    def test_gleiches_spiel_mehrerer_nutzer_zaehlt_einmal(self, user, zweiter):
        _upsert(user["id"], spiel())
        _upsert(zweiter, spiel())
        _upsert(user["id"], spiel(heim="Anderer"))
        assert count_distinct_matches() == 2


# ---------------------------------------------------- Filling in open rates


class TestErgaenzeOffeneSaetze:
    def _ligen(self):
        from db.ligen import ersetze_staffel
        from scraper.fussball_de import Staffel, Tabellenplatz

        def platz(n, name, team_id):
            return Tabellenplatz(n, name, team_id, 10, 5, 3, 2, 20, 10, 18)

        ersetze_staffel(
            Staffel("vl", "/vl", "vl", "verbandsliga", "thueringen", "Thüringenliga"),
            [platz(1, "FC Saalfeld", "t1")],
        )
        ersetze_staffel(
            Staffel("ol", "/ol", "ol", "oberliga", "nofv", "NOFV-Oberliga Süd"),
            [platz(1, "FC Oben", "t2")],
        )

    def test_traegt_pokalsatz_nach(self, user):
        mid = _upsert(user["id"], spiel(heim="FC Saalfeld", gast="SV Unten", spielklasse="Landespokal"),
                      sr=None, sra=None)
        self._ligen()
        assert ergaenze_offene_saetze() == 1
        zeile = _zeile(mid)
        assert (zeile["sr_spesen"], zeile["sra_spesen"]) == (50.0, 40.0)

    def test_eingefrorener_satz_bleibt(self, user):
        mid = _upsert(user["id"], spiel(heim="FC Saalfeld", gast="SV Unten", spielklasse="Landespokal"),
                      sr=12.0, sra=11.0)
        self._ligen()
        assert ergaenze_offene_saetze() == 0
        assert _zeile(mid)["sr_spesen"] == 12.0

    def test_ohne_tabellen_bleibt_leer(self, user):
        mid = _upsert(user["id"], spiel(heim="FC Saalfeld", gast="SV Unten", spielklasse="Landespokal"),
                      sr=None, sra=None)
        assert ergaenze_offene_saetze() == 0
        assert _zeile(mid)["sr_spesen"] is None

    def test_punktspiele_werden_nicht_angefasst(self, user):
        mid = _upsert(user["id"], spiel(heim="FC Saalfeld", spielklasse="Verbandsliga"), sr=None, sra=None)
        self._ligen()
        assert ergaenze_offene_saetze() == 0
        assert _zeile(mid)["sr_spesen"] is None
