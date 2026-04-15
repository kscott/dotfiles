---
name: wrap
description: End-of-session wrap-up. Checks calendar and reminders, logs work with doing CLI, and appends to session log. Use when the user says wrap up, log it, done for the day, or similar.
disable-model-invocation: true
---

## For Claude: if the Skill tool errors on this skill

`disable-model-invocation: true` means only Ken invokes this skill by typing `/wrap`.
If you attempted to invoke it via the Skill tool and got an error: **stop, do not read this file and proceed anyway.** Tell Ken the skill errored and ask him to type `/wrap` himself.

## Current Time
- Now: !`date "+%Y-%m-%d %H:%M"`
- Hostname: !`hostname`

## Session Wrap-Up

You are wrapping up a Claude Code session for Ken Scott. Complete all steps in order.

---

### Step 1: Check calendar and reminders

Use the hostname to determine which commands to run.

**Home Mac (Mac-mini):**

```bash
get-clear recap today
```

This shows today's calendar events and activity log in one view. Use it to surface meetings and completed work that should be logged.

**Work Mac (any other hostname):**

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

reminders what today
reminders list Ibotta
```

`reminders what today` catches anything touched via the CLI during the session.
`reminders list Ibotta` shows what's still open — useful for spotting items completed manually in the Reminders app (they'll be absent from the list).

Ask the user which meetings they attended and whether any reminders were completed during the session. Note any corrections. Do NOT mark reminders done via CLI — the user has already done that.

---

### Step 2: doing CLI entry

Review what was accomplished. Write a concise doing entry (one line, imperative, specific).

**Before running the command, compute the time explicitly. Show your work:**

1. **Now:** read the current time from the `## Current Time` block above (e.g. 22:58)
2. **Rounded end:** round to nearest :00, :15, :30, or :45 (e.g. 22:58 → 23:00)
3. **Start time:** use what the user stated (e.g. "started at 9pm" → 21:00), or derive from conversation context
4. **Rounded start:** round start to nearest :00, :15, :30, or :45
5. **`--back` value:** the rounded start time as a clock time (e.g. `--back 9pm`), NOT a duration

State the result before running:
> Start: 9:00pm — End: 11:00pm — `--back 9pm`

Then run:

```
doing done "<summary> @<tags>" --back <rounded-start-time> --section <section>
```

**Section and tagging:**

Always specify `--section` explicitly — never rely on the default.

| Work done | `--section` | Tags |
|---|---|---|
| Ibotta / work projects | `Work` | `@work` |
| Work meetings | `Work` | `@meeting @work @<group>` — e.g. `@content-squad`, `@retailer-distribution` |
| Personal / home tasks | `Home` | `@home` |
| Get Clear and other personal projects | `Home` | `@projects @get-clear` (or relevant project tag) |
| Trinity Council meeting | `Home` | `@meeting @trinity-council` |
| Trinity Council project work | `Home` | `@projects @trinity-council` |

**Tagging rules:**
- Meeting type (standup, 1:1, sprint review) goes in the entry title — not as a tag
- No sub-type tags like `@standup` or `@sprint-review` — redundant
- The group tag (e.g. `@content-squad`) is the clarifying data for work meetings
- If a session touched more than one project, write a separate `doing done` entry per project

**Example:**
```
doing done "Plex playlists, backup verify notification, library comparison doc @projects @home" --back 9pm --section Home
```

---

### Step 3: Session log

Append a new dated entry to:
`~/Library/Mobile Documents/com~apple~CloudDocs/Productivity/session-log.md`

Format:
```markdown
## YYYY-MM-DD (Weekday, ~H:MMam–H:MMpm) — Home Mac / Work Mac

**Focus:** One-line summary

**Completed:**
- Bullet list of what was done, specific enough to reconstruct context

**Pending:**
- Anything left open, blocked, or handed off
```

Append the new entry at the end of the file. The log is chronological, oldest first.

Both doing and session log are non-negotiable — never do one without the other.

---

### Step 4: Confirm

Report what was logged: doing entries (times + summaries) and session log entry header.

$ARGUMENTS
