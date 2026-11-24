"""
Spiele: Liste, Fahrtkosten, Karte, Einzel- und Sammel-Download.

Die Spiele entstehen ueber main.persist_matches, also genau wie nach einem
Scrape. DOCX und XLSX werden echt gerendert; nur die PDF-Konvertierung
(LibreOffice) und der Geocoder (Nominatim) sind ersetzt.
"""
import zipfile
from datetime import datetime
from io import BytesIO
from urllib.parse import unquote

import pytest

from db_helpers import spiel
from api_hilfen import (  # noqa: F401 - Fixtures
    datenverzeichnis,
    fehlerbild,
    fremder,
    nofv_spiel,
    spiele_anlegen,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _downloads():
    from db.database import get_connection

    conn = get_connection()
    try:
        return [dict(z) for z in conn.execute(
            "SELECT user_id, match_id, filename, file_type FROM download_log ORDER BY id")]
    finally:
        conn.close()


def _dateiname_aus(header: str) -> str:
    """Der UTF-8-Name aus filename*=UTF-8''... des Content-Disposition-Headers."""
    assert header.startswith("attachment; ")
    kodiert = header.split("filename*=UTF-8''", 1)[1]
    return unquote(kodiert)


def _ascii_name_aus(header: str) -> str:
    return header.split('filename="', 1)[1].split('"', 1)[0]


@pytest.fixture
def ein_spiel(user):
    (match_id,) = spiele_anlegen(user["id"], spiel())
    return match_id


@pytest.fixture
def pdf(monkeypatch):
    """Ersetzt LibreOffice: jedes Dokument wird zu einer erkennbaren Pseudo-PDF."""
    import api.main_api as modul

    aufrufe = []

    def konvertieren(dokumente):
        aufrufe.append(list(dokumente))
        return [b"%PDF-1.7 " + name.encode() for name, _ in dokumente]

    monkeypatch.setattr(modul, "convert_docx_bytes_to_pdf", konvertieren)
    return aufrufe


# ===== Liste =====

class TestListe:
    def test_leer(self, client, user, auth_header):
        antwort = client.get("/api/matches", headers=auth_header)
        assert antwort.status_code == 200
        assert antwort.json() == []

    def test_felder_fuer_das_frontend(self, client, user, auth_header, ein_spiel):
        from generator.spesen_calculator import format_spesen

        (eintrag,) = client.get("/api/matches", headers=auth_header).json()

        assert eintrag["_id"] == eintrag["id"] == ein_spiel
        assert eintrag["_datum"] == "2026-12-05"
        assert eintrag["_filename"] == "Spesen_FC Heim_vs_SV Gast_05-12-2026.docx"
        assert eintrag["_expenses"] is None
        assert eintrag["_missing_since"] is None
        assert eintrag["_spielbericht"] is None
        assert eintrag["spiel_info"]["heim_team"] == "FC Heim"
        assert eintrag["spielstaette"]["name"] == "Sportplatz Am Wald"
        assert [p["rolle"] for p in eintrag["schiedsrichter"]] == ["SR", "SRA 1", "SRA 2"]

        spesen = eintrag["_spesen"]
        assert spesen["is_punktspiel"] is True
        assert spesen["sra_count"] == 2
        assert spesen["sr"] == eintrag["sr_spesen"]
        assert spesen["sra"] == eintrag["sra_spesen"]
        assert spesen["sr"] is not None
        assert spesen["hinweis"] is None
        assert spesen["sr_formatted"] == format_spesen(spesen["sr"])
        assert spesen["sra_formatted"] == format_spesen(spesen["sra"])

    def test_eingefrorene_saetze_gelten(self, client, user, auth_header, ein_spiel):
        """Die Karte zeigt den Satz aus der Datenbank, nicht einen neu gerechneten."""
        from db.database import get_connection

        conn = get_connection()
        conn.execute("UPDATE matches SET sr_spesen = 12.5, sra_spesen = 7.5 WHERE id = ?", (ein_spiel,))
        conn.commit()
        conn.close()

        spesen = client.get("/api/matches", headers=auth_header).json()[0]["_spesen"]
        assert (spesen["sr"], spesen["sra"]) == (12.5, 7.5)

    @pytest.mark.parametrize("spielklasse, stichwort", [
        ("Kreispokal", "Pokalspiel"),
        ("Freundschaftsspiele", "Freundschaftsspiel"),
    ])
    def test_hinweis_ohne_satz(self, client, user, auth_header, spielklasse, stichwort):
        spiele_anlegen(user["id"], spiel(spielklasse=spielklasse, heim="FC Unbekannt", gast="SV Niemand"))

        spesen = client.get("/api/matches", headers=auth_header).json()[0]["_spesen"]

        assert spesen["sr"] is None
        assert spesen["is_punktspiel"] is False
        assert spesen["hinweis"].startswith(stichwort)

    def test_neueste_zuerst(self, client, user, auth_header):
        spiele_anlegen(user["id"],
                       spiel(heim="FC Frueh", tag="2026-11-28"),
                       spiel(heim="FC Spaet", tag="2026-12-12"),
                       spiel(heim="FC Mitte", tag="2026-12-05"))

        heim = [m["spiel_info"]["heim_team"] for m in client.get("/api/matches", headers=auth_header).json()]
        assert heim == ["FC Spaet", "FC Mitte", "FC Frueh"]

    def test_nur_eigene_spiele(self, client, user, auth_header, fremder):
        spiele_anlegen(user["id"], spiel(heim="FC Meins"))
        spiele_anlegen(fremder["id"], spiel(heim="FC Fremd"))

        eigene = client.get("/api/matches", headers=auth_header).json()
        fremde = client.get("/api/matches", headers=fremder["header"]).json()

        assert [m["spiel_info"]["heim_team"] for m in eigene] == ["FC Meins"]
        assert [m["spiel_info"]["heim_team"] for m in fremde] == ["FC Fremd"]

    def test_zurueckgezogenes_spiel(self, client, user, auth_header):
        spiele_anlegen(user["id"], spiel(heim="FC Weg", tag="2026-12-05"), spiel(heim="FC Bleibt"))
        # Der naechste Scrape kennt das kuenftige Spiel nicht mehr
        spiele_anlegen(user["id"], spiel(heim="FC Bleibt"))

        nach_heim = {m["spiel_info"]["heim_team"]: m
                     for m in client.get("/api/matches", headers=auth_header).json()}
        assert nach_heim["FC Weg"]["_missing_since"] is not None
        assert nach_heim["FC Bleibt"]["_missing_since"] is None

    def test_spielbericht_wird_zugeordnet(self, client, user, auth_header, datenverzeichnis, ein_spiel):
        from db.spielberichte import speichere_bericht

        bericht_id = speichere_bericht(
            user["id"], "26/27",
            {"dfb_spiel_id": "S1", "datum": "2026-12-05", "uhrzeit": "13:00",
             "heim": "FC Heim", "gast": "SV Gast"},
            {"kosten": {"fahrtkosten": 12.6, "spesen": 30.0},
             "dokumente": [{"dfb_id": "D1", "dateiname": "x.pdf"}]},
            {"D1": b"%PDF"},
        )

        eintrag = client.get("/api/matches", headers=auth_header).json()[0]
        assert eintrag["_spielbericht"] == {"id": bericht_id, "fahrtkosten": 12.6,
                                            "spesen": 30.0, "dokumente": 1}

    def test_fremder_spielbericht_wird_nicht_zugeordnet(self, client, user, auth_header,
                                                        datenverzeichnis, ein_spiel, fremder):
        from db.spielberichte import speichere_bericht

        speichere_bericht(fremder["id"], "26/27",
                          {"dfb_spiel_id": "S1", "datum": "2026-12-05", "heim": "FC Heim", "gast": "SV Gast"},
                          {}, {})

        assert client.get("/api/matches", headers=auth_header).json()[0]["_spielbericht"] is None


# ===== Fahrtkosten =====

def _kosten(client, header, **felder):
    return client.post("/api/matches/expenses", headers=header, json=felder)


class TestFahrtkosten:
    def test_speichert_und_liefert_zurueck(self, client, user, auth_header, ein_spiel):
        antwort = _kosten(client, auth_header, match_id=ein_spiel, sr_km=42, sr_oevm=7.5)

        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["success"] is True
        assert daten["filename"] == "Spesen_FC Heim_vs_SV Gast_05-12-2026.docx"
        assert daten["expenses"] == {"sr_km": 42.0, "sr_oevm": 7.5}
        assert daten["spesen"]["sra_count"] == 2

        # Und bleibt gespeichert
        eintrag = client.get("/api/matches", headers=auth_header).json()[0]
        assert eintrag["_expenses"] == {"sr_km": 42.0, "sr_oevm": 7.5}

    def test_teil_update_laesst_andere_rollen_stehen(self, client, user, auth_header, ein_spiel):
        _kosten(client, auth_header, match_id=ein_spiel, sr_km=42, sra1_km=10)
        daten = _kosten(client, auth_header, match_id=ein_spiel, sra2_oevm=3).json()

        assert daten["expenses"] == {"sr_km": 42.0, "sr_oevm": None,
                                     "sra1_km": 10.0, "sra1_oevm": None,
                                     "sra2_km": None, "sra2_oevm": 3.0}

    def test_teil_update_laesst_anderes_feld_derselben_rolle_stehen(self, client, user, auth_header,
                                                                    ein_spiel):
        _kosten(client, auth_header, match_id=ein_spiel, sr_km=42, sr_oevm=5)
        daten = _kosten(client, auth_header, match_id=ein_spiel, sr_km=50).json()
        assert daten["expenses"] == {"sr_km": 50.0, "sr_oevm": 5.0}

    def test_ausdrueckliches_null_leert(self, client, user, auth_header, ein_spiel):
        _kosten(client, auth_header, match_id=ein_spiel, sr_km=42, sra1_km=10)
        daten = _kosten(client, auth_header, match_id=ein_spiel, sr_km=None).json()
        assert daten["expenses"] == {"sra1_km": 10.0, "sra1_oevm": None}

        daten = _kosten(client, auth_header, match_id=ein_spiel, sra1_km=None).json()
        assert daten["expenses"] is None

    @pytest.mark.parametrize("wert", [0, 0.5, 99999])
    def test_grenzwerte_erlaubt(self, client, user, auth_header, ein_spiel, wert):
        antwort = _kosten(client, auth_header, match_id=ein_spiel, sr_km=wert)
        assert antwort.status_code == 200
        assert antwort.json()["expenses"]["sr_km"] == wert

    @pytest.mark.parametrize("feld, wert", [
        ("sr_km", -1), ("sr_oevm", -0.01), ("sra1_km", 100000), ("sra2_oevm", 1e9),
    ])
    def test_ungueltige_werte_400(self, client, user, auth_header, ein_spiel, feld, wert):
        antwort = _kosten(client, auth_header, match_id=ein_spiel, **{feld: wert})

        assert antwort.status_code == 400
        assert feld in antwort.json()["detail"]
        assert client.get("/api/matches", headers=auth_header).json()[0]["_expenses"] is None

    def test_ungueltiger_wert_speichert_auch_gueltige_nicht(self, client, user, auth_header, ein_spiel):
        assert _kosten(client, auth_header, match_id=ein_spiel, sr_km=10, sra1_km=-5).status_code == 400
        assert client.get("/api/matches", headers=auth_header).json()[0]["_expenses"] is None

    @pytest.mark.parametrize("body", [
        {},                                   # match_id fehlt
        {"match_id": "abc"},
        {"match_id": 1, "sr_km": "viel"},
    ])
    def test_schemafehler_422(self, client, user, auth_header, body):
        assert client.post("/api/matches/expenses", headers=auth_header, json=body).status_code == 422

    def test_unbekanntes_spiel_404(self, client, user, auth_header):
        antwort = _kosten(client, auth_header, match_id=999, sr_km=1)
        assert antwort.status_code == 404
        assert fehlerbild(antwort)["code"] == "NOT_FOUND"

    def test_fremdes_spiel_404_und_unveraendert(self, client, user, auth_header, ein_spiel, fremder):
        from db.matches import get_match

        antwort = _kosten(client, fremder["header"], match_id=ein_spiel, sr_km=1)

        assert antwort.status_code == 404
        assert fehlerbild(antwort)["code"] == "NOT_FOUND"
        assert get_match(ein_spiel)["expenses"] is None

    def test_ueberlebt_erneuten_scrape(self, client, user, auth_header, ein_spiel):
        _kosten(client, auth_header, match_id=ein_spiel, sr_km=42)
        spiele_anlegen(user["id"], spiel())
        assert client.get("/api/matches", headers=auth_header).json()[0]["_expenses"]["sr_km"] == 42.0


# ===== Karte =====

@pytest.fixture
def geocoder(monkeypatch):
    """Ersetzt geocode im API-Modul; Antworten je Adresse in einem Dict."""
    import api.main_api as modul

    antworten = {}
    aufrufe = []

    def geocode(adresse, ort=None):
        aufrufe.append((adresse, ort))
        antwort = antworten.get(adresse)
        if isinstance(antwort, Exception):
            raise antwort
        return antwort

    monkeypatch.setattr(modul, "geocode", geocode)
    return antworten, aufrufe


def _treffer(lat, lon, genauigkeit="adresse"):
    return {"lat": lat, "lon": lon, "genauigkeit": genauigkeit}


class TestKarte:
    def test_alle_anschriften(self, client, user, auth_header, ein_spiel, geocoder):
        antworten, aufrufe = geocoder
        antworten.update({
            "Waldweg 1, 99999 Irgendwo": _treffer(50.9, 11.0),
            "Weg 1, 99999 Irgendwo": _treffer(50.8, 11.1),
            "Weg 2, 99999 Irgendwo": _treffer(50.7, 11.2, "ort"),
            "Weg 3, 99999 Irgendwo": _treffer(50.6, 11.3),
        })

        antwort = client.get(f"/api/matches/{ein_spiel}/geo", headers=auth_header)

        assert antwort.status_code == 200
        daten = antwort.json()
        assert daten["gestoert"] is False
        assert daten["ohne_treffer"] == []
        assert daten["kacheln"]["url"]
        assert "OpenStreetMap" in daten["kacheln"]["attribution"]
        assert [p["typ"] for p in daten["punkte"]] == ["spielstaette", "person", "person", "person"]
        assert daten["punkte"][0] == {
            "typ": "spielstaette", "adresse": "Waldweg 1, 99999 Irgendwo", "lat": 50.9, "lon": 11.0,
            "genauigkeit": "adresse", "eintraege": [{"rolle": "Spielort", "name": "Sportplatz Am Wald"}],
        }
        assert daten["punkte"][2]["genauigkeit"] == "ort"
        # Spielstaette ohne eigenen Ort, Personen mit plz_ort als Rueckfall
        assert aufrufe[0] == ("Waldweg 1, 99999 Irgendwo", None)
        assert aufrufe[1] == ("Weg 1, 99999 Irgendwo", "99999 Irgendwo")

    def test_gleiche_anschrift_wird_ein_punkt(self, client, user, auth_header, geocoder):
        antworten, _ = geocoder
        (match_id,) = spiele_anlegen(user["id"], spiel(adresse="", schiedsrichter=[
            {"rolle": "SR", "name": "Mutter", "strasse": "Hof 1", "plz_ort": "99999 Dorf"},
            {"rolle": "SRA 1", "name": "Sohn", "strasse": "Hof 1", "plz_ort": "99999 Dorf"},
        ]))
        antworten["Hof 1, 99999 Dorf"] = _treffer(50.123456, 11.0)

        daten = client.get(f"/api/matches/{match_id}/geo", headers=auth_header).json()

        (punkt,) = daten["punkte"]
        assert punkt["eintraege"] == [{"rolle": "SR", "name": "Mutter"}, {"rolle": "SRA 1", "name": "Sohn"}]

    def test_ohne_treffer_und_gestoert(self, client, user, auth_header, ein_spiel, geocoder):
        from utils.geocoder import GeocoderNichtErreichbar

        antworten, _ = geocoder
        antworten.update({
            "Waldweg 1, 99999 Irgendwo": _treffer(50.9, 11.0),
            "Weg 1, 99999 Irgendwo": None,
            "Weg 2, 99999 Irgendwo": GeocoderNichtErreichbar("Zeitueberschreitung"),
            "Weg 3, 99999 Irgendwo": _treffer(50.6, 11.3),
        })

        daten = client.get(f"/api/matches/{ein_spiel}/geo", headers=auth_header).json()

        assert daten["gestoert"] is True
        assert len(daten["punkte"]) == 2
        assert daten["ohne_treffer"] == [
            {"rolle": "SR", "name": "Erika Pfeife", "adresse": "Weg 1, 99999 Irgendwo"},
            {"rolle": "SRA 1", "name": "Max Fahne", "adresse": "Weg 2, 99999 Irgendwo"},
        ]

    def test_unbesetzte_rollen_und_fehlende_anschriften(self, client, user, auth_header, geocoder):
        antworten, aufrufe = geocoder
        (match_id,) = spiele_anlegen(user["id"], spiel(adresse="", schiedsrichter=[
            {"rolle": "SR", "name": "Erika Pfeife", "strasse": "", "plz_ort": "99999 Irgendwo"},
            {"rolle": "SRA 1", "name": "", "strasse": "Weg 2", "plz_ort": "99999 Irgendwo"},
            {"rolle": "SRA 2", "name": "Ohne Ort", "strasse": "Weg 3", "plz_ort": ""},
        ]))
        antworten["99999 Irgendwo"] = _treffer(50.0, 11.0, "ort")

        daten = client.get(f"/api/matches/{match_id}/geo", headers=auth_header).json()

        # Nur Erika: kein Spielort, SRA 1 unbesetzt, SRA 2 ohne Ort
        assert aufrufe == [("99999 Irgendwo", "99999 Irgendwo")]
        assert [p["eintraege"] for p in daten["punkte"]] == [[{"rolle": "SR", "name": "Erika Pfeife"}]]

    def test_aus_dem_zwischenspeicher_ohne_netz(self, client, user, auth_header, ein_spiel, monkeypatch):
        """Echter Geocoder, aber alles liegt schon in geocode_cache."""
        import utils.geocoder as geocoder_modul
        from db.geocode import store

        def kein_netz(adresse):
            raise AssertionError(f"Unerwartete Anfrage an den Geocoder: {adresse}")

        monkeypatch.setattr(geocoder_modul, "_abfragen", kein_netz)
        monkeypatch.delenv("NOMINATIM_URL", raising=False)
        provider = geocoder_modul.basis_url()

        store("waldweg 1, 99999 irgendwo", provider, 50.9, 11.0)
        for nr, lat in ((1, 50.8), (2, 50.7)):
            store(f"weg {nr}, 99999 irgendwo", provider, lat, 11.0)
        # Weg 3 ist ein frischer Fehlschlag, der Ort dagegen bekannt
        store("weg 3, 99999 irgendwo", provider, None, None)
        store("99999 irgendwo", provider, 50.5, 11.5)

        daten = client.get(f"/api/matches/{ein_spiel}/geo", headers=auth_header).json()

        assert daten["gestoert"] is False
        assert [(p["lat"], p["genauigkeit"]) for p in daten["punkte"]] == [
            (50.9, "adresse"), (50.8, "adresse"), (50.7, "adresse"), (50.5, "ort"),
        ]

    def test_unbekanntes_spiel_404(self, client, user, auth_header, geocoder):
        assert client.get("/api/matches/999/geo", headers=auth_header).status_code == 404

    def test_fremdes_spiel_404_ohne_anfrage(self, client, user, ein_spiel, fremder, geocoder):
        _, aufrufe = geocoder
        antwort = client.get(f"/api/matches/{ein_spiel}/geo", headers=fremder["header"])
        assert antwort.status_code == 404
        assert aufrufe == []


# ===== Einzel-Download =====

class TestEinzelDownload:
    def test_docx(self, client, user, auth_header, ein_spiel):
        antwort = client.get(f"/api/matches/{ein_spiel}/download/docx", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == DOCX_MIME
        assert _dateiname_aus(antwort.headers["content-disposition"]) == \
            "Spesen_FC Heim_vs_SV Gast_05-12-2026.docx"

        with zipfile.ZipFile(BytesIO(antwort.content)) as docx:
            inhalt = docx.read("word/document.xml").decode("utf-8")
        assert "FC Heim" in inhalt
        assert "Pfeife" in inhalt

        assert _downloads() == [{"user_id": user["id"], "match_id": ein_spiel,
                                 "filename": "Spesen_FC Heim_vs_SV Gast_05-12-2026.docx",
                                 "file_type": "docx"}]

    def test_dokument_traegt_erfasste_kilometer(self, client, user, auth_header, ein_spiel):
        from docx import Document

        def text():
            antwort = client.get(f"/api/matches/{ein_spiel}/download/docx", headers=auth_header)
            dokument = Document(BytesIO(antwort.content))
            return "\n".join(
                [p.text for p in dokument.paragraphs]
                + [z.text for t in dokument.tables for r in t.rows for z in r.cells]
            )

        assert "36,90" not in text()
        # 123 km zu 0,30 EUR - der Wert kommt beim naechsten Download ohne Umweg mit
        _kosten(client, auth_header, match_id=ein_spiel, sr_km=123)
        assert "36,90" in text()

    def test_xlsx_ist_alias_fuer_bearbeitbar(self, client, user, auth_header, ein_spiel):
        """'xlsx' bei einem TFV-Spiel liefert dessen bearbeitbare Datei - ein DOCX."""
        antwort = client.get(f"/api/matches/{ein_spiel}/download/xlsx", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == DOCX_MIME
        assert _dateiname_aus(antwort.headers["content-disposition"]).endswith(".docx")

    @pytest.mark.parametrize("format_", ["docx", "xlsx"])
    def test_nofv_spiel_liefert_excel(self, client, user, auth_header, format_):
        from openpyxl import load_workbook

        (match_id,) = spiele_anlegen(user["id"], nofv_spiel())

        antwort = client.get(f"/api/matches/{match_id}/download/{format_}", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == XLSX_MIME
        name = _dateiname_aus(antwort.headers["content-disposition"])
        assert name == "Spesen_FC Carl Zeiss Jena_vs_BSG Chemie Leipzig_05-12-2026.xlsx"
        assert len(load_workbook(BytesIO(antwort.content)).worksheets) >= 1
        assert _downloads()[0]["file_type"] == "xlsx"

    def test_pdf(self, client, user, auth_header, ein_spiel, pdf):
        antwort = client.get(f"/api/matches/{ein_spiel}/download/pdf", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == "application/pdf"
        assert antwort.content.startswith(b"%PDF")
        assert _dateiname_aus(antwort.headers["content-disposition"]) == \
            "Spesen_FC Heim_vs_SV Gast_05-12-2026.pdf"

        # Konvertiert wird das frisch gerenderte DOCX
        ((name, inhalt),) = pdf[0]
        assert name.endswith(".docx")
        assert inhalt[:2] == b"PK"

        assert _downloads() == [{"user_id": user["id"], "match_id": ein_spiel,
                                 "filename": "Spesen_FC Heim_vs_SV Gast_05-12-2026.pdf",
                                 "file_type": "pdf"}]

    def test_pdf_aus_nofv_excel(self, client, user, auth_header, pdf):
        (match_id,) = spiele_anlegen(user["id"], nofv_spiel())

        antwort = client.get(f"/api/matches/{match_id}/download/pdf", headers=auth_header)

        assert antwort.status_code == 200
        assert pdf[0][0][0].endswith(".xlsx")
        assert _dateiname_aus(antwort.headers["content-disposition"]).endswith(".pdf")

    def test_pdf_fehlgeschlagen_503(self, client, user, auth_header, ein_spiel, monkeypatch):
        monkeypatch.setattr("api.main_api.convert_docx_bytes_to_pdf", lambda dokumente: [None])

        antwort = client.get(f"/api/matches/{ein_spiel}/download/pdf", headers=auth_header)

        assert antwort.status_code == 503
        assert fehlerbild(antwort)["code"] == "PDF_CONVERSION_FAILED"
        assert _downloads() == []

    def test_ohne_libreoffice_503(self, client, user, auth_header, ein_spiel, monkeypatch):
        """Fehlt LibreOffice, gibt es die verstaendliche 503 statt eines 500."""
        from utils import pdf_converter

        def fehlt():
            raise FileNotFoundError("soffice nicht installiert")

        monkeypatch.setattr(pdf_converter, "_find_soffice", fehlt)

        antwort = client.get(f"/api/matches/{ein_spiel}/download/pdf", headers=auth_header)

        assert antwort.status_code == 503
        assert fehlerbild(antwort)["code"] == "PDF_CONVERSION_FAILED"

    @pytest.mark.parametrize("format_", ["doc", "zip", "PDF", "odt"])
    def test_falsches_format_400(self, client, user, auth_header, ein_spiel, format_):
        antwort = client.get(f"/api/matches/{ein_spiel}/download/{format_}", headers=auth_header)

        assert antwort.status_code == 400
        assert fehlerbild(antwort)["code"] == "INVALID_FORMAT"
        assert _downloads() == []

    def test_unbekanntes_spiel_404(self, client, user, auth_header):
        assert client.get("/api/matches/999/download/docx", headers=auth_header).status_code == 404

    def test_fremdes_spiel_404(self, client, user, ein_spiel, fremder, pdf):
        for format_ in ("docx", "pdf"):
            antwort = client.get(f"/api/matches/{ein_spiel}/download/{format_}", headers=fremder["header"])
            assert antwort.status_code == 404
        assert pdf == []
        assert _downloads() == []

    def test_umlaute_und_sonderzeichen_im_dateinamen(self, client, user, auth_header):
        (match_id,) = spiele_anlegen(user["id"], spiel(heim='FSV Preußen "Tölz"', gast="SG Öhrdorf/Süd"))

        antwort = client.get(f"/api/matches/{match_id}/download/docx", headers=auth_header)

        assert antwort.status_code == 200
        header = antwort.headers["content-disposition"]
        assert _dateiname_aus(header) == 'Spesen_FSV Preußen "Tölz"_vs_SG Öhrdorf-Süd_05-12-2026.docx'
        ascii_name = _ascii_name_aus(header)
        assert ascii_name.isascii()
        assert '"' not in ascii_name
        assert ascii_name == "Spesen_FSV Preuen Tolz_vs_SG Ohrdorf-Sud_05-12-2026.docx"

    def test_turnier_ohne_teams(self, client, user, auth_header):
        (match_id,) = spiele_anlegen(user["id"], spiel(heim="", gast="", zeit="09:30"))

        antwort = client.get(f"/api/matches/{match_id}/download/docx", headers=auth_header)

        assert antwort.status_code == 200
        assert _dateiname_aus(antwort.headers["content-disposition"]) == \
            "Spesen_Turnier_05-12-2026_09-30.docx"


# ===== Sammel-Download =====

def _sammel(client, header, match_ids, file_format=None):
    body = {"match_ids": match_ids}
    if file_format is not None:
        body["file_format"] = file_format
    return client.post("/api/matches/download", headers=header, json=body)


def _eintraege(antwort) -> list:
    with zipfile.ZipFile(BytesIO(antwort.content)) as archiv:
        return archiv.namelist()


@pytest.fixture
def drei_spiele(user):
    return spiele_anlegen(
        user["id"],
        spiel(heim="FC Heim", gast="SV Gast"),
        spiel(heim="FSV Preußen", gast="SV Ölsnitz", tag="2026-12-06"),
        nofv_spiel(tag="2026-12-07"),
    )


class TestSammelDownload:
    def test_standard_ist_beides(self, client, user, auth_header, drei_spiele, pdf):
        antwort = _sammel(client, auth_header, drei_spiele)

        assert antwort.status_code == 200
        assert antwort.headers["content-type"] == "application/zip"
        assert _eintraege(antwort) == [
            "Spesen_FC Heim_vs_SV Gast_05-12-2026.docx",
            "Spesen_FC Heim_vs_SV Gast_05-12-2026.pdf",
            "Spesen_FSV Preußen_vs_SV Ölsnitz_06-12-2026.docx",
            "Spesen_FSV Preußen_vs_SV Ölsnitz_06-12-2026.pdf",
            "Spesen_FC Carl Zeiss Jena_vs_BSG Chemie Leipzig_07-12-2026.xlsx",
            "Spesen_FC Carl Zeiss Jena_vs_BSG Chemie Leipzig_07-12-2026.pdf",
        ]
        # Alle PDFs in EINEM Konvertierungsaufruf
        assert len(pdf) == 1
        assert len(pdf[0]) == 3

    def test_inhalte_sind_echte_dokumente(self, client, user, auth_header, drei_spiele, pdf):
        antwort = _sammel(client, auth_header, drei_spiele, "both")

        with zipfile.ZipFile(BytesIO(antwort.content)) as archiv:
            for name in archiv.namelist():
                inhalt = archiv.read(name)
                if name.endswith(".pdf"):
                    assert inhalt.startswith(b"%PDF")
                else:
                    assert inhalt[:2] == b"PK"
            # Umlaute stehen als UTF-8 im Archiv
            assert any(info.flag_bits & 0x800 for info in archiv.infolist() if "ß" in info.filename)

    def test_nur_docx_ohne_pdf_konvertierung(self, client, user, auth_header, drei_spiele, pdf):
        antwort = _sammel(client, auth_header, drei_spiele, "docx")

        assert antwort.status_code == 200
        namen = _eintraege(antwort)
        assert len(namen) == 3
        assert not any(n.endswith(".pdf") for n in namen)
        assert namen[2].endswith(".xlsx")
        assert pdf == []

    def test_nur_pdf(self, client, user, auth_header, drei_spiele, pdf):
        namen = _eintraege(_sammel(client, auth_header, drei_spiele, "pdf"))
        assert len(namen) == 3
        assert all(n.endswith(".pdf") for n in namen)
        # Das Protokoll nennt dieselbe Datei wie beim Einzel-Download
        assert all(eintrag["filename"].endswith(".pdf") for eintrag in _downloads())

    def test_zip_name_und_header(self, client, user, auth_header, drei_spiele):
        antwort = _sammel(client, auth_header, drei_spiele, "docx")

        erwartet = f"Spesen_{datetime.now().strftime('%Y-%m-%d')}.zip"
        header = antwort.headers["content-disposition"]
        assert _dateiname_aus(header) == erwartet
        assert _ascii_name_aus(header) == erwartet

    def test_download_log_je_spiel(self, client, user, auth_header, drei_spiele, pdf):
        _sammel(client, auth_header, drei_spiele, "both")

        eintraege = _downloads()
        assert [e["match_id"] for e in eintraege] == drei_spiele
        assert {e["file_type"] for e in eintraege} == {"both"}
        assert {e["user_id"] for e in eintraege} == {user["id"]}
        assert eintraege[2]["filename"].endswith(".xlsx")

    def test_gleiche_dateinamen_werden_eindeutig(self, client, user, auth_header, pdf):
        # Gleiche Vereine am selben Tag, aber verschiedene Mannschaftsarten:
        # zwei Spiele, derselbe Dateiname
        ids = spiele_anlegen(user["id"],
                             spiel(mannschaftsart="Herren"),
                             spiel(mannschaftsart="A-Junioren", spielklasse="Kreisliga"))

        namen = _eintraege(_sammel(client, auth_header, ids, "both"))

        assert namen == [
            "Spesen_FC Heim_vs_SV Gast_05-12-2026.docx",
            "Spesen_FC Heim_vs_SV Gast_05-12-2026.pdf",
            "Spesen_FC Heim_vs_SV Gast_05-12-2026 (2).docx",
            "Spesen_FC Heim_vs_SV Gast_05-12-2026 (2).pdf",
        ]

    def test_leere_auswahl_400(self, client, user, auth_header):
        antwort = _sammel(client, auth_header, [])
        assert antwort.status_code == 400
        assert fehlerbild(antwort)["code"] == "NO_SELECTION"

    def test_zu_viele_400(self, client, user, auth_header):
        import api.main_api as modul

        antwort = _sammel(client, auth_header, list(range(1, modul.MAX_BULK_DOWNLOAD + 2)))

        assert antwort.status_code == 400
        fehler = fehlerbild(antwort)
        assert fehler["code"] == "TOO_MANY_MATCHES"
        assert str(modul.MAX_BULK_DOWNLOAD) in fehler["message"]

    def test_obergrenze_selbst_ist_erlaubt(self, client, user, auth_header, drei_spiele, monkeypatch):
        monkeypatch.setattr("api.main_api.MAX_BULK_DOWNLOAD", 3)
        assert _sammel(client, auth_header, drei_spiele, "docx").status_code == 200
        assert _sammel(client, auth_header, drei_spiele + drei_spiele[:1], "docx").status_code == 400

    @pytest.mark.parametrize("format_", ["xlsx", "zip", ""])
    def test_falsches_format_400(self, client, user, auth_header, drei_spiele, format_):
        antwort = _sammel(client, auth_header, drei_spiele, format_)
        assert antwort.status_code == 400
        assert fehlerbild(antwort)["code"] == "INVALID_FORMAT"

    def test_schemafehler_422(self, client, user, auth_header):
        assert client.post("/api/matches/download", headers=auth_header, json={}).status_code == 422
        assert client.post("/api/matches/download", headers=auth_header,
                           json={"match_ids": ["a"]}).status_code == 422

    def test_ein_fremdes_spiel_in_der_auswahl_404(self, client, user, auth_header, drei_spiele,
                                                  fremder, pdf):
        (fremdes,) = spiele_anlegen(fremder["id"], spiel(heim="FC Fremd"))

        antwort = _sammel(client, auth_header, [*drei_spiele, fremdes])

        assert antwort.status_code == 404
        assert pdf == []
        assert _downloads() == []

    def test_unbekanntes_spiel_in_der_auswahl_404(self, client, user, auth_header, drei_spiele):
        assert _sammel(client, auth_header, [*drei_spiele, 999], "docx").status_code == 404
        assert _downloads() == []

    def test_teilweiser_pdf_ausfall_503(self, client, user, auth_header, drei_spiele, monkeypatch):
        monkeypatch.setattr("api.main_api.convert_docx_bytes_to_pdf",
                            lambda dokumente: [b"%PDF", None, b"%PDF"])

        antwort = _sammel(client, auth_header, drei_spiele, "both")

        assert antwort.status_code == 503
        fehler = fehlerbild(antwort)
        assert fehler["code"] == "PDF_CONVERSION_FAILED"
        assert "1 von 3" in fehler["message"]
        assert _downloads() == []



# ===== Kilometer-Vorschlaege =====

class TestFahrten:
    def test_liefert_die_vorschlaege(self, client, user, auth_header, ein_spiel, monkeypatch):
        import api.main_api as modul
        gesehen = []
        monkeypatch.setattr(modul, "vorschlaege_fuer_spiel",
                            lambda match: gesehen.append(match["id"]) or {"einzeln": {"km": {"sr": 12}}})

        antwort = client.get(f"/api/matches/{ein_spiel}/fahrten", headers=auth_header)

        assert antwort.status_code == 200
        assert antwort.json() == {"einzeln": {"km": {"sr": 12}}}
        assert gesehen == [ein_spiel]

    def test_fremdes_spiel_ist_unbekannt(self, client, user, auth_header, fremder):
        (fremdes,) = spiele_anlegen(fremder["id"], spiel(heim="FC Fremd"))
        assert client.get(f"/api/matches/{fremdes}/fahrten", headers=auth_header).status_code == 404

    def test_ohne_anmeldung(self, client, ein_spiel):
        assert client.get(f"/api/matches/{ein_spiel}/fahrten").status_code == 401
