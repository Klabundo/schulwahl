"""E2E-Tests für das Abstimmungssystem – frische Test-DB pro Lauf.

Start:  venv/bin/python -m pytest
"""
import re

from datetime import datetime, timedelta

import app as appmod

ADMIN_PW = "admin123"


# ---------- Helfer ----------

def create_election(client, title="Testwahl", max_votes=1, ends_at=""):
    r = client.post("/api/admin/elections", json={
        "title": title, "max_votes": max_votes, "ends_at": ends_at})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["id"]


def add_candidates(client, eid, names):
    for n in names:
        r = client.post(f"/api/admin/elections/{eid}/candidates",
                        json={"name": n})
        assert r.status_code == 200, r.get_data(as_text=True)
    pub = client.get(f"/api/election/{eid}/public").get_json()
    return [c["id"] for c in pub["candidates"]]


def add_ballots(client, eid, count):
    r = client.post(f"/api/admin/elections/{eid}/ballots", json={"count": count})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["added"]


def get_codes(client, eid):
    r = client.get(f"/api/admin/elections/{eid}/ballots")
    assert r.status_code == 200
    return [b["code"] for b in r.get_json()]


def start(client, eid):
    r = client.post(f"/api/admin/elections/{eid}/start")
    assert r.status_code == 200, r.get_data(as_text=True)


def close(client, eid):
    r = client.post(f"/api/admin/elections/{eid}/close")
    assert r.status_code == 200, r.get_data(as_text=True)


def vote(client, eid, code, ids):
    return client.post("/api/vote", json={
        "election_id": eid, "code": code, "candidate_ids": ids})


def public(client, eid):
    r = client.get(f"/api/election/{eid}/public")
    assert r.status_code == 200
    return r.get_json()


def open_elections(client):
    r = client.get("/api/elections/open")
    assert r.status_code == 200
    return r.get_json()


def iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- Basis ----------

def test_seed(client):
    el = public(client, 1)
    assert el["status"] == "draft"
    assert len(el["candidates"]) == 4
    res = client.get("/api/election/1/results").get_json()
    assert res["totals"]["ballots"] == 60


def test_admin_api_requires_login(client):
    assert client.get("/api/admin/overview").status_code == 401
    assert client.post("/api/admin/elections",
                       json={"title": "xx"}).status_code == 401


def test_login_wrong_password(client):
    r = client.post("/login", data={"password": "falsch"})
    assert r.status_code == 200
    assert "Das Passwort stimmt nicht" in r.get_data(as_text=True)


def test_parse_deadline():
    assert appmod.parse_deadline("2026-10-16T12:00") == "2026-10-16 12:00:00"
    assert appmod.parse_deadline("2026-10-16 12:00:30") == "2026-10-16 12:00:30"
    assert appmod.parse_deadline("") is None
    assert appmod.parse_deadline(None) is None
    for bad in ["16.10.2026", "2026-99-16 12:00", "garbage"]:
        try:
            appmod.parse_deadline(bad)
            assert False, f"{bad!r} hätte ValueError werfen müssen"
        except ValueError:
            pass


# ---------- Kern-Ablauf ----------

def test_full_lifecycle(admin_client):
    eid = create_election(admin_client, "Kernwahl")
    cids = add_candidates(admin_client, eid, ["A", "B", "C"])
    add_ballots(admin_client, eid, 5)
    codes = get_codes(admin_client, eid)
    assert len(codes) == 5
    assert all(re.fullmatch(r"[A-Z2-9]{4}-[A-Z2-9]{4}", c) for c in codes)

    assert public(admin_client, eid)["status"] == "draft"
    start(admin_client, eid)
    assert public(admin_client, eid)["status"] == "running"

    # unbekannte Wahl
    assert vote(admin_client, 99999, codes[0], [cids[0]]).status_code == 404
    # unbekannter Code
    r = vote(admin_client, eid, "XXXX-YYYY", [cids[0]])
    assert r.status_code == 400 and "kennen wir nicht" in r.get_json()["error"]
    # gültige Stimme
    r = vote(admin_client, eid, codes[0], [cids[0]])
    assert r.get_json()["ok"] and r.get_json()["total"] == 1
    # Code erneut → abgelehnt
    r = vote(admin_client, eid, codes[0], [cids[0]])
    assert "bereits verwendet" in r.get_json()["error"]
    # kleiner Code (Groß-/Kleinschreibung egal)
    r = vote(admin_client, eid, codes[1].lower(), [cids[1]])
    assert r.get_json()["ok"]

    res = admin_client.get(f"/api/election/{eid}/results").get_json()
    assert res["totals"]["votes"] == 2
    assert res["totals"]["used"] == 2

    close(admin_client, eid)
    r = vote(admin_client, eid, codes[2], [cids[0]])
    assert "bereits beendet" in r.get_json()["error"]

    # Stimmzettel-API kennt „verwendet“
    used = {b["code"]: b["used"] for b in
            admin_client.get(f"/api/admin/elections/{eid}/ballots").get_json()}
    assert used[codes[0]] and used[codes[1]] and not used[codes[2]]


