---
name: 1on1
description: Log a 1:1 meeting with a direct report. Parses meeting notes, writes a dated notes file, and updates the person's _trends.md file. Use when Ken provides 1:1 meeting notes or a meeting summary.
allowed-tools: [Read, Write, Edit, Bash, Glob]
---

# 1:1 Notes Skill

Process 1:1 meeting notes for a direct report. Given a name and meeting notes/summary, write the dated notes file and update the person's running trends file.

## How to invoke

```
/1on1 <name> <notes>
```

Examples:
- `/1on1 Nate <paste meeting summary>`
- `/1on1 Shelbey <paste notes>`

## Base directory

All 1:1 files live under:
```
~/Notes/engineering/leadership/content-squad/1on1s/
```

Each person has their own subfolder, e.g. `nate-ewert-krocker/`. The subfolder name is derived from the person's full name: lowercase, spaces replaced with hyphens.

**Content Squad direct reports:**

| Name | Folder |
|------|--------|
| Shelbey Summers | shelbey-summers |
| Jasmine Hamou | jasmine-hamou |
| Miranda Cascione | miranda-cascione |
| Nate Ewert-Krocker | nate-ewert-krocker |
| Brian Holman | brian-holman |
| Matt Dolan | matt-dolan |

---

## Step 1 — Resolve the person and date

- Match the name from the argument (first name is sufficient) to the correct folder
- Date = today (use `date` via Bash to get current date as YYYY-MM-DD)
- Notes file path: `<base>/<folder>/<YYYY-MM-DD>.md`

---

## Step 2 — Read existing files

Read both files before writing anything:
1. The most recent prior notes file (for format reference)
2. `_trends.md` (for current themes, open action items, and the log)

---

## Step 3 — Write the notes file

Use the format from prior notes files. Standard structure:

```markdown
# <Name> — 1:1 Notes
**Date:** YYYY-MM-DD
**Duration:** ~XX min  ← omit if unknown

---

## Topics Covered

**<Topic>**
<2-4 sentence summary of what was discussed and any guidance Ken gave>

**<Topic>**
...

---

## Next Steps

| Owner | Action |
|-------|--------|
| <Name> | <action> |
| Ken | <action> |
```

Rules:
- Topics should be concise headers with substance underneath — not just topic labels
- Capture Ken's guidance, not just Nate's update
- Next Steps must clearly indicate Owner (the person's first name or Ken)
- Do not include personal/sensitive details in next steps

---

## Step 4 — Update `_trends.md`

This is the most important file. Update all four sections:

### Recurring Themes
- Add new themes if they emerged
- Update existing themes with new context (don't duplicate — evolve the bullet)
- Remove or merge themes that have been resolved or superseded

### Open Action Items
- Add all new action items from today with today's date and Owner column
- Review prior open items: if there's evidence from the notes that something was completed or resolved, update its status
- Keep the Owner column — format: `| Date | Owner | Action | Status |`
- Status values: `Open`, `Resolved — <brief note>`, `Likely resolved — <brief note>`

### Notes & Observations
- Add dated observations that give context beyond the action items
- Personal circumstances (illness, family, stress) worth noting when they affect work context
- Growth signals, communication patterns, recurring concerns
- Don't repeat what's already in Recurring Themes

### 1:1 Log
- Append one row: `| YYYY-MM-DD | <3-6 topic labels, comma separated> |`

---

## Step 5 — Confirm

After writing both files, confirm:
- Notes file path written
- _trends.md updated
- List any action items flagged for Ken (so he can act on them)

$ARGUMENTS
