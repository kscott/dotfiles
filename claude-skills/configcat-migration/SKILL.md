---
name: configcat-migration
description: >
  Full project context and operating guide for the Ibotta ConfigCat migration (LaunchDarkly → ConfigCat,
  target June 30, 2026). Use this skill whenever someone asks about the ConfigCat migration, needs to
  write the weekly newsletter, wants to know team status, needs to escalate an issue, is troubleshooting
  a flag problem, or is covering for Luke Chambers as project captain. Also use when anyone asks about
  PA validation gates, IPN rail testing, SDK key rotation, mobile app version requirements, or the
  migration tracker. If the person identifies themselves as Ken Scott or Maya Shomer, load this skill
  immediately — they are covering leads and will need this context.
---

# ConfigCat Migration — Project Context & Operating Guide

**Project Captain:** Luke Chambers (out June 1–June 20, 2026)
**Engineering Lead:** Maya Shomer
**Covering EMs:** Ken Scott (June 1–18), Maya Shomer (one week overlap)

> Local reference archive (all source docs, newsletter history, flag inventory): `~/ai/configcat-migration/`

---

## ⚠️ CURRENT STATE — updated June 1, 2026 (4:20pm MT)

This guide was written at Luke's planning time. Reconciled against the May 29 newsletter and the **June 1 channel update from Praneeth**:

