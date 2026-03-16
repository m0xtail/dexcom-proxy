import os
import requests
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DEXCOM_SERVER = os.environ.get("DEXCOM_SERVER", "share2.dexcom.com")
USERNAME = os.environ.get("DEXCOM_USERNAME")
PASSWORD = os.environ.get("DEXCOM_PASSWORD")
APPLICATION_ID = "d89443d2-327c-4a6f-89e5-496bbb0317db"

TREND_ARROWS = {
    "None": "?",
    "DoubleUp": "↑↑",
    "SingleUp": "↑",
    "FortyFiveUp": "↗",
    "Flat": "→",
    "FortyFiveDown": "↘",
    "SingleDown": "↓",
    "DoubleDown": "↓↓",
    "NotComputable": "?",
    "RateOutOfRange": "?",
}

def get_session_id():
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/General/LoginPublisherAccountByName"
    payload = {
        "accountName": USERNAME,
        "password": PASSWORD,
        "applicationId": APPLICATION_ID,
    }
    r = requests.post(url, json=payload, timeout=10)
    print(f"LOGIN status={r.status_code} body={r.text[:500]}", flush=True)
    r.raise_for_status()
    return r.json()

def get_latest_glucose(session_id):
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues"
    params = {"sessionId": session_id, "minutes": 10, "maxCount": 1}
    r = requests.post(url, json=params, timeout=10)
    print(f"READINGS status={r.status_code} body={r.text[:500]}", flush=True)
    r.raise_for_status()
    readings = r.json()
    if not readings:
        return None
    reading = readings[0]
    return {
        "value": reading["Value"],
        "trend": TREND_ARROWS.get(reading["Trend"], "?"),
        "trend_name": reading["Trend"],
    }

@app.route("/bg")
def bg():
    if not USERNAME or not PASSWORD:
        return jsonify({"error": "Dexcom credentials not configured"}), 500
    try:
        session_id = get_session_id()
        data = get_latest_glucose(session_id)
        if not data:
            return jsonify({"error": "No recent readings"}), 404
        return jsonify(data)
    except requests.HTTPError as e:
        return jsonify({"error": f"Dexcom HTTP error: {e.response.status_code}", "body": e.response.text[:300]}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
