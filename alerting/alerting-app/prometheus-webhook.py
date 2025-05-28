# prometheus_webhook.py
from flask import Flask, request, jsonify
import requests
import datetime
import os
import boto3
import json

from botocore.exceptions import ClientError

app = Flask(__name__)

# good practice to set debug to false explicitely 
app.config["DEBUG"] = False

# Connect Flask's logger to Gunicorn's log output
import logging
import sys
gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

def get_openai_key():
    if not hasattr(get_openai_key, "cached_key"):
        app.logger.info("Fetching OpenAI secret from Secrets Manager...")
        get_openai_key.cached_key = get_secret()
    return get_openai_key.cached_key

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
        app.logger.error(f"Error fetching secret: {e}")
        raise e

    # The secret string is a JSON-formatted string
    secret_string = get_secret_value_response['SecretString']
    secret_dict = json.loads(secret_string)

    return secret_dict['openai-secret-key']
    
# Loki and OpenAI config
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100/loki/api/v1/query_range")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:109798190983:doggy-alerts:780078be-0b8b-47e8-8c4a-9778a06d5bb2"

app.logger.info(LOKI_URL)
app.logger.info(OPENAI_API_URL)
app.logger.info(SNS_TOPIC_ARN)

def query_loki(start, end, query):
    app.logger.info("inside query loki")
    params = {
        "start": start,
        "end": end,
        "query": query
    }
    try: 
        response = requests.get(LOKI_URL, params=params)
        return response.json()

    except requests.RequestException as e:
        app.logger.info(f"Error querying Loki: {e}")
        return {}

def ask_openai(question):
    app.logger.info("inside ask open ai")
    headers = {
        "Authorization": f"Bearer {get_openai_key()}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are an expert in debugging Kubernetes applications."},
            {"role": "user", "content": question}
        ]
    }
    try: 
        response = requests.post(OPENAI_API_URL, headers=headers, json=data)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        app.logger.info(f"Error calling OpenAI: {e}")
        return {"choices": [{"message": {"content": "Error querying OpenAI"}}]}


def notify_user(subject, message):
    app.logger.info("inside notify user")
    sns = boto3.client("sns", region_name="us-east-1")
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        app.logger.info(f"Successfully published to SNS: {response}")
    except ClientError as e:
        app.logger.info(f"Failed to publish to SNS: {e}")
        # traceback.print_exc()

@app.route("/webhook", methods=["POST"])
def handle_alert():
    try:
        app.logger.info("hook running")
        alert_data = request.json
        for alert in alert_data.get("alerts", []):
            app.logger.info("just recieved alert")
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
            app.logger.info(f"namespace={namespace}, pod={pod}")
            log_query = f'{{namespace="{namespace}", pod="{pod}"}}'
            app.logger.info("loki query")
            app.logger.info(log_query)
            loki_response = query_loki(start_ns, end_ns, log_query)
            app.logger.info("loki response")
            app.logger.info(loki_response)

            log_lines = []
            for stream in loki_response.get("data", {}).get("result", []):
                for entry in stream.get("values", []):
                    log_lines.append(entry[1])

            combined_logs = "\n".join(log_lines[:20])
            app.logger.info("combined logs")
            app.logger.info(f"Using first {len(log_lines[:20])} log lines for OpenAI query.")
            app.logger.info(combined_logs)
            question = f"The following alert was triggered: {alertname} (severity: {severity}) on pod {pod}.\nLogs:\n{combined_logs}\n\nCan you help analyze what happened?"
            app.logger.info(question)
            ai_response = ask_openai(question)

            if "choices" in ai_response:
                answer = ai_response["choices"][0]["message"]["content"]
                app.logger.info(f"AI Response:\n{answer}")
                notify_user(alertname, answer)
                return jsonify({"status": "received"}), 200
            else:
                error_msg = ai_response.get("error", {}).get("message", "Unknown error from OpenAI")
                return jsonify({"error": error_msg}), 500
        
    except Exception as e:
        app.logger.exception("Unhandled exception while processing alert")
        return jsonify({"error": str(e)}), 500
        

    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)