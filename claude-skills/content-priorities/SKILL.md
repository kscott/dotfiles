---
name: content-priorities
description: >
  Drive Ken's Jira board work for the Content Squad so he doesn't have to — Ken finds Jira
  exasperating and actively avoids it, so YOU operate it for him via the Atlassian MCP + REST API.
  Use this skill whenever Ken talks about: the content board / "Content Priorities" board / his
  oversight board, what's "in flight", board triage / refinement / cleanup / hygiene, epics being
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

| Column | Status | Meaning |
|---|---|---|
| Backlog | Backlog (10020) | raw, not yet refined |
| On Deck | Refine (10198) | refined, next up |
| Parked | Selected for Development (10021), Blocked (10050) | stalled / paused |
| In Progress | Started (10031) | actively driven |
| Done | Won't Do (10377), Closed (6) | shipped / killed |

Ready For Development (10034) and the other In-Progress sub-statuses (Code Review, In Review, Ready for
Acceptance, Development, Ready to Deploy, Ready for Design Review) are intentionally unmapped at the epic
level. Re-pull the config if the board may have changed.

### Changing columns (you CAN drive this, not just read it)
The public Agile API is read-only for columns, but the internal endpoint the UI uses accepts writes:
`PUT /rest/greenhopper/1.0/rapidviewconfig/columns`. Always read-modify-write the native shape — never
hand-build from scratch:
1. GET `.../rest/greenhopper/1.0/rapidviewconfig/editmodel?rapidViewId=1858` → take `.rapidListConfig.mappedColumns`.
2. Mutate only what's needed (rename a column; change a column's `mappedStatuses` to `[{id:"..."}]`).
3. **Preserve `isKanPlanColumn: true` on the Kanban backlog column** and each column's `id` — dropping the
   flag returns `400 "Kanban backlog column not found"`.
4. PUT `{currentStatisticsField:{id:"issueCount_"}, rapidViewId:1858, mappedColumns:[...]}` with headers
   `Content-Type: application/json` and `X-Atlassian-Token: no-check`.
5. Verify via the agile config GET. The original editmodel is your revert source.

### Re-ranking (timeline / board row order) — DRIVABLE, one call
Row order in the timeline and on the board is **Rank**. Unlike card colors, this IS reliably drivable:
`PUT /rest/agile/1.0/issue/rank` with `{"issues":[...keys in desired top-to-bottom order...],"rankAfterIssue":"TACO-<topEpic>"}` (or `rankBeforeIssue`). **Array order is preserved**, up to 50 issues per call, returns **204 No Content**. So a full reorder is ONE call: make the intended top epic the anchor and pass all the rest, in order, with `rankAfterIssue: <top epic>`. Use a single clean curl (no `for`-loops, no `-o` file writes — the sandbox hook blocks those shapes; a lone `curl -X PUT … --data '…'` works). Verify with `project = TACO AND issuetype = Epic AND statusCategory != Done ORDER BY Rank ASC`. **Ken never drags rows — drive this for him.** Established good order (2026-06-18): In Progress (active) → Parked → On Deck (CSS cluster first) → Backlog → evergreen containers (Ongoing Maintenance + Renovate, e.g. 4635/3403) last.

## Theme palette (epic color-coding)

Every non-Done epic carries exactly **one theme label**. Ken does NOT manage these — YOU apply and maintain them. He interacts with the *colors* (the **timeline view** "Color by → Label" is his preferred lens; also board card colors), never the labels themselves. The palette is a **small fixed vocabulary** — don't fragment it into per-epic tags. Expand it only when a genuinely new theme emerges from a team ask (then add a row here and re-commit).

| Label | Color | Theme — what belongs |
|---|---|---|
| `kotlin-retirement` | Blue | Retiring/migrating the Kotlin services (BVS, CSS, CRAS) under PROD-3011 |
| `ipn` | Green | IPN / BOWO route work + Retailer Distribution on the IPN |
| `platform-dx` | Yellow | Internal platform, infra, tech-debt, DX, dev-tooling, rules-mcp, monolith decoupling, dependency/runtime upgrades |
| `product` | Purple | Product / business-facing / saver-facing feature work |
| `ops` | Grey | Perpetual containers — Renovate, Ongoing Maintenance (on-call work folds in here — no separate on-call epic as of Q3 2026). Never "complete"; de-emphasized. |

Maintenance rules:
- **Apply the theme label when an epic is created or re-triaged** — same action, so coverage stays complete. After any epic-creation, set its theme.
- **Preserve existing non-theme labels** — set the union, never clobber. Some epics carry an extra functional label (e.g. `renovate-epic-2026` on TACO-3403, `on-call` on TACO-1912); theme labels are additive.
- Periodically run `project = TACO AND issuetype = Epic AND statusCategory != Done` and confirm none are missing a theme label; theme any stragglers (don't guess wildly — pick by the epic's nature, flag genuine ambiguity to Ken).

Surfacing the colors:
- **Timeline:** "Color by → Label" (a view toggle; Jira auto-assigns colors per label value).
- **Board card colors:** ALREADY CONFIGURED on board 1858 (Ken set it up in the UI, 2026-06-18): Card colors → strategy **Queries**, one rule per theme label (`labels = kotlin-retirement` → blue, `ipn` → green, `platform-dx` → yellow, `product` → purple, `ops` → grey). So just keep epics labeled — new epics inherit their color automatically; do NOT try to recreate the rules. (The programmatic write path was a dead end: `rapidviewconfig/cardColorStrategy` 404s and the env blocked further probing; only revisit if the scheme itself needs changing, and do it in the UI.)

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
   - **Perpetual containers** — Renovate (3403) and Ongoing System Maintenance (current: 4635, rolls
     forward each quarter). They never "close"; leave running, don't park, don't measure on burndown.
     **On-call is no longer a separate container** — the quarterly Content On-call epic was retired in
     Q3 2026 (it only existed for now-unused automation); on-call stories now parent to Ongoing Maintenance.
     Don't create or expect a quarterly on-call epic.
