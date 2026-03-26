---
name: team-metrics
description: >
  Generates a weekly team metrics report as an HTML file for an Engineering Manager.
  Collects data from Google Calendar, Jira, Slack, GitHub REST API, and Confluence
  for each requested team member over a specified date range. HTML is the primary
  output — open in browser, export to PDF. Word doc generation is disabled for this user.

  USE THIS SKILL whenever the user asks for any of the following:
  - "pull metrics for [names] for [dates]"
  - "generate the weekly team report"
  - "run metrics for the team / my engineers / my squad"
  - "update the metrics doc for this week"
  - "team metrics for [date range]"
  - "summarize the last N weeks / this sprint / this month"
  - "how has the team been doing", "trend report for [period]"
  - Any request to track or report on team activity across a date range, even if
    the word "metrics" isn't used.
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# Team Metrics Skill

Automates the collection and formatting of weekly engineering team metrics into a
polished HTML report. **Word doc generation is disabled — never run `generate_report.js`.**

---

## Plugins required

All four plugins must be installed and authenticated before running metrics. If any are
missing, run the corresponding setup steps below before collecting data.

| Plugin | Purpose | Install command |
|--------|---------|-----------------|
| **`google-workspace@ibotta`** | Google Calendar (meetings, OOO) + Google Drive sync | `claude mcp add google-workspace@ibotta` |
| **`atlassian-api@ibotta`** | Jira tickets + Confluence pages (direct API, no MCP) | `claude mcp add atlassian-api@ibotta` |
| **Slack MCP** | Slack message counts per channel | Configure in Claude settings |
| **`gh` CLI** | GitHub PRs, reviews, commits (primary data source) | `brew install gh && gh auth login` |

---

## Setup (one-time per machine)

### 1. Copy skill scripts to your metrics folder

Place all of the following files into your local metrics folder (e.g. `~/Documents/Team Metrics/`):

```
fetch_github_metrics.js       ← GitHub PRs via gh CLI (primary) or canvas (fallback)
fetch_atlassian_metrics.py    ← Jira tickets + Confluence pages via direct API
parse_standup.js              ← Obsidian daily standup notes parser
generate_html_report.js       ← Weekly HTML report with charts
generate_report.js            ← Monthly Word doc (appends each week)
generate_summary_report.js    ← Multi-week trend/summary report
team_config_template.json     ← Copy → team_config.json and fill in
```

### 2. Install Node.js dependencies (once)

```bash
npm install docx --prefix ~/Documents/Team\ Metrics/
```

Only needed once. Enables `.docx` monthly rollup output.

### 3. Authenticate the GitHub CLI (one-time)

```bash
gh auth login
```

Select `github.com`, choose HTTPS, authenticate via browser. This gives the skill direct access
to `github.com/Ibotta` for accurate PR data. Only needed once per machine.

```bash
gh auth status   # verify it worked
```

> If `gh` is not installed: `brew install gh`

### 4. Create your team_config.json

```bash
cp ~/Documents/Team\ Metrics/team_config_template.json \
   ~/Documents/Team\ Metrics/team_config.json
```

Fill in `team_config.json`:

| Field | What to put |
|---|---|
| `atlassian_cloud_id` | `e4f75b78-9ffb-402a-8289-631e50914a9f` — Ibotta-wide, do not change |
| `github_org` | `Ibotta` — do not change for Ibotta teams |
| `squad_name` | Short uppercase label used in output filenames, e.g. `ENBL`, `POPS`, `BB` |
| `em_name` | Your full name, e.g. `"Jane Smith, Engineering Manager"` |
| `github_token` | Leave blank — not needed when using gh CLI (recommended) |
| `gh_metrics_canvas_id` | Optional fallback — only needed if gh CLI is unavailable |

For each team member:
- `email` — their Ibotta email
- `slack_handle` — copy exactly from their Slack profile display name
- `jira_account` — their Ibotta email (same as email, usually)
- `github` — their GitHub handle on `github.com/Ibotta` (check their profile URL)
- `calendar_id` — their Ibotta email
- `role` — e.g. `Platform Engineer`, `Staff Platform Engineer`

