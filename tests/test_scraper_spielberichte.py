"""
Spielberichte - Einsatzplan, Bericht-Schnittstelle und Aufbereitung, ohne Browser.

Die Bericht-App ist bei DFBnet editierbar. Deshalb pruefen mehrere Tests das
Sicherheitsnetz: nur GET, nur die freigegebenen Lese-Pfade.
"""
import base64
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from scraper import spielberichte as sb
from scraper.spielberichte import (
    SitzungAbgelaufen,
    aufbereiten,
    finde_einsatzplan,
    hole_bericht,
    hole_dokument,
    ist_lesbar,
    lies_berichte,
    lies_einsatzplan,
    lies_saisons,
    oeffne_bericht_app,
    oeffne_einsatzplan,
    waehle_saison,
    wartet_auf_freigabe,
)

FIXTURES = Path(__file__).parent / "fixtures" / "scraper"

SPIEL_ID = "DFBSPIEL000000000001"
BERICHT_ID = "BERICHT00000000001"
BERICHT_SPIEL_ID = "BERICHTSPIEL0000000001"


@pytest.fixture
def bericht():
    roh = json.loads((FIXTURES / "spielbericht.json").read_text(encoding="utf-8"))
    return roh["spiel"], roh["details"]


# ===== Einsatzplan =====

class PlanLocator:
    def __init__(self, seite, selektor):
        self.seite = seite
        self.selektor = selektor

    @property
    def first(self):
        return self

    def _option(self):
        if self.selektor.startswith('li[role="option"][data-value="'):
            return self.selektor.split('"')[3]
        return None

    def wait_for(self, state=None, timeout=None):
        self.seite.gewartet.append(self.selektor)
        if self.selektor == "select.dfb-Dropdown-nativeSelect" and not self.seite.auswahl_da:
            raise TimeoutError("keine Saisonauswahl")
        option = self._option()
        if option is not None and option not in self.seite.saisons:
            raise TimeoutError(f"Option {option} nicht sichtbar")

    def click(self):
        self.seite.klicks.append(self.selektor)
        option = self._option()
        if option is not None:
            self.seite.gewaehlt = self.seite.nach_klick or option


class PlanSeite:
    """Der Einsatzplan (/spielplus/mod_sbo) mit Saisonauswahl und Liste."""

    def __init__(self, saisons=("26/27", "25/26"), gewaehlt="26/27", zeilen=None, link=None):
        self.saisons = list(saisons)
        self.gewaehlt = gewaehlt
        self.zeilen = zeilen or {}
        self.link = link
        self.nach_klick = None
        self.auswahl_da = True
        self.gotos = []
        self.klicks = []
        self.gewartet = []
        self.url = "about:blank"
        self.navigationen = 0

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append(url)
        self.url = url

    @contextmanager
    def expect_navigation(self, wait_until=None, timeout=None):
        yield
        self.navigationen += 1

    def locator(self, selektor):
        return PlanLocator(self, selektor)

    def evaluate(self, js, arg=None):
        if js is sb._EINSATZPLAN_LINK_JS:
            if isinstance(self.link, Exception):
                raise self.link
            return self.link
        if js is sb._SAISONS_JS:
            return None if not self.auswahl_da else list(self.saisons)
        if js is sb._GEWAEHLTE_SAISON_JS:
            return self.gewaehlt
        if js is sb._LISTE_JS:
            return self.zeilen.get(self.gewaehlt)
        raise AssertionError(f"Unerwartetes Skript: {js[:60]}")


