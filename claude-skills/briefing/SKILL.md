---
name: briefing
description: Session-start briefing. Reads the session log, checks today's calendar, and surfaces urgent reminders so Ken can orient quickly without re-explaining context.
disable-model-invocation: true
---

## Context
- Date: !`date "+%Y-%m-%d %A"`
- Hostname: !`hostname`

## Session Briefing

Orient Ken for this session. Do all three, then give a concise summary.

### 1. Session log
Read the most recent entry in:
`~/Library/Mobile Documents/com~apple~CloudDocs/Productivity/session-log.md`

Pull out: what was last worked on, any open threads, anything explicitly marked pending.

### 2. Calendar
Check today's events using the `calendar_list` MCP tool with range `today`.

If hostname contains `ibotta` or `work`, use the work subset. Otherwise show all.

### 3. Urgent reminders
Use `reminders_list` to check:
- Home Mac: Daily Life, Trinity Council, Household Finances
- Work Mac: Ibotta only

Surface anything overdue, due today, or high priority.

### Output format

Keep it tight. Lead with what matters most.

```
## Briefing — [Day, Date]

**Last session:** [one-line summary of what was worked on]
**Open threads:** [anything pending or in-flight]

**Today:**
- [calendar events]

**Needs attention:**
- [urgent reminders]
```

If $ARGUMENTS is provided, treat it as additional context (e.g. "home session" or "work, skip calendar").

$ARGUMENTS
