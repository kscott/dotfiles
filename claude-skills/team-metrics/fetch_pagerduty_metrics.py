#!/usr/bin/env python3
"""
fetch_pagerduty_metrics.py

Fetches the primary on-call rotation for the configured PagerDuty schedule
and writes metrics_data.pagerduty.json.

This script owns its own output file. It does NOT read or merge other sources.
Use merge_metrics.js to combine all per-source files into metrics_data.json.

Requires:
  - PAGERDUTY_API_TOKEN env var (your PagerDuty API token)
  - pagerduty-api@ibotta plugin installed
  - team_config.json with a `pagerduty_primary_schedule_id` field
    (defaults to "PUL2FDL" — the Content Squad Primary schedule — if absent)

Rotation rule: PagerDuty rotations happen at 9am Monday. We always use
T09:00:00 as the `since` time so the pre-rotation window (midnight–9am) is
excluded and we don't pull in the previous week's on-call person.

Run with uv:
  PYTHONPATH="<plugin-src>" uv run --with requests python3 fetch_pagerduty_metrics.py \\
    --config  team_config.json \\
    --start   2026-05-18 \\
    --end     2026-05-24 \\
    --out     metrics_data.pagerduty.json

The plugin src path is:
  ~/.claude/plugins/marketplaces/ibotta/plugins/pagerduty-api/src
"""

import argparse
import json
import os
import sys


def die(msg):
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Fetch PagerDuty on-call assignments")
parser.add_argument("--config", required=True, help="Path to team_config.json")
parser.add_argument("--start",  required=True, help="Start date YYYY-MM-DD")
parser.add_argument("--end",    required=True, help="End date YYYY-MM-DD")
parser.add_argument("--out",    required=True, help="Path to metrics_data.pagerduty.json")
args = parser.parse_args()

# ── Load config ───────────────────────────────────────────────────────────────
try:
    with open(args.config) as f:
        config = json.load(f)
except Exception as e:
    die(f"Could not read config: {e}")

members = list(config.get("members", {}).keys())
if not members:
    die("No members found in team_config.json")

schedule_id = config.get("pagerduty_primary_schedule_id") or "PUL2FDL"

print(f"\n━━ PagerDuty Metrics Fetch ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"Schedule : {schedule_id} (primary)")
print(f"Range    : {args.start} → {args.end}  (9am Mon rotation rule)")
print(f"Output   : {args.out}")
print(f"──────────────────────────────────────────────────────────────")

# ── Import PD client ──────────────────────────────────────────────────────────
try:
    from pagerduty import SchedulesClient, PagerDutyConfig
except ImportError:
    die(
        "Could not import pagerduty client.\n"
        "  Run this script with PYTHONPATH pointing to the pagerduty-api plugin:\n"
        '    PYTHONPATH="~/.claude/plugins/marketplaces/ibotta/plugins/pagerduty-api/src" \\\n'
        "    uv run --with requests python3 fetch_pagerduty_metrics.py ..."
    )

# ── Query on-calls ────────────────────────────────────────────────────────────
oncall_names = set()
try:
    pd_config = PagerDutyConfig.from_env()
    schedules = SchedulesClient(pd_config)
    oncalls = schedules.list_on_calls(
        schedule_ids=[schedule_id],
        since=f"{args.start}T09:00:00",
        until=f"{args.end}T23:59:59",
    )
    oncall_names = {oc["user"]["summary"] for oc in oncalls.get("oncalls", [])}
    print(f"\nOn-call this week: {', '.join(sorted(oncall_names)) or '(none)'}\n")
except Exception as e:
    die(f"PagerDuty lookup failed: {e}")

# ── Build per-member output ───────────────────────────────────────────────────
# This script owns metrics_data.pagerduty.json — overwrite fresh each run.
metrics = {
    "week": {"start": args.start, "end": args.end},
    "members": {},
}

member_cfgs = config.get("members", {})
for name in members:
    # Match the config name OR an optional `pagerduty_name` alias — PagerDuty
    # may use a legal/full name (e.g. "Nathaniel Ewert-Krocker") that differs
    # from the display name in config (e.g. "Nate Ewert-Krocker").
    aliases = {name}
    pd_alias = member_cfgs.get(name, {}).get("pagerduty_name")
    if pd_alias:
        aliases.add(pd_alias)
    is_on_call = bool(aliases & oncall_names)
    metrics["members"][name] = {
        "on_call": {
            "is_on_call": is_on_call,
            "source": "pagerduty",
            "role": "primary" if is_on_call else None,
        }
    }
    if is_on_call:
        print(f"  ✅ {name}")

# ── Write ─────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
with open(args.out, "w") as f:
    json.dump(metrics, f, indent=2)

print(f"\n━━ Done ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"✅  PagerDuty data written to {args.out}\n")