class TestEinsatzplan:
    def test_link_aus_dem_menue(self):
        link = "https://www.dfbnet.org/spielplus/mod_sbo/webflow.do?event=SEARCH_REFEREE_MATCHES&x=1"
        assert finde_einsatzplan(PlanSeite(link=link)) == link

    @pytest.mark.parametrize("link", [None, "", RuntimeError("Seite weg")])
    def test_sonst_bekannte_url(self, link):
        assert finde_einsatzplan(PlanSeite(link=link)) == sb._EINSATZPLAN_URL

    def test_oeffnen_liefert_saisons(self):
        seite = PlanSeite()
        assert oeffne_einsatzplan(seite, sb._EINSATZPLAN_URL) == ["26/27", "25/26"]
        assert seite.gotos == [sb._EINSATZPLAN_URL]

    def test_oeffnen_ohne_saisonauswahl(self):
        seite = PlanSeite()
        seite.auswahl_da = False
        with pytest.raises(TimeoutError):
            oeffne_einsatzplan(seite, sb._EINSATZPLAN_URL)

    def test_saison_schon_gewaehlt(self):
        seite = PlanSeite(gewaehlt="25/26")
        waehle_saison(seite, "25/26")
        assert seite.klicks == []
        assert seite.navigationen == 0

    def test_saison_waehlen_wie_ein_mensch(self):
        seite = PlanSeite()
        waehle_saison(seite, "25/26")
        assert seite.klicks == ["input.dfb-Dropdown-combobox", 'li[role="option"][data-value="25/26"]']
        assert seite.navigationen == 1
        assert seite.gewaehlt == "25/26"

    def test_saison_nach_klick_nicht_angezeigt(self):
        seite = PlanSeite()
        seite.nach_klick = "26/27"
        with pytest.raises(RuntimeError, match="angezeigt wird '26/27'"):
            waehle_saison(seite, "25/26")

    def test_leere_liste(self):
        assert lies_einsatzplan(PlanSeite()) == []


def _zeile(datum="2025-09-14", status=("spiel_anerkannt",), spiel_id=SPIEL_ID, heim="FC Beispielstadt"):
    return {"datum": datum, "status": list(status), "dfb_spiel_id": spiel_id, "heim": heim}


HEUTE = date(2026, 11, 23)


class TestIstLesbar:
    @pytest.mark.parametrize("status", [
        ("spiel_anerkannt",),
        ("staffel_view",),
        ("staffel_wettbewerb",),
        ("spiel_erfolgt", "spiel_anerkannt"),
    ])
    def test_freigegebener_bericht(self, status):
        assert ist_lesbar(_zeile(status=status), HEUTE) is True

    @pytest.mark.parametrize("zeile", [
        _zeile(spiel_id=None),                        # kein Link (kuenftig oder Turnier)
        _zeile(datum="2026-11-23"),                   # heute
        _zeile(datum="2026-11-29"),                   # kuenftig
        _zeile(datum=""),                             # kaputtes Datum
        _zeile(datum="23.11.2025"),
        _zeile(status=("spiel_erfolgt",)),            # Bericht wird noch ausgefuellt
        _zeile(status=()),
        _zeile(status=("spiel_anerkannt", "spiel_historisch")),
        _zeile(status=("staffel_view", "spiel_geplant")),
    ])
    def test_nicht_lesbar(self, zeile):
        assert ist_lesbar(zeile, HEUTE) is False

    def test_ohne_heute_gilt_heutiges_datum(self):
        assert ist_lesbar(_zeile(datum="2000-01-01")) is True
        assert ist_lesbar(_zeile(datum="2999-01-01")) is False


class TestWartetAufFreigabe:
    def test_vergangen_ohne_freigabe(self):
        assert wartet_auf_freigabe(_zeile(status=("spiel_erfolgt",)), HEUTE) is True

    def test_schon_lesbar(self):
        assert wartet_auf_freigabe(_zeile(), HEUTE) is False

    def test_ohne_bericht_link(self):
        assert wartet_auf_freigabe(_zeile(spiel_id=None, status=("spiel_erfolgt",)), HEUTE) is False

    def test_verlegtes_spiel_wartet_nicht(self):
        assert wartet_auf_freigabe(_zeile(status=("spiel_historisch",)), HEUTE) is False


# ===== Sicherheitsnetz =====

class TestPruefePfad:
    @pytest.mark.parametrize("pfad", [
        f"report/{SPIEL_ID}/create",
        f"report/{BERICHT_ID}/matches",
        f"match/{BERICHT_SPIEL_ID}/details",
        f"match/{BERICHT_SPIEL_ID}/documents/DOKUMENT00000000001",
    ])
    def test_lese_pfade_erlaubt(self, pfad):
        assert sb._pruefe_pfad(pfad) == "/sbo-mobile/v2/oauth/" + pfad

    @pytest.mark.parametrize("pfad", [
        f"report/{BERICHT_ID}/save-report",
        f"report/{BERICHT_ID}/confirm-report",
        f"report/{BERICHT_ID}/withdraw-report",
        f"report/{BERICHT_ID}/delete",
        f"match/{BERICHT_SPIEL_ID}/documents",
        f"match/{BERICHT_SPIEL_ID}/documents/mail",
        f"match/{BERICHT_SPIEL_ID}/officials",
        f"match/{BERICHT_SPIEL_ID}/ontimekickoff",
        f"match/{BERICHT_SPIEL_ID}/edit-details",
        f"report/{BERICHT_ID}/info",
        f"report/{BERICHT_ID}/create?redirect=delete",
        f"report/{BERICHT_ID}/create/",
        f"report/../{BERICHT_ID}/create",
        "report/kurz/create",
        f"/report/{BERICHT_ID}/create",
        "",
    ])
    def test_alles_andere_verboten(self, pfad):
        with pytest.raises(ValueError, match="nicht freigegeben"):
            sb._pruefe_pfad(pfad)

    def test_skripte_rufen_nur_get(self):
        for js in (sb._HOLE_JSON_JS, sb._HOLE_DATEI_JS):
            assert "method: 'GET'" in js
            assert "POST" not in js.upper()
            assert "body" not in js


