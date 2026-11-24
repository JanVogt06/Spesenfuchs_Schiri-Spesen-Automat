"""
The tabs beside the expenses: master data, seasons, match reports including
documents, observations and league tables.

Everything is created via the real write functions from src/db.
"""
import pytest

from api_hilfen import (  # noqa: F401 - Fixtures
    datenverzeichnis,
    fehlerbild,
    fremder,
)


def _log():
    from db.database import get_connection

    conn = get_connection()
    try:
        return [dict(z) for z in conn.execute(
            "SELECT user_id, spielbericht_id, dokument_id, aktion, quelle FROM spielbericht_log ORDER BY id")]
    finally:
        conn.close()


# ===== Master data =====

class TestStammdaten:
    def test_vor_dem_ersten_abruf_null(self, client, user, auth_header):
        antwort = client.get("/api/stammdaten", headers=auth_header)
        assert antwort.status_code == 200
        assert antwort.json() is None

    def test_liefert_klartext(self, client, user, auth_header):
        from db.stammdaten import upsert_stammdaten

        upsert_stammdaten(user["id"], {"name_vorname": "Pfeife, Erika", "geburtsdatum": "01.02.1990",
                                       "verein": "FC Heim", "schiedsrichter_seit": "01.07.2010"})

        daten = client.get("/api/stammdaten", headers=auth_header).json()

        assert daten["user_id"] == user["id"]
        assert daten["name_vorname"] == "Pfeife, Erika"
        assert daten["geburtsdatum"] == "01.02.1990"
        assert daten["verein"] == "FC Heim"
        assert daten["strasse"] == ""

    def test_nur_eigene(self, client, user, auth_header, fremder):
        from db.stammdaten import upsert_stammdaten

        upsert_stammdaten(fremder["id"], {"name_vorname": "Fremd, Franz"})

        assert client.get("/api/stammdaten", headers=auth_header).json() is None
        assert client.get("/api/stammdaten", headers=fremder["header"]).json()["name_vorname"] == "Fremd, Franz"


# ===== Seasons =====

def _saison(user_id, saison="26/27", spiele=None, einsaetze=None, lehrgaenge=None):
    from db.season import replace_saison

    if spiele is None:
        spiele = [
            {"datum": "2026-09-05", "uhrzeit": "15:00", "liga": "Kreisoberliga", "heim": "FC Heim",
             "gast": "SV Gast", "ergebnis": "2:1", "heim_gelb": "3", "gast_rot": "-",
             "eigene_rolle": "SR",
             "gespann": [{"rolle": "SR", "name": "Erika Pfeife", "selbst": True},
                         {"rolle": "SRA 1", "name": "Max Fahne"}]},
            {"datum": "2026-08-22", "uhrzeit": "13:00", "liga": "Kreisliga", "heim": "SV Alt",
             "gast": "FC Neu", "ergebnis": "0:0", "eigene_rolle": "SRA 1", "gespann": []},
        ]
    replace_saison(user_id, saison, spiele=spiele,
                   einsaetze=einsaetze if einsaetze is not None else
                   [{"rolle": "SR", "geleitet": "1"}, {"rolle": "SRA", "geleitet": "1"}],
                   lehrgaenge=lehrgaenge if lehrgaenge is not None else
                   {"lehrabend": "3", "lehrabend_online": "1", "leistungspruefung": "bestanden"})


