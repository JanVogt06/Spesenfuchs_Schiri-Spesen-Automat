"""Passwort aendern."""


def _aendern(client, header, aktuell, neu):
    return client.post("/api/auth/change-password", headers=header,
                       json={"current_password": aktuell, "new_password": neu})


def test_falsches_aktuelles_passwort_meldet_nicht_ab(client, user, auth_header):
    antwort = _aendern(client, auth_header, "falsch", "ganz-neues-passwort")
    # 401 wuerde das Frontend als abgelaufene Sitzung deuten und abmelden
    assert antwort.status_code == 400
    assert antwort.json()["error"]["message"] == "Aktuelles Passwort ist falsch"


def test_neues_passwort_zu_kurz(client, user, auth_header):
    antwort = _aendern(client, auth_header, user["password"], "kurz")
    assert antwort.status_code == 400
    assert "mindestens 8" in antwort.json()["error"]["message"]


def test_neues_gleich_altem(client, user, auth_header):
    antwort = _aendern(client, auth_header, user["password"], user["password"])
    assert antwort.status_code == 400


def test_erfolgreich_und_login_mit_neuem(client, user, auth_header):
    assert _aendern(client, auth_header, user["password"], "ganz-neues-passwort").status_code == 200
    assert client.post("/api/auth/login", json={"email": user["email"], "password": user["password"]}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user["email"], "password": "ganz-neues-passwort"}).status_code == 200


def test_ohne_token(client, user):
    assert _aendern(client, {}, user["password"], "ganz-neues-passwort").status_code == 401
