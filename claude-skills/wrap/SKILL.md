---
name: wrap
description: End-of-session wrap-up. Logs work with doing CLI, checks calendar and reminders, and appends to session log. Use when the user says wrap up, log it, done for the day, end session, or similar.
allowed-tools: Bash, Read, AskUserQuestion
---

# Session Wrap-Up

You are wrapping up a Claude Code session for Ken Scott. Complete all steps in order.

---

## Step 1: Get current time and start time

```bash
date
```

If the user hasn't provided a start time, ask:
> "What time did you start?"

Round both times to the nearest 15 minutes.

---

## Step 2: Check today's calendar

Pull Google Calendar events for today to surface meetings that should be logged:

```bash
uv run --with "google-workspace @ git+ssh://git@github.com/Ibotta/google-workspace-py.git" python3 << 'EOF'
from google_workspace import CalendarClient
from datetime import datetime
from zoneinfo import ZoneInfo

cal = CalendarClient()
tz = ZoneInfo("America/Denver")
today = datetime.now(tz)
start = today.replace(hour=0, minute=0, second=0, microsecond=0)
end = today.replace(hour=23, minute=59)

events = cal.get_events(start_date=start, end_date=end)
for e in events:
    t = e.get('start', {}).get('dateTime', e.get('start', {}).get('date', ''))
    t_end = e.get('end', {}).get('dateTime', '')
    print(f"{t[11:16]}–{t_end[11:16]}  {e['summary']}")
EOF
```

Ask the user which meetings they attended and how (fully, partially, multitasked). Note any time corrections given by the user.

---

## Step 3: Check Ibotta reminders

Run both commands:

```bash
# Shows CLI activity today — any reminders added or marked done via CLI
reminders what today

# Shows current active list — completed items won't appear
reminders list Ibotta
```

`reminders what today` catches anything touched via the CLI during the session.
`reminders list Ibotta` shows what's still open — useful for spotting items the user
completed manually in the Reminders app (they'll be absent from the list).

Ask: "Did you complete any reminders during the session?"

If the user names completed items, note them in the session log. Do NOT mark them done
via CLI — the user has already done that.

---

## Step 4: Log doing entries

Log the main work block first:

```bash
~/.gem/ruby/4.0.1/bin/doing done --section Work --from "<start> to <end>" "<summary> @<tags>"
```

Then log each attended meeting as a separate entry:

```bash
~/.gem/ruby/4.0.1/bin/doing done --section Work --from "<start> to <end>" "<Person> / Ken 1:1 @meeting @content-squad"
```

**Time rules:**
- Use `--from "8:30am to 9:00am"` format — not `--back`
- Round to nearest 15 minutes
- Work block and meetings can overlap — that's fine

**Tagging conventions:**
- Sprint/Jira/squad work: `@content-squad @sprint`
- 1:1s and team meetings: `@meeting @content-squad`
- Get Clear development: `@projects @get-clear`
- Home/personal tasks: `@home`

**Summary style:** One line, imperative, specific enough to reconstruct context.

---

## Step 5: Append to session log

File: `~/Library/Mobile Documents/com~apple~CloudDocs/Productivity/session-log.md`

Append a new entry at the **end** of the file:

```markdown

---

## YYYY-MM-DD (Weekday, H:MMam–H:MMam) — Work Mac

**Focus:** One-line summary

### What we did

Narrative bullets of what was accomplished. Specific enough to reconstruct context
in a future session without re-reading the conversation.

### Key files
- `path/to/file` — what changed and why

### Meetings
- **H:MMam–H:MMam — Meeting name** — brief note; "notes TBD" if not yet written

### Reminders completed
- Item name (if any flagged by user)

### doing entries logged
- H:MMam–H:MMam — Summary @tags
```

Omit sections that don't apply (no "Meetings" if no meetings, no "Reminders completed" if none flagged).

**Both doing and session log are non-negotiable — never do one without the other.**

---

## Step 6: Confirm

Report what was logged: doing entries (times + summaries) and session log entry header.

$ARGUMENTS
