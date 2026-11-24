"""
TFV-Formular (DOCX): Platzhalter, Kaestchen, Fahrtkosten und Summen.

Die Dokumente entstehen im Speicher aus der echten Vorlage und werden mit
python-docx wieder geoeffnet. Welcher Platzhalter in welcher Tabellenzelle
steht, wird einmal aus der Vorlage gelesen - die Tests fragen dann genau
diese Zelle im Ergebnis ab, statt nur irgendwo im Dokument nach Text zu suchen.
"""
import re
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from generator.docx_generator import (
    CHECKBOX_CHECKED,
    CHECKBOX_FONT,
    CHECKBOX_UNCHECKED,
    KM_SATZ_EURO,
    SpesenGenerator,
    format_name_nachname_vorname,
)

VORLAGE = Path(__file__).resolve().parent.parent / "src" / "data" / "Spesenabrechnung_Vorlage.docx"

ANPFIFF = "Samstag · 08.11.2025 · 13:00 Uhr"


def _platzhalter_positionen() -> dict:
    """Platzhalter -> (zeile, spalte, absatz) fuer Zellen mit genau einem Platzhalter."""
    tabelle = Document(VORLAGE).tables[0]
    gesehen = []
    positionen = {}
    for zi, zeile in enumerate(tabelle.rows):
        for si, zelle in enumerate(zeile.cells):
            if any(zelle._tc is tc for tc in gesehen):
                continue
            gesehen.append(zelle._tc)
            for ai, absatz in enumerate(zelle.paragraphs):
                treffer = re.fullmatch(r"\{\{(\w+)\}\}", absatz.text)
                if treffer:
                    positionen[treffer.group(1)] = (zi, si, ai)
    return positionen


POSITIONEN = _platzhalter_positionen()


def _felder(content: bytes) -> dict:
    """Liest die ersetzten Werte an den Platzhalter-Positionen der Vorlage."""
    tabelle = Document(BytesIO(content)).tables[0]
    return {
        name: tabelle.cell(zi, si).paragraphs[ai].text
        for name, (zi, si, ai) in POSITIONEN.items()
    }


def _kaestchen_zeilen(content: bytes) -> str:
    """Die drei Zeilen mit den Kaestchen als ein Text."""
    tabelle = Document(BytesIO(content)).tables[0]
    return "\n".join(tabelle.cell(z, 0).paragraphs[0].text for z in range(3))


def _angekreuzt(content: bytes) -> set:
    """Die Beschriftungen aller angekreuzten Kaestchen."""
    text = _kaestchen_zeilen(content)
    return set(re.findall(rf"{CHECKBOX_CHECKED} ([^\t\n]+)", text))


def _gesamter_text(content: bytes) -> str:
    doc = Document(BytesIO(content))
    teile = [p.text for p in doc.paragraphs]
    for tabelle in doc.tables:
        for zeile in tabelle.rows:
            for zelle in zeile.cells:
                teile.extend(p.text for p in zelle.paragraphs)
    return "\n".join(teile)


def _spiel(**ueberschreiben) -> dict:
    """Ein Spiel in der Form, die db.matches.get_match liefert."""
    spiel = {
        "spiel_info": {
            "heim_team": "FC Rot-Weiß Erfurt II",
            "gast_team": "SV Blau-Gelb Weimar",
            "anpfiff": ANPFIFF,
            "spielklasse": "Verbandsliga",
            "mannschaftsart": "Herren",
            "staffel": "Verbandsliga Thüringen",
        },
        "spielstaette": {
            "name": "Sportplatz Am Ring",
            "adresse": "Ringstraße 5, 99084 Erfurt",
        },
        "schiedsrichter": [
            {"rolle": "SR", "name": "Max Mustermann", "strasse": "Hauptstr. 1", "plz_ort": "99438 Bad Berka"},
            {"rolle": "SRA 1", "name": "Eva Maria Muster", "strasse": "Nebenweg 2", "plz_ort": "99423 Weimar"},
            {"rolle": "SRA 2", "name": "Karl Beispiel", "strasse": "Gasse 3", "plz_ort": "99510 Apolda"},
        ],
    }
    spiel.update(ueberschreiben)
    return spiel


@pytest.fixture(scope="module")
def generator():
    return SpesenGenerator(str(VORLAGE))


# ===== Namen =====

