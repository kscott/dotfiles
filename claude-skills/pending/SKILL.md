---
name: pending
description: Show what's pending and needs attention. Checks the right reminder lists based on which machine is running (Ibotta at work, Daily Life + Trinity Council + Household Finances at home).
disable-model-invocation: true
---

## Context
- Hostname: !`hostname`
- Date: !`date "+%Y-%m-%d %A"`

## What's Pending

Check reminders and surface what needs attention. Use the `reminders_list` and `reminders_find` MCP tools.

**Machine-aware list selection:**

If hostname contains `ibotta` or `work` → check **Ibotta** list only.
Otherwise (home Mac) → check these three lists:
- **Daily Life**
- **Trinity Council**
- **Household Finances**

Skip Ibotta, Product Roadmap, and any other lists unless explicitly asked.

**What to surface:**
1. Overdue items (due date has passed)
2. Due today or tomorrow
3. High priority items regardless of due date
4. Anything that looks time-sensitive from context

**Format:**
Group by urgency. Be concise — this is a quick orientation, not a full dump. If nothing urgent, say so.

$ARGUMENTS
