---
name: sprint-capacity
description: >
  Evaluates a sprint's capacity and likelihood of completion for the Content Squad.
  Fetches the current or specified sprint's stories, compares total points against
  team capacity, identifies risks, and gives a completion likelihood assessment.
  Use when asked to "evaluate the sprint", "check sprint capacity", "will we finish
  the sprint", "sprint health", or "how are we tracking".
allowed-tools: Bash, Read, AskUserQuestion
---

# Sprint Capacity Skill

Evaluates sprint capacity and completion likelihood for the Content Squad (TACO project).

## Team baseline (Content Squad)

- **Sprint length:** 2 weeks
- **Team size:** 6 engineers (Shelbey, Jasmine, Miranda, Nate, Brian, Matt)
- **Typical velocity:** **48–51 pts/sprint** (sprint-committed work, from Sprints 15–20 actuals)
  - Full range: 29–61 pts; Sprint 17 (29 pts) is a known outlier — holiday/shortened sprint
  - Use 48–51 as the planning baseline; flag if current sprint is <35 or >55
  - Run `/sprint-velocity` to refresh this baseline before planning reviews
- **Capacity reducers:** PTO, on-call rotation, recurring meetings, holidays

Always check the actual sprint data and adjust for the current sprint's known absences.

---

## Workflow

### 1. Fetch the sprint

**Important:** `acli search` does not support custom fields (including story points) in `--fields`.
Fetch issue metadata first, then pull story points and sprint dates per-item via `view`.

```bash
# Step 1: Get all sprint items (metadata only)
acli jira workitem search \
  --jql "project = TACO AND sprint in openSprints()" \
  --fields "key,summary,status,assignee,issuetype" \
  --limit 100 --json
```

The `--json` flag returns a JSON **list** (not a dict). Parse keys from it, then fetch points:

```bash
# Step 2: For each key, get story points (customfield_10033) and sprint dates (customfield_10008)
acli jira workitem view TACO-XXXX --fields "*all" --json
# customfield_10033 = story points (integer or null)
# customfield_10008 = list of sprint objects with name, startDate, endDate, state
```

For a specific sprint by name, use `sprint = 'Content Sprint NN'` in the JQL instead of `openSprints()`.

### 2. Check the Content Squad calendar for absences

Always pull the Content Squad calendar for the sprint window before assessing capacity.
This is the authoritative source for OOO — don't rely on asking the user.

```python
from google_workspace import CalendarClient
from datetime import datetime
from zoneinfo import ZoneInfo

tz = ZoneInfo("America/Denver")
cal = CalendarClient(calendar_id="ibotta.com_51okdukrm1r3lifcvf0f187os8@group.calendar.google.com")
events = cal.get_events(
    start_date=datetime(YYYY, M, D, tzinfo=tz),
    end_date=datetime(YYYY, M, D, tzinfo=tz)
)
```

Run with:
```bash
uv run --with "google-workspace @ git+ssh://git@github.com/Ibotta/google-workspace-py.git" python3 -c "..."
```

From the calendar events, build a capacity table:

| Engineer | OOO days | Working days available | Effective capacity |
|----------|----------|----------------------|-------------------|
| Miranda | 6 of 10 | 4 | ~40% |
| Matt | 5 of 10 | 5 | ~50% |
| Nate | 1 of 10 | 9 | ~90% |
| Shelbey | 1 of 10 | 9 | ~90% |
| Jasmine | 0 | 10 | 100% |
| Brian | 0 | 10 | 100% |

Flag engineers who are out for the majority of week 2 — their stories need to
finish in week 1 or be handed off.

### 3. Check PagerDuty for on-call assignments

Pull the Content Squad Primary and Secondary schedules for the sprint window.
On-call load is real work that reduces story capacity.

```python
PYTHONPATH="/Users/ken.scott/.claude/plugins/cache/ibotta/pagerduty-api/1.0.0/src"

from pagerduty import SchedulesClient, PagerDutyConfig

config = PagerDutyConfig.from_env()
schedules = SchedulesClient(config)

# Content Squad Primary: PUL2FDL  |  Secondary: PTY2TZH
for sched_id, label in [('PUL2FDL', 'Primary'), ('PTY2TZH', 'Secondary')]:
    result = schedules.get_schedule(
        sched_id,
        since='SPRINT_START',   # ISO 8601
        until='SPRINT_END',
        time_zone='America/Denver'
    )
    entries = result['schedule']['final_schedule']['rendered_schedule_entries']
    for e in entries:
        print(label, e['user']['summary'], e['start'][:10], '→', e['end'][:10])
```

Run with:
```bash
PYTHONPATH="/Users/ken.scott/.claude/plugins/cache/ibotta/pagerduty-api/1.0.0/src" \
  uv run --with requests python3 -c "..."
```

