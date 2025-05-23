# prometheus_webhook.py
from flask import Flask, request, jsonify
import requests
import datetime
import os

app = Flask(__name__)

# Loki and OpenAI config
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100/loki/api/v1/query_range")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

def query_loki(start, end, query):
    params = {
        "start": start,
        "end": end,
        "query": query
    }
    response = requests.get(LOKI_URL, params=params)
    return response.json()

def ask_openai(question):
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are an expert in debugging Kubernetes applications."},
            {"role": "user", "content": question}
        ]
    }
    response = requests.post(OPENAI_API_URL, headers=headers, json=data)
    return response.json()

@app.route("/webhook", methods=["POST"])
def handle_alert():
    alert_data = request.json
    for alert in alert_data.get("alerts", []):
        starts_at = alert.get("startsAt")
        labels = alert.get("labels", {})
        namespace = labels.get("namespace", "default")
        pod = labels.get("pod", "")
        severity = labels.get("severity", "unknown")
        alertname = labels.get("alertname", "Alert")

        # Convert times
        start_dt = datetime.datetime.strptime(starts_at, "%Y-%m-%dT%H:%M:%SZ")
        end_dt = start_dt + datetime.timedelta(minutes=5)
        start_ns = int(start_dt.timestamp() * 1e9)
        end_ns = int(end_dt.timestamp() * 1e9)

        # Loki query
        log_query = f'{{namespace="{namespace}", pod="{pod}"}}'
        loki_response = query_loki(start_ns, end_ns, log_query)

        log_lines = []
        for stream in loki_response.get("data", {}).get("result", []):
            for entry in stream.get("values", []):
                log_lines.append(entry[1])

        combined_logs = "\n".join(log_lines[:20])
        question = f"The following alert was triggered: {alertname} (severity: {severity}) on pod {pod}.\nLogs:\n{combined_logs}\n\nCan you help analyze what happened?"

        ai_response = ask_openai(question)
        answer = ai_response["choices"][0]["message"]["content"]

        print(f"AI Response:\n{answer}")

    return jsonify({"status": "received"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)