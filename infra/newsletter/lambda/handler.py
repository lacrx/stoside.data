import json
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])
ALLOWED_LISTS = set(os.environ.get("ALLOWED_LISTS", "").split(","))
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def cors_origin(event):
    origin = (event.get("headers") or {}).get("origin", "")
    if origin in ALLOWED_ORIGINS:
        return origin
    return ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else "*"


def respond(status, body, event, content_type="application/json"):
    headers = {
        "Access-Control-Allow-Origin": cors_origin(event),
        "Content-Type": content_type,
    }
    if content_type == "application/json":
        body = json.dumps(body)
    return {"statusCode": status, "headers": headers, "body": body}


def handle_subscribe(event):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return respond(400, {"error": "Invalid JSON"}, event)

    email = (body.get("email") or "").strip().lower()
    list_id = (body.get("list_id") or "").strip().lower()

    if not email or not EMAIL_RE.match(email):
        return respond(400, {"error": "Invalid email address"}, event)

    if list_id not in ALLOWED_LISTS:
        return respond(400, {"error": "Invalid list"}, event)

    token = str(uuid.uuid4())

    table.put_item(
        Item={
            "list_id": list_id,
            "email": email,
            "unsubscribe_token": token,
            "status": "active",
            "subscribed_at": datetime.now(timezone.utc).isoformat(),
        },
        ConditionExpression="attribute_not_exists(email) OR #s = :unsub",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":unsub": "unsubscribed"},
    )

    return respond(200, {"message": "Subscribed"}, event)


def handle_unsubscribe(event):
    params = event.get("queryStringParameters") or {}
    token = params.get("token", "")
    list_id = params.get("list", "")

    if not token:
        return respond(400, {"error": "Missing token"}, event)

    result = table.query(
        IndexName="token-index",
        KeyConditionExpression="unsubscribe_token = :t",
        ExpressionAttributeValues={":t": token},
    )

    items = result.get("Items", [])
    if not items:
        return respond(
            404,
            "<html><body><p>Link not found or already used.</p></body></html>",
            event,
            content_type="text/html",
        )

    item = items[0]
    table.update_item(
        Key={"list_id": item["list_id"], "email": item["email"]},
        UpdateExpression="SET #s = :val",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":val": "unsubscribed"},
    )

    return respond(
        200,
        "<html><body><p>You have been unsubscribed. You will no longer receive emails from this list.</p></body></html>",
        event,
        content_type="text/html",
    )


def lambda_handler(event, context):
    path = event.get("rawPath", "")
    method = event.get("requestContext", {}).get("http", {}).get("method", "")

    if method == "POST" and path == "/subscribe":
        try:
            return handle_subscribe(event)
        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            return respond(200, {"message": "Subscribed"}, event)
        except Exception as e:
            print(f"Subscribe error: {e}")
            return respond(500, {"error": "Internal error"}, event)

    if method == "GET" and path == "/unsubscribe":
        try:
            return handle_unsubscribe(event)
        except Exception as e:
            print(f"Unsubscribe error: {e}")
            return respond(500, {"error": "Internal error"}, event)

    return respond(404, {"error": "Not found"}, event)
