---
name: review-recognition
description: >
  Summarizes Awardco recognition notifications for Ken's direct reports, grouped
  by person and organized into themes useful for performance reviews. Reads Gmail
  for Awardco emails in a given date range (default: current calendar year) and
  produces a thematic summary per report. Use when asked to "summarize recognition",
  "review recognitions", "pull Awardco for reviews", or similar.
allowed-tools: Bash, Read, AskUserQuestion, mcp__claude_ai_Gmail__gmail_search_messages, mcp__claude_ai_Gmail__gmail_read_message
---

# Review Recognition Skill

Summarizes Awardco recognition notifications for Ken's direct reports, organized
into themes useful for performance review preparation.

## Direct Reports (current)

Shelbey Summers, Jasmine Hamou, Miranda Cascione, Nate Ewert-Krocker, Brian Holman, Matt Dolan

Update this list if the team changes.

---

## Key lesson from first run

Awardco sends two types of emails to ken.scott@ibotta.com:

1. **"You've been recognized!"** subject — Ken himself was recognized. Skip these; they're about Ken, not his reports.
2. **"Recognition Notification"** / **"Private Recognition Notification"** subject — could be a manager notification for a report. Must read the email body.

**Do not trust the snippet or body preview text.** The body text is the message *addressed to the recipient* — it uses "you/your" but refers to the person being recognized, not Ken. The only reliable indicator is the `<h1>` tag inside the HTML body, which reads `[Name] was recognized!`.

Extract it efficiently:
```python
import re
match = re.search(r'<h1[^>]*>\s*(.*?)\s*</h1>', body, re.DOTALL)
# Look for "X was recognized!" or "X, Y and others were recognized!"
```

---

## Workflow

### Step 1: Determine date range

If the user provides a range (e.g. "Q3" or "Jan–Jun" or "2025"), use that.

Otherwise default to **current calendar year**: January 1 to today.

```python
from datetime import date
year = date.today().year
after = f"{year}/01/01"
before = f"{year}/12/31"
```

### Step 2: Fetch Awardco emails

```
query: from:no-reply@ibotta.awardco.com after:{after} before:{before}
maxResults: 100
```

Page through results if `nextPageToken` is returned — there may be more than 100.

Filter out immediately (by subject):
- "You've been recognized!" → skip (Ken was recognized, not a report)
- Anything with "birthday" in the subject → skip

Keep:
- "Recognition Notification"
- "Private Recognition Notification"

### Step 3: Read each kept email and extract recipient

For each kept email, read the full message body and extract:
- **Recipient:** from the `<h1>` tag — `[Name] was recognized!`
- **Giver:** from the `<h4>` tag — `[Giver] recognized [Recipient]!`
- **Message:** from the `<p>` inside the main content table

If the recipient is not one of Ken's direct reports, skip it.

> **Efficiency tip:** Read emails in batches of 5 in parallel. With 50+ emails this matters.

### Step 4: Group by report and identify themes

For each direct report, review all their recognitions and identify 3–5 themes. Good themes are:

- **Specific and behavioral** — not just "did good work" but *what kind* of work and *how*
- **Pattern-based** — a theme requires at least 2 signals, unless one recognition is exceptionally specific
- **Cross-team vs. squad** — note when recognition comes from outside the Content Squad; it signals broader reputation
- **Incident/under-pressure behavior** — stepping up during on-call, weekends, or production issues is worth calling out separately
- **Initiative vs. assigned work** — did they do it because it was their story, or because they saw a need?

Good theme examples from prior run:
- "Technical credibility beyond the squad" (recognized repeatedly by non-squad members)
- "Incident ownership and reliability" (multiple recognitions for stepping up under pressure)
- "Teaching and knowledge sharing" (consistent pattern of helping others understand, not just solve)
- "Quarter-defining ownership" (a single recognition that captures a sustained contribution)

### Step 5: Present results

For each report, write:

```
## [Name]

**[Theme 1 title]**
Narrative description with specific examples from the recognitions. Name the givers
where useful — "X (Purchase Gateway EM) recognized..." signals cross-team reach.

**[Theme 2 title]**
...

*Note: [Optional observation about volume, gaps, or caveats.]*
```

Order reports by recognition volume (most first), or alphabetically if similar.

**Do not write to a file automatically.** Present the summary in the conversation first. If Ken approves or asks to save it, write to:

```
~/Notes/engineering/leadership/content-squad/recognition-{year}.md
```

Or the range if not a full year (e.g. `recognition-2025-H1.md`).

---

## Notes

- Some recognitions are private ("Private Recognition Notification") — include them in themes but don't quote them verbatim
- Group recognitions count as one recognition per person listed, not one total
- A report with few recognitions isn't necessarily underperforming — note the gap, don't draw conclusions
- If a theme only has one data point, use hedged language: "One notable recognition for..." rather than presenting it as a pattern