class ApiSeite:
    """Die Bericht-App: beantwortet die fetch-Skripte aus einer Tabelle."""

    def __init__(self, antworten):
        self.antworten = antworten
        self.abrufe = []

    def evaluate(self, js, url):
        assert js in (sb._HOLE_JSON_JS, sb._HOLE_DATEI_JS)
        self.abrufe.append(url)
        antwort = self.antworten[url.removeprefix("/sbo-mobile/v2/oauth/")]
        return antwort


class TestHoleJson:
    def test_daten(self):
        seite = ApiSeite({f"report/{SPIEL_ID}/create": {"status": 200, "daten": BERICHT_ID}})
        assert sb._hole_json(seite, f"report/{SPIEL_ID}/create") == BERICHT_ID
        assert seite.abrufe == [f"/sbo-mobile/v2/oauth/report/{SPIEL_ID}/create"]

    @pytest.mark.parametrize("status", [401, 403, 410])
    def test_sitzung_abgelaufen(self, status):
        seite = ApiSeite({f"report/{SPIEL_ID}/create": {"status": status}})
        with pytest.raises(SitzungAbgelaufen):
            sb._hole_json(seite, f"report/{SPIEL_ID}/create")

    @pytest.mark.parametrize("status", [404, 500, None])
    def test_andere_fehler(self, status):
        seite = ApiSeite({f"report/{SPIEL_ID}/create": {"status": status}})
        with pytest.raises(RuntimeError) as fehler:
            sb._hole_json(seite, f"report/{SPIEL_ID}/create")
        assert not isinstance(fehler.value, SitzungAbgelaufen)
        # Keine Kennungen im Protokoll
        assert SPIEL_ID not in str(fehler.value)

    def test_verbotener_pfad_wird_gar_nicht_abgerufen(self):
        seite = ApiSeite({})
        with pytest.raises(ValueError):
            sb._hole_json(seite, f"report/{BERICHT_ID}/save-report")
        assert seite.abrufe == []


class TestHoleDokument:
    PFAD = f"match/{BERICHT_SPIEL_ID}/documents/DOKUMENT00000000001"

    def test_datei(self):
        inhalt = b"%PDF-1.4 erfunden"
        seite = ApiSeite({self.PFAD: {"status": 200, "typ": "application/pdf",
                                      "inhalt": base64.b64encode(inhalt).decode()}})
        assert hole_dokument(seite, BERICHT_SPIEL_ID, "DOKUMENT00000000001") == inhalt

    def test_leere_datei(self):
        seite = ApiSeite({self.PFAD: {"status": 200, "inhalt": None}})
        assert hole_dokument(seite, BERICHT_SPIEL_ID, "DOKUMENT00000000001") == b""

    def test_sitzung_abgelaufen(self):
        seite = ApiSeite({self.PFAD: {"status": 410}})
        with pytest.raises(SitzungAbgelaufen):
            hole_dokument(seite, BERICHT_SPIEL_ID, "DOKUMENT00000000001")

    def test_http_fehler(self):
        seite = ApiSeite({self.PFAD: {"status": 404}})
        with pytest.raises(RuntimeError, match="HTTP 404"):
            hole_dokument(seite, BERICHT_SPIEL_ID, "DOKUMENT00000000001")

    def test_ungueltige_dokument_id(self):
        with pytest.raises(ValueError):
            hole_dokument(ApiSeite({}), BERICHT_SPIEL_ID, "../../delete")


