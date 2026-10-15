import base64
import csv
import hashlib
import io
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime

import qrcode
import qrcode.constants
from flask import (Flask, Response, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SCHULWAHL_DB") or os.path.join(
    BASE, "schulwahl.db")

app = Flask(__name__)
app.permanent_session_lifetime = 3600 * 12
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def hash_password(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()
    return f"{salt}:{digest}"


def check_password(pw, stored):
    salt, digest = stored.split(":", 1)
    return hashlib.sha256((salt + pw).encode("utf-8")).hexdigest() == digest


def meta(db, key, default=None):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def new_code(db):
    while True:
        code = "-".join(
            "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
            for _ in range(2)
        )
        if not db.execute("SELECT 1 FROM ballots WHERE code=?", (code,)).fetchone():
            return code


def open_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def parse_deadline(v):
    """Normalisiert „YYYY-MM-DD THH:MM[[:SS]“ auf „YYYY-MM-DD HH:MM:SS“.

    Leerer Wert → None (keine Frist). Ungültiger Wert → ValueError.
    """
    v = (v or "").strip().replace("T", " ")
    if not v:
        return None
    if len(v) == 16:
        v += ":00"
    return datetime.strptime(
        v, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")


def auto_close_expired(db):
    """Schließt laufende Wahlen, deren Stichtag erreicht ist.
    Gibt die Anzahl neu beendeter Wahlen zurück."""
    closed = 0
    ts = now()
    for r in db.execute(
        "SELECT id FROM elections "
        "WHERE status='running' AND ends_at IS NOT NULL AND ends_at <= ?",
        (ts,),
    ).fetchall():
        db.execute(
            "UPDATE elections SET status='closed', ended_at=? WHERE id=?",
            (ts, r["id"]),
        )
        closed += 1
    if closed:
        db.commit()
    return closed


def _auto_close_loop():
    while True:
        conn = open_db()
        try:
            auto_close_expired(conn)
        except Exception:
            pass
        finally:
            conn.close()
        time.sleep(10)


threading.Thread(target=_auto_close_loop, daemon=True,
                 name="schulwahl-auto-close").start()


def election_payload(eid, db=None):
    own = db is None
    db = db or open_db()
    try:
        el = db.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
        if not el:
            return None
        rows = db.execute(
            """SELECT c.*, coalesce(v.count, 0) AS votes
               FROM candidates c
               LEFT JOIN (SELECT candidate_id, COUNT(*) AS count FROM votes
                          WHERE election_id=? GROUP BY candidate_id) v
               ON c.id = v.candidate_id
               WHERE c.election_id=?
               ORDER BY c.sort, c.id""",
            (eid, eid),
        ).fetchall()
        total_votes = db.execute(
            "SELECT COUNT(*) n FROM votes WHERE election_id=?", (eid,),
        ).fetchone()["n"]
        total_ballots = db.execute(
            "SELECT COUNT(*) n FROM ballots WHERE election_id=?", (eid,),
        ).fetchone()["n"]
        used = db.execute(
            "SELECT COUNT(*) n FROM ballots WHERE election_id=? AND used_at IS NOT NULL",
            (eid,),
        ).fetchone()["n"]
        el = dict(el)
        el["candidates"] = [
            {**dict(c), "name": c["name"]} for c in rows
        ]
        el["totals"] = {
            "votes": total_votes,
            "ballots": total_ballots,
            "used": used,
        }
        return el
    finally:
        if own:
            db.close()


def is_admin():
    return bool(session.get("admin"))


def check_admin():
    if not is_admin():
        return None
    return get_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        pw = request.form.get("password", "")
        db = get_db()
        stored = meta(db, "admin_pass")
        if stored and check_password(pw, stored):
            session["admin"] = True
            session.permanent = True
            return redirect(url_for("admin"))
        error = "Das Passwort stimmt nicht. Nochmal versuchen?"
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.route("/vote")
def vote():
    return render_template(
        "vote.html",
        election_id=request.args.get("e", ""),
        code=request.args.get("c", ""),
    )


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/admin")
def admin():
    if not is_admin():
        return redirect(url_for("login"))
    return render_template("admin.html")


@app.route("/api/elections/open")
def api_elections_open():
    db = get_db()
    rows = db.execute(
        """SELECT e.id, e.title, e.status, e.ends_at,
            (SELECT COUNT(*) FROM votes v WHERE v.election_id=e.id) AS votes
           FROM elections e
           WHERE e.status='running'
             AND (e.ends_at IS NULL OR e.ends_at > ?)
           ORDER BY e.id DESC""",
        (now(),),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/election/<int:eid>/public")
def api_election_public(eid):
    el = election_payload(eid)
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    safe = {
        "id": el["id"],
        "title": el["title"],
        "description": el["description"],
        "status": el["status"],
        "round": el.get("round") or 1,
        "max_votes": el["max_votes"],
        "ends_at": el.get("ends_at"),
        "candidates": [
            {"id": c["id"], "name": c["name"], "slogan": c["slogan"]}
            for c in el["candidates"]
        ],
    }
    return jsonify(safe)


@app.route("/api/vote", methods=["POST"])
def api_vote():
    data = request.get_json(silent=True) or {}
    eid = data.get("election_id")
    code = (data.get("code") or "").strip().upper()
    candidate_ids = data.get("candidate_ids") or []
    if not eid or not code or not candidate_ids:
        return jsonify(
            ok=False,
            error="Bitte Wahl-Nummer, Stimmcode und Auswahl angeben."), 400
    db = get_db()
    el = db.execute(
        "SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return jsonify(ok=False, error="Wahl nicht gefunden."), 404
    if el["status"] != "running":
        msg = {"draft": "Diese Wahl hat noch nicht begonnen.",
               "closed": "Diese Wahl ist bereits beendet."}.get(
            el["status"], "Diese Wahl ist gerade nicht offen.")
        return jsonify(ok=False, error=msg), 400
    if el["ends_at"] and el["ends_at"] <= now():
        return jsonify(
            ok=False, error="Diese Wahl ist bereits beendet."), 400
    ballot = db.execute(
        "SELECT * FROM ballots WHERE election_id=? AND code=?",
        (eid, code),
    ).fetchone()
    if not ballot:
        return jsonify(
            ok=False,
            error="Diesen Stimmcode kennen wir nicht – bitte noch "
                  "einmal auf dem Zettel prüfen."), 400
    if ballot["used_at"]:
        return jsonify(
            ok=False,
            error="Dieser Stimmcode wurde bereits verwendet. "
                  "Ein Zettel, eine Stimme."), 400
    candidates = db.execute(
        "SELECT id FROM candidates WHERE election_id=?", (eid,)
    ).fetchall()
    valid_ids = {c["id"] for c in candidates}
    if len(set(candidate_ids)) != len(candidate_ids):
        return jsonify(ok=False,
                       error="Bitte keine Doppelauswahl."), 400
    if not all(int(cid) in valid_ids for cid in candidate_ids):
        return jsonify(ok=False, error="Diese Auswahl ist ungültig."), 400
    if el["max_votes"] and len(candidate_ids) > el["max_votes"]:
        return jsonify(
            ok=False,
            error=f"Du kannst hier maximal {el['max_votes']} "
                  f"Optionen ankreuzen.",
        ), 400
    ts = now()
    for cid in candidate_ids:
        db.execute(
            "INSERT INTO votes (election_id, candidate_id, cast_at) VALUES (?,?,?)",
            (eid, int(cid), ts),
        )
    db.execute("UPDATE ballots SET used_at=? WHERE id=?", (ts, ballot["id"]))
    db.commit()
    total = db.execute(
        "SELECT COUNT(*) n FROM votes WHERE election_id=?", (eid,)
    ).fetchone()["n"]
    return jsonify(ok=True, message="Deine Stimme wurde gezählt.",
                   total=total)


@app.route("/api/election/<int:eid>/results")
def api_results(eid):
    el = election_payload(eid)
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    return jsonify(el)


@app.route("/stream/<int:eid>")
def stream(eid):
    def gen():
        last = None
        conn = open_db()
        try:
            while True:
                el = election_payload(eid, conn) or {"error": "not found"}
                payload = json.dumps(el, default=str)
                if payload != last:
                    yield f"data: {payload}\n\n"
                    last = payload
                time.sleep(1.5)
        finally:
            conn.close()

    return Response(gen(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


@app.route("/api/admin/overview")
def api_admin_overview():
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    rows = db.execute(
        """SELECT e.*,
          (SELECT COUNT(*) FROM candidates c WHERE c.election_id=e.id) AS candidate_count,
          (SELECT COUNT(*) FROM ballots b WHERE b.election_id=e.id) AS ballot_count,
          (SELECT COUNT(*) FROM votes v WHERE v.election_id=e.id) AS vote_count
         FROM elections e ORDER BY e.id DESC"""
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/elections", methods=["POST"])
def api_admin_create_election():
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="Titel angeben."), 400
    try:
        ends_at = parse_deadline(data.get("ends_at"))
    except ValueError:
        return jsonify(
            error="Ungültiges Datum – bitte als „JJJJ-MM-TT HH:MM“ angeben."), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO elections
           (title, description, max_votes, status, created_at, ends_at)
           VALUES (?,?,?,?,?,?)""",
        (title,
         (data.get("description") or "").strip(),
         int(data.get("max_votes") or 1),
         "draft",
         now(),
         ends_at),
    )
    db.commit()
    return jsonify(id=cur.lastrowid)


@app.route("/api/admin/elections/<int:eid>", methods=["DELETE"])
def api_admin_delete_election(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    db.execute("DELETE FROM elections WHERE id=?", (eid,))
    db.commit()
    return jsonify(ok=True)


@app.route("/api/admin/elections/<int:eid>/final", methods=["POST"])
def api_admin_final(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    top = int(data.get("top") or 2)
    if not 2 <= top <= 10:
        return jsonify(
            error="Gib eine Zahl zwischen 2 und 10 an."), 400
    db = get_db()
    el = db.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    if el["status"] != "closed":
        return jsonify(error="Beende zuerst Runde 1."), 400
    if el["round"] is not None and el["round"] > 1:
        return jsonify(error="Das ist selbst schon ein Finale."), 400
    ranked = db.execute(
        """SELECT c.id, c.name, c.slogan
           FROM candidates c
           LEFT JOIN (SELECT candidate_id, COUNT(*) n FROM votes
                      WHERE election_id=? GROUP BY candidate_id) v
           ON c.id = v.candidate_id
           WHERE c.election_id=?
           ORDER BY coalesce(v.n, 0) DESC, c.name ASC""",
        (eid, eid),
    ).fetchall()
    if len(ranked) < 2:
        return jsonify(
            error="Für ein Finale braucht man mindestens 2 "
                  "Kandidat:innen aus Runde 1."), 400
    if top > len(ranked):
        top = len(ranked)
    ts = now()
    cur = db.execute(
        """INSERT INTO elections
           (title, description, max_votes, status, created_at, round, parent_id)
           VALUES (?,?,?, 'draft', ?, ?, ?)""",
        (f"{el['title']} – Finale",
         el["description"].strip() and
         "Finale: Die besten Projekte aus der 1. Runde duellieren sich. " +
         el["description"]
         or f"Finale aus: {el['title']}",
         el["max_votes"],
         ts,
         (el["round"] or 1) + 1,
         eid),
    )
    new_id = cur.lastrowid
    for i, c in enumerate(ranked[:top]):
        db.execute(
            """INSERT INTO candidates (election_id, name, slogan, sort)
               VALUES (?, ?, ?, ?)""",
            (new_id, c["name"], c["slogan"], i + 1),
        )
    db.commit()
    return jsonify(ok=True, id=new_id)


@app.route("/api/admin/elections/<int:eid>/deadline", methods=["POST"])
def api_admin_deadline(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    try:
        ends_at = parse_deadline(data.get("ends_at"))
    except ValueError:
        return jsonify(
            error="Ungültiges Datum – bitte als „JJJJ-MM-TT HH:MM“ angeben."), 400
    db = get_db()
    el = db.execute(
        "SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    if el["status"] == "closed":
        return jsonify(
            error="Diese Wahl ist bereits beendet – ein Stichtag passt "
                  "nicht mehr dazu."), 400
    db.execute("UPDATE elections SET ends_at=? WHERE id=?", (ends_at, eid))
    db.commit()
    return jsonify(ok=True, ends_at=ends_at)


def set_election_status(eid, status, ts_field=None):
    db = get_db()
    ts = now()
    db.execute(
        f"UPDATE elections SET status=?, {ts_field}=COALESCE({ts_field}, ?) WHERE id=?",
        (status, ts, eid),
    )
    db.commit()


@app.route("/api/admin/elections/<int:eid>/start", methods=["POST"])
def api_admin_start(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    el = db.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    if el["status"] in ("closed", "running"):
        msg = {"closed": "Diese Wahl ist bereits beendet.",
               "running": "Diese Wahl läuft bereits."}[el["status"]]
        return jsonify(error=msg), 400
    set_election_status(eid, "running", "started_at")
    return jsonify(ok=True)


@app.route("/api/admin/elections/<int:eid>/close", methods=["POST"])
def api_admin_close(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    el = db.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    set_election_status(eid, "closed", "ended_at")
    return jsonify(ok=True)


@app.route("/api/admin/elections/<int:eid>/candidates", methods=["POST"])
def api_admin_add_candidate(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="Bitte einen Namen angeben."), 400
    db = get_db()
    db.execute(
        """INSERT INTO candidates (election_id, name, slogan, sort)
           VALUES (?,?,?,
             (SELECT coalesce(MAX(sort),0)+1 FROM candidates WHERE election_id=?))""",
        (eid, name, (data.get("slogan") or "").strip(), eid),
    )
    db.commit()
    return jsonify(ok=True)


@app.route(
    "/api/admin/elections/<int:eid>/candidates/<int:cid>", methods=["DELETE"])
def api_admin_del_candidate(eid, cid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    db.execute(
        "DELETE FROM candidates WHERE id=? AND election_id=?", (cid, eid))
    db.execute(
        "DELETE FROM votes WHERE candidate_id=? AND election_id=?", (cid, eid))
    db.commit()
    return jsonify(ok=True)


@app.route("/api/admin/elections/<int:eid>/ballots", methods=["POST"])
def api_admin_add_ballots(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    count = int(data.get("count") or 0)
    if not 1 <= count <= 500:
        return jsonify(
            error="Bitte gib eine Zahl zwischen 1 und 500 an."), 400
    db = get_db()
    el = db.execute("SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    if el["status"] == "closed":
        return jsonify(error="Wahl ist beendet."), 400
    for _ in range(count):
        db.execute(
            "INSERT INTO ballots (election_id, code) VALUES (?,?)",
            (eid, new_code(db)),
        )
    db.commit()
    return jsonify(ok=True, added=count)


@app.route("/api/admin/elections/<int:eid>/ballots")
def api_admin_ballots(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    db = get_db()
    rows = db.execute(
        "SELECT id, code, used_at FROM ballots WHERE election_id=? ORDER BY id",
        (eid,),
    ).fetchall()
    qhost = (request.args.get("host") or "").strip().rstrip("/")
    out = []
    for r in rows:
        rel = url_for("vote", e=eid, c=r["code"])
        url = f"{qhost}{rel}" if qhost else url_for(
            "vote", e=eid, c=r["code"], _external=True)
        buf = io.BytesIO()
        qrcode.make(url, box_size=6, border=1, error_correction=qrcode.constants.ERROR_CORRECT_M).save(
            buf, "PNG")
        data_url = "data:image/png;base64," + base64.b64encode(
            buf.getvalue()).decode("ascii")
        out.append({
            "id": r["id"],
            "code": r["code"],
            "used": bool(r["used_at"]),
            "url": url,
            "qr": data_url,
        })
    return jsonify(out)


@app.route("/api/admin/elections/<int:eid>/results.csv")
def api_results_csv(eid):
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    el = election_payload(eid)
    if not el:
        return jsonify(error="Wahl nicht gefunden."), 404
    status_text = {"draft": "bereit", "running": "läuft",
                   "closed": "beendet"}.get(el["status"], el["status"])
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(["Wahl", el["title"]])
    w.writerow(["Wahl-Nummer", el["id"]])
    w.writerow(["Status", status_text])
    if el.get("ends_at"):
        w.writerow(["Stichtag", el["ends_at"]])
    w.writerow([])
    w.writerow(["Kandidat:in", "Stimmen", "Anteil"])
    total = el["totals"]["votes"]
    for c in el["candidates"]:
        share = f"{round(100 * c['votes'] / total)} %" if total else "–"
        w.writerow([c["name"], c["votes"], share])
    w.writerow([])
    w.writerow(["Stimmen gesamt", total])
    w.writerow(["Stimmzettel", el["totals"]["ballots"]])
    w.writerow(["Ausgezählt", el["totals"]["used"]])
    part = (round(100 * el["totals"]["used"] / el["totals"]["ballots"])
            if el["totals"]["ballots"] else 0)
    w.writerow(["Beteiligung", f"{part} %"])
    return Response(
        "\ufeff" + buf.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="wahl-{eid}-ergebnisse.csv"'})


@app.route("/print/<int:eid>")
def print_ballots(eid):
    if not is_admin():
        return redirect(url_for("login"))
    db = get_db()
    el = db.execute(
        "SELECT * FROM elections WHERE id=?", (eid,)).fetchone()
    if not el:
        return "Wahl nicht gefunden.", 404
    try:
        per = int(request.args.get("per", "50"))
    except ValueError:
        per = 50
    per = min(max(per, 10), 100)
    with_qr = request.args.get("qr") == "1"
    qhost = (request.args.get("host") or "").strip().rstrip("/")
    base_url = qhost or url_for("index", _external=True).rstrip("/")
    rows = db.execute(
        "SELECT code, used_at FROM ballots WHERE election_id=? ORDER BY id",
        (eid,),
    ).fetchall()
    pages = []
    for i in range(0, len(rows), per):
        page = []
        for r in rows[i:i + per]:
            item = dict(r)
            if with_qr:
                url = f"{base_url}/vote?e={eid}&c={item['code']}"
                buf = io.BytesIO()
                qrcode.make(
                    url, box_size=6, border=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                ).save(buf, "PNG")
                item["qr"] = "data:image/png;base64," + base64.b64encode(
                    buf.getvalue()).decode("ascii")
            page.append(item)
        pages.append(page)
    return render_template(
        "print.html",
        el=el,
        pages=pages,
        per=per,
        total=len(rows),
        base_url=base_url,
        with_qr=with_qr,
        host=qhost,
    )


@app.route("/api/admin/password", methods=["POST"])
def api_admin_password():
    if not check_admin():
        return jsonify(error="unauthorized"), 401
    data = request.get_json(silent=True) or {}
    old = data.get("old") or ""
    new = data.get("new") or ""
    if len(new) < 4:
        return jsonify(error="Das neue Passwort braucht mindestens 4 Zeichen."), 400
    db = get_db()
    stored = meta(db, "admin_pass")
    if not stored or not check_password(old, stored):
        return jsonify(error="Das aktuelle Passwort ist falsch."), 400
    db.execute(
        "UPDATE meta SET value=? WHERE key='admin_pass'",
        (hash_password(new),),
    )
    db.commit()
    return jsonify(ok=True)


def seed(db):
    if db.execute("SELECT COUNT(*) n FROM elections").fetchone()["n"]:
        return
    ts = now()
    cur = db.execute(
        """INSERT INTO elections
           (title, description, max_votes, status, created_at)
           VALUES (?,?,1,'draft',?)""",
        ("Demo: Klimaprojekt der Schule",
         "Wofür soll die Projektspende der Öko-Woche (500 €) Verwendung "
         "finden? Stimmt ab mit eurem Code – eine Person, eine Stimme.",
         ts),
    )
    eid = cur.lastrowid
    for name, slogan in [
        ("Gemüsebeet auf dem Schulhof", "Frische Salate für die Kantine – geerntet von uns."),
        ("Fahrradwerkstatt", "Reparieren statt wegwerfen – mit Werkzeug und Boxen"),
        ("Solarpanel auf dem Dach", "Saubere Energie für den Computerraum"),
        ("Mülltrennungs-Crew", "Sortierstationen + Streifen in den Pausen"),
    ]:
        db.execute(
            "INSERT INTO candidates (election_id, name, slogan) VALUES (?,?,?)",
            (eid, name, slogan),
        )
    for _ in range(60):
        db.execute("INSERT INTO ballots (election_id, code) VALUES (?,?)",
                   (eid, new_code(db)))
    db.commit()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS elections (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      parent_id INTEGER,
      "round" INTEGER NOT NULL DEFAULT 1,
      description TEXT NOT NULL DEFAULT '',
      max_votes INTEGER NOT NULL DEFAULT 1,
      status TEXT NOT NULL DEFAULT 'draft',
      created_at TEXT,
      started_at TEXT,
      ended_at TEXT,
      ends_at TEXT
    );
    CREATE TABLE IF NOT EXISTS candidates (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
      name TEXT NOT NULL,
      slogan TEXT NOT NULL DEFAULT '',
      sort INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS ballots (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
      code TEXT NOT NULL UNIQUE,
      used_at TEXT
    );
    CREATE TABLE IF NOT EXISTS votes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      election_id INTEGER NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
      candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
      cast_at TEXT
    );
    """)
    cols = {r["name"] for r in db.execute("PRAGMA table_info(elections)")}
    if "parent_id" not in cols:
        db.execute("ALTER TABLE elections ADD COLUMN parent_id INTEGER")
    if "round" not in cols:
        db.execute(
            'ALTER TABLE elections ADD COLUMN "round" INTEGER '
            "NOT NULL DEFAULT 1")
    if "ends_at" not in cols:
        db.execute("ALTER TABLE elections ADD COLUMN ends_at TEXT")
    if not meta(db, "secret_key"):
        db.execute("INSERT INTO meta VALUES ('secret_key', ?)",
                   (secrets.token_hex(32),))
    if not db.execute(
            "SELECT 1 FROM meta WHERE key='admin_pass'").fetchone():
        db.execute("INSERT INTO meta VALUES ('admin_pass', ?)",
                   (hash_password("admin123"),))
    db.commit()
    db.close()


def _init():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    init_db()
    seed(db)
    app.secret_key = meta(db, "secret_key")
    db.close()


_init()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"* http://<LAN-IP>:8000  (bei Port {port})")
    print(f"* Admin: http://<LAN-IP>:{port}/admin  (Standard-Passwort: admin123)")
    app.run(host=host, port=port)
