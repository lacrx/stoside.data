#!/usr/bin/env python3
"""Send a newsletter to all active subscribers on a list.

Usage:
    python send.py --list stoside --subject "September Update" --body newsletter.md

Requires: boto3, markdown
Uses the 'civic' AWS profile.
"""

import argparse
import time
import sys

import boto3
import markdown


TABLE_NAME = "newsletter-subscribers"
API_BASE_URL = "https://uz6kxsrese.execute-api.us-east-1.amazonaws.com"
FROM_EMAIL = "newsletter@stoside.org"
REGION = "us-east-1"
RATE_LIMIT = 10  # emails per second (SES sandbox: 1/sec, production: 14/sec)

session = boto3.Session(profile_name="civic", region_name=REGION)
dynamodb = session.resource("dynamodb")
ses = session.client("ses")
table = dynamodb.Table(TABLE_NAME)


def get_subscribers(list_id: str) -> list[dict]:
    items = []
    kwargs = {
        "KeyConditionExpression": "list_id = :lid",
        "FilterExpression": "#s = :active",
        "ExpressionAttributeNames": {"#s": "status"},
        "ExpressionAttributeValues": {":lid": list_id, ":active": "active"},
    }
    while True:
        resp = table.query(**kwargs)
        items.extend(resp["Items"])
        if "LastEvaluatedKey" not in resp:
            break
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def render_email(md_path: str, unsubscribe_url: str) -> str:
    with open(md_path) as f:
        body_md = f.read()

    body_html = markdown.markdown(body_md)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; padding: 1rem; color: #121212;">
{body_html}
<hr style="border: none; border-top: 1px solid #e2e2e2; margin: 2rem 0 1rem;">
<p style="font-size: 0.8rem; color: #767676;">
    <a href="{unsubscribe_url}" style="color: #767676;">Unsubscribe</a>
</p>
</body>
</html>"""


def send_newsletter(list_id: str, subject: str, md_path: str, dry_run: bool = False):
    subscribers = get_subscribers(list_id)
    if not subscribers:
        print(f"No active subscribers on list '{list_id}'.")
        return

    print(f"Found {len(subscribers)} active subscriber(s) on '{list_id}'.")

    if dry_run:
        for sub in subscribers:
            print(f"  [dry-run] {sub['email']}")
        return

    sent = 0
    failed = 0

    for sub in subscribers:
        unsubscribe_url = f"{API_BASE_URL}/unsubscribe?token={sub['unsubscribe_token']}&list={list_id}"
        html = render_email(md_path, unsubscribe_url)

        try:
            ses.send_email(
                Source=FROM_EMAIL,
                Destination={"ToAddresses": [sub["email"]]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Html": {"Data": html, "Charset": "UTF-8"}},
                },
            )
            sent += 1
            print(f"  sent: {sub['email']}")
        except Exception as e:
            failed += 1
            print(f"  FAILED: {sub['email']} -- {e}")

        time.sleep(1.0 / RATE_LIMIT)

    print(f"\nDone. Sent: {sent}, Failed: {failed}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send newsletter to subscribers")
    parser.add_argument("--list", required=True, help="List ID (e.g. stoside)")
    parser.add_argument("--subject", required=True, help="Email subject line")
    parser.add_argument("--body", required=True, help="Path to markdown file")
    parser.add_argument("--dry-run", action="store_true", help="List recipients without sending")
    args = parser.parse_args()

    send_newsletter(args.list, args.subject, args.body, dry_run=args.dry_run)