class TestHoleBericht:
    def test_kopf_und_details_je_spiel(self):
        seite = ApiSeite({
            f"report/{SPIEL_ID}/create": {"status": 200, "daten": BERICHT_ID},
            f"report/{BERICHT_ID}/matches": {"status": 200, "daten": [{"id": BERICHT_SPIEL_ID, "identifier": "1"}]},
            f"match/{BERICHT_SPIEL_ID}/details": {"status": 200, "daten": {"matchInfo": {}}},
        })

        assert hole_bericht(seite, SPIEL_ID) == [
            {"spiel": {"id": BERICHT_SPIEL_ID, "identifier": "1"}, "details": {"matchInfo": {}}}
        ]
        assert len(seite.abrufe) == 3

    @pytest.mark.parametrize("antwort", [None, "", "kurz", {"id": BERICHT_ID}, "ID MIT LEERZEICHEN0"])
    def test_ohne_gueltige_berichts_id(self, antwort):
        seite = ApiSeite({f"report/{SPIEL_ID}/create": {"status": 200, "daten": antwort}})
        with pytest.raises(RuntimeError, match="Keine Berichts-ID"):
            hole_bericht(seite, SPIEL_ID)
        assert len(seite.abrufe) == 1

    def test_bericht_ohne_spiele(self):
        seite = ApiSeite({
            f"report/{SPIEL_ID}/create": {"status": 200, "daten": BERICHT_ID},
            f"report/{BERICHT_ID}/matches": {"status": 200, "daten": None},
        })
        assert hole_bericht(seite, SPIEL_ID) == []


class AppSeite:
    def __init__(self):
        self.gotos = []
        self.warte_auf = None

    @contextmanager
    def expect_response(self, bedingung, timeout=None):
        self.warte_auf = bedingung
        yield

    def goto(self, url, wait_until=None, timeout=None):
        self.gotos.append(url)


class TestOeffneBerichtApp:
    def test_laedt_app_und_wartet_auf_info(self):
        seite = AppSeite()
        oeffne_bericht_app(seite, SPIEL_ID)

        assert seite.gotos == [
            f"https://www.dfbnet.org/sbo-mobile/v2/#/match-report/report/{SPIEL_ID}?dmg_company=DFBNET"
        ]

        class Antwort:
            def __init__(self, url):
                self.url = url

        bedingung = seite.warte_auf
        assert bedingung(Antwort(f"https://www.dfbnet.org/sbo-mobile/v2/oauth/report/{BERICHT_ID}/info"))
        assert not bedingung(Antwort(f"https://www.dfbnet.org/sbo-mobile/v2/oauth/report/{BERICHT_ID}/matches"))
        assert not bedingung(Antwort("https://www.dfbnet.org/andere/info"))


# ===== Aufbereitung =====

