# prometheus_webhook.py
from flask import Flask, request, jsonify
import requests
import datetime
import os
import boto3
import json
from openai import OpenAI
import time
import random
from openai import OpenAI, OpenAIError, RateLimitError, APIConnectionError, APIStatusError, Timeout


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


# Loki and OpenAI config
LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100/loki/api/v1/query_range")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
SNS_TOPIC_ARN = os.getenv("SNS_ARN", "arn:aws:sns:us-east-1:109798190983:doggy-alerts")
LB_HOST = os.getenv("LOAD_BALANCER_URL")

app.logger.info(LOKI_URL)
app.logger.info(OPENAI_API_URL)
app.logger.info(SNS_TOPIC_ARN)
app.logger.info(LB_HOST)


def get_openai_key():
    app.logger.info("inside get openAI key")
    if not hasattr(get_openai_key, "cached_key"):
        app.logger.info("Fetching OpenAI secret from Secrets Manager")
        get_openai_key.cached_key = get_secret()
    print("back inside get_openai_key() and printing final return value")
    print(get_openai_key.cached_key)
    return get_openai_key.cached_key

def get_secret():
    app.logger.info("inside get secret")
    secret_name = "openai-key"
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
    app.logger.info("openai secret key")
    app.logger.info(secret_dict)

    return secret_dict['key']

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

    client = OpenAI(
        api_key=get_openai_key()
    )

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini", 
            store=True,
            messages=[
                {"role": "system", "content": "You are an expert in debugging Kubernetes applications."},
                {"role": "user", "content": question}
            ]
        )
        return completion.choices[0].message.content

    except RateLimitError as e:
        wait = 2 + random.uniform(0, 1)
        app.logger.warning(f"Rate limit hit. Retrying in {wait:.2f}s...")
        time.sleep(wait)
        return {"error": "Rate limit exceeded, try again later."}

    except Timeout as e:
        app.logger.warning("Request to OpenAI timed out.")
        return {"error": "Timeout occurred while contacting OpenAI."}

    except APIConnectionError as e:
        app.logger.error(f"API connection error: {e}")
        return {"error": "API connection error"}

    except APIStatusError as e:
        app.logger.error(f"API returned non-200 status: {e.status_code}")
        return {"error": f"API error: status {e.status_code}"}

    except OpenAIError as e:
        app.logger.error(f"Unhandled OpenAI error: {e}")
        return {"error": "Unhandled OpenAI error"}

    except Exception as e:
        app.logger.error(f"Unexpected error: {e}")
        return {"error": "Unexpected error occurred"}

    return {"error": "Failed to get a response from OpenAI"}


def notify_user(subject, message):
    app.logger.info("inside notify user")
    sns = boto3.client("sns", region_name="us-east-1")
    try:
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        app.logger.info(f"Successfully published to SNS: {response}")
    except ClientError as e:
        app.logger.info(f"Failed to publish to SNS: {e}")

@app.route("/webhook", methods=["POST"])
def handle_alert():
    try:
        app.logger.info("hook running")
        alert_data = request.json
        for alert in alert_data.get("alerts", []):
            app.logger.info("just recieved alert")
            app.logger.info(alert)
            starts_at = alert.get("startsAt")
            labels = alert.get("labels", {})
            namespace = labels.get("namespace", "default")
            pod = labels.get("pod", "")
            severity = labels.get("severity", "unknown")
            alertname = labels.get("alertname", "Alert")

            # Convert times
            start_dt = datetime.datetime.strptime(starts_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)
            end_dt = start_dt + datetime.timedelta(minutes=10)
            start_dt = start_dt - datetime.timedelta(minutes=10)  # pull a bit earlier too

            
            start_ns = int(start_dt.timestamp() * 1e9)
            end_ns = int(end_dt.timestamp() * 1e9)

            # Loki query
            app.logger.info(f"namespace={namespace}, pod={pod}")
            log_query = f'{{namespace="{namespace}", pod="{pod}"}}'
            app.logger.info("loki query")
            app.logger.info(log_query)
            app.logger.info(start_ns)
            app.logger.info(end_ns)
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
            app.logger.info(f"AI Response:\n{ai_response}")

            if isinstance(ai_response, str) and not ai_response.startswith("Error:"):
                print("inside succesful if block about to notify user")
                notify_user(alertname, ai_response)
                return jsonify({"status": "recieved"}), 200
            else:
                # ai_response is an error string or failure notice
                error_msg = str(ai_response)
                return jsonify({"error": error_msg}), 500
        
    except Exception as e:
        app.logger.exception("Unhandled exception while processing alert")
        return jsonify({"error": str(e)}), 500
        

    

if __name__ == "__main__":
    notify_user("Host Url", LB_HOST)
    app.run(host="0.0.0.0", port=5000)