class TestSaisons:
    def test_liste_leer(self, client, user, auth_header):
        assert client.get("/api/saison", headers=auth_header).json() == []

    def test_liste_neueste_zuerst(self, client, user, auth_header):
        _saison(user["id"], "24/25")
        _saison(user["id"], "26/27")
        # Start of season: only courses, no match yet - must still appear
        _saison(user["id"], "25/26", spiele=[], einsaetze=[])

        liste = client.get("/api/saison", headers=auth_header).json()

        assert [s["saison"] for s in liste] == ["26/27", "25/26", "24/25"]
        assert [s["spiele"] for s in liste] == [2, 0, 2]
        assert liste[0]["letztes_spiel"] == "2026-09-05"
        assert liste[1]["letztes_spiel"] is None

    def test_saison_mit_schraegstrich(self, client, user, auth_header):
        _saison(user["id"], "26/27")

        antwort = client.get("/api/saison/26/27", headers=auth_header)

        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["saison"] == "26/27"
        assert [s["heim"] for s in daten["spiele"]] == ["FC Heim", "SV Alt"]
        erstes = daten["spiele"][0]
        assert erstes["heim_gelb"] == 3
        assert erstes["gast_rot"] is None
        assert erstes["gespann"] == [
            {"rolle": "SR", "name": "Erika Pfeife", "ist_selbst": True},
            {"rolle": "SRA 1", "name": "Max Fahne", "ist_selbst": False},
        ]
        assert erstes["spielbericht"] is None
        assert [e["rolle"] for e in daten["einsaetze"]] == ["SR", "SRA"]
        assert daten["lehrgaenge"]["leistungspruefung"] == "bestanden"

    def test_saison_nur_mit_lehrgaengen(self, client, user, auth_header):
        _saison(user["id"], "26/27", spiele=[], einsaetze=[])

        daten = client.get("/api/saison/26/27", headers=auth_header).json()

        assert daten["spiele"] == []
        assert daten["lehrgaenge"]["lehrabend"] == "3"

    def test_unbekannte_saison_404(self, client, user, auth_header):
        _saison(user["id"], "26/27")

        antwort = client.get("/api/saison/25/26", headers=auth_header)

        assert antwort.status_code == 404
        fehler = fehlerbild(antwort)
        assert fehler["code"] == "NOT_FOUND"
        assert "25/26" in fehler["message"]

    def test_fremde_saison_404(self, client, user, auth_header, fremder):
        _saison(fremder["id"], "26/27")

        assert client.get("/api/saison", headers=auth_header).json() == []
        assert client.get("/api/saison/26/27", headers=auth_header).status_code == 404

    def test_spielbericht_wird_zugeordnet(self, client, user, auth_header, datenverzeichnis):
        from db.spielberichte import speichere_bericht

        _saison(user["id"], "26/27")
        bericht_id = speichere_bericht(
            user["id"], "26/27",
            # Spelling as in the match report module: team number appended
            {"dfb_spiel_id": "S1", "datum": "2026-09-05", "uhrzeit": "15:00",
             "heim": "FC Heim 1.", "gast": "SV Gast"},
            {"kosten": {"fahrtkosten": 9.0, "spesen": 30.0}}, {},
        )

        spiele = client.get("/api/saison/26/27", headers=auth_header).json()["spiele"]

        assert spiele[0]["spielbericht"] == {"id": bericht_id, "fahrtkosten": 9.0,
                                             "spesen": 30.0, "dokumente": 0}
        assert spiele[1]["spielbericht"] is None


# ===== Match reports =====

@pytest.fixture
def bericht(user, datenverzeichnis):
    """A match report with a PDF and an image document."""
    from db.spielberichte import get_bericht, speichere_bericht

    bericht_id = speichere_bericht(
        user["id"], "26/27",
        {"dfb_spiel_id": "SPIEL1", "datum": "2026-09-05", "uhrzeit": "15:00",
         "gruppe": "KOL", "nummer": "123", "heim": "FC Heim", "gast": "SV Gast", "ergebnis": "2:1"},
        {
            "spielkennung": "KOL-123",
            "kosten": {"fahrtkosten": 12.6, "spesen": 30.0},
            "verlauf": [{"minute": 12, "text": "Tor"}],
            "kategorien": {"1": "Sonderbericht", "2": "Spesendokument"},
            "dokumente": [
                {"dfb_id": "DOK1", "dateiname": "Sonderbericht Spielabbruch.pdf", "kategorie_id": 1,
                 "beschreibung": "Abbruch", "hochgeladen": {"name": "Erika Pfeife", "zeit": "05.09.2026 18:00"}},
                {"dfb_id": "DOK2", "dateiname": "Quittung Über.jpg", "kategorie_id": 2,
                 "hochgeladen": {"name": "Erika Pfeife", "zeit": "05.09.2026 18:05"}},
            ],
        },
        {"DOK1": b"%PDF-1.4 sonderbericht", "DOK2": b"\xff\xd8\xff bild"},
    )
    dokumente = {d["dfb_dokument_id"]: d["id"] for d in get_bericht(user["id"], bericht_id)["dokumente"]}
    return {"id": bericht_id, "pdf": dokumente["DOK1"], "bild": dokumente["DOK2"]}


