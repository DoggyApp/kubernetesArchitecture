# prometheus_webhook.py
from flask import Flask, request, jsonify
import requests
import datetime
import os
import boto3
import json
from botocore.exceptions import ClientError

app = Flask(__name__)



def get_secret():

    secret_name = "openai-secret-key"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    # The secret string is a JSON-formatted string
    secret_string = get_secret_value_response['SecretString']
    secret_dict = json.loads(secret_string)

    return secret_dict['openai-secret-key']
    
# Loki and OpenAI config
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100/loki/api/v1/query_range")
OPENAI_API_KEY = get_secret()
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:109798190983:doggy-alerts:780078be-0b8b-47e8-8c4a-9778a06d5bb2"

def query_loki(start, end, query):
    params = {
        "start": start,
        "end": end,
        "query": query
    }
    try: 
        response = requests.get(LOKI_URL, params=params)
        return response.json()

    except requests.RequestException as e:
        print(f"Error querying Loki: {e}")
        return {}

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
    try: 
        response = requests.post(OPENAI_API_URL, headers=headers, json=data)
        return response.json()
    except requests.RequestException as e:
        print(f"Error calling OpenAI: {e}")
        return {"choices": [{"message": {"content": "Error querying OpenAI"}}]}


def notify_user(subject, message):
    sns = boto3.client("sns", region_name="us-east-1")
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject,
        Message=message
    )
    except ClientError as e:
        print(f"Failed to publish to SNS: {e}")

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
        start_dt = datetime.datetime.strptime(starts_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
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

        notify_user(alertname, answer)

    return jsonify({"status": "received"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)