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
| **Google Calendar MCP** | Google Calendar (meetings, OOO) — built-in claude.ai MCP | Already available — no install needed |
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

### 6. Google Calendar

No setup needed. Calendar data is fetched via the built-in Google Calendar MCP
(`mcp__claude_ai_Google_Calendar__list_events`), which is already authenticated
through your claude.ai account.

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

## Week convention

**Weeks run Monday–Sunday.** When the user says "team metrics" with no explicit date range,
default to the most recent completed Monday–Sunday week (i.e., last Mon–Sun, not Mon–Fri).

- `start` = most recent completed Monday (YYYY-MM-DD)
- `end`   = the Sunday of that same week (YYYY-MM-DD)
- `working_days` = 5 (Mon–Fri only — weekends are excluded from all calculations)

**Always compute the Monday date with actual date math — never guess.**

Run this first, every time:

```bash
python3 -c "
from datetime import date, timedelta
today = date.today()
# weekday(): Mon=0, Sun=6
days_since_monday = today.weekday()
# 'last week' = the Mon-Sun week that ended before this week started
last_monday = today - timedelta(days=days_since_monday + 7)
last_sunday = last_monday + timedelta(days=6)
print('Today:', today, today.strftime('%A'))
print('Last week Mon:', last_monday)
print('Last week Sun:', last_sunday)
"
```

Use the printed `Last week Mon` and `Last week Sun` as `start` and `end`. Do not proceed
until you have confirmed the actual day-of-week from this output.

---

## Step-by-step workflow

### Step 1 — Parse inputs

Extract from the user's request:
- **Members**: comma-separated names, or "ALL" for everyone in config
- **Start date**: YYYY-MM-DD (first working day of range, usually Monday)
- **End date**: YYYY-MM-DD (last working day, usually Friday)

"This week" = current Mon–Fri. "Last week" = previous Mon–Fri.

> **Weekend rule**: Saturday and Sunday are **excluded from all capacity math** —
> meeting hours, OOO days, available hours, Jira ticket counts — because those
> calculations assume a 5-day workweek.
>
> **However**, weekend Slack or GitHub activity is a signal that something was wrong —
> an incident, a crunch, or an on-call fire. **Do not silently discard it.**
> Instead, surface it: if a team member posted Slack messages or opened/merged PRs
> on Saturday or Sunday, flag it in their card as a `"weekend_activity"` note
> (e.g. `"Slack messages Saturday Apr 26"`, `"PR merged Sunday Apr 27"`).
> This is not a metric to optimize — it's a health indicator.

Load `team_config.json` to resolve names to system identifiers.
Calculate `working_days` = count of Mon–Fri in [start, end]. **Never count Sat/Sun.**

> **Pipeline architecture (read this).** Each data source writes its own file:
> `metrics_data.calendar.json`, `metrics_data.atlassian.json`,
> `metrics_data.github.json`, `metrics_data.pagerduty.json`,
> `metrics_data.slack.json`. After all five exist, run `merge_metrics.js` —
> it validates completeness, writes the merged `metrics_data.json`, and (only
> on a fully-successful merge) deletes the five source files. Do **not** have
> Claude write to `metrics_data.json` directly during steps 2–6.
>
> Each per-source file shares the same top-level shape:
> ```json
> { "week": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
>   "members": { "<Name>": { /* only this source's fields */ } } }
> ```

---

### Step 2 — Google Calendar (meetings & OOO)

**Preferred:** run the `fetch_calendar_metrics.py` script — writes
`metrics_data.calendar.json`:

```bash
uv run \
  --with "google-workspace @ git+ssh://git@github.com/Ibotta/google-workspace-py.git" \
  --with requests \
  python3 $SKILL_DIR/fetch_calendar_metrics.py \
  --config  <metrics-folder>/team_config.json \
  --members ALL \
  --start   <YYYY-MM-DD> \
  --end     <YYYY-MM-DD> \
  --out     <metrics-folder>/metrics_data.calendar.json
```

The `google-workspace` package is an internal Ibotta library hosted at
`github.com/Ibotta/google-workspace-py`. The first run will clone it via SSH
(make sure `ssh -T git@github.com` succeeds); subsequent runs hit the uv
cache and are fast.

**Fallback (Claude-driven):** if the script can't run, Claude uses the
**`mcp__claude_ai_Google_Calendar__list_events`** MCP tool, applies the rules
below, and writes the result directly to `metrics_data.calendar.json`. Call
all members in
parallel — one call per person, using their `calendar_id` (email) from config.

```
list_events(
  calendarId = member.calendar_id,
  startTime  = "<start>T00:00:00",
  endTime    = "<end+1day>T00:00:00",   # exclusive upper bound covers full Sunday
  timeZone   = "America/Denver",
  pageSize   = 250
)
```