> **Optional — canvas fallback**: If `gh` CLI is unavailable, set `gh_metrics_canvas_id`
> in `team_config.json` to the `F...` ID from your squad's Slack canvas in
> `#<squad>-team-gh-metrics`. Copy the link from the Canvas tab in that channel.

### 5. Set up Atlassian API credentials (Jira + Confluence)

Add to your `~/.zshrc`:

```bash
export ATLASSIAN_API_USER="your.email@ibotta.com"
export ATLASSIAN_API_TOKEN="your_token_here"
```

Get a token at: **https://id.atlassian.com/manage-profile/security/api-tokens** → Create API token.

Then reload: `source ~/.zshrc`

Install the plugin:
```bash
claude mcp add atlassian-api@ibotta
```

### 6. Set up Google Workspace plugin (Calendar + Drive)

```bash
claude mcp add google-workspace@ibotta
/google-workspace:setup    # one-time OAuth browser sign-in
```

### 7. Connect the Slack MCP in Claude settings

> **Ibotta note**: GitHub PR data is fetched via the `gh` CLI from `github.com/Ibotta`
> (a standard GitHub.com org). Run `gh auth login` once to enable this. The `gh` CLI
> is the primary and most accurate source. If unavailable, the script falls back to
> a Slack canvas (set `gh_metrics_canvas_id`) or the GitHub REST API (last resort).

---

## Running metrics each week

Ask Claude (in Claude Code):

```
Pull metrics for the team for the week of 2026-03-16 to 2026-03-20.
Metrics folder: ~/Documents/Team Metrics/
```

Or for specific members:

```
Pull metrics for Erin McDermott, Emily Lau, Tyler Gassman
for the week of 2026-03-16 to 2026-03-20.
Metrics folder: ~/Documents/Team Metrics/
```

---

## Step-by-step workflow

### Step 1 — Parse inputs

Extract from the user's request:
- **Members**: comma-separated names, or "ALL" for everyone in config
- **Start date**: YYYY-MM-DD (first working day of range, usually Monday)
- **End date**: YYYY-MM-DD (last working day, usually Friday)

"This week" = current Mon–Fri. "Last week" = previous Mon–Fri.

> **Weekend rule**: Saturday and Sunday are **always excluded** from all calculations —
> meetings, OOO days, Slack messages, Jira activity, everything. Even if the user
> provides a date range that spans a weekend, only Mon–Fri dates are processed.
> Never count, display, or include any activity that falls on a Saturday or Sunday.

Load `team_config.json` to resolve names to system identifiers.
Calculate `working_days` = count of Mon–Fri in [start, end]. **Never count Sat/Sun.**

Initialize `metrics_data.json`:

```json
{
  "week": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "working_days": 5 },
  "members": {}
}
```

---

### Step 2 — Google Calendar (meetings & OOO)

**Count meetings**: events where the member is an accepted attendee. Exclude:
- **Any event on Saturday or Sunday** — weekends are never counted
- All-day events (home/office location markers, OOO)
- Focus time / deep work blocks
- Clockwise-generated events (lunch blocks, focus time, team headsdown blocks)
- Events the member has declined
- Solo reminders or personal events

**Count meeting hours**: sum duration of events where:
- Not an all-day event
- Not transparent / free / declined by the member
- Not a Clockwise-generated block (❇️ prefix or "Clockwise" in title)
- Not a solo event (≤1 attendee — check `len(attendees)`, not `numAttendees`)
- Not a heads-down/focus block by name (e.g. "headsdown", "focus time", "do not book")
- Not a personal reminder or out-of-office event

Compute:
```
available_hours = (working_days - ooo_days) * 8
meeting_pct     = round(total_meeting_hours / available_hours * 100)
avg_hrs_per_day = total_meeting_hours / max(working_days - ooo_days, 1)
```

**Count OOO days**: look for all-day events with "Out of Office", "OOO", or
"Vacation" in the title during [start, end]. Count unique **weekdays** (Mon–Fri) blocked.
**Never count Saturday or Sunday as OOO days**, even if the event spans the weekend.