class TestAufbereiten:
    def test_kopfdaten(self, bericht):
        daten = aufbereiten(*bericht)

        assert daten["spielkennung"] == "460101001"
        assert daten["heim"] == "FC Beispielstadt"          # ohne weiche Trennstriche
        assert daten["gast"] == "SV Musterdorf 2."          # Leerraum zusammengefasst
        assert daten["runde"] == "5. Spieltag"
        assert daten["anstoss_geplant"] == "2025-09-14T15:00:00"
        assert daten["beginn"] == "2025-09-14T15:02:00"
        assert daten["ende"] == "2025-09-14T16:52:00"
        assert daten["nachspielzeit"] == {"h1": 2, "h2": 4, "v1": None, "v2": None}
        assert daten["spielstaette"] == {
            "name": "Sportplatz Am Beispielweg",
            "ort": "99999 Beispielstadt",
            "strasse": "Beispielweg 1",
            "belag": "Kunstrasen",
        }
        assert daten["zuschauer"] == 120
        assert daten["kosten"] == {"fahrtkosten": 42.6, "spesen": 75.0}
        assert daten["bericht_spiel_id"] == BERICHT_SPIEL_ID

    def test_ergebnis(self, bericht):
        assert aufbereiten(*bericht)["ergebnis"] == {
            "halbzeit": "1:1",
            "regulaer": "2:1",
            "verlaengerung": None,
            "endstand": "2:1",
            "wertung": "",
            "abbruch_minute": None,
        }

    def test_ergebnis_ohne_tore(self, bericht):
        spiel, details = bericht
        details["matchResult"] = {"finalResult": {"homeTeamGoals": 0, "awayTeamGoals": None}}
        assert aufbereiten(spiel, details)["ergebnis"]["endstand"] is None

    def test_null_tore_sind_ein_ergebnis(self, bericht):
        spiel, details = bericht
        details["matchResult"] = {"finalResult": {"homeTeamGoals": 0, "awayTeamGoals": 0}}
        assert aufbereiten(spiel, details)["ergebnis"]["endstand"] == "0:0"

    def test_ereignisse_chronologisch(self, bericht):
        ereignisse = aufbereiten(*bericht)["ereignisse"]

        assert [(e["minute"], e["nachspielzeit"], e["typ"], e["seite"], e["person"]) for e in ereignisse] == [
            (None, None, "typ99", "", ""),
            (12, None, "gelb", "gast", "Fluegel"),
            (30, None, "gelb", "heim", "Trainer, Theo"),
            (45, None, "eigentor", "gast", "Verteidiger, Volker"),
            (45, 2, "elfmetertor", "heim", "Stuermer, Sven"),
            (60, None, "wechsel", "heim", "Ersatz, Erik"),
            (67, None, "tor", "heim", "Stuermer, Sven"),
            (88, None, "rot", "gast", "Verteidiger, Volker"),
        ]

    def test_ereignis_details(self, bericht):
        ereignisse = aufbereiten(*bericht)["ereignisse"]
        nach_typ = {(e["minute"], e["typ"]): e for e in ereignisse}

        wechsel = nach_typ[(60, "wechsel")]
        assert (wechsel["nummer"], wechsel["person_raus"], wechsel["nummer_raus"]) == (14, "Stuermer, Sven", 9)

        gelb = nach_typ[(12, "gelb")]
        assert gelb["grund"] == "Foulspiel"
        assert gelb["funktion"] is None
        assert "person_raus" not in gelb

        assert nach_typ[(88, "rot")]["sonderbericht"] is True
        assert nach_typ[(12, "gelb")]["sonderbericht"] is False

        offizieller = nach_typ[(30, "gelb")]
        assert offizieller["funktion"] == "Trainer, Betreuer"
        assert offizieller["nummer"] is None
        assert offizieller["grund"] == "Reklamieren"

    def test_aufstellung(self, bericht):
        aufstellung = aufbereiten(*bericht)["aufstellung"]

        assert aufstellung["heim"]["spieler"] == [
            {"id": "P1", "nummer": 1, "name": "Torwart, Tim", "kapitaen": False,
             "torwart": True, "ersatz": False, "status": "A"},
            {"id": "P2", "nummer": 9, "name": "Stuermer, Sven", "kapitaen": True,
             "torwart": False, "ersatz": False, "status": "Amateur"},
            {"id": "P3", "nummer": 14, "name": "Ersatz, Erik", "kapitaen": False,
             "torwart": False, "ersatz": True, "status": ""},
        ]
        assert [s["name"] for s in aufstellung["gast"]["spieler"]] == ["Verteidiger, Volker", "Fluegel"]
        assert aufstellung["heim"]["offizielle"] == [
            {"id": "O1", "name": "Trainer, Theo", "funktion": "Trainer, Betreuer"}
        ]
        assert aufstellung["gast"]["offizielle"] == [
            {"id": "O2", "name": "Coach, Carla", "funktion": "Trainerin"}
        ]

    def test_gespann_aus_rollen(self, bericht):
        assert aufbereiten(*bericht)["gespann"] == [
            {"rolle": "SR", "rolle_name": "Schiedsrichter", "name": "Muster, Max",
             "verein": "FC Schiriverein", "nicht_angetreten": False},
            {"rolle": "SRA1", "rolle_name": "1. Assistent", "name": "Beispiel, Erika",
             "verein": "SV Pfeife", "nicht_angetreten": False},
            {"rolle": "SRA2", "rolle_name": "2. Assistent", "name": "Probe, Paul",
             "verein": "", "nicht_angetreten": True},
        ]

    def test_gespann_ohne_rollen_aus_ansetzung(self, bericht):
        spiel, details = bericht
        details["matchOfficials"] = []
        details["appointedOfficials"].reverse()

        gespann = aufbereiten(spiel, details)["gespann"]

        assert [(p["rolle"], p["name"], p["rolle_name"]) for p in gespann] == [
            ("SR", "Muster, Max", ""), ("SRA1", "Beispiel, Erika", ""), ("SRA2", "Probe, Paul", ""),
        ]

    def test_bestaetigung_nur_wenn_bestaetigt(self, bericht):
        assert aufbereiten(*bericht)["bestaetigung"] == {
            "heim": {"name": "Heim, Betreuer", "zeit": "2025-09-14T17:00:00"},
            "gast": None,
            "schiedsrichter": {"name": "Muster, Max", "zeit": "2025-09-14T18:00:00"},
        }

    def test_vorkommnisse_kontrollen_bemerkungen(self, bericht):
        daten = aufbereiten(*bericht)

        assert daten["vorkommnisse"] == {
            "gemeldet": True,
            "gewalt": False,
            "diskriminierung": True,
            "spielabbruch": False,
            "beschuldigte": ["Spieler", "Zuschauer"],
            "geschaedigte": ["Schiedsrichter"],
        }
        assert daten["kontrollen"] == [
            {"name": "Passkontrolle", "wert": "ja", "bemerkung": ""},
            {"name": "Platzaufbau", "wert": "", "bemerkung": "Netz fehlte"},
        ]
        assert daten["bemerkungen"] == "Platz war tief."
        assert daten["fairplay"] is True

    def test_dokumente_nur_sichtbare(self, bericht):
        daten = aufbereiten(*bericht)

        assert daten["dokumente"] == [
            {"dfb_id": "DOKUMENT00000000001", "kategorie_id": 3, "dateiname": "spesen.pdf",
             "beschreibung": "Spesen",
             "hochgeladen": {"name": "Muster, Max", "zeit": "2025-09-14T18:10:00"}},
            {"dfb_id": "DOKUMENT00000000002", "kategorie_id": 2, "dateiname": "sonderbericht.pdf",
             "beschreibung": "", "hochgeladen": None},
        ]
        assert daten["kategorien"] == {2: "Sonderbericht", 3: "Spesendokument", 4: "Sonstiges"}

    def test_keine_persoenlichen_daten(self, bericht):
        text = json.dumps(aufbereiten(*bericht), ensure_ascii=False)

        for geheim in ("GEHEIM", "@example.org", "2000-01-01", "2001-02-02", "TELEFON", "geheim.pdf"):
            assert geheim not in text

    def test_leere_details(self):
        daten = aufbereiten({"id": BERICHT_SPIEL_ID}, {})

        assert daten["heim"] == ""
        assert daten["ereignisse"] == []
        assert daten["gespann"] == []
        assert daten["dokumente"] == []
        assert daten["bestaetigung"] == {"heim": None, "gast": None, "schiedsrichter": None}
        assert daten["vorkommnisse"]["beschuldigte"] == []
        assert daten["bericht_spiel_id"] == BERICHT_SPIEL_ID

    def test_stammdaten_aus_matchinfo_als_rueckfall(self):
        details = {"matchInfo": {"id": "INFO00000001", "identifier": "99", "kickOff": "2025-01-01T10:00",
                                 "venue": {"name": "Halle", "town": "Musterdorf"}}}
        daten = aufbereiten({}, details)

        assert daten["spielkennung"] == "99"
        assert daten["anstoss_geplant"] == "2025-01-01T10:00"
        assert daten["spielstaette"]["name"] == "Halle"
        assert daten["spielstaette"]["ort"] == "Musterdorf"
        assert daten["bericht_spiel_id"] == "INFO00000001"