- **Android eval-event anomaly is RESOLVED (June 1).** The cause was events firing from users with the app **in the background** — easily filterable on the data side, not a CC bucketing bug. **Android testing is now enabled**; iOS + Android are both go for any flags going forward. The **gaming A/A test is unblocked** (Praneeth pinged Jennifer Newfield to enable it). This was the hottest item at handoff — it cleared on day one.
- **PA confidence gate CLEARED May 29** (project is GREEN). iOS validation complete (Justin Vallely removed LD entirely from iOS, PR #21018).
- **Phase 2 target is May 22** per the Analytics Validation Plan (the table below originally said May 12).

**Top open item now: the IPN rail A/A test is still unscheduled** (required for the Phase 2 gate). Chris Foley's recent channel posts are about Management API keys, not the rail test. Confirm scheduling with Chris Foley (IPN) + Praneeth this week.

---

## What This Migration Is

Ibotta is replacing LaunchDarkly with ConfigCat as its primary feature flag vendor by **June 30, 2026**.
The goal is fully internal-capable experimentation and cost optimization. All teams are migrating their
flags service-by-service. LD remains live as a kill switch throughout — nothing gets deleted until Phase 3.

---

## Phase Status & Gates

| Phase | Target | Gate | Status (as of June 1 handoff) |
|---|---|---|---|
| Phase 1 — Parallel Running | May 1 (CI: May 14) | PA sign-off, at least one live flag with clean event data | ✅ PA gate cleared May 29. Consumer Innovations extended to May 14. |
| Phase 2 — Controlled Cutover | May 22 | IPN rail A/A test pass + clean event fidelity on migrated flags | IPN test still needs to be scheduled — see below. |
| Phase 3 — Full Cutover & Cleanup | June 12 | PA sign-off + SDK key rotation confirmed per service | Tracker must show all teams confirmed before this gate opens. |

**LD full sunset: June 30, 2026.** After that, LD SDK dependencies get removed from all services.

---

## Key People & Roles

| Person | Role | Notes |
|---|---|---|
| Luke Chambers | Project Captain | Out June 1–20. Escalate to Ken (week 1), then Maya after June 8. |
| Maya Shomer | Engineering Lead | In office through ~June 8, then also OOO. Primary technical decision-maker. |
| Ken Scott | Covering EM | June 1–18. Added to leads meetings. Has been looped in. |
| Eric Meyers | PA — gate owner | Owns Phase 1 and Phase 3 sign-off gates. |
| Praneeth Yaramosu | PA — validation | ConfigCat test setup coordination with Emma English. (Also spelled "Yaramouso" in some docs.) |
| Chris Foley | IPN contact | Reach out to schedule the IPN rail A/A test. **This has not been scheduled yet as of handoff.** |
| Jon Steege | CAFE tech lead | Leading CAFE migration (~80+ flags). High confidence, ahead of schedule. |
| Matt Wells | CAFE EM | Confirmed CAFE completion by May 22. |
| Jonathan Sanchez Munoz | Mobile tech lead | Leading mobile migration. Found Android eval-event root cause; owns 6.339 fix. |
| Justin Vallely | Mobile EM | Removed LD entirely from iOS (PR #21018). In conversations on app release timing. |
| Parker Johnson | Consumer Innovations (web-v2) | CI extended deadline May 14. Dev complete by then. |
| Michael Bonini | Monolith shared client | PR #16903 merged. Consumer Foundations only has one flag to migrate. |
| Csilla Kisfaludi | ConfigCat vendor contact | csilla@configcat.com. Works Hungary hours — emails sent after 11 AM MT get a response next morning. |
| Kristie Stalberger | Escalation (week of June 1) | If Ken needs EM-level escalation before Maya is available on June 8. |

---

## Per-Team Status Summary

Teams that have **fully removed LD** from their ecosystem do not need tracking — they're done.

| Team | Status | Notes |
|---|---|---|
| Consumer Foundations | Complete | One flag migrated; monolith now has SDK key from `consumer-comms` domain. Luke's own team. |
| Mobile (iOS/Android) | iOS + Android validated (June 1) | iOS done (LD removed, PR #21018). Android eval-event anomaly resolved June 1 — cause was background-app events, filterable on the data side; Android testing now enabled, gaming test unblocked. App 6.339.0 targeted in-market by June 1 to enforce minimum version before June 30 sunset. iOS uses CC directly (OpenFeature SDK still alpha); Android uses OpenFeature multi-provider (LD primary, CC fallback). |
| Consumer Innovations (web-v2) | web-v2 & bex-api in prod; bex-v3 on the way | Phase 1 extended to May 14. Parker Johnson leading. |
| CAFE | Complete | ~113 fraud/cashout flags. No A/B test flags = no PA dependency. Jon Steege leading. |
| Monolith (shared client) | Complete | PR #16903 merged. Teams using the monolith use this shared client. |
| Audiences | In progress | Target 6/12 (AUD-3346). |
| IRP | In progress | Many old flags to delete; only ~10 to migrate. Howie Chen leading. |

**The Migration Tracker is the single source of truth for per-team status:**
https://docs.google.com/spreadsheets/d/1Z4fq4vKLYDnHRAC1eBsG7D-UDq4Ae2oL6XwPnoPuvns/edit?gid=529297798#gid=529297798

Luke will ensure it is current before June 1. If the tracker looks stale after June 1, the first action is
to ping team leads in #configcat-migration to self-report.

---

## The One Thing Ken May Need to Actively Drive

Most of the migration will be in monitor mode by June 1. **The exception is Product Analytics.**

PA may need Engineering support if there are issues surfacing from the Datalake — for example, if
`featureflagserviced` event data looks wrong, if the IPN rail A/A test surfaces unexpected behavior,
or if flag event fidelity checks fail. When that happens, Ken's job as project captain is to organize
the right engineers to respond. The PA validation plan lives here:
https://docs.google.com/document/d/1oww-Gn3TBIpUSpYnnNj1j9L0sgr0mhKsFZAMEN6aLdM/edit

**IPN rail A/A test — must not slip.** This is required for Phase 2 gate. It has not been scheduled as
of Luke's departure. Ken should confirm with Chris Foley (IPN) and Praneeth (PA) that it is scheduled
within the first few days. If it slips into June, it could block Phase 3.

---

## SDK Key Rotation (Phase 3 Gate)

Before Phase 3 can close, every team must confirm they are pointing to **enterprise prod SDK keys**,
not test environment keys. Luke is setting up a self-reporting system in the Migration Tracker before
June 1. Any team that has not self-reported by early June should be chased by Ken via #configcat-migration.

---

## Mobile App Version Requirement

Mobile must release app version **6.339.0** with dev complete by **May 27** and in market by **June 1**.
This is required to enforce a minimum app version before the LD sunset on June 30. If this release
slips, escalate to Justin Vallely immediately — it directly threatens the June 30 deadline.
**Note (June 1):** Android eval-event validation is complete — see the Current State banner.

---

## Escalation Paths

| Situation | Who to Contact |
|---|---|
| Technical flag/config issue | Maya Shomer (after June 8) |
| EM-level escalation, week of June 1 | Kristie Stalberger |
| ConfigCat vendor issue (outage, quota, config problem) | Csilla Kisfaludi — csilla@configcat.com — Hungary hours, reply next morning if after 11 AM MT |
| PA gate or event fidelity issue | Eric Meyers (gate owner), Praneeth Yaramosu |
| IPN rail test | Chris Foley |

---

## Decisions Already Made (Do Not Relitigate)

- **Multivariate/JSON flags:** handled case-by-case per team. Teams own this decision for their services. (CC has no native variant/JSON type — store JSON as a text setting and parse on fetch, or use a CDN-style approach.)
- **FE/BE shared flags:** use a % rollout flag for UX + on/off for backend. Enable backend first, roll UX second. Disable UX first, then backend. If exact segment overlap is needed, address the underlying API versioning issue or use an X-Feature header.
- **ConfigCat org taxonomy:** Org = Ibotta, Product = Domain, Config = Service/System, Setting = Flag.
- **User identifier:** `customer_id` by default.
- **Backend polling:** auto-poll at 60s default, tunable per service.
- **Frontend/mobile polling:** manual at session start.
- **Slack integration in prod:** not done, low priority. Luke will try before June 1 but no one has asked for it.

---

## Key Resources

| Resource | Link |
|---|---|
| Migration Tracker (source of truth) | https://docs.google.com/spreadsheets/d/1Z4fq4vKLYDnHRAC1eBsG7D-UDq4Ae2oL6XwPnoPuvns/edit?gid=529297798#gid=529297798 |
| Weekly Newsletter Doc | https://docs.google.com/document/d/1C89k18sB-ZjtM7g04Go1GbmuePzUeUV35M3tCP4dgbo/edit?tab=t.0 |
| PA Validation Plan | https://docs.google.com/document/d/1oww-Gn3TBIpUSpYnnNj1j9L0sgr0mhKsFZAMEN6aLdM/edit |
| Engineering Implementation Plan | `~/ai/configcat-migration/engineering-implementation-and-testing-plan.pdf` |
| How-To Guide | `~/ai/configcat-migration/how-to-guide.pdf` |
| ADR: Feature Flag SDK | https://docs.google.com/document/d/1Tf4JKjGZ_8Fm2NtIZNjJ4SU4yRIAbIzOLTp2Tlqu3i0/edit |
| Feature Flag Master Spreadsheet | https://docs.google.com/spreadsheets/d/1HwR4gEDrSOqISccrLiaggAhPsN_P3uQS2dSzmnuVQw4/edit |
| Monolith Shared Client | PR #16903 (merged) |
| Slack channel | #configcat-migration (ID: C0AG7BG54HY) |
| ConfigCat portal | app.configcat.com (Okta SSO) |
| Local reference archive | `~/ai/configcat-migration/` |

---

## Writing the Weekly Newsletter

The newsletter goes into the Weekly Newsletter Doc linked above. It is published weekly, typically
on Thursdays. Ken Scott owns the write during Luke's absence.

**Format:**

```
[Date]

EXECUTIVE SUMMARY
Status: 🟢 On Track / 🟡 At Risk / 🔴 Off Track
[2-4 sentence summary of the week's most important movement. Call out any gates at risk.]
Know someone who wants to stay informed? Reach out to Luke Chambers to get added to the distro list.

DETAILED UPDATES
[Project & Status Updates section with named shoutouts, specific flag counts or PRs where relevant,
and clear next actions. Use bold headers per workstream. End with "Key Actions / Next Steps" bullets.]
*Generated with Claude*

RESOURCES
[Standard resource block — always include all links from the Key Resources table above.]
```

**How to generate it with Claude:**

1. Pull the latest from #configcat-migration (past 7 days).
2. Check the Migration Tracker for any status changes.
3. Note any gate movements, blockers, or PA/IPN developments.
4. Ask Claude: "Write the weekly ConfigCat newsletter for [date]. Here's what happened this week: [paste Slack summary or tell Claude what changed]."

The newsletter is written in an accessible, non-technical tone for a broad audience. Blameless framing.
Shoutout individuals by name when they ship something. Keep the executive summary scannable — busy
stakeholders read only that section.
