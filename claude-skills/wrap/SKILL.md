---
name: wrap
description: End-of-session wrap-up. Logs work with doing CLI and appends to session log. Use when the user says wrap up, log it, done for the day, or similar.
disable-model-invocation: true
---

## Current Time
- Now: !`date "+%Y-%m-%d %H:%M"`
- Hostname: !`hostname`

## Session Wrap-Up

You are wrapping up a Claude Code session for Ken Scott. Do both steps — never one without the other.

### Step 1: doing CLI entry

Review what was accomplished in this conversation. Write a concise doing entry (one line, imperative, specific) and add it with:

```
doing done "<summary> @<tags>" --back <elapsed>
```

**Tagging conventions:**
- Project/code work: `@projects @<project-name>` (e.g. `@projects @get-clear`)
- Home/personal tasks: `@home`
- Work tasks: `@work`
- Meetings: `@meeting @work @<group>` or `@meeting @trinity-council`
- Multiple tags are fine

**Time rules:**
- Round to nearest 15 minutes (forward or back)
- Use `--back` to backdate start (e.g. `--back 2h`, `--back 45m`)
- If you know a specific start time, use `--back` to match it
- Use elapsed time from when the conversation started to now

**Example:**
```
doing done "Plex playlists, backup verify notification, library comparison doc @projects @home" --back 2h
```

### Step 2: Session log

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

Insert the new entry immediately after the `---` separator at the top, before any existing entries.

Do not ask for confirmation. Do both steps, then report done.

$ARGUMENTS