def test_vote_on_draft_rejected(admin_client):
    eid = create_election(admin_client, "Noch nicht angefangen")
    cids = add_candidates(admin_client, eid, ["A"])
    add_ballots(admin_client, eid, 1)
    r = vote(admin_client, eid, get_codes(admin_client, eid)[0], [cids[0]])
    assert r.status_code == 400
    assert "noch nicht begonnen" in r.get_json()["error"]


def test_max_votes_and_duplicates(admin_client):
    eid = create_election(admin_client, "Mehrfachwahl", max_votes=2)
    cids = add_candidates(admin_client, eid, ["A", "B", "C"])
    add_ballots(admin_client, eid, 3)
    codes = get_codes(admin_client, eid)
    start(admin_client, eid)

    assert vote(admin_client, eid, codes[0], cids[:2]).get_json()["ok"]
    r = vote(admin_client, eid, codes[1], cids[:3])
    assert "maximal 2 Optionen" in r.get_json()["error"]
    r = vote(admin_client, eid, codes[2], [cids[0], cids[0]])
    assert "Doppelauswahl" in r.get_json()["error"]


def test_delete_election_cascades(admin_client):
    eid = create_election(admin_client, "Wegwerfen")
    add_candidates(admin_client, eid, ["A"])
    add_ballots(admin_client, eid, 2)
    assert client_delete_ok(admin_client, eid)
    assert client_public_gone(admin_client, eid)


def client_delete_ok(client, eid):
    return client.delete(f"/api/admin/elections/{eid}").status_code == 200


def client_public_gone(client, eid):
    return client.get(f"/api/election/{eid}/public").status_code == 404


# ---------- Parallel-Wahlen ----------

def test_parallel_elections(admin_client):
    e1 = create_election(admin_client, "Wahl 1")
    e2 = create_election(admin_client, "Wahl 2")
    c1 = add_candidates(admin_client, e1, ["A"])
    c2 = add_candidates(admin_client, e2, ["B"])
    add_ballots(admin_client, e1, 2)
    add_ballots(admin_client, e2, 2)
    start(admin_client, e1)
    start(admin_client, e2)

    running = {e["id"] for e in open_elections(admin_client)}
    assert {e1, e2} <= running

    codes1 = get_codes(admin_client, e1)
    codes2 = get_codes(admin_client, e2)
    # Code aus Wahl 1 taugt nicht für Wahl 2
    r = vote(admin_client, e2, codes1[0], [c2[0]])
    assert "kennen wir nicht" in r.get_json()["error"]
    # beide Wahlen verlaufen unabhängig
    assert vote(admin_client, e1, codes1[0], [c1[0]]).get_json()["ok"]
    assert vote(admin_client, e2, codes2[0], [c2[0]]).get_json()["ok"]
    assert (admin_client.get(f"/api/election/{e1}/results")
            .get_json()["totals"]["votes"]) == 1
    assert (admin_client.get(f"/api/election/{e2}/results")
            .get_json()["totals"]["votes"]) == 1


# ---------- Stichtag / Auto-Beenden ----------