class TestNamensformat:
    def test_vorname_nachname_wird_umgedreht(self):
        assert format_name_nachname_vorname("Max Mustermann") == "Mustermann, Max"

    def test_mehrere_vornamen(self):
        assert format_name_nachname_vorname("Eva Maria Muster") == "Muster, Eva Maria"

    def test_einzelnes_wort_bleibt(self):
        assert format_name_nachname_vorname("Mustermann") == "Mustermann"

    def test_leer_bleibt_leer(self):
        assert format_name_nachname_vorname("") == ""

    def test_leerzeichen_werden_ignoriert(self):
        assert format_name_nachname_vorname("  Max   Mustermann  ") == "Mustermann, Max"


# ===== Grunddaten =====

class TestStammdaten:
    def test_vorlage_kennt_alle_erwarteten_platzhalter(self):
        erwartet = {
            "HEIM_TEAM", "GAST_TEAM", "SPIELKLASSE", "SPIELNUMMER", "DATUM", "ANSTOSS", "SPIELORT",
            "SR_NAME", "SR_STRASSE", "SR_PLZ_ORT",
            "SRA1_NAME", "SRA1_STRASSE", "SRA1_PLZ_ORT",
            "SRA2_NAME", "SRA2_STRASSE", "SRA2_PLZ_ORT",
            "SR_Kilometer", "SRA1_Kilometer", "SRA2_Kilometer",
            "SR_OEVM", "SRA1_OEVM", "SRA2_OEVM",
            "SR_Spesen", "SR1_Spesen", "SR2_Spesen",
            "SR_Summe", "SRA1_Summe", "SRA2_Summe", "Summe",
        }
        assert erwartet <= set(POSITIONEN)

    def test_kein_platzhalter_bleibt_stehen(self, generator):
        content = generator.render_document(_spiel(), {"sr_km": 10})
        assert "{{" not in _gesamter_text(content)
        assert "}}" not in _gesamter_text(content)

    def test_kein_platzhalter_bleibt_stehen_bei_leerem_spiel(self, generator):
        content = generator.render_document({})
        assert "{{" not in _gesamter_text(content)

    def test_liefert_gueltige_docx_bytes(self, generator):
        content = generator.render_document(_spiel())
        assert content[:2] == b"PK"

    def test_spieldaten(self, generator):
        felder = _felder(generator.render_document(_spiel()))
        assert felder["HEIM_TEAM"] == "FC Rot-Weiß Erfurt II"
        assert felder["GAST_TEAM"] == "SV Blau-Gelb Weimar"
        assert felder["SPIELKLASSE"] == "Verbandsliga"
        assert felder["SPIELNUMMER"] == ""
        assert felder["DATUM"] == "08.11.2025"
        assert felder["ANSTOSS"] == "13:00"

    def test_spielnummer_aus_der_datenbank(self, generator):
        felder = _felder(generator.render_document({**_spiel(), "spielnummer": "659000082"}))
        assert felder["SPIELNUMMER"] == "659000082"

    def test_datum_auch_neben_der_unterschrift(self, generator):
        doc = Document(BytesIO(generator.render_document(_spiel())))
        assert any("08.11.2025" in p.text and "Unterschrift" in p.text for p in doc.paragraphs)

    def test_spielort_aus_name_und_adresse(self, generator):
        felder = _felder(generator.render_document(_spiel()))
        assert felder["SPIELORT"] == "Sportplatz Am Ring\nRingstraße 5, 99084 Erfurt"

    def test_anpfiff_ohne_trenner_bleibt_als_datum(self, generator):
        spiel = _spiel()
        spiel["spiel_info"]["anpfiff"] = "irgendwann"
        felder = _felder(generator.render_document(spiel))
        assert felder["DATUM"] == "irgendwann"
        assert felder["ANSTOSS"] == ""

    def test_gespann(self, generator):
        felder = _felder(generator.render_document(_spiel()))
        assert felder["SR_NAME"] == "Mustermann, Max"
        assert felder["SR_STRASSE"] == "Hauptstr. 1"
        assert felder["SR_PLZ_ORT"] == "99438 Bad Berka"
        assert felder["SRA1_NAME"] == "Muster, Eva Maria"
        assert felder["SRA1_STRASSE"] == "Nebenweg 2"
        assert felder["SRA1_PLZ_ORT"] == "99423 Weimar"
        assert felder["SRA2_NAME"] == "Beispiel, Karl"
        assert felder["SRA2_STRASSE"] == "Gasse 3"
        assert felder["SRA2_PLZ_ORT"] == "99510 Apolda"

    def test_rollen_nach_rolle_nicht_nach_reihenfolge(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = list(reversed(spiel["schiedsrichter"]))
        felder = _felder(generator.render_document(spiel))
        assert felder["SR_NAME"] == "Mustermann, Max"
        assert felder["SRA2_NAME"] == "Beispiel, Karl"

    def test_fehlende_assistenten_bleiben_leer(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = spiel["schiedsrichter"][:1]
        felder = _felder(generator.render_document(spiel))
        for feld in ("SRA1_NAME", "SRA1_STRASSE", "SRA1_PLZ_ORT",
                     "SRA2_NAME", "SRA2_STRASSE", "SRA2_PLZ_ORT"):
            assert felder[feld] == ""

    def test_ohne_jede_angabe_alles_leer(self, generator):
        felder = _felder(generator.render_document({}))
        for feld in ("HEIM_TEAM", "GAST_TEAM", "SR_NAME", "SR_Spesen", "SR_Summe", "Summe"):
            assert felder[feld] == ""
        assert felder["SPIELORT"] == "\n"


# ===== Spesensaetze =====

class TestSpesen:
    def test_berechnete_saetze_verbandsliga(self, generator):
        felder = _felder(generator.render_document(_spiel()))
        assert felder["SR_Spesen"] == "50,00 €"
        assert felder["SR1_Spesen"] == "40,00 €"
        assert felder["SR2_Spesen"] == "40,00 €"

    def test_eingefrorene_saetze_gewinnen(self, generator):
        felder = _felder(generator.render_document(_spiel(sr_spesen=33.0, sra_spesen=22.5)))
        assert felder["SR_Spesen"] == "33,00 €"
        assert felder["SR1_Spesen"] == "22,50 €"
        assert felder["SR2_Spesen"] == "22,50 €"

    def test_eingefroren_ohne_satz_wird_nicht_neu_gerechnet(self, generator):
        # Ein eingefrorenes None ist eine Aussage ("kein Satz"), kein fehlender Wert
        felder = _felder(generator.render_document(_spiel(sr_spesen=None, sra_spesen=None)))
        assert felder["SR_Spesen"] == ""
        assert felder["SR1_Spesen"] == ""

    def test_assistentensatz_nur_mit_assistent(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = spiel["schiedsrichter"][:2]
        felder = _felder(generator.render_document(spiel))
        assert felder["SR1_Spesen"] == "40,00 €"
        assert felder["SR2_Spesen"] == ""

    def test_kein_satz_bei_ueberregionalem_spiel(self, generator):
        spiel = _spiel()
        spiel["spiel_info"].update(spielklasse="Bundesliga", staffel="Bundesliga")
        felder = _felder(generator.render_document(spiel))
        assert felder["SR_Spesen"] == ""
        assert felder["SR1_Spesen"] == ""
        assert felder["SR2_Spesen"] == ""

    def test_juniorinnen_ohne_assistentensatz(self, generator):
        spiel = _spiel()
        spiel["spiel_info"].update(spielklasse="Kreisliga", mannschaftsart="B-Juniorinnen", staffel="")
        felder = _felder(generator.render_document(spiel))
        assert felder["SR_Spesen"] == "20,00 €"
        assert felder["SR1_Spesen"] == ""


# ===== Fahrtkosten und Summen =====

class TestFahrtkosten:
    def test_ohne_fahrtkosten_keine_summen(self, generator):
        felder = _felder(generator.render_document(_spiel()))
        for prefix in ("SR", "SRA1", "SRA2"):
            assert felder[f"{prefix}_Kilometer"] == ""
            assert felder[f"{prefix}_OEVM"] == ""
            assert felder[f"{prefix}_Summe"] == ""
        assert felder["Summe"] == ""

    def test_kilometer_zum_standardsatz(self, generator):
        assert KM_SATZ_EURO == 0.30
        felder = _felder(generator.render_document(_spiel(), {"sr_km": 100}))
        assert felder["SR_Kilometer"] == "30,00 €"

    def test_kilometer_werden_auf_cent_gerundet(self, generator):
        felder = _felder(generator.render_document(_spiel(), {"sr_km": 33.3}))
        assert felder["SR_Kilometer"] == "9,99 €"

    def test_eingefrorener_km_satz(self, generator):
        felder = _felder(generator.render_document(_spiel(km_satz=0.35), {"sr_km": 100}))
        assert felder["SR_Kilometer"] == "35,00 €"
        assert felder["SR_Summe"] == "85,00 €"

    def test_oevm(self, generator):
        felder = _felder(generator.render_document(_spiel(), {"sra1_oevm": 12.5}))
        assert felder["SRA1_OEVM"] == "12,50 €"
        assert felder["SRA1_Kilometer"] == ""
        assert felder["SRA1_Summe"] == "52,50 €"

    def test_summen_je_person_und_gesamt(self, generator):
        expenses = {
            "sr_km": 100, "sr_oevm": 12.5,
            "sra1_km": 50,
            "sra2_km": 0,
        }
        felder = _felder(generator.render_document(_spiel(), expenses))
        assert felder["SR_Kilometer"] == "30,00 €"
        assert felder["SR_OEVM"] == "12,50 €"
        assert felder["SR_Summe"] == "92,50 €"
        assert felder["SRA1_Kilometer"] == "15,00 €"
        assert felder["SRA1_Summe"] == "55,00 €"
        # 0 km ist erfasst: Feld leer, aber die Summe steht
        assert felder["SRA2_Kilometer"] == ""
        assert felder["SRA2_Summe"] == "40,00 €"
        assert felder["Summe"] == "187,50 €"

    def test_gesamtsumme_erst_wenn_alle_erfasst(self, generator):
        felder = _felder(generator.render_document(_spiel(), {"sr_km": 100, "sra1_km": 50}))
        assert felder["SR_Summe"] == "80,00 €"
        assert felder["SRA1_Summe"] == "55,00 €"
        assert felder["SRA2_Summe"] == ""
        assert felder["Summe"] == ""

    def test_none_zaehlt_nicht_als_erfasst(self, generator):
        expenses = {"sr_km": 100, "sra1_km": 50, "sra2_km": None, "sra2_oevm": None}
        felder = _felder(generator.render_document(_spiel(), expenses))
        assert felder["SRA2_Summe"] == ""
        assert felder["Summe"] == ""

    def test_explizite_null_oevm_zaehlt_als_erfasst(self, generator):
        expenses = {"sr_oevm": 0, "sra1_oevm": 0, "sra2_oevm": 0}
        felder = _felder(generator.render_document(_spiel(), expenses))
        assert felder["SR_OEVM"] == ""
        assert felder["SR_Summe"] == "50,00 €"
        assert felder["Summe"] == "130,00 €"

    def test_nicht_angesetzte_rolle_braucht_keine_fahrtkosten(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = spiel["schiedsrichter"][:1]
        felder = _felder(generator.render_document(spiel, {"sr_km": 10}))
        assert felder["SR_Summe"] == "53,00 €"
        assert felder["Summe"] == "53,00 €"

    def test_nicht_angesetzte_rolle_bekommt_keine_summe(self, generator):
        spiel = _spiel()
        spiel["schiedsrichter"] = spiel["schiedsrichter"][:1]
        felder = _felder(generator.render_document(spiel, {"sr_km": 10, "sra1_km": 20}))
        assert felder["SRA1_Summe"] == ""
        assert felder["Summe"] == "53,00 €"

    def test_ohne_satz_keine_summe(self, generator):
        # Fahrtkosten allein saehen wie der Endbetrag aus
        expenses = {"sr_km": 100, "sra1_km": 50, "sra2_km": 10}
        felder = _felder(generator.render_document(_spiel(sr_spesen=None, sra_spesen=None), expenses))
        assert felder["SR_Spesen"] == ""
        assert felder["SR_Kilometer"] == "30,00 €"
        assert felder["SR_Summe"] == ""
        assert felder["SRA1_Summe"] == ""
        assert felder["Summe"] == ""

    def test_ohne_assistentensatz_summe_aus_fahrtkosten(self, generator):
        # Juniorinnen: SR-Satz bekannt, fuer Assistenten keiner vorgesehen
        spiel = _spiel(sr_spesen=20.0, sra_spesen=None)
        spiel["schiedsrichter"] = spiel["schiedsrichter"][:2]
        felder = _felder(generator.render_document(spiel, {"sr_km": 10, "sra1_km": 20}))
        assert felder["SR_Summe"] == "23,00 €"
        assert felder["SR1_Spesen"] == ""
        assert felder["SRA1_Summe"] == "6,00 €"
        assert felder["Summe"] == "29,00 €"

    def test_leere_expenses_wie_keine(self, generator):
        assert _felder(generator.render_document(_spiel(), {})) == \
            _felder(generator.render_document(_spiel(), None))


# ===== Kaestchen =====

class TestKaestchen:
    @pytest.mark.parametrize("spielklasse, erwartet", [
        ("Verbandsliga", "Punktspiel"),
        ("Kreispokal", "Pokalspiel"),
        ("Kreisfreundschaftsspiele", "Freundschaftsspiel"),
        ("Hallenturnier", "Punktspiel"),
    ])
    def test_wettbewerbsart(self, generator, spielklasse, erwartet):
        spiel = _spiel(sr_spesen=None, sra_spesen=None)
        spiel["spiel_info"]["spielklasse"] = spielklasse
        angekreuzt = _angekreuzt(generator.render_document(spiel))
        assert erwartet in angekreuzt
        andere = {"Punktspiel", "Pokalspiel", "Freundschaftsspiel", "Entscheidungsspiel"} - {erwartet}
        assert not angekreuzt & andere

    @pytest.mark.parametrize("mannschaftsart, erwartet", [
        ("Herren", "Männer"),
        ("Männer", "Männer"),
        ("Herren Ü35", "Alte Herren"),
        ("Alte Herren", "Alte Herren"),
        ("Frauen", "Frauen"),
        ("B-Juniorinnen", "Mädchen"),
        ("Mädchen", "Mädchen"),
        ("A-Junioren", "A-Junioren"),
        ("B-Junioren", "B-Junioren"),
        ("C-Junioren", "C-Junioren"),
        ("D-Junioren", "D-Junioren"),
        ("E-Junioren", "E-Junioren"),
        ("F-Junioren", "F-Junioren"),
        ("Freizeitsport", "Sonstige"),
        ("", "Sonstige"),
    ])
    def test_mannschaftsart(self, generator, mannschaftsart, erwartet):
        spiel = _spiel(sr_spesen=None, sra_spesen=None)
        spiel["spiel_info"]["mannschaftsart"] = mannschaftsart
        angekreuzt = _angekreuzt(generator.render_document(spiel))
        assert angekreuzt == {"Punktspiel", erwartet}

    def test_juniorinnen_nicht_als_junioren(self, generator):
        # "a-juniorinnen" enthaelt nicht "a-junioren" - aber die Reihenfolge der
        # Zweige muss trotzdem Maedchen vor den Altersklassen pruefen
        spiel = _spiel(sr_spesen=None, sra_spesen=None)
        spiel["spiel_info"]["mannschaftsart"] = "A-Juniorinnen"
        assert "A-Junioren" not in _angekreuzt(generator.render_document(spiel))

    def test_genau_ein_wettbewerb_und_eine_mannschaft(self, generator):
        text = _kaestchen_zeilen(generator.render_document(_spiel()))
        assert text.count(CHECKBOX_CHECKED) == 2
        assert text.count(CHECKBOX_UNCHECKED) == 15 - 2

    def test_entscheidungsspiel_nie_angekreuzt(self, generator):
        spiel = _spiel(sr_spesen=None, sra_spesen=None)
        spiel["spiel_info"]["spielklasse"] = "Entscheidungsspiel"
        assert "Entscheidungsspiel" not in _angekreuzt(generator.render_document(spiel))

    def test_kaestchen_in_symbolschrift(self, generator):
        doc = Document(BytesIO(generator.render_document(_spiel())))
        absatz = doc.tables[0].cell(0, 0).paragraphs[0]
        kaestchen_runs = [r for r in absatz.runs if r.text in (CHECKBOX_CHECKED, CHECKBOX_UNCHECKED)]
        assert len(kaestchen_runs) == 4
        for run in kaestchen_runs:
            assert run.font.name == CHECKBOX_FONT

    def test_ueber_runs_verteiltes_kaestchen_wird_ersetzt(self, generator):
        # {{CHECKBOX_SONSTIGE}} steht in der Vorlage auf drei Runs verteilt
        spiel = _spiel(sr_spesen=None, sra_spesen=None)
        spiel["spiel_info"]["mannschaftsart"] = "Freizeitsport"
        text = _kaestchen_zeilen(generator.render_document(spiel))
        assert f"{CHECKBOX_CHECKED} Sonstige" in text


# ===== Ersetzung ueber Run-Grenzen =====

class TestRunGrenzen:
    def _absatz(self, *teile):
        doc = Document()
        absatz = doc.add_paragraph()
        for teil in teile:
            absatz.add_run(teil)
        return absatz

    def test_platzhalter_in_einem_run_mit_umgebung(self, generator):
        absatz = self._absatz("vor {{X}} nach")
        generator._replace_placeholder_in_paragraph(absatz, "{{X}}", "WERT", False)
        assert absatz.text == "vor WERT nach"

    def test_platzhalter_ueber_drei_runs(self, generator):
        absatz = self._absatz("vor {", "{X", "}} nach")
        generator._replace_placeholder_in_paragraph(absatz, "{{X}}", "WERT", False)
        assert absatz.text == "vor WERT nach"
        assert [r.text for r in absatz.runs] == ["vor WERT", "", " nach"]

    def test_checkbox_ueber_runs_bekommt_symbolschrift(self, generator):
        absatz = self._absatz("{", "{K}}", " Text")
        generator._replace_placeholder_in_paragraph(absatz, "{{K}}", CHECKBOX_CHECKED, True)
        assert absatz.runs[0].text == CHECKBOX_CHECKED
        assert absatz.runs[0].font.name == CHECKBOX_FONT
        assert absatz.text == f"{CHECKBOX_CHECKED} Text"

    def test_text_ersetzung_aendert_schrift_nicht(self, generator):
        absatz = self._absatz("{{X}}")
        generator._replace_placeholder_in_paragraph(absatz, "{{X}}", "WERT", False)
        assert absatz.runs[0].font.name is None

    def test_fehlender_platzhalter_aendert_nichts(self, generator):
        absatz = self._absatz("nur {{ANDERES}}")
        generator._replace_placeholder_in_paragraph(absatz, "{{X}}", "WERT", False)
        assert absatz.text == "nur {{ANDERES}}"

    def test_absatz_ohne_runs(self, generator):
        absatz = Document().add_paragraph()
        generator._replace_in_paragraph(absatz, {"{{X}}": ("WERT", False)})
        assert absatz.text == ""

    def test_mehrere_platzhalter_im_selben_absatz(self, generator):
        absatz = self._absatz("{{A}} und {", "{B}}")
        generator._replace_in_paragraph(absatz, {"{{A}}": ("1", False), "{{B}}": ("2", False)})
        assert absatz.text == "1 und 2"

    def test_ersatzwert_wird_zu_text(self):
        tabelle = SpesenGenerator._collect_replacements({"K": True, "L": False}, {"Z": 5})
        assert tabelle == {
            "{{K}}": (CHECKBOX_CHECKED, True),
            "{{L}}": (CHECKBOX_UNCHECKED, True),
            "{{Z}}": ("5", False),
        }


# ===== Dateien =====

class TestDateien:
    def test_fehlende_vorlage(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            SpesenGenerator(str(tmp_path / "gibtsnicht.docx"))

    def test_generate_document_ohne_output_dir(self, generator):
        with pytest.raises(ValueError):
            generator.generate_document(_spiel())

    def test_generate_document_legt_datei_an(self, tmp_path):
        gen = SpesenGenerator(str(VORLAGE), output_dir=tmp_path / "out")
        pfad = gen.generate_document(_spiel(), expenses={"sr_km": 100})
        assert pfad == tmp_path / "out" / "Spesen_FC Rot-Weiß Erfurt II_vs_SV Blau-Gelb Weimar_08-11-2025.docx"
        assert _felder(pfad.read_bytes())["SR_Kilometer"] == "30,00 €"

    def test_generate_document_mit_eigenem_namen(self, tmp_path):
        gen = SpesenGenerator(str(VORLAGE), output_dir=tmp_path)
        assert gen.generate_document(_spiel(), output_filename="x.docx") == tmp_path / "x.docx"

    def test_generate_all_documents(self, tmp_path):
        gen = SpesenGenerator(str(VORLAGE), output_dir=tmp_path)
        zweites = _spiel()
        zweites["spiel_info"] = dict(zweites["spiel_info"], heim_team="Heim B", gast_team="Gast B")
        expenses_map = {
            ("FC Rot-Weiß Erfurt II", "SV Blau-Gelb Weimar", "2025-11-08"): {"sr_km": 100},
        }
        kaputt = {"spiel_info": None}

        pfade = gen.generate_all_documents([_spiel(), kaputt, zweites], expenses_map)

        assert len(pfade) == 2
        assert _felder(pfade[0].read_bytes())["SR_Kilometer"] == "30,00 €"
        assert _felder(pfade[1].read_bytes())["SR_Kilometer"] == ""
