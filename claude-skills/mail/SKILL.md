---
name: mail
description: Send and find email via Fastmail/JMAP. Always use this skill instead of running the mail CLI directly.
allowed-tools: Bash
---

# Mail

## Syntax

!`mail help`

## Key rules

- `send`: recipient (`<to>`) first, all other fields optional and in any order
- Use `find` before composing to pull context — especially for replies
- `--draft` flag saves without sending
- `body` accepts plain text; keep it brief for clarity
- `from` defaults to the primary Fastmail identity — only specify if sending from an alias

## Task

User request: $ARGS

If this is a reply or follow-up, run `mail find <query>` first for context.
Construct the correct command and run it. Confirm before sending unless the user has explicitly said to send.