class TestSpielbericht:
    def test_liefert_bericht(self, client, user, auth_header, bericht):
        antwort = client.get(f"/api/spielberichte/{bericht['id']}", headers=auth_header)

        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["id"] == bericht["id"]
        assert daten["heim"] == "FC Heim"
        assert daten["fahrtkosten"] == 12.6
        assert daten["daten"]["verlauf"] == [{"minute": 12, "text": "Tor"}]
        assert [d["kategorie"] for d in daten["dokumente"]] == ["Sonderbericht", "Spesendokument"]
        assert [d["dateiname"] for d in daten["dokumente"]] == \
            ["Sonderbericht Spielabbruch.pdf", "Quittung Über.jpg"]
        # The path on disk stays internal
        assert all("pfad" not in d for d in daten["dokumente"])

    @pytest.mark.parametrize("quelle, erwartet", [
        (None, "direkt"), ("saison", "saison"), ("spesen", "spesen"),
        ("bericht", "direkt"), ("<script>", "direkt"),
    ])
    def test_ansehen_wird_protokolliert(self, client, user, auth_header, bericht, quelle, erwartet):
        params = {"quelle": quelle} if quelle is not None else {}
        client.get(f"/api/spielberichte/{bericht['id']}", headers=auth_header, params=params)

        assert _log() == [{"user_id": user["id"], "spielbericht_id": bericht["id"], "dokument_id": None,
                           "aktion": "ansehen", "quelle": erwartet}]

    def test_doppelklick_zaehlt_einmal(self, client, user, auth_header, bericht):
        for _ in range(3):
            client.get(f"/api/spielberichte/{bericht['id']}", headers=auth_header, params={"quelle": "saison"})
        client.get(f"/api/spielberichte/{bericht['id']}", headers=auth_header, params={"quelle": "spesen"})

        assert [e["quelle"] for e in _log()] == ["saison", "spesen"]

    def test_fehler_im_log_verhindert_bericht_nicht(self, client, user, auth_header, bericht, monkeypatch):
        def kaputt(*args, **kwargs):
            raise RuntimeError("Log-Tabelle gesperrt")

        monkeypatch.setattr("api.main_api.log_spielbericht", kaputt)

        assert client.get(f"/api/spielberichte/{bericht['id']}", headers=auth_header).status_code == 200

    def test_unbekannt_404(self, client, user, auth_header, bericht):
        antwort = client.get("/api/spielberichte/999", headers=auth_header)
        assert antwort.status_code == 404
        assert fehlerbild(antwort)["code"] == "NOT_FOUND"
        assert _log() == []

    def test_fremder_bericht_404_ohne_log(self, client, bericht, fremder):
        antwort = client.get(f"/api/spielberichte/{bericht['id']}", headers=fremder["header"])
        assert antwort.status_code == 404
        assert _log() == []

    def test_ungueltige_id_422(self, client, user, auth_header):
        assert client.get("/api/spielberichte/abc", headers=auth_header).status_code == 422


