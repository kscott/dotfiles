---
name: sprint-velocity
description: >
  Calculates real sprint velocity for the Content Squad by analyzing completed
  sprints. Fetches done points per sprint, queries non-sprint work in the same
  windows, and produces a velocity table with estimates clearly marked.
  Use when asked to "calculate velocity", "what's our velocity", "establish
  a baseline", "how many points do we usually finish", or "velocity history".
allowed-tools: Bash, Read, AskUserQuestion
---

# Sprint Velocity Skill

Calculates historical sprint velocity for the Content Squad (TACO project).

## Team context

- **Squad:** Shelbey, Jasmine, Miranda, Nate, Brian, Matt
- **Sprint cadence:** 2 weeks
- **Current naming:** "Content Sprint NN" — increment NN for each sprint

---

## Workflow

### 1. Determine sprint range

Default: last 6 completed sprints. Accept a number if the user specifies (e.g. "last 8 sprints").
Determine the most recent closed sprint number by querying a known recent item:

```bash
acli jira workitem search \
  --jql "project = TACO AND sprint in closedSprints()" \
  --fields "key" --limit 1 --json
# Returns a list. Take the first non-null item's key, then:
acli jira workitem view KEY --fields "*all" --json
# Sprint info is in customfield_10008 — list of sprint objects with name, startDate, endDate, state
```

### 2. Fetch sprint-committed done points

For each sprint (e.g. "Content Sprint 20"):

```bash
# Step 1: get all items in the sprint
acli jira workitem search \
  --jql "project = TACO AND sprint = 'Content Sprint NN'" \
  --fields "key,summary,status,issuetype" \
  --limit 100 --json
# Returns a list (not a dict). Filter nulls. Only include issuetype: Story, Bug, Task.

# Step 2: for each key, fetch story points
acli jira workitem view TACO-XXXX --fields "customfield_10033,issuetype,status" --json
# customfield_10033 = story points (integer or null if unpointed)
# status.statusCategory.key == "done" means Done
```

Calculate:
- **Total committed** — sum of all pointed items
- **Done pts** — sum of pointed items where statusCategory = done
- **Carryover** — committed minus done (if > 0)
- **Unpointed count** — items with null points (flag as hidden capacity)

### 3. Fetch non-sprint completed work

For the same date window, find work done outside sprints. This catches bugs,
hotfixes, and unplanned items resolved during the sprint period.

```bash
acli jira workitem search \
  --jql "project = TACO AND sprint is EMPTY
         AND statusCategory = Done
         AND resolutiondate >= \"YYYY-MM-DD\"
         AND resolutiondate <= \"YYYY-MM-DD\"
         AND issuetype in (Story, Bug, Task)
         AND summary !~ \"Renovate\"
         AND summary !~ \"Automated PR\"
         AND assignee in (
           shelbey.summers@ibotta.com,
           jasmine.hamou@ibotta.com,
           miranda.cascione@ibotta.com,
           nate.ewertkrocker@ibotta.com,
           brian.holman@ibotta.com,
           matt.dolan@ibotta.com
         )" \
  --fields "key,summary,status" --limit 50 --json
```

**Important:** Filter by assignee to squad members only — without this, the query
picks up product, design, and other team items that inflate the count.

For each returned item, fetch points via `view` as in Step 2.
For unpointed non-sprint items, apply **2 pts as a conservative estimate** and
mark all such values clearly as *(est.)* in output.

### 4. Identify sprint date ranges

Sprint dates come from `customfield_10008` on any item in that sprint.
If exact dates aren't available for older sprints, estimate by working backwards
from the most recent known sprint start at 2-week intervals.

### 5. Present the velocity table

```
## Content Squad Velocity — Sprints NN–NN

### Sprint-committed work

| Sprint | Period | Done pts | Committed | Carryover |
|--------|--------|----------|-----------|-----------|
| Sprint 20 | Mar 11–Mar 25 | 44 | 44 | — |
| Sprint 19 | Feb 25–Mar 11 | 44 | 44 | — |
| Sprint 18 | Feb 11–Feb 25 | 58 | 63 | 5 |
| Sprint 17 | Jan 28–Feb 11 | 29 ⚠️ | 29 | — |
| Sprint 16 | Jan 14–Jan 28 | 61 | 61 | — |
| Sprint 15 | Dec 31–Jan 14 | 50 | 50 | — |

⚠️ Sprint 17 is an outlier (11 items vs typical 20–26) — likely holiday/shortened sprint.

### Non-sprint work (squad members only)

| Sprint period | Items | Pointed pts | Unpointed | Est. pts |
|---------------|-------|-------------|-----------|----------|
| Sprint 20 period | 7 | 8 | 3 | 6 *(est.)* |
| ... | | | | |

### Velocity baseline

| Scope | Avg done pts/sprint |
|-------|-------------------|
| All 6 sprints (sprint work only) | 48 |
| Excl. outlier Sprint 17 | 51 |
| With non-sprint work (known pts only) | 55 |
| With non-sprint work (incl. estimates†) | 58 *(est.)* |

†Estimated values apply 2 pts per unpointed item. Treat as a floor, not a ceiling.

### Recommendation
Use **48–51 pts** as the planning baseline for sprint-committed work.
Non-sprint work adds real capacity but is hard to predict — account for it
qualitatively (e.g. on-call weeks typically consume ~5–10 unplanned pts).
```

### 6. Flag outliers

Call out any sprint where:
- Done pts < 35 — likely holiday, team event, or unusual circumstances
- Carryover > 10 pts — persistent overcommitment pattern
- Non-sprint items > 20 in a period — data may be noisy; verify filter

---

## Notes

- Story points: `customfield_10033` (via `acli jira workitem view` only — not available in `search --fields`)
- Sprint info: `customfield_10008` — list of sprint objects with `name`, `startDate`, `endDate`, `state`
- `search --json` returns a **list**, not a dict — filter nulls before iterating
- Sprint name format: `"Content Sprint NN"` — use exact name in JQL
- Jira project: TACO | Ibotta instance: ibotta.atlassian.net
- Pair with `/sprint-capacity` to apply the baseline to the current sprint assessment
