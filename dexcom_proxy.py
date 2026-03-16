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
    # Try newer endpoint first (G7), fall back to classic
    for endpoint in [
        "LoginPublisherAccountById",
        "LoginPublisherAccountByName",
    ]:
        url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/General/{endpoint}"
        payload = {
            "accountName": USERNAME,
            "password": PASSWORD,
            "applicationId": APPLICATION_ID,
        }
        r = requests.post(url, json=payload, timeout=10)
        print(f"LOGIN {endpoint} status={r.status_code} body={r.text[:500]}", flush=True)
        if r.status_code == 200:
            session = r.json()
            if session and session != "00000000-0000-0000-0000-000000000000":
                return session
    raise Exception("Could not authenticate with Dexcom Share — check credentials and that Share/Follow is enabled in the G7 app")

def get_account_id():
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/General/AuthenticatePublisherAccount"
    payload = {
        "accountName": USERNAME,
        "password": PASSWORD,
        "applicationId": APPLICATION_ID,
    }
    r = requests.post(url, json=payload, timeout=10)
    print(f"ACCOUNT_ID status={r.status_code} body={r.text[:500]}", flush=True)
    r.raise_for_status()
    return r.json()

def get_session_id_by_account_id(account_id):
    url = f"https://{DEXCOM_SERVER}/ShareWebServices/Services/General/LoginPublisherAccountById"
    payload = {
        "accountId": account_id,
        "password": PASSWORD,
        "applicationId": APPLICATION_ID,
    }
    r = requests.post(url, json=payload, timeout=10)
    print(f"SESSION_BY_ID status={r.status_code} body={r.text[:500]}", flush=True)
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
        # Two-step auth for G7: get account ID first, then session
        try:
            account_id = get_account_id()
            session_id = get_session_id_by_account_id(account_id)
        except Exception as e:
            print(f"Two-step auth failed: {e}, trying single-step", flush=True)
            session_id = get_session_id()

        if not session_id or session_id == "00000000-0000-0000-0000-000000000000":
            return jsonify({"error": "Invalid credentials or Share not enabled"}), 401

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
