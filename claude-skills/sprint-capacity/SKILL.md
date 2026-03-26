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

### 2. Build the picture

Calculate:
- **Total committed points** — sum of all pointed stories
- **Unpointed stories** — count and flag; these are hidden risk
- **Points by status:**
  - Done / Closed
  - In Progress / In Review
  - Not started (Backlog / Selected for Development)
- **Points by person** — is load distributed evenly or concentrated?
- **On-call impact** — who is on call this sprint? Subtract ~25–30% of their capacity.

### 3. Assess capacity

```
Available capacity = (working days in sprint) × (team size) × 8h × 0.6
  (0.6 = 60% of time available for sprint work after meetings, reviews, etc.)

Effective capacity in points = available capacity / avg hours per point
  (use 4h/point as a rough default; adjust if team velocity suggests otherwise)
```

Flag if:
- Total committed points > 55 pts (~110% of 51 baseline) → **overcommitted**
- Total committed points < 35 pts → **underloaded** — confirm intentional or pull from backlog
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

Present a concise summary:

```
## Sprint: [Sprint Name]
**Period:** Mon Mar 23 – Fri Apr 5

### Capacity
| | Points |
|---|---|
| Committed | 47 |
| Done | 18 |
| In Progress | 14 |
| Not Started | 15 |
| Unpointed | 3 stories ⚠️ |

### Load by Engineer
| Engineer | Points | Notes |
|----------|--------|-------|
| Jasmine | 12 | On-call week 1 — effective capacity reduced |
| Miranda | 9 | |
| Shelbey | 8 | |
| Nate | 8 | |
| Brian | 6 | |
| Matt | 4 | 3 stories unpointed |

### Assessment
🟡 **At Risk** — 47 points is within range but 3 unpointed stories add hidden risk.
Jasmine's on-call load may slow progress on TACO-XXXX.

### Risks
- TACO-XXXX has not moved since sprint start — needs check-in
- 3 Matt stories unpointed — run /sprint-point to size before mid-sprint
- If unpointed stories average 5 pts, effective total is ~62 — overcommitted

### Recommendation
Drop one 8-point story to backlog, or confirm Matt's stories are small (≤2 pts each).
```

**Likelihood ratings:**
- 🟢 **On Track** — committed ≤ velocity, good distribution, <10% unpointed
- 🟡 **At Risk** — mild overcommit, unpointed stories, or concentrated load
- 🔴 **At Risk / Overcommitted** — >120% velocity, significant unknowns, key engineer constrained

---

## Notes

- Always ask about PTO or known absences before finalizing the assessment — calendar data helps but isn't always complete
- On-call engineer: assume ~25–30% capacity reduction during their on-call week
- Pair with `/sprint-point` to close the unpointed story gap before finalizing the assessment
- Jira project: TACO | Ibotta instance: ibotta.atlassian.net
