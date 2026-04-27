---
name: reminders
description: Add, change, find, complete, and manage Apple Reminders. Always use this skill instead of running the reminders CLI directly.
allowed-tools: Bash
---

# Reminders

Current time: !`date "+%A %B %-d, %Y %-I:%M%p" | tr '[:upper:]' '[:lower:]'`

## Syntax

!`reminders help`

## Argument order rules — read before every command

| Command | Order |
|---------|-------|
| add | **title** → list → date |
| change | **title** → list → field value |
| rename | **title** → new-title → list |
| done | **title** → list |
| remove | **title** → list |
| show | **title** → list |

**Title always comes first. List always comes second. Never swap them.**

## Context

- Default list on Work Mac: **Ibotta**. Use `Home` for personal reminders.
- Use `find` before `change`, `done`, or `remove` to confirm the exact title.
- `note` must be the last field in any `change` or `add` command.

## Task

User request: $ARGS

1. If the operation is `change`, `done`, or `remove` — run `reminders find <keyword>` first to confirm the exact title.
2. Construct the command using the syntax above. Title first, list second. No exceptions.
3. Run it and show the result.
