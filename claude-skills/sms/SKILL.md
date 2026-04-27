---
name: sms
description: Send iMessages and SMS via Messages.app. Always use this skill instead of running the sms CLI directly.
allowed-tools: Bash
---

# SMS

## Syntax

!`sms help`

## Key rules

- `send`: contact name or phone number first, message text after — all remaining args become the message
- Contact name must match a name in Contacts (or be a phone number)
- Sends via Messages.app — iMessage if available, SMS otherwise
- Confirm message content with the user before sending unless explicitly told to send

## Task

User request: $ARGS

Confirm the recipient and message, then run the command. Show the result.
