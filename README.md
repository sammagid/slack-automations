# Weekly Energy Summary (Emporia Vue -> Slack)

Every Monday (or on demand), this GitHub Action:

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
workflow runs automatically every Monday at 13:00 UTC. You can also trigger
it immediately from the **Actions** tab → "Weekly Energy Summary" → **Run workflow**,
which is the easiest way to test your secrets before waiting for the schedule.

Adjust the cron schedule in `.github/workflows/weekly-energy-summary.yml` if
you want a different day/time — the schedule is in UTC.

## Notes on how usage is categorized

- Emporia's "Main" channel represents your whole-home total. The script
  sums this separately from individual circuits, so it isn't double-counted
  in the stacked chart.
- If the sum of your monitored circuits is less than the Main total, the
  difference is shown as an **"Unmonitored/Other"** segment in the chart,
  mirroring the "Balance" figure in the Emporia app.
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
