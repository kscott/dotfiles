---
name: contacts
description: Find, add, change, and manage Apple Contacts. Always use this skill instead of running the contacts CLI directly.
allowed-tools: Bash
---

# Contacts

## Syntax

!`contacts help`

## Key rules

- `add`: name first, then optional fields (`email E`, `phone P`)
- `add <name> to <group>`: adds an existing contact to a group
- `change`: name first, then `add` or `remove`, then field
- `rename`: name first, new name second
- `remove <name> from <group>`: removes from group only, does not delete contact
- Use `find` before `change`, `rename`, or `remove` to confirm the exact name

## Task

User request: $ARGS

Construct the correct command and run it. Show the result.