4. **Before closing an epic** — check for open *active* children (in-review/started); they'd be stranded.
   Re-home them (often to the current Ongoing System Maintenance epic, e.g. 4635) first. If an epic has real research worth keeping
   (e.g. all-spike investigation epics), preserve it in Confluence under the **Content Squad** page
   (id `1379893545`, space `TT`) before closing, and leave a pointer comment on the epic.

## The overdue / date sweep

Board 1858's working lens is the **timeline** ("Color by → Label"). An epic with no **Start Date**
(`customfield_10152`) or no **due date** (`duedate`) **doesn't render there** — it's invisible exactly
where Ken looks. The Monday `manager-bot` `jira-hygiene` skill won't catch this: it validates date
*sanity* (duration-in-range, dates-within-parent) across the whole component, never date *presence*, and
isn't scoped to this board. So date presence + currency on 1858 is **this** skill's job. Run on demand.

Fields: Start Date = `customfield_10152` (i.e. `cf[10152]`), due date = standard `duedate`.

**Two buckets, one read each.**

1. **Missing dates** — active-column epics lacking a start or due date. Active = In Progress (Started),
   Parked (Selected for Development, Blocked), On Deck (Refine). **Backlog is exempt** — undated raw
   epics are fine there.
   ```bash
   curl -s -u "$ATLASSIAN_API_USER:$ATLASSIAN_API_TOKEN" \
     --data-urlencode 'jql=project = TACO AND issuetype = Epic AND status IN ("Started","Selected for Development","Blocked","Refine") AND (duedate IS EMPTY OR cf[10152] IS EMPTY) ORDER BY Rank ASC' \
     --data-urlencode 'fields=summary,status,duedate,customfield_10152' --data-urlencode 'maxResults=100' \
     -G "https://ibotta.atlassian.net/rest/api/3/search/jql" \
     | jq -r '.issues[] | [.key, .fields.status.name, (.fields.customfield_10152//"NO-START"), (.fields.duedate//"NO-DUE"), .fields.summary] | @tsv'
   ```

2. **Overdue** — non-Done epics whose due date is already past.
   ```bash
   curl -s -u "$ATLASSIAN_API_USER:$ATLASSIAN_API_TOKEN" \
     --data-urlencode 'jql=project = TACO AND issuetype = Epic AND statusCategory != Done AND duedate < startOfDay() ORDER BY duedate ASC' \
     --data-urlencode 'fields=summary,status,duedate,customfield_10152' --data-urlencode 'maxResults=100' \
     -G "https://ibotta.atlassian.net/rest/api/3/search/jql" \
     | jq -r '.issues[] | [.key, .fields.status.name, (.fields.duedate//"NO-DUE"), .fields.summary] | @tsv'
   ```

**Setting dates** — top-level fields, no read-modify-write needed (unlike board columns):
```bash
curl -s -u "$ATLASSIAN_API_USER:$ATLASSIAN_API_TOKEN" -X PUT -H 'Content-Type: application/json' \
  "https://ibotta.atlassian.net/rest/api/3/issue/TACO-NNNN" \
  --data '{"fields":{"customfield_10152":"2026-06-22","duedate":"2026-08-15"}}'
```
(Or MCP `editJiraIssue` with the same field payload.)

**How to act — report + propose, then apply:**
- **Missing dates:** propose a start (≈ today if already Started, else the next refinement window) and a
  due (start + the epic's likely duration from scope). Setting/extending dates is light curation →
  announce the one-liner and apply. If you can't infer a sensible duration, ask rather than guess.
- **Overdue:** the due date slipped. Default fix is **re-date** to a realistic target, NOT a push-to-close.
  Suggest closing only if the work is genuinely done/abandoned — and closing stays **confirm-first** (check
  for stranded active children per the triage workflow).

**Honor the same exceptions as parking** — don't mis-handle a known-good epic:
- **Pre-direction foundation** (e.g. TACO-4137) — if overdue, re-date or clear the due date; never pitch as
  a quick close. Parent direction is unsettled.
- **Perpetual containers** (Ongoing Maintenance, current 4635; Renovate 3403) — carry full-period dates by
  design. When one lapses at quarter-end, roll it to the next period; don't flag as a problem. (No separate
  on-call container as of Q3 2026 — on-call folds into Ongoing Maintenance.)
- **Opportunistic long-runners** (e.g. 4320) and **non-sprint platform work** (board 641) — fine to carry
  distant due dates; don't compress them.

## Lessons that bit us (don't repeat)
- Verify board/sprint state from the API; don't infer from activity dates alone.
- "No story in the current sprint" ≠ "dead." It cleanly flags genuinely-dead epics, but over-flags the
  four exception types above. Always distinguish before recommending a park.
- Sprint membership = `sprint IN openSprints()`. Closed epics should flow to the Done column — if they
  vanish on close, the board *filter* is excluding Done (e.g. `status NOT IN (closed)`), not a mapping bug.