class TestSpielberichtDokument:
    def _url(self, bericht, dokument_id=None):
        return f"/api/spielberichte/{bericht['id']}/dokumente/{dokument_id or bericht['pdf']}"

    def test_pdf(self, client, user, auth_header, bericht):
        from urllib.parse import unquote

        antwort = client.get(self._url(bericht), headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.content == b"%PDF-1.4 sonderbericht"
        assert antwort.headers["content-type"] == "application/pdf"
        header = antwort.headers["content-disposition"]
        assert unquote(header.split("filename*=UTF-8''")[1]) == "Sonderbericht Spielabbruch.pdf"

    def test_anderes_format(self, client, user, auth_header, bericht):
        from urllib.parse import unquote

        antwort = client.get(self._url(bericht, bericht["bild"]), headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.content == b"\xff\xd8\xff bild"
        assert antwort.headers["content-type"] == "application/octet-stream"
        header = antwort.headers["content-disposition"]
        assert unquote(header.split("filename*=UTF-8''")[1]) == "Quittung Über.jpg"
        assert 'filename="Quittung Uber.jpg"' in header

    @pytest.mark.parametrize("aktion, erwartet", [
        (None, "dokument_laden"), ("laden", "dokument_laden"),
        ("oeffnen", "dokument_oeffnen"), ("loeschen", "dokument_laden"),
    ])
    def test_wird_protokolliert(self, client, user, auth_header, bericht, aktion, erwartet):
        params = {"aktion": aktion} if aktion else {}
        client.get(self._url(bericht), headers=auth_header, params=params)

        assert _log() == [{"user_id": user["id"], "spielbericht_id": bericht["id"],
                           "dokument_id": bericht["pdf"], "aktion": erwartet, "quelle": "bericht"}]

    def test_fremdes_dokument_404(self, client, bericht, fremder):
        assert client.get(self._url(bericht), headers=fremder["header"]).status_code == 404
        assert _log() == []

    def test_dokument_eines_anderen_berichts_404(self, client, user, auth_header, bericht):
        from db.spielberichte import speichere_bericht

        anderer = speichere_bericht(user["id"], "26/27",
                                    {"dfb_spiel_id": "SPIEL2", "datum": "2026-09-12",
                                     "heim": "A", "gast": "B"}, {}, {})

        antwort = client.get(f"/api/spielberichte/{anderer}/dokumente/{bericht['pdf']}", headers=auth_header)
        assert antwort.status_code == 404

    def test_unbekanntes_dokument_404(self, client, user, auth_header, bericht):
        assert client.get(self._url(bericht, 999), headers=auth_header).status_code == 404

    def test_datei_fehlt_auf_der_platte_404(self, client, user, auth_header, bericht, datenverzeichnis):
        for datei in (datenverzeichnis / "spielberichte").rglob("*.pdf"):
            datei.unlink()

        antwort = client.get(self._url(bericht), headers=auth_header)

        assert antwort.status_code == 404
        assert _log() == []

    def test_pfad_ausserhalb_des_datenordners_404(self, client, user, auth_header, bericht,
                                                  datenverzeichnis):
        from db.database import get_connection

        geheim = datenverzeichnis.parent / "geheim.txt"
        geheim.write_text("nicht fuer dich")

        conn = get_connection()
        conn.execute("UPDATE spielbericht_dokumente SET pfad = '../geheim.txt' WHERE id = ?", (bericht["pdf"],))
        conn.commit()
        conn.close()

        antwort = client.get(self._url(bericht), headers=auth_header)

        assert antwort.status_code == 404
        assert "nicht fuer dich" not in antwort.text


# ===== Observations =====

class TestBeobachtungen:
    def test_leer(self, client, user, auth_header):
        antwort = client.get("/api/beobachtungen", headers=auth_header)
        assert antwort.status_code == 200
        assert antwort.json() == {"saisons": [], "beobachtungen": [], "schiedsrichter_seit": None}

    def test_mit_noten_und_seit(self, client, user, auth_header):
        from db.beobachtungen import replace_beobachtungs_saison
        from db.stammdaten import upsert_stammdaten

        upsert_stammdaten(user["id"], {"schiedsrichter_seit": "01.07.2010"})
        replace_beobachtungs_saison(user["id"], "schiri-portal", "26/27", [
            {"datum": "2026-09-05", "uhrzeit": "15:00", "rolle": "SR", "note": "8.4",
             "heim": "FC Heim", "gast": "SV Gast", "beobachter": "B. Obachter"},
            {"datum": "2026-10-10", "uhrzeit": "14:00", "rolle": "SR", "note": 8.7,
             "heim": "FC Neu", "gast": "SV Alt"},
        ])

        daten = client.get("/api/beobachtungen", headers=auth_header).json()

        assert daten["schiedsrichter_seit"] == "01.07.2010"
        assert [(s["quelle"], s["saison"], s["anzahl"]) for s in daten["saisons"]] == \
            [("schiri-portal", "26/27", 2)]
        assert [b["note"] for b in daten["beobachtungen"]] == [8.7, 8.4]
        assert daten["beobachtungen"][1]["beobachter"] == "B. Obachter"

    def test_nur_eigene(self, client, user, auth_header, fremder):
        from db.beobachtungen import replace_beobachtungs_saison

        replace_beobachtungs_saison(fremder["id"], "schiri-portal", "26/27",
                                    [{"datum": "2026-09-05", "rolle": "SR", "note": 8.0}])

        assert client.get("/api/beobachtungen", headers=auth_header).json()["beobachtungen"] == []


# ===== Leagues =====

class TestLigen:
    def test_leer(self, client, user, auth_header):
        antwort = client.get("/api/ligen", headers=auth_header)
        assert antwort.status_code == 200
        assert antwort.json() == {
            "bestand": {"staffeln": 0, "mannschaften": 0, "aktualisiert_at": None},
            "staffeln": [],
        }

    def test_tabellen_hoechste_klasse_zuerst(self, client, user, auth_header):
        from db.ligen import ersetze_staffel
        from scraper.fussball_de import Staffel, Tabellenplatz

        def platz(n, name, team_id, punkte):
            return Tabellenplatz(n, name, team_id, 10, 5, 3, 2, 20, 10, punkte)

        ersetze_staffel(Staffel("lk", "/lk", "lk", "landesklasse", "thueringen", "Landesklasse Ost"),
                        [platz(2, "SV Zwei", "t2", 15), platz(1, "FC Eins", "t1", 20)])
        ersetze_staffel(Staffel("vl", "/vl", "vl", "verbandsliga", "thueringen", "Thüringenliga"),
                        [platz(1, "FC Saalfeld", "t3", 30)])

        daten = client.get("/api/ligen", headers=auth_header).json()

        assert daten["bestand"]["staffeln"] == 2
        assert daten["bestand"]["mannschaften"] == 3
        assert daten["bestand"]["aktualisiert_at"] is not None
        assert [s["staffel_id"] for s in daten["staffeln"]] == ["vl", "lk"]
        landesklasse = daten["staffeln"][1]
        assert landesklasse["mannschaften"] == 2
        assert [(z["platz"], z["mannschaft"], z["punkte"]) for z in landesklasse["tabelle"]] == \
            [(1, "FC Eins", 20), (2, "SV Zwei", 15)]