# ===== Ablauf =====

class TestLiesSaisons:
    @pytest.fixture
    def ablauf(self, monkeypatch):
        protokoll = {"geoeffnet": 0, "gewaehlt": [], "fehler": set(), "oeffnen_fehler_ab": None}

        def oeffne(page, url):
            protokoll["geoeffnet"] += 1
            if protokoll["oeffnen_fehler_ab"] and protokoll["geoeffnet"] >= protokoll["oeffnen_fehler_ab"]:
                raise TimeoutError("Einsatzplan laedt nicht")
            return ["26/27", "25/26", "24/25"]

        def waehle(page, saison):
            protokoll["gewaehlt"].append(saison)
            if saison in protokoll["fehler"]:
                raise RuntimeError("falsche Saison angezeigt")
            page.gewaehlt = saison

        monkeypatch.setattr(sb, "oeffne_einsatzplan", oeffne)
        monkeypatch.setattr(sb, "waehle_saison", waehle)
        monkeypatch.setattr(sb, "lies_einsatzplan", lambda page: [{"saison": page.gewaehlt}])
        return protokoll

    def test_liest_gewuenschte_saisons(self, ablauf):
        angeboten = []
        fortschritt = []

        def saisons_fuer(liste):
            angeboten.append(liste)
            return ["26/27", "25/26"]

        ergebnis = lies_saisons(PlanSeite(), sb._EINSATZPLAN_URL, saisons_fuer,
                                lambda *a: fortschritt.append(a))

        assert angeboten == [["26/27", "25/26", "24/25"]]
        assert ergebnis == {"26/27": {"zeilen": [{"saison": "26/27"}]},
                            "25/26": {"zeilen": [{"saison": "25/26"}]}}
        assert fortschritt == [(1, 2, "Einsatzplan 26/27 (1/2)"), (2, 2, "Einsatzplan 25/26 (2/2)")]

    def test_fehlerhafte_saison_fehlt(self, ablauf):
        ablauf["fehler"] = {"25/26"}

        ergebnis = lies_saisons(PlanSeite(), sb._EINSATZPLAN_URL, lambda l: l)

        assert list(ergebnis) == ["26/27", "24/25"]
        assert ablauf["geoeffnet"] == 2  # einmal am Anfang, einmal nach dem Fehler

    def test_bricht_ab_wenn_einsatzplan_nicht_wieder_aufgeht(self, ablauf):
        ablauf["fehler"] = {"26/27"}
        ablauf["oeffnen_fehler_ab"] = 2

        assert lies_saisons(PlanSeite(), sb._EINSATZPLAN_URL, lambda l: l) == {}
        assert ablauf["gewaehlt"] == ["26/27"]