Apply these rules to each event to decide whether to count it as a meeting:

**Skip** (never count):
- `start.date` present (all-day event) — use separately for OOO detection
- `eventType` is `"focusTime"` or `"outOfOffice"` (timed OOO/focus blocks)
- `transparency` is `"transparent"` (shows as free)
- Member's `responseStatus` is `"declined"`
- `status` is `"cancelled"`
- Title matches Clockwise/lunch/focus heuristic: contains any of `lunch`, `❇️`,
  `clockwise`, `focus time`, `headsdown`, `heads down`, `heads-down`, `do not book`,
  `deep work`
- Event falls on Saturday or Sunday (check `start.dateTime` day-of-week)
- Zero attendees (`attendees` field absent or empty) AND no `recurringEventId`

**Count** everything else as a meeting; sum `(end.dateTime - start.dateTime)` in hours.

**OOO days**: scan all-day events (`start.date` present) for titles containing `ooo`,
`out of office`, `vacation`, `pto`. Count unique Mon–Fri calendar dates blocked.
Also accept `eventType == "outOfOffice"` on all-day events.

Compute:
```
available_hours = (working_days - ooo_days) * 8
meeting_pct     = round(total_meeting_hours / available_hours * 100)
avg_hrs_per_day = total_meeting_hours / max(working_days - ooo_days, 1)
```

Write to `metrics_data.calendar.json → members[name].calendar`.

---

### Step 3 — GitHub PRs — gh CLI (primary method for Ibotta)

The script automatically uses the `gh` CLI when it is installed and authenticated.
No extra flags needed — just run:

```bash
node $SKILL_DIR/fetch_github_metrics.js \
  --config  <metrics-folder>/team_config.json \
  --members "Name One,Name Two" \
  --start   <YYYY-MM-DD> \
  --end     <YYYY-MM-DD> \
  --out     <metrics-folder>/metrics_data.github.json
```

The script queries `github.com/Ibotta` (or the org in `github_org`) directly:
- **PRs opened**: `gh search prs --author=<handle> --owner=<org> --created "<start>..<end>"`
- **PRs merged this week**: `gh search prs --author=<handle> --merged --merged-at "<start>..<end>"`
- **Reviews given**: `gh api search/issues` with `reviewed-by:<handle>` filter
- **Comments received**: sum of `commentsCount` on opened PRs

Source will be recorded as `"gh-cli"` in `metrics_data.github.json`.

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
PLUGIN_SRC="$HOME/.claude/plugins/marketplaces/ibotta/plugins/atlassian-api/src"
PYTHONPATH="$PLUGIN_SRC" uv run --with requests \
  python3 $SKILL_DIR/fetch_atlassian_metrics.py \
  --config  <metrics-folder>/team_config.json \
  --members "Name One,Name Two"  \
  --start   2026-03-16 \
  --end     2026-03-20 \
  --out     <metrics-folder>/metrics_data.atlassian.json
```

Collects per person:

**Jira:**
- Active tickets (statusCategory != Done): key, summary, status, type, URL
- Tickets closed this week (updated to Done within the date range)

**Confluence:**
- Pages created this week (CQL: `creator = accountId AND created >= start`)
- Pages updated this week, excluding those also created (CQL: `contributor = accountId AND lastModified >= start`)
- Comment count this week

Writes to `metrics_data.atlassian.json → members[name].jira` and `members[name].confluence`. On-call is **not** part of this step — see Step 6.

> **Credentials**: reads `ATLASSIAN_API_USER` and `ATLASSIAN_API_TOKEN` from environment.
> These must be set in `~/.zshrc`. Get a token at id.atlassian.com → Security → API tokens.

---

### Step 5 — Slack messages

> **⚠️ FYI — Slack MCP pagination**: The `slack_search_public` tool returns a maximum
> of 20 results per call, but supports a `cursor` parameter for pagination. Paginate up
> to **5 pages** (max 100 results total) per search by passing the `cursor` from each
> response into the next call. Stop early if fewer than 20 results are returned (end of
> results). If 100 results are reached and there are still more, display the count as
> **"100+"** rather than "100" in all reports.

Search for messages from the member using their **Slack ID** from `team_config.json`
(`slack_id` field). **Always use `<@ID>` format — never use `slack_handle` for searches.**
Scoped to Mon–Fri only (never include Saturday or Sunday messages):

```
from:<@SLACK_ID> after:<start_minus_1_day> before:<end_plus_1_day>
```

Example: `from:<@U038HFBCMCJ> after:2026-04-26 before:2026-05-02`

When counting results for `total_messages` and per-channel breakdowns, count **only Mon–Fri
messages**. But do **not discard** weekend messages — if any exist, note them separately as
`"weekend_activity"` on the member's data (date + channel). Weekend Slack activity is a
health flag, not a metric to sum.

**Pagination**: for each search, paginate up to 5 pages (passing `cursor` from each response) to collect up to 100 results. Stop early if a page returns fewer than 20 results. If all 5 pages are full (100 results) and a cursor still exists, record and display the count as `"100+"` to signal it is capped.

Then run per-channel searches to get per-channel counts. Channels are discovered organically from search results — wherever the person posted, it appears.

Collect:
- `total_messages` — integer total (sum per-channel counts; treat "100+" as 100)
- `per_channel` — list of `{ channel, count, summary? }` for channels with activity
- `active_window` — earliest and latest message timestamp as a time range

**Channel summaries:** After collecting counts, check `slack_summary_channels` in `team_config.json`. For each of those channels where the person had activity, re-read the messages and write a `summary`: 1–2 sentences describing what they were actually doing there — topics raised, questions answered, work referenced. Skip if count is 0. Channels not in `slack_summary_channels` get count only (no `summary` field).

After gathering, Claude writes a small JSON file (e.g. `/tmp/slack_input.json`)
with the per-member data and pipes it to `write_slack_source.py`, which
validates the shape and writes `metrics_data.slack.json` atomically:

```bash
python3 $SKILL_DIR/write_slack_source.py \
  --config <metrics-folder>/team_config.json \
  --start  <YYYY-MM-DD> \
  --end    <YYYY-MM-DD> \
  --data   /tmp/slack_input.json \
  --out    <metrics-folder>/metrics_data.slack.json
