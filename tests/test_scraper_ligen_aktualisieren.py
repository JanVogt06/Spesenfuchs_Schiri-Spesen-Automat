"""
Naechtlicher Ligen-Abgleich: Ankervereine aus den eigenen Ansetzungen,
Staffelsuche, Schreiben der Tabellen - und was danach aus einem DFBnet-Namen
wird.

fussball.de wird nie abgerufen: entdecke_staffeln und hole_tabelle sind
ersetzt. Die Datenbank kommt aus der db-Fixture.
"""
from datetime import datetime, UTC

import pytest

from db.database import get_connection
from db.ligen import alle_staffeln, finde_mannschaft, tabelle
from scraper import fussball_de, ligen_aktualisieren
from scraper.fussball_de import FussballDeNichtErreichbar, Staffel, Tabellenplatz
from scraper.ligen_aktualisieren import Ziel, aktualisiere_alle, aktualisiere_liga


@pytest.fixture(autouse=True)
def _kein_netz(monkeypatch):
    def verboten(*args, **kwargs):
        raise AssertionError("Test wollte fussball.de wirklich abrufen")

    monkeypatch.setattr(fussball_de, "urlopen", verboten)


def _ansetzung(user_id, heim, datum, spielklasse="Verbandsliga", staffel="Verbandsliga",
               mannschaftsart="Herren", nummer=[0]):
    """Legt eine Ansetzung mit dem Noetigsten an."""
    nummer[0] += 1
    jetzt = datetime.now(UTC).isoformat()
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO matches (user_id, match_key, heim_team, gast_team, datum,
                                 mannschaftsart, spielklasse, staffel, km_satz,
                                 first_seen_at, scraped_at)
            VALUES (?, ?, ?, 'Gast', ?, ?, ?, ?, 0.3, ?, ?)
            """,
            (user_id, f"test-{nummer[0]}", heim, datum, mannschaftsart, spielklasse,
             staffel, jetzt, jetzt),
        )
        conn.commit()
    finally:
        conn.close()


def _staffel(nummer, spielklasse="verbandsliga", name=None):
    slug = f"{spielklasse}-staffel-{nummer}-{spielklasse}-herren-saison2627-thueringen"
    staffel_id = f"02TEST{spielklasse.upper()[:4]}{nummer}"
    return Staffel(
        staffel_id=staffel_id,
        pfad=f"/spieltagsuebersicht/{slug}/-/staffel/{staffel_id}",
        slug=slug,
        spielklasse=spielklasse,
        verband="thueringen",
        anzeigename=name or f"{spielklasse.title()} Staffel {nummer}",
    )


def _platz(platz, mannschaft, team_id):
    return Tabellenplatz(platz, mannschaft, team_id, 10, 5, 3, 2, 20, 10, 18)


class FakeFussballDe:
    """Ersetzt entdecke_staffeln und hole_tabelle."""

    def __init__(self, staffeln_je_verein, tabellen):
        self.staffeln_je_verein = staffeln_je_verein
        self.tabellen = tabellen
        self.gesucht = []
        self.abgerufen = []

    def entdecke_staffeln(self, verein, spielklasse, verband, mit_nachbarstaffeln):
        self.gesucht.append((verein, spielklasse, verband, mit_nachbarstaffeln))
        ergebnis = self.staffeln_je_verein.get(verein, [])
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis

    def hole_tabelle(self, staffel):
        self.abgerufen.append(staffel.staffel_id)
        ergebnis = self.tabellen[staffel.staffel_id]
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return ergebnis


@pytest.fixture
def fussball(monkeypatch):
    def einrichten(staffeln_je_verein, tabellen=None):
        fake = FakeFussballDe(staffeln_je_verein, tabellen or {})
        monkeypatch.setattr(ligen_aktualisieren, "entdecke_staffeln", fake.entdecke_staffeln)
        monkeypatch.setattr(ligen_aktualisieren, "hole_tabelle", fake.hole_tabelle)
        return fake

    return einrichten


VERBANDSLIGA = Ziel("verbandsliga", "thueringen", "Verbandsliga", True)
OBERLIGA = Ziel("oberliga", "deutschland", "Oberliga", False)


# ===== Ankervereine =====

class TestAnkervereine:
    def test_nur_herren_dieser_spielklasse_mit_heimmannschaft(self, user):
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        _ansetzung(user["id"], "SV Junior", "2026-10-02", mannschaftsart="A-Junioren")
        _ansetzung(user["id"], "SV Kreis", "2026-10-03", spielklasse="Kreisoberliga")
        _ansetzung(user["id"], "", "2026-10-04")

        assert ligen_aktualisieren._ankervereine("Verbandsliga") == ["FC Beispielstadt"]

    def test_neueste_zuerst_und_jeder_verein_einmal(self, user):
        _ansetzung(user["id"], "SV Alt", "2024-09-01")
        _ansetzung(user["id"], "FC Neu", "2026-10-01")
        _ansetzung(user["id"], "SV Alt", "2025-09-01")
        _ansetzung(user["id"], "SV Mitte", "2026-03-01")

        assert ligen_aktualisieren._ankervereine("Verbandsliga") == ["FC Neu", "SV Mitte", "SV Alt"]

    def test_hoechstens_drei_je_staffel(self, user):
        for tag, verein in enumerate(["A", "B", "C", "D"], start=1):
            _ansetzung(user["id"], verein, f"2026-10-0{tag}")

        assert ligen_aktualisieren._ankervereine("Verbandsliga") == ["D", "C", "B"]

    def test_reihum_aus_parallelen_staffeln(self, user):
        # Die vier juengsten Ansetzungen stammen alle aus "Nord" - trotzdem
        # muss "Sued" mit seinem besten Anker frueh drankommen.
        for tag, verein in enumerate(["N1", "N2", "N3", "N4"], start=5):
            _ansetzung(user["id"], verein, f"2026-10-0{tag}", spielklasse="Oberliga", staffel="Nord")
        _ansetzung(user["id"], "S1", "2026-09-01", spielklasse="Oberliga", staffel="Sued")
        _ansetzung(user["id"], "S2", "2026-08-01", spielklasse="Oberliga", staffel="Sued")

        assert ligen_aktualisieren._ankervereine("Oberliga") == ["N4", "S1", "N3", "S2", "N2"]

    def test_ohne_staffelangabe(self, user):
        _ansetzung(user["id"], "FC Ohne", "2026-10-01", staffel=None)
        assert ligen_aktualisieren._ankervereine("Verbandsliga") == ["FC Ohne"]

    def test_keine_ansetzung(self, db):
        assert ligen_aktualisieren._ankervereine("Verbandsliga") == []


# ===== Eine Liga abgleichen =====

class TestAktualisiereLiga:
    def test_ohne_anker_bleibt_liga_unbekannt(self, db, fussball):
        fake = fussball({})

        assert aktualisiere_liga(VERBANDSLIGA) == 0
        assert fake.gesucht == []
        assert alle_staffeln() == []

    def test_schreibt_tabellen(self, user, fussball):
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        staffel = _staffel(1)
        fake = fussball(
            {"FC Beispielstadt": [staffel]},
            {staffel.staffel_id: [_platz(1, "FC Beispielstadt", "T1"), _platz(2, "SV Musterdorf 2.", "T2")]},
        )

        assert aktualisiere_liga(VERBANDSLIGA) == 2
        assert fake.gesucht == [("FC Beispielstadt", "verbandsliga", "thueringen", True)]

        zeilen = tabelle(staffel.staffel_id)
        assert [(z["mannschaft"], z["kern"], z["nummer"]) for z in zeilen] == [
            ("FC Beispielstadt", "fc beispielstadt", 1),
            ("SV Musterdorf 2.", "sv musterdorf", 2),
        ]
        assert alle_staffeln()[0]["rang"] == 4

    def test_kette_beendet_suche_nach_erstem_treffer(self, user, fussball):
        _ansetzung(user["id"], "FC Neu", "2026-10-02")
        _ansetzung(user["id"], "FC Alt", "2026-10-01")
        s1, s2 = _staffel(1, "landesklasse"), _staffel(2, "landesklasse")
        fake = fussball(
            {"FC Neu": [s1, s2], "FC Alt": [s1]},
            {s1.staffel_id: [_platz(1, "FC Neu", "T1")], s2.staffel_id: [_platz(1, "FC Fremd", "T2")]},
        )

        ziel = Ziel("landesklasse", "thueringen", "Verbandsliga", True)
        assert aktualisiere_liga(ziel) == 2
        assert [g[0] for g in fake.gesucht] == ["FC Neu"]

    def test_erster_anker_nicht_gefunden(self, user, fussball):
        _ansetzung(user["id"], "FC Umbenannt", "2026-10-02")
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        staffel = _staffel(1)
        fake = fussball(
            {"FC Umbenannt": [], "FC Beispielstadt": [staffel]},
            {staffel.staffel_id: [_platz(1, "FC Beispielstadt", "T1")]},
        )

        assert aktualisiere_liga(VERBANDSLIGA) == 1
        assert [g[0] for g in fake.gesucht] == ["FC Umbenannt", "FC Beispielstadt"]

    def test_anker_nicht_erreichbar(self, user, fussball):
        _ansetzung(user["id"], "FC Weg", "2026-10-02")
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        staffel = _staffel(1)
        fussball(
            {"FC Weg": FussballDeNichtErreichbar("503"), "FC Beispielstadt": [staffel]},
            {staffel.staffel_id: [_platz(1, "FC Beispielstadt", "T1")]},
        )

        assert aktualisiere_liga(VERBANDSLIGA) == 1

    def test_ohne_kette_werden_alle_anker_gefragt(self, user, fussball):
        _ansetzung(user["id"], "FC Nord", "2026-10-02", spielklasse="Oberliga", staffel="Nord")
        _ansetzung(user["id"], "FC Sued", "2026-10-01", spielklasse="Oberliga", staffel="Sued")
        nord, sued = _staffel(1, "oberliga"), _staffel(2, "oberliga")
        fake = fussball(
            {"FC Nord": [nord], "FC Sued": [sued, nord]},
            {nord.staffel_id: [_platz(1, "FC Nord", "T1")], sued.staffel_id: [_platz(1, "FC Sued", "T2")]},
        )

        assert aktualisiere_liga(OBERLIGA) == 2
        assert [g[0] for g in fake.gesucht] == ["FC Nord", "FC Sued"]
        assert all(g[3] is False for g in fake.gesucht)
        # Jede Staffel nur einmal abgerufen, auch wenn zwei Anker sie kennen
        assert sorted(fake.abgerufen) == sorted([nord.staffel_id, sued.staffel_id])

    def test_kein_anker_gefunden(self, user, fussball):
        _ansetzung(user["id"], "FC Unbekannt", "2026-10-01")
        fake = fussball({"FC Unbekannt": []})

        assert aktualisiere_liga(VERBANDSLIGA) == 0
        assert fake.abgerufen == []

    def test_nicht_erreichbare_tabelle_laesst_andere_stehen(self, user, fussball):
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        s1, s2 = _staffel(1, "landesklasse"), _staffel(2, "landesklasse")
        fussball(
            {"FC Beispielstadt": [s1, s2]},
            {s1.staffel_id: FussballDeNichtErreichbar("500"), s2.staffel_id: [_platz(1, "FC Beispielstadt", "T1")]},
        )

        ziel = Ziel("landesklasse", "thueringen", "Verbandsliga", True)
        assert aktualisiere_liga(ziel) == 1
        assert [s["staffel_id"] for s in alle_staffeln()] == [s2.staffel_id]

    def test_leere_tabelle_behaelt_alten_stand(self, user, fussball):
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        staffel = _staffel(1)
        tabellen = {staffel.staffel_id: [_platz(1, "FC Beispielstadt", "T1")]}
        fussball({"FC Beispielstadt": [staffel]}, tabellen)
        aktualisiere_liga(VERBANDSLIGA)

        tabellen[staffel.staffel_id] = []
        assert aktualisiere_liga(VERBANDSLIGA) == 0
        assert [z["mannschaft"] for z in tabelle(staffel.staffel_id)] == ["FC Beispielstadt"]

    def test_absteiger_verschwindet(self, user, fussball):
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        staffel = _staffel(1)
        tabellen = {staffel.staffel_id: [_platz(1, "FC Beispielstadt", "T1"), _platz(2, "SV Absteiger", "T2")]}
        fussball({"FC Beispielstadt": [staffel]}, tabellen)
        aktualisiere_liga(VERBANDSLIGA)

        tabellen[staffel.staffel_id] = [_platz(1, "FC Beispielstadt", "T1")]
        aktualisiere_liga(VERBANDSLIGA)

        assert finde_mannschaft("SV Absteiger") is None


# ===== Was danach aus einem DFBnet-Namen wird =====

class TestZuordnungNachAbgleich:
    @pytest.fixture
    def ligen(self, user, fussball):
        _ansetzung(user["id"], "FC Beispielstadt", "2026-10-01")
        _ansetzung(user["id"], "SV Landanker", "2026-10-01", spielklasse="Landesklasse", staffel="Staffel 1")
        vl = _staffel(1, "verbandsliga")
        lk1, lk2 = _staffel(1, "landesklasse"), _staffel(2, "landesklasse")
        fussball(
            {"FC Beispielstadt": [vl], "SV Landanker": [lk1, lk2]},
            {
                vl.staffel_id: [
                    _platz(1, "FC Beispielstadt", "V1"),
                    _platz(2, "SV Grün-Weiß Musterdorf", "V2"),
                ],
                lk1.staffel_id: [
                    _platz(1, "FC Beispielstadt II", "L1"),
                    _platz(2, "SV Doppelort", "L2"),
                ],
                lk2.staffel_id: [
                    _platz(1, "SV Doppelort", "L3"),
                    _platz(2, "SV 1920 Probehausen", "L4"),
                ],
            },
        )
        aktualisiere_liga(VERBANDSLIGA)
        aktualisiere_liga(Ziel("landesklasse", "thueringen", "Landesklasse", True))

    @pytest.mark.parametrize("dfbnet_name, spielklasse", [
        ("FC Beispielstadt", "verbandsliga"),
        ("SG FC Beispielstadt I", "verbandsliga"),
        ("FC Beispielstadt II", "landesklasse"),
        ("FC Beispielstadt 2.", "landesklasse"),
        ("SV Gruen-Weiss Musterdorf", None),   # andere Schreibweise: kein Treffer
        ("SV Grün-Weiß Musterdorf", "verbandsliga"),
        ("SV 1920 Probehausen", "landesklasse"),
    ])
    def test_kern_und_nummer(self, ligen, dfbnet_name, spielklasse):
        treffer = finde_mannschaft(dfbnet_name)
        assert (treffer and treffer["spielklasse"]) == spielklasse

    def test_falsche_mannschaftsnummer_ergibt_nichts(self, ligen):
        # Dritte Mannschaft steht in keiner Tabelle - NICHT die erste nehmen
        assert finde_mannschaft("FC Beispielstadt III") is None
        assert finde_mannschaft("SG FC Beispielstadt 3.") is None

    def test_mehrdeutig_ergibt_nichts(self, ligen):
        assert finde_mannschaft("SV Doppelort") is None

    def test_anderer_verein_gleicher_stadt_ergibt_nichts(self, ligen):
        assert finde_mannschaft("SV 09 Probehausen") is None
        assert finde_mannschaft("Probehausen") is None

    def test_unbekannt_und_leer(self, ligen):
        assert finde_mannschaft("TSV Nirgendwo") is None
        assert finde_mannschaft("") is None


# ===== Alle Ligen =====

class TestAktualisiereAlle:
    def test_fehler_in_einer_liga_stoppt_die_anderen_nicht(self, monkeypatch):
        gerufen = []

        def fake(ziel):
            gerufen.append(ziel.spielklasse)
            if ziel.spielklasse == "landesklasse":
                raise RuntimeError("Seitenaufbau geaendert")
            return 10

        monkeypatch.setattr(ligen_aktualisieren, "aktualisiere_liga", fake)

        assert aktualisiere_alle() == 30
        assert gerufen == ["verbandsliga", "landesklasse", "regionalliga", "oberliga"]

    def test_ueberregionale_ligen_ohne_nachbarstaffeln(self):
        ziele = {z.spielklasse: z for z in ligen_aktualisieren.ZIELE}
        assert ziele["verbandsliga"].mit_nachbarstaffeln is True
        assert ziele["landesklasse"].mit_nachbarstaffeln is True
        assert ziele["regionalliga"].mit_nachbarstaffeln is False
        assert ziele["oberliga"].mit_nachbarstaffeln is False
        assert ziele["regionalliga"].verband == "region-nordostdeutschland"