#### GitHub PRs — gh CLI (primary method for Ibotta)

The script automatically uses the `gh` CLI when it is installed and authenticated.
No extra flags needed — just run:

```bash
node <metrics-folder>/fetch_github_metrics.js \
  --config  <metrics-folder>/team_config.json \
  --members "Name One,Name Two" \
  --start   <YYYY-MM-DD> \
  --end     <YYYY-MM-DD> \
  --out     <metrics-folder>/metrics_data.json
```

The script queries `github.com/Ibotta` (or the org in `github_org`) directly:
- **PRs opened**: `gh search prs --author=<handle> --owner=<org> --created "<start>..<end>"`
- **PRs merged this week**: `gh search prs --author=<handle> --merged --merged-at "<start>..<end>"`
- **Reviews given**: `gh api search/issues` with `reviewed-by:<handle>` filter
- **Comments received**: sum of `commentsCount` on opened PRs

Source will be recorded as `"gh-cli"` in `metrics_data.json`.

**Fallback — Slack canvas** (if gh CLI is not authenticated):
Read the GitHub metrics canvas from Slack using the `slack_read_canvas` MCP tool
with the canvas ID from `team_config.json` (`gh_metrics_canvas_id`).
Save the canvas markdown to `/tmp/canvas_metrics.md`, then pass:
`--canvas-content /tmp/canvas_metrics.md` to the script.

**Last resort — GitHub REST API** (only for public github.com repos):
Set `github_token` in `team_config.json`. Not recommended for Ibotta.

---

### Step 4 — Jira + Confluence

Run the `fetch_atlassian_metrics.py` script. This uses the `atlassian-api@ibotta`
plugin directly (no MCP needed at runtime — just env vars):

```bash
PLUGIN_SRC="$HOME/.claude/plugins/cache/ibotta/atlassian-api/1.0.0/src"
PYTHONPATH="$PLUGIN_SRC" uv run --with requests \
  python3 <metrics-folder>/fetch_atlassian_metrics.py \
  --config  <metrics-folder>/team_config.json \
  --members "Name One,Name Two"  \
  --start   2026-03-16 \
  --end     2026-03-20 \
  --out     <metrics-folder>/metrics_data.json
```

Collects per person:

**Jira:**
- Active tickets (statusCategory != Done): key, summary, status, type, URL
- Tickets closed this week (updated to Done within the date range)
- On-call detection: looks for "oncall" / "on-call" keywords in ticket titles

**Confluence:**
- Pages created this week (CQL: `creator = accountId AND created >= start`)
- Pages updated this week, excluding those also created (CQL: `contributor = accountId AND lastModified >= start`)
- Comment count this week

Writes to `metrics_data.json → members[name].jira` and `members[name].confluence`.

> **Credentials**: reads `ATLASSIAN_API_USER` and `ATLASSIAN_API_TOKEN` from environment.
> These must be set in `~/.zshrc`. Get a token at id.atlassian.com → Security → API tokens.

---

### Step 5 — Slack messages

> **⚠️ FYI — Slack MCP result cap**: The `slack_search_public` (and
> `slack_search_public_and_private`) tool returns a **maximum of 20 results per call**
> and does not paginate. This means any count of exactly 20 is a floor, not a true
> total — the actual number of messages may be higher. To avoid misleading readers,
> display counts that hit the limit as **"20+"** rather than "20" in all reports.

Search for messages from the member in each channel they're active in,
**scoped to Mon–Fri only** (never include Saturday or Sunday messages):
```
from:<slack_handle> after:<start_minus_1_day> before:<end_plus_1_day>
```
When counting results, discard any messages whose timestamp falls on a Saturday or Sunday.

**Cap handling**: if the total count returned equals 20, record and display it as
`"20+"` in both the HTML report and the Word doc to signal the result is capped.