Still pull both schedules for visibility, but only apply capacity reduction for **primary on-call**.
Secondary is light — backup only, treat as full capacity.

Apply **25–30% capacity reduction for primary on-call days**.
An engineer on primary for a full week loses ~25% of that week's capacity.

### 4. Build the picture

Calculate:
- **Total committed points** — sum of all pointed stories
- **Unpointed stories** — count and flag; these are hidden risk
- **Points by status:**
  - Done / Closed
  - In Progress / In Review
  - Not started (Backlog / Selected for Development)
- **Points by person** — cross-reference against calendar availability
- **Adjusted capacity** — reduce each engineer's points proportionally to their OOO days

```
Adjusted points for engineer = assigned pts × (available days / 10)
Adjusted sprint total = sum of all engineers' adjusted points
```

Flag if:
- Total committed points > 55 pts (~110% of 51 baseline) → **overcommitted**
- Total committed points < 35 pts → **underloaded** — confirm intentional or pull from backlog
- Adjusted total < committed total by >15% → **capacity gap** — OOO is material
- Any engineer is OOO for week 2 with unstarted stories → **week-2 risk**
- More than 20% of stories are unpointed → **hidden risk**
- Any single engineer carries >40% of the sprint points → **concentration risk**
- On-call engineer has a full sprint load → **on-call squeeze**

### 4. Check sprint progress (if mid-sprint)

If the sprint is in progress, calculate burn rate:

```
Days elapsed / Total sprint days = % of time used
Points done / Total committed points = % of work done

If % work done < % time used − 15%: at risk
If % work done > % time used: ahead of pace
```

Also check: are there any stories with no movement since sprint start?

### 5. Deliver the assessment

```
## Sprint: [Sprint Name]
**Period:** Wed Mar 25 – Wed Apr 8

### Capacity
| | Points |
|---|---|
| Committed | 28 |
| Done | 0 |
| Ready to Deploy | 1 |
| In Progress | 13 |
| Not Started | 14 |
| Unpointed | 0 ✅ |

### Absences (from Content Squad calendar)
| Engineer | OOO | Days lost | Impact |
|----------|-----|-----------|--------|
| Matt | Apr 2–15 | 5 of 10 | Stories must finish week 1 |
| Miranda | Apr 3–4, Apr 6–11 | 6 of 10 | Stories must finish week 1 |
| Nate | Mar 27 | 1 of 10 | Minimal |
| Shelbey | Apr 3–4 | 1 of 10 | Minimal |

### Load by Engineer (adjusted for OOO)
| Engineer | Assigned | OOO adj. | Stories | Notes |
|----------|----------|----------|---------|-------|
| Jasmine | 6 | 6 | TACO-2788, TACO-3156 | |
| Miranda | 6 | 2.4 ⚠️ | TACO-3887, TACO-3120 | Out week 2 — must start now |
| Shelbey | 5 | 4.5 | TACO-3886 | |
| Nate | 5 | 4.5 | TACO-3486 | |
| Brian | 4 | 4 | TACO-3935, TACO-3789 | |
| Matt | 2 | 1 ⚠️ | TACO-3942 | Out week 2 — must close this week |

**Adjusted total: ~22 pts effective capacity vs 28 committed**

### Assessment
🔴 **At Risk** — OOO reduces effective capacity by ~21%. Matt and Miranda
together carry 8 pts with very limited week-2 availability.

### Risks
- TACO-3887 (Miranda, 5pts, not started) — she's out Apr 3 through end of sprint
- TACO-3942 (Matt, carryover) — repeated deprioritization; must close this week
- Effective capacity ~22 pts vs 28 committed if OOO holds

### Recommendation
Miranda should start TACO-3887 immediately; it needs to be in review by Apr 2.
Matt needs to close TACO-3942 by Apr 1. Consider pulling TACO-3887 to next sprint
if Miranda can't start it today.
```

**Likelihood ratings:**
- 🟢 **On Track** — committed ≤ adjusted capacity, good distribution, <10% unpointed
- 🟡 **At Risk** — mild overcommit, unpointed stories, or moderate OOO impact
- 🔴 **At Risk** — OOO materially reduces capacity, key stories unstarted, or carryover pattern

---

## Notes

- Content Squad calendar ID: `ibotta.com_51okdukrm1f3lifcvf0f187os8@group.calendar.google.com`
- On-call engineer: assume ~25–30% capacity reduction during their on-call week
- Pair with `/sprint-point` to close the unpointed story gap before finalizing the assessment
- Pair with `/sprint-velocity` to verify the baseline before sprint planning
- Jira project: TACO | Ibotta instance: ibotta.atlassian.net