def test_deadline_flow(admin_client):
    eid = create_election(admin_client, "Mit Frist")
    cids = add_candidates(admin_client, eid, ["A"])
    add_ballots(admin_client, eid, 2)
    codes = get_codes(admin_client, eid)
    start(admin_client, eid)

    future = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")
    r = admin_client.post(f"/api/admin/elections/{eid}/deadline",
                          json={"ends_at": future})
    assert r.status_code == 200
    assert public(admin_client, eid)["ends_at"] == future + ":00"
    assert vote(admin_client, eid, codes[0], [cids[0]]).get_json()["ok"]

    # Frist in der Vergangenheit → Voting sofort abgelehnt …
    past = (datetime.now() - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
    r = admin_client.post(f"/api/admin/elections/{eid}/deadline",
                          json={"ends_at": past})
    assert r.status_code == 200
    r = vote(admin_client, eid, codes[1], [cids[0]])  # ungenutzter Code
    assert "bereits beendet" in r.get_json()["error"]

    # … und der Auto-Beender schließt die Wahl dann ab
    conn = appmod.open_db()
    try:
        closed = appmod.auto_close_expired(conn)
    finally:
        conn.close()
    assert closed >= 1
    el = public(admin_client, eid)
    assert el["status"] == "closed"
    assert el["ends_at"] == past

    # Stichtag bei beendeter Wahl → abgelehnt
    assert admin_client.post(
        f"/api/admin/elections/{eid}/deadline",
        json={"ends_at": future}).status_code == 400


def test_deadline_clear_and_invalid(admin_client):
    eid = create_election(admin_client, "Frist los")
    add_candidates(admin_client, eid, ["A"])
    future = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    assert admin_client.post(
        f"/api/admin/elections/{eid}/deadline",
        json={"ends_at": future}).status_code == 200
    assert public(admin_client, eid)["ends_at"] == future + ":00"
    # leere Eingabe → Stichtag entfernt
    assert admin_client.post(
        f"/api/admin/elections/{eid}/deadline",
        json={"ends_at": ""}).status_code == 200
    assert public(admin_client, eid)["ends_at"] is None
    # ungültiges Datum → 400
    assert admin_client.post(
        f"/api/admin/elections/{eid}/deadline",
        json={"ends_at": "gestern"}).status_code == 400


def test_expired_not_in_open_list(admin_client):
    eid = create_election(admin_client, "Abgelaufen", ends_at=iso())
    add_candidates(admin_client, eid, ["A"])
    add_ballots(admin_client, eid, 1)
    start(admin_client, eid)
    conn = appmod.open_db()
    try:
        appmod.auto_close_expired(conn)
    finally:
        conn.close()
    assert eid not in {e["id"] for e in open_elections(admin_client)}


# ---------- Finale ----------

def test_final_flow(admin_client):
    eid = create_election(admin_client, "Vorrunde")
    cids = add_candidates(admin_client, eid, ["A", "B", "C"])
    add_ballots(admin_client, eid, 4)
    codes = get_codes(admin_client, eid)
    start(admin_client, eid)
    vote(admin_client, eid, codes[0], [cids[0]])
    vote(admin_client, eid, codes[1], [cids[0]])
    vote(admin_client, eid, codes[2], [cids[1]])
    close(admin_client, eid)

    r = admin_client.post(f"/api/admin/elections/{eid}/final",
                          json={"top": 2})
    assert r.status_code == 200, r.get_data(as_text=True)
    fid = r.get_json()["id"]
    fin = public(admin_client, fid)
    assert fin["round"] == 2
    assert fin["title"].endswith("– Finale")
    assert fin["status"] == "draft"
    names = [c["name"] for c in fin["candidates"]]
    assert names == ["A", "B"]  # A mit 2, B mit 1, C ohne

    # Finale selbst darf kein weiteres Finale bekommen
    start(admin_client, fid)
    close(admin_client, fid)
    r = admin_client.post(f"/api/admin/elections/{fid}/final", json={"top": 2})
    assert "selbst schon ein Finale" in r.get_json()["error"]

    # Finale mit zu wenig Kandidat:innen
    solo = create_election(admin_client, "Allein")
    add_candidates(admin_client, solo, ["Einsame:r"])
    add_ballots(admin_client, solo, 1)
    start(admin_client, solo)
    close(admin_client, solo)
    r = admin_client.post(f"/api/admin/elections/{solo}/final", json={"top": 2})
    assert r.status_code == 400
    # Finale aus laufender Wahl
    running = create_election(admin_client, "Läuft noch")
    add_candidates(admin_client, running, ["X", "Y"])
    start(admin_client, running)
    r = admin_client.post(f"/api/admin/elections/{running}/final", json={"top": 2})
    assert "Beende zuerst" in r.get_json()["error"]


# ---------- CSV & Druck ----------

def test_csv_export(admin_client):
    eid = create_election(admin_client, "CSV-Wahl")
    cids = add_candidates(admin_client, eid, ["Projekt X", "Projekt Y"])
    add_ballots(admin_client, eid, 10)
    codes = get_codes(admin_client, eid)
    start(admin_client, eid)
    vote(admin_client, eid, codes[0], [cids[0]])
    vote(admin_client, eid, codes[1], [cids[0]])
    vote(admin_client, eid, codes[2], [cids[1]])

    r = admin_client.get(f"/api/admin/elections/{eid}/results.csv")
    assert r.status_code == 200
    assert "text/csv" in r.content_type
    assert 'filename="wahl-%d-ergebnisse.csv"' % eid in r.headers["Content-Disposition"]
    body = r.get_data(as_text=True)
    assert body.startswith("\ufeff")  # BOM für Excel
    assert "Projekt X;2" in body
    assert "Projekt Y;1" in body
    assert "Stimmen gesamt;3" in body
    assert "Beteiligung;30 %" in body


def test_csv_requires_login(client):
    assert client.get("/api/admin/elections/1/results.csv").status_code == 401


def test_print_page(admin_client):
    eid = create_election(admin_client, "Druck-Wahl")
    add_ballots(admin_client, eid, 12)
    codes = get_codes(admin_client, eid)

    r = admin_client.get(f"/print/{eid}?per=10")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Stimmzettel drucken" in body
    assert codes[0] in body
    assert "Seite 2 von 2" in body
    assert "Stimmzettel 11–12" in body
    assert "data:image/png" not in body  # ohne QR standardmäßig

    r = admin_client.get(f"/print/{eid}?per=10&qr=1")
    assert "data:image/png;base64" in r.get_data(as_text=True)


def test_print_requires_login(client):
    r = client.get("/print/1")
    assert r.status_code in (302, 307)
    assert "/login" in r.headers["Location"]


def test_print_unknown_election(admin_client):
    assert admin_client.get("/print/99999").status_code == 404
