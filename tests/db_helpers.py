"""
Helpers for the database layer tests.

Not a test module (the name does not start with test_), so pytest collects
nothing here. The test files import it directly - tests/ is on sys.path
during a run.
"""
from datetime import datetime, timedelta, UTC


class Uhr:
    """
    A stopped clock for modules that call datetime.now().

    Replaces the name `datetime` in the target module with a subclass whose
    now() returns the configured time. Everything else (fromisoformat,
    constructor, comparisons) remains the real datetime.
    """

    def __init__(self, jetzt: datetime):
        self.jetzt = jetzt

    def weiter(self, **delta) -> None:
        self.jetzt = self.jetzt + timedelta(**delta)

    def einbauen(self, monkeypatch, *module) -> "Uhr":
        uhr = self

        class _Fest(datetime):
            @classmethod
            def now(cls, tz=None):
                return uhr.jetzt if tz is None else uhr.jetzt.astimezone(tz)

        for modul in module:
            monkeypatch.setattr(modul, "datetime", _Fest)
        return self


def feste_uhr(monkeypatch, *module, jetzt=None) -> Uhr:
    """Clock set to 23.11.2026 12:00 UTC (or now) in the given modules."""
    return Uhr(jetzt or datetime(2026, 11, 23, 12, 0, tzinfo=UTC)).einbauen(monkeypatch, *module)


def anpfiff(tag: str, zeit: str = "13:00") -> str:
    """'2026-12-05' -> 'Samstag · 05.12.2026 · 13:00 Uhr' (weekday irrelevant)."""
    jahr, monat, t = tag.split("-")
    return f"Samstag · {t}.{monat}.{jahr} · {zeit} Uhr"


def spiel(
    heim="FC Heim",
    gast="SV Gast",
    tag="2026-12-05",
    zeit="13:00",
    mannschaftsart="Herren",
    spielklasse="Kreisoberliga",
    staffel="Kreisoberliga Mittelthueringen",
    spieltag="12",
    staette="Sportplatz Am Wald",
    adresse="Waldweg 1, 99999 Irgendwo",
    platz_typ="Rasen",
    schiedsrichter=None,
) -> dict:
    """A match in the structure the scraper delivers."""
    if schiedsrichter is None:
        schiedsrichter = [
            {"rolle": "SR", "name": "Erika Pfeife", "telefon": "1", "email": "sr@example.org",
             "strasse": "Weg 1", "plz_ort": "99999 Irgendwo"},
            {"rolle": "SRA 1", "name": "Max Fahne", "telefon": "2", "email": "a1@example.org",
             "strasse": "Weg 2", "plz_ort": "99999 Irgendwo"},
            {"rolle": "SRA 2", "name": "Moritz Fahne", "telefon": "3", "email": "a2@example.org",
             "strasse": "Weg 3", "plz_ort": "99999 Irgendwo"},
        ]
    return {
        "spiel_info": {
            "anpfiff": anpfiff(tag, zeit),
            "heim_team": heim,
            "gast_team": gast,
            "mannschaftsart": mannschaftsart,
            "spielklasse": spielklasse,
            "staffel": staffel,
            "spieltag": spieltag,
        },
        "spielstaette": {"name": staette, "adresse": adresse, "platz_typ": platz_typ},
        "schiedsrichter": schiedsrichter,
    }


def nutzer_anlegen(conn, email="schiri@example.org") -> int:
    """Creates a user via SQL - works on any schema version."""
    cursor = conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, "hash", "2025-01-01T00:00:00+00:00"),
    )
    conn.commit()
    return cursor.lastrowid


def spiel_einfuegen(conn, user_id, match_key, **felder) -> int:
    """A row directly in matches (from schema version 3)."""
    werte = {
        "user_id": user_id,
        "match_key": match_key,
        "datum": "2025-11-08",
        "km_satz": 0.30,
        "first_seen_at": "2025-11-01T00:00:00+00:00",
        "scraped_at": "2025-11-01T00:00:00+00:00",
        **felder,
    }
    spalten = ", ".join(werte)
    platzhalter = ", ".join(f":{k}" for k in werte)
    cursor = conn.execute(f"INSERT INTO matches ({spalten}) VALUES ({platzhalter})", werte)
    conn.commit()
    return cursor.lastrowid


def migriere_bis(monkeypatch, version: int) -> int:
    """
    Brings the database at database.DB_PATH to exactly `version`.

    For this, MIGRATIONS is temporarily cut down to the first steps and restored
    afterwards - so the real runner is what executes.
    """
    import db.database as database
    import db.migrations as migrations

    alle = migrations.MIGRATIONS
    monkeypatch.setattr(migrations, "MIGRATIONS", [m for m in alle if m[0] <= version])
    try:
        database.init_database()
    finally:
        monkeypatch.setattr(migrations, "MIGRATIONS", alle)
    return user_version()


def user_version() -> int:
    import db.database as database

    conn = database.get_connection()
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def tabellen() -> set:
    import db.database as database

    conn = database.get_connection()
    try:
        return {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    finally:
        conn.close()
