#!/usr/bin/env python3
"""
Weekly Emporia Vue energy summary -> Slack.

Pulls the last 7 days of circuit-level usage from an Emporia Vue account via
pyemvue, in both kWh and $ (Emporia computes $ itself from your configured
cost schedule - no manual rate math on this end). Renders a stacked bar
chart (one bar per day, one stack segment per circuit) and posts both the
numbers and the chart image to a Slack channel.

Required environment variables:
    EMPORIA_EMAIL          Emporia account email
    EMPORIA_PASSWORD       Emporia account password
    SLACK_BOT_TOKEN        Slack bot token (xoxb-...) with chat:write and
                           files:write scopes, invited into the target channel
    SLACK_CHANNEL_ID       Slack channel ID to post into (e.g. C0123456789)

Note: for $ figures to be non-zero, the Emporia account needs a cost
schedule configured (Emporia app -> account/location settings -> utility
cost). If no cost schedule is set, Emporia's API just returns 0 for Unit.USD.
"""

import os
import sys
import datetime
from collections import defaultdict

import dateutil.tz
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from pyemvue import PyEmVue
from pyemvue.enums import Scale, Unit

DAYS = 7  # always summarize the trailing 7 days


def env(name, default=None, required=False):
    # Treat unset AND empty-string env vars as "not provided". GitHub Actions
    # sets env vars to "" (rather than omitting them) when a referenced
    # `vars.X` / `secrets.X` doesn't exist, so this matters in practice.
    val = os.environ.get(name)
    if not val:
        val = default
    if required and not val:
        print(f"ERROR: missing required environment variable {name}", file=sys.stderr)
        sys.exit(1)
    return val


def login():
    email = env("EMPORIA_EMAIL", required=True)
    password = env("EMPORIA_PASSWORD", required=True)
    vue = PyEmVue()
    ok = vue.login(username=email, password=password)
    if not ok:
        print("ERROR: Emporia login failed - check EMPORIA_EMAIL/EMPORIA_PASSWORD", file=sys.stderr)
        sys.exit(1)
    return vue


def collect_devices(vue):
    """Fetch devices and merge multi-entry devices (e.g. multi-phase panels)
    into a single VueDevice per device_gid, the same way pyemvue's own CLI
    example does it."""
    devices = vue.get_devices()
    by_gid = {}
    for device in devices:
        if device.device_gid not in by_gid:
            vue.populate_device_properties(device)
            by_gid[device.device_gid] = device
        else:
            by_gid[device.device_gid].channels += device.channels
    return by_gid


def get_week_window(devices_by_gid):
    """Use the timezone of the first device (falls back to UTC) to build a
    window of DAYS full local days ending at the most recent local
    midnight."""
    tz_name = None
    for device in devices_by_gid.values():
        if device.time_zone:
            tz_name = device.time_zone
            break
    tz = dateutil.tz.gettz(tz_name) if tz_name else dateutil.tz.tzutc()

    local_now = datetime.datetime.now(tz)
    end_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_local = end_local - datetime.timedelta(days=DAYS)

    end_utc = end_local.astimezone(dateutil.tz.tzutc()).replace(tzinfo=None)
    start_utc = start_local.astimezone(dateutil.tz.tzutc()).replace(tzinfo=None)
    return start_utc, end_utc


def fetch_usage(vue, devices_by_gid, start_utc, end_utc, unit):
    """Fetches usage for every channel in the given Emporia `unit`
    (Unit.KWH.value or Unit.USD.value).

    Returns:
        day_labels: list[str] len == DAYS
        main_by_day: list[float] len == DAYS (whole-home total, summed
                     across any "Main" channels found)
        circuit_values: dict[circuit_name] -> list[float] len == DAYS
        found_main: bool
    """
    day_labels = None
    main_by_day = [0.0] * DAYS
    circuit_values = defaultdict(lambda: [0.0] * DAYS)
    found_main = False

    for device in devices_by_gid.values():
        device_label_prefix = ""
        if len(devices_by_gid) > 1:
            device_label_prefix = f"{device.device_name or device.device_gid}: "

        for channel in device.channels:
            usage_list, chart_start = vue.get_chart_usage(
                channel,
                start_utc,
                end_utc,
                scale=Scale.DAY.value,
                unit=unit,
            )
            if not usage_list:
                continue

            # Normalize to exactly DAYS entries (API sometimes returns a
            # trailing partial bucket for "today").
            usage_list = (usage_list + [0.0] * DAYS)[:DAYS]
            usage_list = [u or 0.0 for u in usage_list]

            if day_labels is None:
                day_labels = [
                    (chart_start + datetime.timedelta(days=i)).strftime("%a %m/%d")
                    for i in range(DAYS)
                ]

            if channel.name == "Main":
                found_main = True
                for i, u in enumerate(usage_list):
                    main_by_day[i] += u
            else:
                name = f"{device_label_prefix}{channel.name}"
                for i, u in enumerate(usage_list):
                    circuit_values[name][i] += u

    if day_labels is None:
        day_labels = [
            (start_utc + datetime.timedelta(days=i)).strftime("%a %m/%d")
            for i in range(DAYS)
        ]

    return day_labels, main_by_day, dict(circuit_values), found_main