```

The script:
- Refuses any `--out` path that doesn't end in `.slack.json` (so it can never
  clobber another per-source file, even with a typo).
- Validates that every member name exists in `team_config.json`.
- Validates each member's slack dict has `total_messages` (int or `"<N>+"`),
  `per_channel` (list of `{channel, count, summary?}`), and `active_window`.
- Writes atomically via tmp-file + rename.

Input shape for `/tmp/slack_input.json` (either `{ "<Name>": {...} }` directly
or wrapped as `{ "members": { ... } }`):

```json
{
  "Shelbey Summers": {
    "slack": {
      "total_messages": "60+",
      "per_channel": [
        { "channel": "#content_squad", "count": 4,
          "summary": "1-2 sentences about what they were doing here" },
        { "channel": "#gamers", "count": 2 }
      ],
      "active_window": "Mon 9:56am – Fri 3:04pm"
    },
    "partial_absences": [
      { "date": "May 22", "note": "slept poorly, going to try and rest" }
    ]
  }
}
```

This step is Claude-driven because the channel summaries and partial-absence
detection need LLM judgment — but the file-writing is delegated to the guarded
script so a Claude misstep can't damage other source files.

**Note on "100+" cap**: Each Slack search paginates up to 5 pages (max 100 results). If all 5 pages fill and a cursor remains, display the count as "100+". Sum all channel counts for the displayed total.

#### Partial absence detection

While scanning each person's Slack messages, also look for messages indicating they were sick or partially unavailable. These are surfaced as a flag on the member card — they do **not** affect capacity math.

**Detection patterns** (all from #content_squad, all from team members):
- `"not feeling well"` / `"not feeling great"` / `"feeling not great"`
- `"headache"` + context of resting or being offline
- `"stomach bug"` / `"fever"` / `"fighting this illness"` / `"fighting off"`
- `"allergies"` + `"Benadryl"` / `"rest"`
- `"take the day"` / `"take the rest of the day"` / `"take the morning"`
- `"rest for a bit"` / `"rest a bit longer"` / `"lie back down"`
- `"cut out early"` / `"cutting out"` + illness context
- `"call it a day"` when posted in the morning + illness context

**Do NOT flag** (distracted but working):
- "attention will be divided" (kid sick at home)
- "won't make standup" alone
- "step out for a little while" for errands
- Personal/family logistics without illness

For each match, store:
```json
"partial_absences": [
  { "date": "Mar 20", "note": "not feeling great, back this afternoon" },
  { "date": "Mar 23", "note": "headache, taking the morning to rest" }
]
```

Write to `metrics_data.slack.json → members[name].partial_absences` alongside the
slack data for that member. The count across the team appears as a summary card
in the report; individual entries appear as a collapsible section on each member
card (amber, open by default if non-empty).

Similarly, weekend Slack activity is written to `members[name].weekend_activity`
in `metrics_data.slack.json` (see the Weekend rule near the top of this skill).

---

### Step 6 — On-call (PagerDuty)

On-call is sourced from PagerDuty, **not Jira**. Only the **primary** (L1) on-call person is tracked.

The schedule ID lives in `team_config.json` as `pagerduty_primary_schedule_id`
(defaults to `PUL2FDL`, the Content Squad Primary schedule). The secondary
schedule (`PTY2TZH` for Content) is not tracked.

**Rotation rule:** Rotations happen at **9am Monday**. The script always uses `T09:00:00` as the `since` time so the pre-rotation window (midnight–9am) is excluded and doesn't pull in the previous week's on-call person.

```bash
PLUGIN_SRC="$HOME/.claude/plugins/marketplaces/ibotta/plugins/pagerduty-api/src"
PYTHONPATH="$PLUGIN_SRC" uv run --with requests \
  python3 $SKILL_DIR/fetch_pagerduty_metrics.py \
  --config  <metrics-folder>/team_config.json \
  --start   <YYYY-MM-DD> \
  --end     <YYYY-MM-DD> \
  --out     <metrics-folder>/metrics_data.pagerduty.json
