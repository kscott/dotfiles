---
name: retailer-distribution
description: >
  Operating guide for the Ibotta "Retailer Distribution on the IPN" initiative (Ken Scott, captain).
  Use this skill whenever someone needs the weekly status update, the Wednesday check-in, E2E testing
  planning, scheduling a working session with the tech leads, team/critical-path status, or anything
  about the Captain Plan, seams, or banner validation. ALWAYS use it to produce the Friday weekly
  update — it owns the full publish flow (Slack channel + Confluence + local archive + distribution-list
  DMs), which is easy to do incompletely. Trigger on: "retailer distro update", "weekly update",
  "Wednesday check-in", "E2E test plan", "retailer distribution status", "schedule the working session".
---

# Retailer Distribution on the IPN — Operating Guide

**Captain:** Ken Scott · **PM (day-to-day):** Adrienne Debigare · **PM (consultative):** Jed Staufer · **Architect:** Garrett Mayer
**Target:** backend APIs ready by **end of Q2 (June 30, 2026)** to support Quoting Tool integration in Q3.

> **What it is:** decoupling retailer-targeted offers from legacy D2C retailer IDs so offers can be distributed across the IPN by *banner*. RDef is the translation layer (client side = retailers, publisher side = banners). **MVP** = backend APIs only. **v1** = Ibotta App (D2C) migrated to IPN rails (follow-on; not required by end of Q2).

## This skill is process. The facts live in supporting files — read them first.

Everything that changes (people, Slack IDs, hard IDs, team status, quirks) lives in `~/ai/retailer-distribution/`. Don't hardcode any of it here — read it from source each time:

| Need | File |
|---|---|
| Status, dependencies, ADR questions, timeline/LOE, **Reference IDs** (channel, Confluence space/parent, E2E sheet), team quirks | `Captain Plan - Retailer Distribution on the IPN.md` |
| **People & Slack IDs** — tech leads, EMs, stakeholders, and the weekly distribution list | `Weekly Update Distribution List.md` |
| Friday-update **template** + Past Updates **archive** + Wednesday check-in template | `Weekly Updates.md` |
| Background / architecture | `CONTEXT.md`, `D2C Fields…`, `IPN Purchase Data Flows.md` |

> The Captain Plan §6 "Reference IDs" block has every ID this flow needs. Pull IDs from there — never paste them into this skill.

## Cadence (async; sync only when a decision needs it)

- **Wednesday** — post the check-in to the channel (live, so leads reply in thread).
- **Friday** — aggregate into the weekly update and publish it everywhere (below). Read the Wednesday thread replies first.

---

## THE FRIDAY WEEKLY UPDATE — full flow (do ALL of it)

1. **Gather.** Read the Captain Plan (§3 LOE table, §1 people, §2 open ADRs, §6 Reference IDs). Read the channel for the week. Read the **Wednesday check-in thread** replies — that's the primary team-status input. Pull Jira detail if a team called out tickets.
2. **Draft** using the template in `Weekly Updates.md`. Slack **mrkdwn** (`_italic_` headers, `*bold*`, `•` bullets, `<url|text>` links, `:large_green_circle:` / `:large_yellow_circle:` / `:red_circle:` status). ~30-second readable. **Show Ken the draft before posting.**
3. On approval, **publish to all four places** (this is the part that's easy to do incompletely):
   - **a. Slack** — post **live** to the initiative channel. Not a draft.
   - **b. Confluence** — create a page in the PG space, child of the weekly-update parent page (IDs in Captain Plan §6), titled **`Weekly Update — Week of [Month Day], 2026`**. Mirror the prior week's structure (Status / Progress this week / Team status / Critical path / Watch items, plus any "Decided this week"). `contentFormat: html`.
   - **c. Archive** — prepend the finalized update to the **Past Updates** section of `Weekly Updates.md` (newest first) with both **Confluence:** and **Slack:** links.
   - **d. Distribution-list DMs** — Slack-DM each person in the **"Weekly Updates"** section of `Weekly Update Distribution List.md` a short note + the Confluence link. (They're stakeholders kept in the loop; tech leads/EMs already get it via the channel.)

DM template:
> Retailer Distribution weekly update (Week of [Month Day]) is posted — :large_green_circle: on track. [one-line TL;DR]. Full writeup: <CONFLUENCE_URL|Confluence>

---

## THE WEDNESDAY CHECK-IN

Post the check-in template (in `Weekly Updates.md`) **live** to the channel — never a draft; leads reply in thread. Use the **Monday** date for "Week of". Tag the tech-lead seams (pull current handles from the Distribution List). On Friday, read the thread before drafting; if a team didn't reply, note "no update".

---

## E2E testing

**Boundaries / seams** (also the sheet's tabs):
- **Distribution** — Program API → ODS (PA→RDef, RDef→ODS, NG→RDef, NG→ODS)
- **Purchase** — Purchase Gateway → Match (NG→PG, PG→Match)
- **Publisher (D2C) ↔ IPN** — RDef → Content (RewardUpdated); Content ↔ Network Graph (v1, not an MVP gate)

**Approach:** async fill via the sheet stalled once (empty on deadline). The pattern that unstuck it: **seed every seam with a draft test plan** (one happy path + a few edge cases per seam, suggested owners, marked draft), then run a **working session** for leads to supplement and confirm owners. Framing to keep: the seed is a *deliberately shallow first pass — each lead owns fully testing their own seams.*

### Reading/writing the E2E sheet with the `gws` CLI (sheet ID in Captain Plan §6)
The `gws` CLI prints a `Using keyring backend: keyring` line to stdout — **strip it before parsing JSON** (`| grep -v "keyring backend"`).

```bash
# read a tab
gws sheets +read --spreadsheet <SHEET_ID> --range "'Distribution — PA→ODS'!A1:I50" --format json 2>/dev/null | grep -v "keyring backend"

# write/overwrite a range (RAW keeps text literal — arrows, em-dashes)
gws sheets spreadsheets values update \
  --params '{"spreadsheetId":"<SHEET_ID>","range":"'"'"'Distribution — PA→ODS'"'"'!A1","valueInputOption":"RAW"}' \
  --json '{"values":[["row","of","cells"]]}'
```
For multi-row writes, build the payload in Python and call `gws` via `subprocess` (avoids shell-quoting pain with arrows/em-dashes). Confluence / Jira / Calendar use the `claude_ai` Atlassian + Google MCP tools.

## Conventions

- **Slack format = mrkdwn** for both the channel and DMs (single `*bold*`, `_italic_`, `<url|text>`), matching the archived templates.
- **Estimating a team's landing date:** check how that team tracks work before promising a date — not all of them point or run sprints (the Captain Plan notes the quirks per team). If there's no points/sprint data, keep it qualitative or ask the EM/tech lead.
- **Before inviting people or attributing work,** confirm current roles from the Distribution List — personnel changes (handoffs, interim EMs) are recorded there, not here.
