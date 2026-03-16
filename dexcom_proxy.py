import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__)
CORS(app)

DEXCOM_SERVER = os.environ.get("DEXCOM_SERVER", "share2.dexcom.com")
USERNAME = os.environ.get("DEXCOM_USERNAME")
PASSWORD = os.environ.get("DEXCOM_PASSWORD")
APPLICATION_ID = "d89443d2-327c-4a6f-89e5-496bbb0317db"
DATABASE_URL = os.environ.get("DATABASE_URL")

TREND_ARROWS = {
    "None": "?", "DoubleUp": "↑↑", "SingleUp": "↑", "FortyFiveUp": "↗",
    "Flat": "→", "FortyFiveDown": "↘", "SingleDown": "↓", "DoubleDown": "↓↓",
    "NotComputable": "?", "RateOutOfRange": "?",
}

def get_db():
    url = DATABASE_URL
    if url and url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg2.connect(url, cursor_factory=RealDictCursor)

def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id BIGINT PRIMARY KEY,
                dose REAL NOT NULL,
                bg REAL,
                note TEXT,
                ts TIMESTAMPTZ NOT NULL
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("DB initialized", flush=True)
    except Exception as e:
        print(f"DB init error: {e}", flush=True)

# ── Dexcom ────────────────────────────────────────────────────────────────────

def get_account_id():
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/General/AuthenticatePublisherAccount"
    r = requests.post(url, json={"accountName": USERNAME, "password": PASSWORD, "applicationId": APPLICATION_ID}, timeout=10)
    print(f"ACCOUNT_ID status={r.status_code} body={r.text[:300]}", flush=True)
    r.raise_for_status()
    return r.json()

def get_session_id_by_account_id(account_id):
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/General/LoginPublisherAccountById"
    r = requests.post(url, json={"accountId": account_id, "password": PASSWORD, "applicationId": APPLICATION_ID}, timeout=10)
    print(f"SESSION status={r.status_code} body={r.text[:300]}", flush=True)
    r.raise_for_status()
    return r.json()

def get_latest_glucose(session_id):
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues"
    r = requests.post(url, json={"sessionId": session_id, "minutes": 10, "maxCount": 1}, timeout=10)
    r.raise_for_status()
    readings = r.json()
    if not readings:
        return None
    reading = readings[0]
    return {"value": reading["Value"], "trend": TREND_ARROWS.get(reading["Trend"], "?"), "trend_name": reading["Trend"]}

@app.route("/bg")
def bg():
    if not USERNAME or not PASSWORD:
        return jsonify({"error": "Dexcom credentials not configured"}), 500
    try:
        account_id = get_account_id()
        session_id = get_session_id_by_account_id(account_id)
        if not session_id or session_id == "00000000-0000-0000-0000-000000000000":
            return jsonify({"error": "Invalid credentials"}), 401
        data = get_latest_glucose(session_id)
        if not data:
            return jsonify({"error": "No recent readings"}), 404
        return jsonify(data)
    except requests.HTTPError as e:
        return jsonify({"error": f"Dexcom HTTP error: {e.response.status_code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Entries ───────────────────────────────────────────────────────────────────

@app.route("/entries", methods=["GET"])
def get_entries():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM entries ORDER BY ts DESC LIMIT 200")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify([{
            "id": r["id"],
            "dose": r["dose"],
            "bg": r["bg"],
            "note": r["note"],
            "ts": r["ts"].isoformat()
        } for r in rows])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/entries", methods=["POST"])
def add_entry():
    try:
        data = request.get_json()
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO entries (id, dose, bg, note, ts) VALUES (%s, %s, %s, %s, %s)",
            (data["id"], data["dose"], data.get("bg"), data.get("note", ""), data["ts"])
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/entries/<int:entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM entries WHERE id = %s", (entry_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"ok": True})

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