def add_unmonitored_segment(main_kwh_by_day, circuit_kwh):
    """Adds an 'Unmonitored/Other' series for the gap between the
    whole-home Main reading and the sum of monitored circuits (mirrors the
    Emporia app's "Balance"). Returns a new dict; does not mutate input."""
    chart_series = dict(circuit_kwh)

    if any(m > 0 for m in main_kwh_by_day):
        sum_circuits = [0.0] * DAYS
        for vals in circuit_kwh.values():
            for i, u in enumerate(vals):
                sum_circuits[i] += u
        balance = [max(0.0, main_kwh_by_day[i] - sum_circuits[i]) for i in range(DAYS)]
        if any(b > 0.01 for b in balance):
            chart_series["Unmonitored/Other"] = balance

    return chart_series


def render_stacked_bar_chart(day_labels, chart_series, out_path):
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)

    x = range(len(day_labels))
    bottom = [0.0] * len(day_labels)
    colors = plt.get_cmap("tab20").colors

    for idx, (name, vals) in enumerate(chart_series.items()):
        ax.bar(x, vals, bottom=bottom, label=name, color=colors[idx % len(colors)])
        bottom = [b + v for b, v in zip(bottom, vals)]

    ax.set_xticks(list(x))
    ax.set_xticklabels(day_labels, rotation=0)
    ax.set_ylabel("kWh")
    ax.set_title("Daily Energy Usage by Circuit")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1.0), fontsize=8, borderaxespad=0)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def format_summary_text(start_utc, end_utc, total_kwh, total_cost, circuit_kwh, circuit_cost):
    date_range = f"{start_utc.strftime('%b %d')} - {(end_utc - datetime.timedelta(days=1)).strftime('%b %d, %Y')}"
    lines = [f"*Weekly Energy Summary* ({date_range})", ""]
    lines.append(f"*Total usage:* {total_kwh:.1f} kWh")
    lines.append(f"*Total cost:* ${total_cost:,.2f}")

    names = sorted(circuit_kwh.keys(), key=lambda n: circuit_cost.get(n, 0.0), reverse=True)
    if names:
        lines.append("")
        lines.append("*By circuit:*")
        for name in names:
            kwh = circuit_kwh.get(name, 0.0)
            cost = circuit_cost.get(name, 0.0)
            lines.append(f"\u2022 {name}: {kwh:.1f} kWh (${cost:,.2f})")

    return "\n".join(lines)


def post_to_slack(text, image_path):
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    token = env("SLACK_BOT_TOKEN", required=True)
    channel = env("SLACK_CHANNEL_ID", required=True)
    client = WebClient(token=token)

    try:
        client.files_upload_v2(
            channel=channel,
            file=image_path,
            title="Weekly energy usage by circuit",
            initial_comment=text,
        )
    except SlackApiError as e:
        print(f"ERROR: Slack upload failed: {e.response['error']}", file=sys.stderr)
        sys.exit(1)


def main():
    vue = login()
    devices_by_gid = collect_devices(vue)
    if not devices_by_gid:
        print("ERROR: no Emporia devices found on this account", file=sys.stderr)
        sys.exit(1)

    start_utc, end_utc = get_week_window(devices_by_gid)

    day_labels, main_kwh_by_day, circuit_kwh, found_main = fetch_usage(
        vue, devices_by_gid, start_utc, end_utc, unit=Unit.KWH.value
    )
    _, main_cost_by_day, circuit_cost, _ = fetch_usage(
        vue, devices_by_gid, start_utc, end_utc, unit=Unit.USD.value
    )

    if found_main:
        total_kwh = sum(main_kwh_by_day)
        total_cost = sum(main_cost_by_day)
    else:
        total_kwh = sum(sum(vals) for vals in circuit_kwh.values())
        total_cost = sum(sum(vals) for vals in circuit_cost.values())

    circuit_kwh_totals = {name: sum(vals) for name, vals in circuit_kwh.items()}
    circuit_cost_totals = {name: sum(vals) for name, vals in circuit_cost.items()}

    text = format_summary_text(
        start_utc, end_utc, total_kwh, total_cost, circuit_kwh_totals, circuit_cost_totals
    )

    chart_series = add_unmonitored_segment(main_kwh_by_day, circuit_kwh)
    chart_path = "/tmp/weekly_energy_chart.png"
    render_stacked_bar_chart(day_labels, chart_series, chart_path)

    post_to_slack(text, chart_path)
    print("Posted weekly energy summary to Slack.")
    print(text)


if __name__ == "__main__":
    main()