class FakeBerichtApp:
    """Ersetzt oeffne_bericht_app, hole_bericht und hole_dokument."""

    def __init__(self, bericht, monkeypatch):
        self.bericht = bericht
        self.geoeffnet = []
        self.berichte = []
        self.dokumente = []
        # Folge von Ausnahmen je Spiel-ID bzw. Dokument-ID; None = klappt
        self.bericht_fehler = {}
        self.dokument_fehler = {}
        self.oeffnen_fehler = []
        monkeypatch.setattr(sb, "oeffne_bericht_app", self.oeffne)
        monkeypatch.setattr(sb, "hole_bericht", self.hole_bericht)
        monkeypatch.setattr(sb, "hole_dokument", self.hole_dokument)

    def oeffne(self, page, spiel_id):
        self.geoeffnet.append(spiel_id)
        if self.oeffnen_fehler:
            fehler = self.oeffnen_fehler.pop(0)
            if fehler:
                raise fehler

    def hole_bericht(self, page, spiel_id):
        self.berichte.append(spiel_id)
        folge = self.bericht_fehler.get(spiel_id) or []
        if folge:
            fehler = folge.pop(0)
            if isinstance(fehler, Exception):
                raise fehler
            return fehler
        spiel, details = self.bericht
        return [{"spiel": spiel, "details": details}]

    def hole_dokument(self, page, bericht_spiel_id, dokument_id):
        self.dokumente.append((bericht_spiel_id, dokument_id))
        folge = self.dokument_fehler.get(dokument_id) or []
        if folge:
            raise folge.pop(0)
        return f"PDF {dokument_id}".encode()


@pytest.fixture
def app(bericht, monkeypatch):
    return FakeBerichtApp(bericht, monkeypatch)


ZEILEN = [_zeile(spiel_id=f"DFBSPIEL00000000000{n}", heim=f"Heim {n}") for n in range(1, 4)]


