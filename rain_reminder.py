#!/usr/bin/env python3
"""
Evening rain reminder -> Slack.

Runs daily at 6:00pm Pacific (see the GitHub Actions workflow for how DST is
handled). Checks tomorrow's max daily precipitation probability for a fixed
location via Open-Meteo (free, no API key required) and posts a reminder to
Slack ONLY if that probability meets RAIN_THRESHOLD_PERCENT. No message is
sent on dry days.

Required environment variables:
    SLACK_BOT_TOKEN         Slack bot token (xoxb-...) with chat:write scope,
                             invited into the target channel
    RAIN_SLACK_CHANNEL_ID   Slack channel ID to post into (e.g. C0123456789)
"""

import os
import sys
import datetime

import requests
import dateutil.tz

LOCATION_NAME = "Oakland, CA"
LATITUDE = 37.8044
LONGITUDE = -122.2711
PACIFIC_TZ = dateutil.tz.gettz("America/Los_Angeles")

# Only send a reminder if tomorrow's max chance of rain is at least this.
# Any lower and it stays quiet - adjust to taste.
RAIN_THRESHOLD_PERCENT = 10


def env(name, default=None, required=False):
    # Treat unset AND empty-string env vars as "not provided". GitHub Actions
    # sets env vars to "" (rather than omitting them) when a referenced
    # `secrets.X` doesn't exist, so this matters in practice.
    val = os.environ.get(name)
    if not val:
        val = default
    if required and not val:
        print(f"ERROR: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return val


def get_tomorrow_rain_chance():
    """Returns (tomorrow_date, precipitation_probability_percent) for
    LOCATION_NAME using Open-Meteo's free forecast API."""
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "precipitation_probability_max",
        "timezone": "America/Los_Angeles",
        "forecast_days": 2,
    }
    resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    dates = data["daily"]["time"]
    probs = data["daily"]["precipitation_probability_max"]

    tomorrow_local = datetime.datetime.now(PACIFIC_TZ).date() + datetime.timedelta(days=1)
    tomorrow_str = tomorrow_local.isoformat()

    if tomorrow_str in dates:
        idx = dates.index(tomorrow_str)
    else:
        # Shouldn't normally happen with forecast_days=2, but fall back to
        # the second entry (index 1 = "tomorrow" relative to today) rather
        # than crashing outright.
        idx = 1 if len(dates) > 1 else 0

    return tomorrow_local, probs[idx]


def post_to_slack(message):
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    token = env("SLACK_BOT_TOKEN", required=True)
    channel = env("RAIN_SLACK_CHANNEL_ID", required=True)
    client = WebClient(token=token)

    try:
        client.chat_postMessage(channel=channel, text=message)
    except SlackApiError as e:
        print(f"ERROR: Slack message failed: {e.response['error']}", file=sys.stderr)
        sys.exit(1)


def main():
    print("Checking tomorrow's rain forecast...")
    tomorrow, chance = get_tomorrow_rain_chance()
    print(f"Tomorrow ({tomorrow}): {chance}% max chance of rain")

    if chance < RAIN_THRESHOLD_PERCENT:
        print(f"Below threshold ({RAIN_THRESHOLD_PERCENT}%) - not sending a reminder.")
        return

    message = (
        f"\U0001F327\uFE0F There is a {chance:.0f}% chance rain on the forecast "
        f"tomorrow for {LOCATION_NAME}. You might want to bring in the couch cushions!"
    )
    post_to_slack(message)
    print("Posted rain reminder to Slack.")
    print(message)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("ERROR: unhandled exception during run:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
