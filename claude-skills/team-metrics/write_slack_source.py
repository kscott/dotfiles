#!/usr/bin/env python3
"""
write_slack_source.py

Writes ONLY metrics_data.slack.json. Slack data is Claude-driven (channel
summaries and partial-absence detection need LLM judgment), but the
write-to-file step should be guarded so the slack writer can never
accidentally overwrite another source file.

Fool-proofing built in:
  - `--out` MUST end in `.slack.json` — otherwise refuses to write.
  - Script never reads any other source file.
  - Validates that every member referenced exists in team_config.json.
  - Validates the per-member slack dict has the required fields.
  - Writes atomically via a `.tmp` file + rename so a crash mid-write
    can't leave a corrupted source file.

Input shape (--data path, or "-" for stdin):

  {
    "Shelbey Summers": {
      "slack": {
        "total_messages": "60+",          # int or "<N>+" sentinel string
        "per_channel": [
          { "channel": "#content_squad", "count": 4,
            "summary": "1-2 sentences about what they were doing here" },
          { "channel": "#gamers", "count": 2 }    # summary optional
        ],
        "active_window": "Mon 9:56am – Fri 3:04pm"
      },
      "partial_absences": [                  # optional
        { "date": "May 22", "note": "slept poorly, going to try and rest" }
      ],
      "weekend_activity": [                  # optional
        { "date": "May 24", "channel": "#content_squad",
          "note": "responded to oncall page" }
      ]
    },
    "Jasmine Hamou": { ... }
    ...
  }

Either provide that as the top-level value, or wrap it: { "members": { ... } }.
Either form is accepted.

Run:
  python3 write_slack_source.py \\
    --config  team_config.json \\
    --start   2026-05-18 \\
    --end     2026-05-24 \\
    --data    /tmp/slack_input.json \\
    --out     metrics_data.slack.json
"""

import argparse
import json
import os
import sys
import tempfile


def die(msg, code=1):
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    sys.exit(code)


# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Write metrics_data.slack.json (slack-only, guarded)")
parser.add_argument("--config", required=True, help="Path to team_config.json")
parser.add_argument("--start",  required=True, help="Week start YYYY-MM-DD")
parser.add_argument("--end",    required=True, help="Week end YYYY-MM-DD")
parser.add_argument("--data",   required=True,
                    help='JSON file with per-member slack data, or "-" for stdin')
parser.add_argument("--out",    required=True,
                    help="Output path — MUST end in '.slack.json'")
args = parser.parse_args()

# ── Fool-proofing: refuse any output path that isn't a *.slack.json file ─────
out_path = os.path.abspath(args.out)
if not out_path.endswith(".slack.json"):
    die(
        f"--out must end in '.slack.json' (got '{args.out}').\n"
        f"This script is the slack-source writer; refusing to write to any\n"
        f"other path to prevent clobbering other per-source files."
    )

# ── Load config to validate member names ─────────────────────────────────────
try:
    with open(args.config) as f:
        config = json.load(f)
except Exception as e:
    die(f"Could not read --config: {e}")

expected_members = set((config.get("members") or {}).keys())
if not expected_members:
    die("team_config.json has no members listed")

# ── Load --data ──────────────────────────────────────────────────────────────
try:
    if args.data == "-":
        raw = json.load(sys.stdin)
    else:
        with open(args.data) as f:
            raw = json.load(f)
except Exception as e:
    die(f"Could not parse --data input: {e}")

# Accept either { "members": { ... } } or { "Name": { ... } } directly
if isinstance(raw, dict) and "members" in raw and isinstance(raw["members"], dict):
    members_in = raw["members"]
else:
    members_in = raw

if not isinstance(members_in, dict):
    die("--data must be a dict keyed by member name (or have a 'members' dict)")

# ── Validate member names ────────────────────────────────────────────────────
unknown = [n for n in members_in if n not in expected_members]
if unknown:
    die(
        f"Unknown member(s) in --data: {', '.join(unknown)}\n"
        f"Known members: {', '.join(sorted(expected_members))}"
    )

# Missing-member warning (not fatal — Claude may intentionally skip someone
# who had zero activity. Heads-up worth printing though.)
missing = [n for n in expected_members if n not in members_in]
if missing:
    print(
        f"⚠️  Warning: --data has no entry for {len(missing)} member(s): "
        f"{', '.join(missing)}.\n"
        f"   merge_metrics.js will refuse to clean up source files unless all\n"
        f"   members are present in every source. Add zero-activity entries if\n"
        f"   these members really had no Slack activity this week.\n",
        file=sys.stderr,
    )

# ── Validate per-member slack shape ──────────────────────────────────────────
REQUIRED_SLACK_FIELDS = ("total_messages", "per_channel", "active_window")
problems = []

for name, slice_ in members_in.items():
    if not isinstance(slice_, dict):
        problems.append(f"{name}: value must be a dict")
        continue

    slack = slice_.get("slack")
    if not isinstance(slack, dict):
        problems.append(f"{name}: missing 'slack' dict")
        continue

    for fld in REQUIRED_SLACK_FIELDS:
        if fld not in slack:
            problems.append(f"{name}.slack: missing required field '{fld}'")

    # total_messages: int OR a "<N>+" cap sentinel
    tm = slack.get("total_messages")
    if not (isinstance(tm, int) or (isinstance(tm, str) and tm.endswith("+"))):
        problems.append(
            f"{name}.slack.total_messages: must be an int or '<N>+' string (got {tm!r})"
        )

    # per_channel: list of {channel, count, summary?}
    pc = slack.get("per_channel")
    if not isinstance(pc, list):
        problems.append(f"{name}.slack.per_channel: must be a list")
    else:
        for i, entry in enumerate(pc):
            if not isinstance(entry, dict):
                problems.append(f"{name}.slack.per_channel[{i}]: must be a dict")
                continue
            if "channel" not in entry or "count" not in entry:
                problems.append(
                    f"{name}.slack.per_channel[{i}]: missing 'channel' or 'count'"
                )

    # Optional fields, just sanity-check the type if present
    pa = slice_.get("partial_absences")
    if pa is not None and not isinstance(pa, list):
        problems.append(f"{name}.partial_absences: if present, must be a list")
    wa = slice_.get("weekend_activity")
    if wa is not None and not isinstance(wa, list):
        problems.append(f"{name}.weekend_activity: if present, must be a list")

if problems:
    die("Validation failed:\n  - " + "\n  - ".join(problems))

# ── Build the output document ────────────────────────────────────────────────
# Pass through only the documented peer fields per member. Anything else in
# the input is dropped to avoid polluting metrics_data.json with unknown
# fields when merge_metrics.js runs.
PEER_FIELDS = ("slack", "partial_absences", "weekend_activity")

doc = {
    "week": {"start": args.start, "end": args.end},
    "members": {},
}
for name, slice_ in members_in.items():
    out_slice = {}
    for fld in PEER_FIELDS:
        if fld in slice_:
            out_slice[fld] = slice_[fld]
    doc["members"][name] = out_slice

# ── Atomic write ─────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
tmp_fd, tmp_path = tempfile.mkstemp(
    prefix=".slack-source.", suffix=".tmp",
    dir=os.path.dirname(out_path) or ".",
)
try:
    with os.fdopen(tmp_fd, "w") as f:
        json.dump(doc, f, indent=2)
    os.replace(tmp_path, out_path)
except Exception as e:
    try: os.unlink(tmp_path)
    except OSError: pass
    die(f"Failed to write {out_path}: {e}")

print(f"✅  Wrote {out_path}")
print(f"    {len(doc['members'])} member(s), week {args.start} → {args.end}")
