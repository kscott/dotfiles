---
name: time-survey
description: >-
  Fill out Ibotta's quarterly Engineering Time Study for Ken's team. Accounting
  surveys EMs one week per quarter for how each engineer level splits time across
  Development / Project meetings / Non-project meetings / Admin. Use whenever Ken
  mentions the "time study", "time survey", "Jellyfish survey", needs to fill the
  Accounting time-study sheet, or asks to estimate where his team's (or his own)
  time went for a given week. Handles self-reported splits AND deriving estimates
  from Jira / GitHub / calendar when people don't respond.
---

# Engineering Time Study

Accounting runs this **once per quarter**, for **one specified week**, to interpret
Jellyfish data for financial records (capex/opex). It is **not** a productivity or
efficiency measure — say so if anyone worries. Ken (the EM) fills one tab per his team.

## The four buckets (memorize these)

| Bucket | Definition | Typical signals |
|---|---|---|
| **Development Activity** | design, coding, installation, testing, on-call, bug fixes, maintenance | GitHub PRs/reviews/commits, Jira dev stories closed, PagerDuty on-call |
| **Project Meetings** | meetings *directly* about current dev efforts/projects | calendar: backlog/refinement/planning, design/arch reviews, kanban, data-contract, initiative syncs |
| **Non-project meetings** | 1:1s, company stand-ups, ad-hoc meetings | calendar: `Name / Name` 1:1s, standups, all-hands, EM syncs |
| **Admin and other** | email/Slack, non-coding dev (workshops/training materials), coaching/mentoring, team building, training sessions, hackathons | residual; async coordination; status writeups |

**Each level's four numbers MUST total 100%.** Report **% of working (non-FTO) time** —
if someone was out 2 days, it's the split of the days they worked, not padded.

## The operating rule for bucketing (this resolves the hard calls)

- **On the calendar, synchronous, with others → a Meeting.** Project vs. Non-project by topic.
  - 1:1s, standups, all-hands, EM/leadership syncs, ad-hoc → **Non-project**.
  - Backlog/planning/design/arch/kanban/data-contract/initiative work syncs → **Project**.
- **Not a calendar meeting →** either **Development** (if it's coding/design/testing/maintenance/on-call) or **Admin** (everything else).
- **Async coordination is Admin, not a meeting.** Writing a status update, posting a Slack check-in, the retailer-distribution weekly update — these are "email and Slack" → **Admin**. Only a live RD *working session* is a Project meeting.
- **Scheduled ≠ meeting when the activity is explicitly Admin.** Training sessions, team outings, hackathons, MYR sessions, social events sit in **Admin** even though they're on the calendar.
- **Being technical in your *approach* to management work does not make it Development.** Jira board hygiene, writing a director brief off a security analysis, decomposing work into Jira stories, building a design/decision doc — these produce *management artifacts*, not shipped product → **Admin** (a design doc that feeds real implementation can be Development; use judgment). For an EM, real hands-on Development is usually small.
- **On-call time is Development.**

**Report the truth for the week they ask about. Never flex a bucket up or down toward a "normal" or "ideal" week.** (Ken is firm on this.)

## Workflow

### 1. Find the sheet and the survey week
The sheet title contains the week (e.g. "Engineering Time Study - Week of Jun 22-26, 2026").
Read the **Instructions** tab to confirm categories/week. Each team gets a tab (a copy of
"Response - COPY ME" renamed to the team). For Ken it's the **Content Squad** tab.
Read it with the `gws` CLI:
```
gws sheets +read --spreadsheet <ID> --range "'Content Squad'!A1:J30" --format json
```

### 2. Roster, Manager column, and active levels
The team tab auto-fills `Members:` and `# of team members` from the Roster (row 4-5).
Layout: row 7 = seniority headers, rows 8-11 = the four buckets, row 13 = auto Percent Total,
row 15 = "Additional hours above 40".

Column map: **B** Associate · **C** Mid level · **D** Senior · **E** Staff · **F** Principal · **G** Distinguished · **H** Manager.
Row map: **8** Development · **9** Project Meetings · **10** Non-project meetings · **11** Admin.
**Only fill levels that have members.** Leave empty levels blank. **Interns are excluded** (not in the roster).

### 3. Title → seniority-band mapping
Map each member's Workday/role title to a sheet column:
`Distinguished* → Distinguished`, `Principal* → Principal`, `Staff* → Staff`,
`Senior* → Senior`, plain `Engineer` / `Platform Engineer` / `Software Engineer` (no modifier) `→ Mid level`,
`*Intern → excluded`, the EM → **Manager**.
Confirm against the Roster — titles in `~/ai/team-metrics/team_config.json` can be stale
(verify promotions; e.g. Jasmine moved Platform→Senior in 2026). When unsure, ask Ken.

### 4. Gather each person's split — self-report first, derive second
**Preferred: self-reported in a DM.** Ken usually asks the team in standup to DM him their
split. Search each member's DM (needs the private Slack search; Ken's request to read DMs is
consent):
```
from:<@SLACK_ID> to:me after:<week_start_minus_1>   (channel_types=im)
```
Look for percentages OR hours. **If reported in hours, convert to % of their week** (e.g.
26h dev / 40h = 65%). Honor their numbers as-is.

**Fallback when someone doesn't respond: derive from data** with `derive_time_survey.py`
(reads a team-metrics `metrics_data.json` + pulls calendars). See script header for the
command. **Limitations — be honest about these:**
- Development % and overall shape come out roughly right for engaged ICs.
- The **project-vs-non-project meeting split is weak** (keyword classifier on event titles).
- **Admin is under-counted** — non-coding work that leaves no calendar/GitHub/Jira trace is invisible.
- So: use derived numbers to fill non-responders and to sanity-check responders, but prefer self-reports. Flag derived rows as estimates to Ken.

### 5. Ken's own row (Manager column)
Estimate from his **work calendar + the session log**, NOT `doing` (his `doing` is mostly
personal/home/Trinity/homelab and must be excluded). Meetings come straight off the calendar
(project vs non-project per the rule above). Non-meeting work for an EM is overwhelmingly Admin
(board hygiene, kickoff, metrics, briefs, planning, email/Slack); genuine Development is usually
near zero unless he actually shipped code that week.

### 6. Average by band, round to 100
If a level has multiple members, average their four numbers. Round to whole numbers with
**largest-remainder** so each column still totals exactly 100 (both scripts do this).

### 7. Write the sheet
```
python3 fill_survey.py --spreadsheet <ID> --tab "Content Squad" --data /tmp/survey_values.json [--dry-run]
```
Data JSON: `{"Mid level": {"Development Activity": .., "Project Meetings": .., "Non-project meetings": .., "Admin and other": ..}, "Senior": {...}, "Distinguished": {...}, "Manager": {...}}`.
Values render as `X%` (USER_ENTERED). Verify row 13 shows 100% for each filled column afterward.

### 8. "Additional hours above 40"
Row 15 — only if someone worked beyond 40h that week. Default blank. Ask Ken; don't invent overtime.

## Scripts
- `derive_time_survey.py` — estimate the four buckets per person + per band from `metrics_data.json` + calendars (fallback for non-responders / sanity check).
- `fill_survey.py` — write a band→percentages JSON into the team tab via `gws` (validates each column = 100%).

## Notes
- This is an org-shared sheet Accounting reads — show Ken the grid before writing, and confirm the title→band mapping.
- The team-metrics pipeline (`team-metrics` skill) is the natural data source; run/refresh it for the survey week first if `metrics_data.json` is stale.