```

For each configured member the script writes `on_call: { is_on_call, source: "pagerduty", role: "primary"|null }` into `metrics_data.pagerduty.json`. If two people appear (e.g. handoff mid-week because the primary went OOO), both get `is_on_call: true`.

> **OOO note (calendar concern, not PD):** OOO is detected in Step 2 from the
> individual calendar first, then the squad calendar (`squad_calendar_id`) as a
> fallback for members who use Slack status instead of personal calendars. Both
> are merged by the calendar fetch.

---

### Step 7 — Merge sources

Once all five per-source files exist (`metrics_data.calendar.json`,
`metrics_data.atlassian.json`, `metrics_data.github.json`,
`metrics_data.pagerduty.json`, `metrics_data.slack.json`), run:

```bash
node $SKILL_DIR/merge_metrics.js \
  --config  <metrics-folder>/team_config.json \
  --target  <metrics-folder>/metrics_data.json
```

The merge script validates:
- All five source files exist
- They share the same `week.start` and `week.end`
- Every configured member appears in every source

**On a fully-successful merge:** writes `metrics_data.json` and **deletes the five source files** so the next run starts clean.

**On any failure:** writes a partial `metrics_data.json` with whatever could be merged, prints what's missing, and **leaves the source files in place** for inspection or re-run. Re-run the failing fetcher, then `merge_metrics.js` again.

Pass `--no-cleanup` to skip the source-file deletion even on success (useful when debugging).

---

### Step 8 — Generate reports

Read `output_formats` from `team_config.json` (defaults to `["html"]` if absent). Run the corresponding script for each format listed.

**`"html"`** — interactive report with charts; also archives `metrics_data.json` to `metrics_archive/`:
```bash
node $SKILL_DIR/generate_html_report.js \
  --members ALL \
  --start   <start> \
  --end     <end> \
  --data    ~/ai/team-metrics/metrics_data.json \
  --config  ~/ai/team-metrics/team_config.json \
  --out     ~/ai/team-metrics
```

**`"md"`** — plain Markdown, no npm dependencies:
```bash
node $SKILL_DIR/generate_md_report.js \
  --members ALL \
  --start   <start> \
  --end     <end> \
  --data    ~/ai/team-metrics/metrics_data.json \
  --config  ~/ai/team-metrics/team_config.json \
  --out     ~/ai/team-metrics
```

**`"docx"`** — cumulative monthly Word doc (prepends new week each run); requires `npm install` in `$SKILL_DIR` first:
```bash
node $SKILL_DIR/generate_report.js \
  --members ALL \
  --start   <start> \
  --end     <end> \
  --data    ~/ai/team-metrics/metrics_data.json \
  --config  ~/ai/team-metrics/team_config.json \
  --out     ~/ai/team-metrics
```

---

### Step 9 — Sync to Google Drive (optional)

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
1. For each format in `output_formats`, confirm the output path
2. Open generated files: `open <path>` for each (browser for HTML, default app for MD/docx)
3. If `"docx"` was generated, note whether it was newly created or appended (and how many weeks it now contains)

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

## Data schema

The final `metrics_data.json` (after `merge_metrics.js`) has this shape. Each
per-source file shares the top-level shape but only contains its own fields per
member (e.g. `metrics_data.calendar.json` has only `members[name].calendar`).

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
        "per_channel": [
          { "channel": "#content_squad", "count": 15, "summary": "Daily standups, raised a question about CONTENT-412 scope, responded to Brian's prod alert." },
          { "channel": "#content_git", "count": 5, "summary": "Commented on two PRs: approved Nate's content-service change, left feedback on Miranda's indexer fix." },
          { "channel": "#ibotta_unhinged", "count": 3 }
        ],
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
      "on_call": { "is_on_call": true, "source": "pagerduty", "role": "primary" },
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
