---
name: calendar
description: List, search, add, and remove Apple Calendar events. Always use this skill instead of running the calendar CLI directly.
allowed-tools: Bash
---

# Calendar

Current time: !`date "+%A %B %-d, %Y %-I:%M%p" | tr '[:upper:]' '[:lower:]'`

## Syntax

!`calendar help`

## Key rules

- `add`: title first, then date, then time range (`9am to 10am`)
- `show` / `remove`: title first, optional date second
- Prefix a subset name to filter by calendar group: `calendar work today`, `calendar personal week`
- Use `find` before `remove` to confirm the exact title

## Task

User request: $ARGS

Construct the correct command and run it. Show the result.
