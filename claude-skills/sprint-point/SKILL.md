---
name: sprint-point
description: >
  Suggests story point values for unpointed Jira stories using the Content Squad
  Story Point Rubric. Fetches unpointed stories from a sprint or backlog, analyzes
  each story's summary and description, and recommends a point value with reasoning.
  Use when asked to "point stories", "estimate stories", "suggest points", or
  "help with backlog refinement".
allowed-tools: Bash, Read, AskUserQuestion
---

# Sprint Point Skill

Suggests story point values for unpointed Jira stories using the Content Squad rubric.

## Rubric (source of truth)

~/Notes/engineering/leadership/content-squad/Story Point Rubric.md

**Scale summary:**
| Points | Signal |
|--------|--------|
| 1 | Obvious, clean, no surprises — a few hours |
| 2 | Clear scope, straightforward — ~1 day |
| 3 | Understood, minor unknowns — 2–3 days |
| 5 | Real unknowns, needs investigation — 3–5 days |
| 8 | Not well understood, lots of open questions — week+ |
| 13+ | Too large or unclear — break it down first |

**Rules:**
- No half-points; round up when in doubt
- Points cover everything to Done: dev, review, acceptance
- 13+ means stop and decompose — flag it, don't just point it

---

## Workflow

### 1. Get the stories

If the user specifies a sprint or provides story keys, use those.
Otherwise, fetch unpointed stories from the TACO project:

**Important:** `acli search` does not support custom fields in `--fields`. Use `--json` and parse
the returned list. To get description or story points, follow up with `view` per item.

```bash
# Unpointed stories (backlog + active, not done)
# "Story Points" is EMPTY works in JQL even though it can't be in --fields
acli jira workitem search \
  --jql "project = TACO AND issuetype = Story AND \"Story Points\" is EMPTY AND statusCategory != Done" \
  --fields "key,summary,status,assignee" \
  --limit 20 --json
```

The result is a JSON **list**. For each key, fetch full details:
```bash
acli jira workitem view TACO-XXXX --fields "*all" --json
# description is in fields.description (Atlassian Document Format — extract .content[].content[].text)
# story points: customfield_10033 (null = unpointed)
# sprint: customfield_10008 (list of sprint objects with name, startDate, endDate)
```

For a specific sprint:
```bash
acli jira workitem search \
  --jql "project = TACO AND issuetype = Story AND sprint in openSprints() AND \"Story Points\" is EMPTY" \
  --fields "key,summary,status,assignee" \
  --limit 20 --json
```

For a specific epic:
```bash
acli jira workitem search \
  --jql "project = TACO AND issuetype = Story AND \"Epic Link\" = TACO-XXXX AND \"Story Points\" is EMPTY" \
  --fields "key,summary,status,assignee" \
  --limit 20 --json
```

### 2. Analyze each story

For each story, evaluate:
- **Clarity** — is the scope well-defined or ambiguous?
- **Complexity** — how many systems, files, or concepts are involved?
- **Uncertainty** — are there open questions, unknowns, or dependencies?
- **Effort** — roughly how long would a competent engineer take, including review?

Apply the rubric. Flag any story that looks like a 13+ and recommend decomposition.

### 3. Present recommendations

Show a table with your suggestion and one-sentence reasoning for each:

```
| Key | Summary | Suggested Points | Reasoning |
|-----|---------|-----------------|-----------|
| TACO-1234 | Add retry logic to SQS consumer | 3 | Well-scoped, existing pattern to follow; minor uncertainty around error handling edge cases |
| TACO-1235 | Migrate CC2 to Kubernetes | 13+ | Too broad — needs breakdown into phases before pointing |
```

**Do not apply points to Jira automatically.** Present recommendations and wait for Ken to confirm each one (or confirm all at once). Only after approval:

```bash
acli jira workitem edit --key "TACO-XXXX" --field "story_points=3"
```

### 4. Flag stories needing decomposition

For any 13+ story, call it out explicitly with a suggestion for how to break it down:
- Could it be a spike + implementation stories?
- Can it be split by layer (API, data, UI)?
- Is there a smaller slice that delivers value independently?

---

## Notes

- Read the full rubric at `~/Notes/engineering/leadership/content-squad/Story Point Rubric.md` before scoring — especially the calibration section
- When in doubt between two values, ask: "would a competent engineer be surprised by anything here?" If yes, go higher
- On-call items should also be pointed — same scale
