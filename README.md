# Home Automations -> Slack

This repo has two independent GitHub Actions automations:

1. **Weekly Energy Summary** — Emporia Vue usage/cost report, every Sunday
2. **Rain Reminder** — a heads-up if rain is forecasted tomorrow, every evening

They share nothing except the `requirements.txt` file — each has its own
script and its own workflow, and you can enable either one independently.

---

# 1. Weekly Energy Summary (Emporia Vue -> Slack)

Every Sunday at 5:00pm Pacific time (or on demand), this GitHub Action:

1. Logs into your Emporia Vue account with [`pyemvue`](https://github.com/magico13/PyEmVue)
2. Pulls the last 7 days of usage for every circuit, in both kWh and $
   (the $ figures come straight from Emporia's API, using whatever cost
   schedule you've set up in the Emporia app — no manual rate math here)
3. Renders a stacked bar chart (one bar per day, one color per circuit)
4. Posts the numbers + chart image to a Slack channel

## Files

- `weekly_energy_summary.py` — the script that does all of the above
- `requirements.txt` — Python dependencies
- `.github/workflows/weekly-energy-summary.yml` — the schedule + CI job

## What gets posted to Slack

Two messages, in order:
1. A short greeting: "Here is your energy summary for the past week! Love, Sam"
2. The chart image, with the numbers (total kWh, total cost, and a per-circuit
   breakdown) attached as the file's comment

## 1. Set up a cost schedule in Emporia (for the $ figures)

The $ numbers come from Emporia's own `Unit.USD` usage endpoint. If you
haven't already, set your utility rate in the Emporia app under your
account/location settings (cost per kWh, or a full rate schedule if your
utility supports it). If no cost schedule is configured, Emporia's API just
returns $0.

## 2. Create a Slack app + bot token

Image uploads require a **bot token**, not an incoming webhook.

1. Go to <https://api.slack.com/apps> → **Create New App** → From scratch
2. Under **OAuth & Permissions**, add these Bot Token Scopes:
   - `chat:write`
   - `files:write`
3. Click **Install to Workspace**, then copy the **Bot User OAuth Token** (starts with `xoxb-`)
4. In Slack, invite the bot to the channel you want the summary posted to:
   `/invite @your-bot-name`
5. Get the channel ID: open the channel in Slack → click the channel name →
   scroll down in the details panel → copy the Channel ID (starts with `C`).

## 3. Add repo secrets

**Settings → Secrets and variables → Actions → Secrets** (repository secrets,
not environment secrets — no need for the extra approval-gate machinery here):

| Name | Value |
|---|---|
| `EMPORIA_EMAIL` | Your Emporia account email |
| `EMPORIA_PASSWORD` | Your Emporia account password |
| `SLACK_BOT_TOKEN` | The `xoxb-...` token from step 2 |
| `SLACK_CHANNEL_ID` | The channel ID from step 2 |

## 4. Enable the workflow

Commit this repo (or these files into an existing repo) and push. The
workflow is scheduled to run every Sunday at 5:00pm Pacific time. You can
also trigger it immediately from the **Actions** tab → "Weekly Energy Summary"
→ **Run workflow**, which is the easiest way to test your secrets before
waiting for the schedule (manual runs always execute immediately, regardless
of time).

**Why the workflow file has two `cron` lines:** GitHub Actions schedules are
always in UTC, and Pacific time shifts by an hour between PST and PDT
depending on daylight saving. To land on 5:00pm Pacific year-round, the
workflow schedules for both possible UTC times (one for PDT, one for PST).
A check step at the start of the job looks at which of the two cron entries
actually triggered this run (via GitHub's `github.event.schedule`) and
compares that against whether Pacific time is currently in daylight saving
or not, running only if they match. This is deliberately based on the
*season*, not the *current clock hour* — GitHub Actions doesn't guarantee
scheduled runs fire exactly on time (delays of minutes to hours are normal
under load), so a check based on "is it currently 5pm" would incorrectly
skip a run that's simply running late. Manual runs (`workflow_dispatch`)
skip this check entirely and always run.

If you want a different day/time, edit both `cron` lines in
`.github/workflows/weekly-energy-summary.yml` (they should be 1 hour apart —
UTC in winter, UTC-1 in summer, relative to your target Pacific time), and
update the matching `PDT_CRON` / `PST_CRON` values inside the "Determine
whether to run" step in the same file so they stay in sync with the new
`cron` lines.

## Notes on how usage is categorized

- The 7-day window and all chart/summary dates are always in **Pacific
  time**, computed directly rather than relying on whatever timezone (if
  any) is configured on your Emporia device.
- Emporia's "Main" channel represents your whole-home total. The script
  sums this separately from individual circuits, so it isn't double-counted
  in the stacked chart. Emporia doesn't always populate that channel's
  `name` field as the string `"Main"` — on some accounts it's blank or
  null — so detection also checks the channel's `type` field, which is
  more reliable. This total feeds the *Total usage* / *Total cost* lines
  at the top of the message rather than appearing as its own line in "By
  circuit" or as its own bar segment.
- The chart shows only actual monitored circuits — no "Other"/"Unmonitored"
  catch-all segment. If your circuits don't fully add up to the whole-home
  total, that gap simply isn't shown in the chart (it's still reflected in
  the *Total usage*/*Total cost* lines at the top, which come from Main).
- The script doesn't group or truncate circuits — every monitored circuit
  gets its own segment in the chart and its own line in the Slack summary.

## Running locally

```bash
pip install -r requirements.txt
export EMPORIA_EMAIL=you@example.com
export EMPORIA_PASSWORD=yourpassword
export SLACK_BOT_TOKEN=xoxb-...
export SLACK_CHANNEL_ID=C0123456789
python weekly_energy_summary.py
```

---

# 2. Rain Reminder (Open-Meteo -> Slack)

Every evening at 6:00pm Pacific time (or on demand), this GitHub Action:

1. Checks tomorrow's max daily chance of rain for Oakland, CA via
   [Open-Meteo](https://open-meteo.com/) (free, no API key or account needed)
2. Posts a reminder to Slack **only if** that chance is at least 30% — dry
   forecasts produce no message at all

The message looks like:

> 🌧️ There is a 30% chance rain on the forecast tomorrow for Oakland, CA
> tomorrow. You might want to bring in the couch cushions!

## Files

- `rain_reminder.py` — the script that does all of the above
- `.github/workflows/rain-reminder.yml` — the schedule + CI job
- Uses the same `requirements.txt` as the energy summary (only `requests`,
  `python-dateutil`, and `slack_sdk` are actually needed for this one)

## Configuration

Location and threshold are hardcoded at the top of `rain_reminder.py`
(no secrets needed for the weather data itself, since Open-Meteo is free
and keyless):

```python
LOCATION_NAME = "Oakland, CA"
LATITUDE = 37.8044
LONGITUDE = -122.2711
RAIN_THRESHOLD_PERCENT = 30
```

Change these directly in the file if you want a different city or a
different sensitivity (e.g. lower the threshold to get warned about even a
small chance of rain, or raise it to only hear about likely rain).

## 1. Add a Slack channel + secret

This can use the **same Slack bot** you already created for the energy
summary — bots can post to multiple channels, they just need to be invited
to each one individually.

1. Create (or pick) the Slack channel you want rain reminders posted to
2. Invite the bot: `/invite @your-bot-name` in that channel
3. Get that channel's ID the same way as before (click the channel name →
   scroll down in the details panel → copy the Channel ID)
4. Add a new repo secret: `RAIN_SLACK_CHANNEL_ID` set to that channel ID

You do **not** need a new `SLACK_BOT_TOKEN` — the existing one already has
the `chat:write` scope this script needs, since it only sends plain text
messages (no file/image upload here).

## 2. Enable the workflow

Same deal as the energy summary: push the files, then either wait for the
6:00pm Pacific schedule or trigger it manually from the **Actions** tab →
"Rain Reminder" → **Run workflow** to test it immediately. A manual run will
actually post to Slack if tomorrow's forecast clears the 30% threshold, or
just print "Below threshold - not sending a reminder." if it doesn't — that
second case is normal and not a failure.

The same two-`cron`-lines DST handling from the energy summary applies here
too (see that section above for why) — just for 18:00 (6:00pm) instead of
17:00.