class TestLiesBerichte:
    def test_ohne_zeilen_wird_app_nicht_geoeffnet(self, app):
        assert lies_berichte(object(), [], lambda d: False) == {}
        assert app.geoeffnet == []

    def test_liest_berichte_und_neue_dokumente(self, app):
        fortschritt = []

        ergebnis = lies_berichte(object(), ZEILEN[:2], lambda d: d == "DOKUMENT00000000002",
                                 lambda *a: fortschritt.append(a))

        assert app.geoeffnet == [ZEILEN[0]["dfb_spiel_id"]]
        assert list(ergebnis) == [z["dfb_spiel_id"] for z in ZEILEN[:2]]
        eintrag = ergebnis[ZEILEN[0]["dfb_spiel_id"]]
        assert eintrag["zeile"] is ZEILEN[0]
        assert eintrag["daten"]["heim"] == "FC Beispielstadt"
        assert eintrag["dateien"] == {"DOKUMENT00000000001": b"PDF DOKUMENT00000000001"}
        # Abruf ueber die Bericht-Spiel-ID, nicht die Einsatzplan-ID
        assert app.dokumente[0] == (BERICHT_SPIEL_ID, "DOKUMENT00000000001")
        assert fortschritt[0] == (1, 2, "Spielbericht 2025-09-14 Heim 1 (1/2)")

    def test_dokumentfehler_kostet_nur_das_dokument(self, app):
        app.dokument_fehler["DOKUMENT00000000001"] = [RuntimeError("HTTP 404")]

        ergebnis = lies_berichte(object(), ZEILEN[:1], lambda d: False)

        assert ergebnis[ZEILEN[0]["dfb_spiel_id"]]["dateien"] == {
            "DOKUMENT00000000002": b"PDF DOKUMENT00000000002"
        }

    def test_abgelaufene_sitzung_laedt_app_einmal_neu(self, app):
        zweite = ZEILEN[1]["dfb_spiel_id"]
        app.bericht_fehler[zweite] = [SitzungAbgelaufen("410 auf report")]

        ergebnis = lies_berichte(object(), ZEILEN, lambda d: True)

        assert list(ergebnis) == [z["dfb_spiel_id"] for z in ZEILEN]
        assert app.geoeffnet == [ZEILEN[0]["dfb_spiel_id"], zweite]
        assert app.berichte.count(zweite) == 2

    def test_zweite_abgelaufene_sitzung_gibt_auf(self, app):
        zweite, dritte = ZEILEN[1]["dfb_spiel_id"], ZEILEN[2]["dfb_spiel_id"]
        app.bericht_fehler[zweite] = [SitzungAbgelaufen("410"), SitzungAbgelaufen("410")]

        ergebnis = lies_berichte(object(), ZEILEN, lambda d: True)

        # Was bis dahin gelesen war, bleibt; danach wird nichts mehr versucht
        assert list(ergebnis) == [ZEILEN[0]["dfb_spiel_id"]]
        assert dritte not in app.berichte

    def test_nur_einmal_pro_lauf_neu_laden(self, app):
        zweite, dritte = ZEILEN[1]["dfb_spiel_id"], ZEILEN[2]["dfb_spiel_id"]
        app.bericht_fehler[zweite] = [SitzungAbgelaufen("410")]
        app.bericht_fehler[dritte] = [SitzungAbgelaufen("410")]

        ergebnis = lies_berichte(object(), ZEILEN, lambda d: True)

        assert list(ergebnis) == [ZEILEN[0]["dfb_spiel_id"], zweite]
        assert len(app.geoeffnet) == 2

    def test_abgelaufene_sitzung_beim_dokument(self, app):
        app.dokument_fehler["DOKUMENT00000000001"] = [SitzungAbgelaufen("401 beim Dokument")]

        ergebnis = lies_berichte(object(), ZEILEN[:1], lambda d: False)

        assert len(app.geoeffnet) == 2
        assert set(ergebnis[ZEILEN[0]["dfb_spiel_id"]]["dateien"]) == {
            "DOKUMENT00000000001", "DOKUMENT00000000002",
        }

    def test_anderer_fehler_ueberspringt_nur_diesen_bericht(self, app):
        zweite = ZEILEN[1]["dfb_spiel_id"]
        app.bericht_fehler[zweite] = [RuntimeError("HTTP 500")]

        ergebnis = lies_berichte(object(), ZEILEN, lambda d: True)

        assert list(ergebnis) == [ZEILEN[0]["dfb_spiel_id"], ZEILEN[2]["dfb_spiel_id"]]
        assert app.berichte.count(zweite) == 1  # kein zweiter Versuch
        assert len(app.geoeffnet) == 1

    def test_bericht_ohne_spiel(self, app):
        app.bericht_fehler[ZEILEN[0]["dfb_spiel_id"]] = [[]]

        ergebnis = lies_berichte(object(), ZEILEN[:2], lambda d: True)

        assert list(ergebnis) == [ZEILEN[1]["dfb_spiel_id"]]

    def test_neuladen_scheitert_gelesenes_bleibt(self, app):
        zweite = ZEILEN[1]["dfb_spiel_id"]
        app.bericht_fehler[zweite] = [SitzungAbgelaufen("410")]
        app.oeffnen_fehler = [None, TimeoutError("App laedt nicht")]

        ergebnis = lies_berichte(object(), ZEILEN, lambda d: True)

        assert list(ergebnis) == [ZEILEN[0]["dfb_spiel_id"]]
