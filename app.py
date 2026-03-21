import sqlite3
import io
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "rfid_secret_key_change_me"

DB_PATH          = "rfid_system.db"
ADMIN_PASSWORD   = "admin"
API_KEY          = "mysecretkey123"
CANTEEN_CAPACITY = 45


def check_api_key():
    return request.headers.get("X-API-Key") == API_KEY


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS allowed_list (
                isic_id    TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                is_allowed INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                isic_id   TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                status    TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exits (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                isic_id   TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        conn.commit()


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def root():
    if session.get("is_admin"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    if session.get("is_admin"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    body = request.get_json(force=True, silent=True) or {}
    if body.get("password") == ADMIN_PASSWORD:
        session["is_admin"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/canteen")
def canteen():
    return render_template("canteen.html", capacity=CANTEEN_CAPACITY)


@app.route("/api/canteen")
def api_canteen():
    today = date.today().strftime("%Y-%m-%d")
    with get_db() as conn:
        entries = conn.execute(
            "SELECT COUNT(*) AS cnt FROM logs WHERE status='ALLOWED' AND timestamp LIKE ?",
            (today + "%",)
        ).fetchone()["cnt"]

        exits = conn.execute(
            "SELECT COUNT(*) AS cnt FROM exits WHERE timestamp LIKE ?",
            (today + "%",)
        ).fetchone()["cnt"]

        denied_today = conn.execute(
            "SELECT COUNT(*) AS cnt FROM logs WHERE status IN ('DENIED','UNKNOWN') AND timestamp LIKE ?",
            (today + "%",)
        ).fetchone()["cnt"]

    inside = max(0, min(entries - exits, CANTEEN_CAPACITY))
    return jsonify({
        "inside":        inside,
        "capacity":      CANTEEN_CAPACITY,
        "entries_today": entries,
        "exits_today":   exits,
        "denied_today":  denied_today
    })


@app.route("/api/canteen/history")
def api_canteen_history():
    today = date.today().strftime("%Y-%m-%d")

    with get_db() as conn:
        hourly = []
        for hour in range(24):
            h_str  = f"{hour:02d}"
            cutoff = today + " " + h_str + ":59:59"
            e = conn.execute(
                "SELECT COUNT(*) AS cnt FROM logs WHERE status='ALLOWED' AND timestamp LIKE ? AND timestamp <= ?",
                (today + "%", cutoff)
            ).fetchone()["cnt"]
            x = conn.execute(
                "SELECT COUNT(*) AS cnt FROM exits WHERE timestamp LIKE ? AND timestamp <= ?",
                (today + "%", cutoff)
            ).fetchone()["cnt"]
            hourly.append(max(0, min(e - x, CANTEEN_CAPACITY)))

        weekly_labels = []
        weekly_peaks  = []
        for days_ago in range(6, -1, -1):
            d     = (date.today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            label = (date.today() - timedelta(days=days_ago)).strftime("%a")
            weekly_labels.append(label)
            peak = 0
            for hour in range(24):
                h_str  = f"{hour:02d}"
                cutoff = d + " " + h_str + ":59:59"
                e = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM logs WHERE status='ALLOWED' AND timestamp LIKE ? AND timestamp <= ?",
                    (d + "%", cutoff)
                ).fetchone()["cnt"]
                x = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM exits WHERE timestamp LIKE ? AND timestamp <= ?",
                    (d + "%", cutoff)
                ).fetchone()["cnt"]
                net = max(0, min(e - x, CANTEEN_CAPACITY))
                if net > peak:
                    peak = net
            weekly_peaks.append(peak)

    return jsonify({
        "capacity":      CANTEEN_CAPACITY,
        "hourly":        hourly,
        "weekly_labels": weekly_labels,
        "weekly_peaks":  weekly_peaks
    })


@app.route("/rfid", methods=["POST"])
def rfid():
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    card_id    = str(data.get("id", "")).strip()
    name       = str(data.get("name", "UNKNOWN")).strip()
    is_allowed = int(data.get("is_allowed", 0))
    is_test    = bool(data.get("is_test", False))

    if not card_id:
        return jsonify({"error": "Missing id"}), 400

    if is_test:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO allowed_list (isic_id, name, is_allowed)
                VALUES (?, ?, ?)
                ON CONFLICT(isic_id) DO UPDATE SET
                    name=excluded.name, is_allowed=excluded.is_allowed
            """, (card_id, name, is_allowed))
            conn.commit()
        return jsonify({"result": "registered", "id": card_id}), 200

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        row = conn.execute(
            "SELECT is_allowed FROM allowed_list WHERE isic_id=?", (card_id,)
        ).fetchone()
        if row is None:
            status = "UNKNOWN"
        elif row["is_allowed"] == 1:
            status = "ALLOWED"
        else:
            status = "DENIED"
        conn.execute(
            "INSERT INTO logs (isic_id, timestamp, status) VALUES (?,?,?)",
            (card_id, timestamp, status)
        )
        conn.commit()
    return jsonify({"result": status, "id": card_id}), 200


@app.route("/unlog", methods=["POST"])
def unlog():
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data    = request.get_json(force=True, silent=True)
    card_id = str(data.get("id", "")).strip() if data else ""
    if not card_id:
        return jsonify({"error": "Missing id"}), 400

    today     = date.today().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        user = conn.execute(
            "SELECT name FROM allowed_list WHERE isic_id=?", (card_id,)
        ).fetchone()
        name = user["name"] if user else "UNKNOWN"

        entries = conn.execute(
            "SELECT COUNT(*) AS cnt FROM logs WHERE isic_id=? AND status='ALLOWED' AND timestamp LIKE ?",
            (card_id, today + "%")
        ).fetchone()["cnt"]

        exits = conn.execute(
            "SELECT COUNT(*) AS cnt FROM exits WHERE isic_id=? AND timestamp LIKE ?",
            (card_id, today + "%")
        ).fetchone()["cnt"]

        if entries - exits <= 0:
            return jsonify({"result": "NOT_INSIDE", "id": card_id, "name": name}), 200

        conn.execute(
            "INSERT INTO exits (isic_id, timestamp) VALUES (?,?)", (card_id, timestamp)
        )
        conn.commit()

    return jsonify({"result": "UNLOGGED", "id": card_id, "name": name, "timestamp": timestamp}), 200


@app.route("/dashboard")
@admin_required
def dashboard():
    with get_db() as conn:
        logs = conn.execute("""
            SELECT l.id, l.isic_id, l.timestamp, l.status,
                   COALESCE(a.name, 'UNKNOWN') AS name
            FROM logs l
            LEFT JOIN allowed_list a ON l.isic_id = a.isic_id
            ORDER BY l.id DESC LIMIT 40
        """).fetchall()

    granted = [r for r in logs if r["status"] == "ALLOWED"]
    denied  = [r for r in logs if r["status"] == "DENIED"]
    unknown = [r for r in logs if r["status"] == "UNKNOWN"]
    return render_template("index.html", granted=granted, denied=denied, unknown=unknown)


@app.route("/manage", methods=["GET", "POST"])
@admin_required
def manage():
    if request.method == "POST":
        isic_id    = str(request.form.get("isic_id", "")).strip()
        name       = str(request.form.get("name", "")).strip()
        is_allowed = int(request.form.get("is_allowed", 1))

        if not isic_id or not name:
            flash("ERROR: isic_id and name are required.", "error")
            return redirect(url_for("manage"))

        with get_db() as conn:
            conn.execute("""
                INSERT INTO allowed_list (isic_id, name, is_allowed)
                VALUES (?,?,?)
                ON CONFLICT(isic_id) DO UPDATE SET
                    name=excluded.name, is_allowed=excluded.is_allowed
            """, (isic_id, name, is_allowed))
            conn.commit()

        flash(f"OK: User '{name}' saved.", "ok")
        return redirect(url_for("manage"))

    with get_db() as conn:
        users = conn.execute(
            "SELECT isic_id, name, is_allowed FROM allowed_list ORDER BY name"
        ).fetchall()

    authorized = [u for u in users if u["is_allowed"] == 1]
    blocked    = [u for u in users if u["is_allowed"] == 0]
    return render_template("manage.html", authorized=authorized, blocked=blocked)


@app.route("/clear")
@admin_required
def clear_logs():
    with get_db() as conn:
        conn.execute("DELETE FROM logs")
        conn.execute("DELETE FROM exits")
        conn.commit()
    flash("OK: All logs cleared.", "ok")
    return redirect(url_for("dashboard"))


@app.route("/toggle/<isic_id>")
@admin_required
def toggle(isic_id):
    with get_db() as conn:
        conn.execute("""
            UPDATE allowed_list
            SET is_allowed = CASE WHEN is_allowed=1 THEN 0 ELSE 1 END
            WHERE isic_id=?
        """, (isic_id,))
        conn.commit()
    return redirect(url_for("manage"))


@app.route("/delete/<isic_id>")
@admin_required
def delete(isic_id):
    with get_db() as conn:
        conn.execute("DELETE FROM allowed_list WHERE isic_id=?", (isic_id,))
        conn.commit()
    flash(f"OK: User '{isic_id}' deleted.", "ok")
    return redirect(url_for("manage"))


@app.route("/import", methods=["POST"])
@admin_required
def import_users():
    if not PANDAS_AVAILABLE:
        flash("ERROR: pandas not installed.", "error")
        return redirect(url_for("manage"))

    file = request.files.get("file")
    if not file or not file.filename:
        flash("ERROR: No file selected.", "error")
        return redirect(url_for("manage"))

    try:
        raw = file.read()
        if file.filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw), dtype=str)
        elif file.filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(raw), dtype=str)
        else:
            flash("ERROR: Only .csv and .xlsx supported.", "error")
            return redirect(url_for("manage"))

        df.columns = [c.strip().lower() for c in df.columns]
        if not {"isic_id", "name"}.issubset(set(df.columns)):
            flash("ERROR: File must have isic_id and name columns.", "error")
            return redirect(url_for("manage"))

        if "is_allowed" not in df.columns:
            df["is_allowed"] = "1"
        df["is_allowed"] = df["is_allowed"].fillna("1").astype(str)

        inserted = 0
        with get_db() as conn:
            for _, row in df.iterrows():
                isic_id = str(row["isic_id"]).strip()
                name    = str(row["name"]).strip()
                if not isic_id or not name:
                    continue
                conn.execute("""
                    INSERT INTO allowed_list (isic_id, name, is_allowed)
                    VALUES (?,?,?)
                    ON CONFLICT(isic_id) DO UPDATE SET
                        name=excluded.name, is_allowed=excluded.is_allowed
                """, (isic_id, name, int(row["is_allowed"])))
                inserted += 1
            conn.commit()

        flash(f"OK: Imported {inserted} user(s).", "ok")
    except Exception as e:
        flash(f"ERROR: {e}", "error")

    return redirect(url_for("manage"))


@app.route("/api/logs")
@admin_required
def api_logs():
    with get_db() as conn:
        logs = conn.execute("""
            SELECT l.id, l.isic_id, l.timestamp, l.status,
                   COALESCE(a.name, 'UNKNOWN') AS name
            FROM logs l
            LEFT JOIN allowed_list a ON l.isic_id = a.isic_id
            ORDER BY l.id DESC LIMIT 40
        """).fetchall()
    return jsonify([dict(r) for r in logs])


@app.route("/api/users")
@admin_required
def api_users():
    with get_db() as conn:
        users = conn.execute(
            "SELECT isic_id, name, is_allowed FROM allowed_list ORDER BY name"
        ).fetchall()
    return jsonify([dict(u) for u in users])


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