Then run per-channel searches to get per-channel counts. Key channels to check:
- `#enablement-apis`, `#eapi-squad-only`, `#client_apis_engineering` (or your squad's channels)
- DMs with the EM

Collect:
- `total_messages` — integer total (sum per-channel counts; treat "20+" as 20)
- `per_channel` — list of `{ channel, count }` for channels with activity
- `active_window` — earliest and latest message timestamp as a time range

Write to `metrics_data.json → members[name].slack`.

**Note on "20+" cap**: Slack search returns max 20 results per query. If a channel shows
"20+", the actual count is at least 20. Sum all channel counts for the displayed total.

---

### Step 6 — Obsidian standups (optional)

If `obsidian_standup_file` is set in `team_config.json` and the file exists, run:

```bash
node <metrics-folder>/parse_standup.js \
  --config  <metrics-folder>/team_config.json \
  --file    <standup-file-path> \
  --members ALL \
  --start   2026-03-16 \
  --end     2026-03-20 \
  --out     <metrics-folder>/metrics_data.json
```

Parses daily standup entries per person from the Obsidian markdown file and writes
bullet summaries to `metrics_data.json → members[name].standup`.

Expected format in the standup file:
```markdown
3/16
- Erin - PAPI demo prep, EMDash work, Flights epic loose ends
- Emily - Meetings, wrapping ENBL-1103/1105
```

---

### Step 7 — Generate HTML report

```bash
node <metrics-folder>/generate_html_report.js \
  --members ALL \
  --start   2026-03-16 \
  --end     2026-03-20 \
  --data    <metrics-folder>/metrics_data.json \
  --config  <metrics-folder>/team_config.json \
  --out     <metrics-folder>
```
Apply the same `"20+"` rule per channel if that channel's count hits 20.

Produces `<SQUAD>_Metrics_Week_<start>_to_<end>.html`.
Open in any browser — has charts, per-person detail, and an "Export PDF" button.
Also archives data to `metrics_archive/metrics_<start>_to_<end>.json`.

---

### Step 8 — Generate Word doc

> **Disabled for this user.** Do not run `generate_report.js`. Skip this step entirely.

---

### Step 9 — Sync to Google Drive

Upload both files to Google Drive using the `google-workspace:drive` skill:

```python
# Run via uv
from google_workspace import DriveClient
drive = DriveClient()
FOLDER_ID = config["google_drive_folder_id"] or None

# Upload HTML
drive.upload_file("ENBL_Metrics_Week_....html", "<path>", "text/html", parent_id=FOLDER_ID)

# Upload Word doc (replace existing if present)
drive.upload_file("ENBL_Team_Metrics_March_2026.docx", "<path>",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  parent_id=FOLDER_ID)
```

Print the Drive URLs so the user can open or share them.

---

### Step 10 — Deliver output

After generating:
1. Run `open <path-to-html>` to open the report in the browser
2. Confirm: HTML path, Word doc path, Drive URLs
3. Note whether the Word doc was newly created or appended (and how many weeks it contains)

---

## Metrics collected per person

| Category | What is collected |
|----------|-------------------|
| **Calendar** | Meeting hours · Available hours · Meeting % · Avg hrs/day · OOO days |
| **GitHub** | PRs Opened · PRs Updated (WIP carry-overs) · PRs Merged · Reviews Given · Commits Pushed · Comments Received |
| **Jira** | Active tickets (count + list) · Tickets closed this week · On-call detection |
| **Slack** | Total messages · Per-channel breakdown · Active time window |
| **Confluence** | Pages created · Pages updated · Comments |
| **Standups** | Per-day bullet summaries from Obsidian standup notes |

---

## Data schema (`metrics_data.json`)

```json
{
  "week": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD", "working_days": 5 },
  "members": {
    "<Member Name>": {
      "calendar": {
        "total_meeting_hours": 13.33,
        "available_hours": 40,
        "meeting_pct": 33,
        "avg_hrs_per_day": 2.67,
        "ooo_days": 0
      },
      "prs": {
        "opened": [
          { "num": "<str>", "title": "<str>", "date": "<Mon D>",
            "repo": "<org/repo>", "status": "Open|Merged|Closed" }
        ],
        "reviews_given": [
          { "pr": "<str>", "title": "<str>", "date": "<Mon D>", "repo": "<org/repo>" }
        ],
        "comments_received": <int>,
        "source": "gh-cli|slack-canvas|github"
      },
      "jira": {
        "assigned_total":   7,
        "closed_this_week": 1,
        "active":         [{ "key": "ENBL-123", "summary": "...", "status": "Started", "type": "Story", "url": "..." }],
        "closed_tickets": [{ "key": "ENBL-100", "summary": "...", "status": "Closed",  "type": "Story", "url": "..." }]
      },
      "slack": {
        "total_messages": 23,
        "per_channel": [{ "channel": "#eapi-squad-only", "count": 15 }, { "channel": "#enablement-apis", "count": 8 }],
        "active_window": "9:02am – 4:48pm"
      },
      "confluence": {
        "created":   1,
        "updated":   1,
        "commented": 0,
        "pages": [
          { "title": "Mock Monolith Research",   "action": "created", "url": "https://ibotta.atlassian.net/..." },
          { "title": "Claude Code - Getting Started", "action": "updated", "url": "https://ibotta.atlassian.net/..." }
        ]
      },
      "on_call": { "is_on_call": true, "source": "jira" },
      "standup": [
        { "date": "Mar 16", "bullets": ["PAPI demo prep", "EMDash work", "Flights epic"] },
        { "date": "Mar 18", "bullets": ["AI Immersion day", "EMDash follow-ups"] }
      ]
    }
  }
}
```

---

## Handling missing or partial data

| Situation | What to do |
|-----------|------------|
| `gh` CLI not authenticated | Run `gh auth login`, or fall back to `--canvas-content` mode |
| `ATLASSIAN_API_USER` / `ATLASSIAN_API_TOKEN` not set | Add to `~/.zshrc`, run `source ~/.zshrc` |
| `atlassian-api` plugin not installed | Run `claude mcp add atlassian-api@ibotta` |
| Jira account not found for email | Check `jira_account` field in config matches their Atlassian email |
| Calendar access denied | Record `total_meeting_hours: 0, ooo_days: 0` — don't block the rest |
| Slack MCP not connected | Record `total_messages: 0` — note in report |
| Obsidian file not found | Skip standup step silently — it's optional |
| Google Drive upload fails | Note the local file paths — Drive sync is non-blocking |
| Word doc fails with "Cannot find module docx" | Run `npm install docx --prefix <metrics-folder>` |

---

## Multi-week summary reports

```
Summarize team metrics from 2026-02-01 to 2026-03-15.
Metrics folder: ~/Documents/Team Metrics/
```

```bash
node <metrics-folder>/generate_summary_report.js \
  --start    2026-02-01 \
  --end      2026-03-15 \
  --config   <metrics-folder>/team_config.json \
  --data-dir <metrics-folder>/metrics_archive/ \
  --members  ALL \
  --out      <metrics-folder> \
  --group-by week
```

Use `--group-by month` for half-year or full-year reports.
Requires at least one archived JSON in `metrics_archive/`.

---

## Handling missing or partial data

- **gh CLI not authenticated**: run `gh auth status`. If not logged in, run `gh auth login`
  and follow the browser prompts. Once authenticated, the script auto-uses gh CLI mode.
- **gh CLI not installed**: run `brew install gh`, then `gh auth login`.
- **Canvas fallback — member not found**: the `github` handle in config must match exactly
  what appears on `github.com/Ibotta` (e.g. `witygass` not `Tyler Gassman`).
- **Jira/Confluence shows 0 or errors**: Atlassian MCP connector must be connected.
  The `atlassian_cloud_id` is pre-filled for Ibotta — do not change it.
- **Word doc fails with "Cannot find module docx"**: run
  `npm install docx --prefix <metrics-folder>`.
- **Calendar access denied**: record `total_meeting_hours: 0, ooo_days: 0`.

---

## Archive folder

Each weekly HTML report run automatically saves a copy of `metrics_data.json` to
`<metrics-folder>/metrics_archive/metrics_<start>_to_<end>.json`. This is the data
source for the summary report. **Do not delete files in this folder.**
