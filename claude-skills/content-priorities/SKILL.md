---
name: content-priorities
description: >
  Drive Ken's Jira board work for the Content Squad so he doesn't have to — Ken finds Jira
  exasperating and actively avoids it, so YOU operate it for him via the Atlassian MCP + REST API.
  Use this skill whenever Ken talks about: the content board / "Content Priorities" board / his
  oversight board, what's "in flight", board triage / grooming / cleanup / hygiene, epics being
  misplaced or mis-statused, parking epics, what can be closed soon, team siloing, WIP / work-in-
  progress concentration, sprint vs non-sprint work, opportunistic or parked or pre-direction epics,
  or generally "help me make sense of / clean up the content board." Also triggers on board IDs
  1858 / 2159 / 641 and TACO epic triage. If Ken describes a Jira-board-level task in his own words,
  reach for this even if he doesn't name it — he won't remember the name.
---

# Content Priorities — driving Ken's Jira boards

**Operating principle:** Ken avoids Jira and wants Claude to drive it. Do the work, show what you're
about to change before mutating (one line), then execute. Verify against real data — never infer board
state. Parking/moving is reversible; closing/Won't-Do is heavier — confirm intent first.

`cloudId` is always `ibotta.atlassian.net`. Project key `TACO` (id `10287`), "Content Squad".

## The three boards

| Board | ID | What it is |
|---|---|---|
| **Content Priorities** | **1858** | Ken's *personal* oversight board (kanban, filter `14598`). Epic-level "what's in flight." Edits here are his curation/hygiene — low blast radius, don't drive team process. **This is the board he means by default.** |
| **Sprint board** | **2159** | Team's scrum board. Filter is just `project = TACO` — sprint scoping happens via the active sprint, so "in the sprint" = `sprint IN openSprints()`, NOT a filter clause. |
| **Non-sprint board** | **641** | On-call + platform work. Subfilter `issuetype not in (Initiative, "Strategic Objective") AND sprint is EMPTY`. Visible at standup; deliberately NOT counted in velocity. |

Never call non-sprint work "invisible," and never pull on-call/platform work into the sprint to make it
"show up" — that distorts velocity, which is intentionally scoped to planned/committed work.

## Reading board config (the MCP can't, the REST API can)

The Atlassian MCP does **not** expose agile board configuration (columns/filter). Ken has
`ATLASSIAN_API_TOKEN` + `ATLASSIAN_API_USER` in his work-Mac env, so read it directly with curl
(values stay hidden; env vars expand in-shell):

```bash
# Columns + status mapping for a board
curl -s -u "$ATLASSIAN_API_USER:$ATLASSIAN_API_TOKEN" \
  "https://ibotta.atlassian.net/rest/agile/1.0/board/1858/configuration" \
  | jq '{board:.name, type, filterId:.filter.id, columns:[.columnConfig.columns[]|{name,statusIds:[.statuses[].id]}]}'

# A board's filter JQL
curl -s -u "$ATLASSIAN_API_USER:$ATLASSIAN_API_TOKEN" \
  "https://ibotta.atlassian.net/rest/api/3/filter/14598" | jq '{name, jql}'
```

**JQL via MCP returns huge payloads** — `searchJiraIssuesUsingJql` saves oversized results to a file.
Always request minimal `fields`, then `jq` the file; never read the raw JSON inline. For multi-epic
analysis, delegate to a subagent so the bulk output stays out of the main context.

## Board 1858 column → status map (verified 2026-06-18)

| Column | Statuses |
|---|---|
| Backlog | Refine (10198) |
| To Do | Backlog (10020), Ready For Development (10034) |
| **Parked** | Selected for Development (10021), Blocked (10050) |
| In Progress | Started (10031) |
| Done | Won't Do (10377), Closed (6) |

Quirk: the column named "Backlog" holds the *Refine* status; the "To Do" column holds the *Backlog*
status. Read column membership by status, not by name. Re-pull the config if the board may have changed.

## Status & transition IDs (TACO epic/story workflow — global transitions, verify if one fails)

Statuses: Backlog `10020`, Refine `10198`, Ready For Development `10034`, Selected for Development
`10021`, Blocked `10050`, Started `10031`, In Review `10019`, Code Review `10039`, Ready for Acceptance
`10042`, Development `3`, Won't Do `10377`, Closed `6`.

Transitions (`transitionJiraIssue`): Start Progress → Started `191` · **Park** (Selected for Development)
`421` · Blocked `351` · Won't Do `451` · Close → Closed `371` · Add to Backlog `121` · Refine `401`.

Standardize "in progress" epics on **Started** (191). Park = move to Selected for Development (421),
which lands in the Parked column. Re-parent a story with `editJiraIssue` → `{"parent":{"key":"TACO-NNNN"}}`.

## The triage workflow

1. **Misplaced epics** — epic in a To Do column but child stories are in progress / closed → should be
   In Progress. Epic in In Progress but nothing started → may belong back in To Do. (Count `Closed`
   children as real progress; `Won't Do` children are abandoned, NOT progress.)
2. **Idle / park-for-now candidates** — in-flight epic with **0 children in `openSprints()` AND 0 children
   in an In Progress statusCategory**. These aren't being driven to closure now → park to focus the board.
3. **Always-check exceptions before parking** (these look idle by sprint-presence but are NOT dead):
   - **Non-sprint platform work** (e.g. Miranda's BEP/lambda/terraform) — progressing on board 641.
   - **Opportunistic long-runners** (e.g. TACO-4320 JS→TS) — intermittent sprint presence is by design.
   - **Pre-direction foundation work** (e.g. TACO-4137 BOWO IPN) — high % done but parent initiative's
     direction unsettled; finishing is premature. Don't pitch as a push-to-close quick win.
   - **Perpetual containers** — Renovate (3403), Ongoing Maintenance (3372), On-call (4210). They never
     "close"; leave running, don't park, don't measure on burndown.
4. **Before closing an epic** — check for open *active* children (in-review/started); they'd be stranded.
   Re-home them (often to Ongoing Maintenance 3372) first. If an epic has real research worth keeping
   (e.g. all-spike investigation epics), preserve it in Confluence under the **Content Squad** page
   (id `1379893545`, space `TT`) before closing, and leave a pointer comment on the epic.

## Lessons that bit us (don't repeat)
- Verify board/sprint state from the API; don't infer from activity dates alone.
- "No story in the current sprint" ≠ "dead." It cleanly flags genuinely-dead epics, but over-flags the
  four exception types above. Always distinguish before recommending a park.
- Sprint membership = `sprint IN openSprints()`. Closed epics should flow to the Done column — if they
  vanish on close, the board *filter* is excluding Done (e.g. `status NOT IN (closed)`), not a mapping bug.
