#!/usr/bin/env python3
"""
fetch_atlassian_metrics.py

Fetches Jira + Confluence data and writes metrics_data.atlassian.json.

This script owns its own output file — does NOT read or merge other sources.
On-call data lives in fetch_pagerduty_metrics.py.
Use merge_metrics.js to combine all per-source files into metrics_data.json.

Requires:
  - ATLASSIAN_API_USER env var (your Ibotta email)
  - ATLASSIAN_API_TOKEN env var (Atlassian API token from id.atlassian.com)
  - atlassian-api@ibotta plugin installed (provides the atlassian client library)

Run with uv:
  PYTHONPATH="<plugin-src>" uv run --with requests python3 fetch_atlassian_metrics.py \\
    --config  team_config.json \\
    --members "Name One,Name Two"  (or "ALL") \\
    --start   2026-03-16 \\
    --end     2026-03-20 \\
    --out     metrics_data.atlassian.json

The plugin src path is:
  ~/.claude/plugins/marketplaces/ibotta/plugins/atlassian-api/src
"""

import argparse
import json
import os
import sys


def die(msg):
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    sys.exit(1)


# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="Fetch Jira + Confluence metrics")
parser.add_argument("--config",  required=True, help="Path to team_config.json")
parser.add_argument("--members", required=True, help='"Name One,Name Two" or "ALL"')
parser.add_argument("--start",   required=True, help="Start date YYYY-MM-DD")
parser.add_argument("--end",     required=True, help="End date YYYY-MM-DD")
parser.add_argument("--out",     required=True, help="Path to metrics_data.atlassian.json")
args = parser.parse_args()

# ── Load config ───────────────────────────────────────────────────────────────
try:
    with open(args.config) as f:
        config = json.load(f)
except Exception as e:
    die(f"Could not read config: {e}")

all_members = list(config.get("members", {}).keys())
if args.members.strip().upper() == "ALL":
    members = all_members
else:
    members = [m.strip() for m in args.members.split(",") if m.strip()]

for m in members:
    if m not in config["members"]:
        die(f'Member "{m}" not found in team_config.json')

# ── Credentials ───────────────────────────────────────────────────────────────
api_user  = os.environ.get("ATLASSIAN_API_USER") or os.environ.get("JIRA_API_USER")
api_token = os.environ.get("ATLASSIAN_API_TOKEN") or os.environ.get("JIRA_API_TOKEN")

if not api_user or not api_token:
    die(
        "Missing Atlassian credentials.\n"
        "  Add to your ~/.zshrc:\n"
        '    export ATLASSIAN_API_USER="your.email@ibotta.com"\n'
        '    export ATLASSIAN_API_TOKEN="your_token_here"\n'
        "  Get a token at: https://id.atlassian.com/manage-profile/security/api-tokens"
    )

os.environ["ATLASSIAN_API_USER"]  = api_user
os.environ["ATLASSIAN_API_TOKEN"] = api_token

# ── Import atlassian client ───────────────────────────────────────────────────
try:
    from atlassian import JiraClient, ConfluenceClient, AtlassianConfig
except ImportError:
    die(
        "Could not import atlassian client.\n"
        "  Run this script with PYTHONPATH pointing to the atlassian-api plugin:\n"
        '    PYTHONPATH="~/.claude/plugins/marketplaces/ibotta/plugins/atlassian-api/src" \\\n'
        "    uv run --with requests python3 fetch_atlassian_metrics.py ..."
    )

config_atl = AtlassianConfig.from_env()
jira       = JiraClient(config_atl)
confluence = ConfluenceClient(config_atl)

WEEK_START = args.start
WEEK_END   = args.end
BASE_URL   = "https://ibotta.atlassian.net"

JIRA_FIELDS = ["summary", "status", "assignee", "issuetype", "updated", "resolutiondate", "priority", "customfield_10033"]

print(f"\n━━ Atlassian Metrics Fetch ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"Members : {', '.join(members)}")
print(f"Range   : {WEEK_START} → {WEEK_END}")
print(f"Output  : {args.out}")
print(f"──────────────────────────────────────────────────────────────")

# ── Look up Jira account IDs by email ─────────────────────────────────────────
def get_jira_account_id(email):
    try:
        users = jira.get("/user/search", params={"query": email})
        if users:
            return users[0]["accountId"]
    except Exception as e:
        print(f"  ⚠️  Could not look up {email}: {e}", file=sys.stderr)
    return None


def jira_ticket(issue):
    key = issue["key"]
    f   = issue["fields"]
    pts = f.get("customfield_10033")
    return {
        "key":     key,
        "summary": f.get("summary", ""),
        "status":  f.get("status", {}).get("name", ""),
        "type":    f.get("issuetype", {}).get("name", ""),
        "url":     f"{BASE_URL}/browse/{key}",
        "points":  int(pts) if pts is not None else None,
    }


def conf_page(item):
    return {
        "title":  item.get("title", ""),
        "action": "created",
        "url":    BASE_URL + item.get("_links", {}).get("webui", ""),
    }


# This script owns metrics_data.atlassian.json — overwrite fresh each run.
metrics = {
    "week": {"start": WEEK_START, "end": WEEK_END},
    "members": {},
}

# ── Fetch per member ──────────────────────────────────────────────────────────
for name in members:
    member_cfg = config["members"][name]
    email      = member_cfg.get("email") or member_cfg.get("jira_account", "")

    print(f"\n  → {name} ({email})")

    account_id = get_jira_account_id(email)
    if not account_id:
        print(f"    ⚠️  Jira account not found for {email} — skipping Jira/Confluence")
        metrics["members"][name] = {
            "jira": {
                "assigned_total": 0, "closed_this_week": 0,
                "active": [], "closed_tickets": [],
                "_note": f"Jira account not found for {email}",
            },
            "confluence": {
                "created": 0, "updated": 0, "commented": 0, "pages": [],
            },
        }
        continue

    # ── JIRA ─────────────────────────────────────────────────────────────────
    # Active tickets (not done)
    jql_active = f'assignee = "{account_id}" AND statusCategory != Done ORDER BY updated DESC'
    try:
        active_raw = jira.search_issues(jql_active, fields=JIRA_FIELDS, max_results=30)
        active = [jira_ticket(i) for i in active_raw.get("issues", [])]
    except Exception as e:
        print(f"    ⚠️  Jira active tickets error: {e}", file=sys.stderr)
        active = []

    # Closed this week
    jql_closed = (
        f'assignee = "{account_id}" AND statusCategory = Done '
        f'AND updated >= "{WEEK_START}" AND updated <= "{WEEK_END}" '
        f'ORDER BY updated DESC'
    )
    try:
        closed_raw = jira.search_issues(jql_closed, fields=JIRA_FIELDS, max_results=20)
        closed = [jira_ticket(i) for i in closed_raw.get("issues", [])]
    except Exception as e:
        print(f"    ⚠️  Jira closed tickets error: {e}", file=sys.stderr)
        closed = []

    closed_pts = sum(t["points"] for t in closed if t["points"] is not None)
    print(f"    Jira active : {len(active)}")
    print(f"    Jira closed : {len(closed)} (this week) — {closed_pts} pts")

    # ── CONFLUENCE ───────────────────────────────────────────────────────────
    # Pages created this week
    cql_created = (
        f'creator = "{account_id}" AND type = page '
        f'AND created >= "{WEEK_START}" AND created <= "{WEEK_END}"'
    )
    try:
        created_raw = confluence.search_cql(cql_created, limit=20)
        created_pages = [conf_page(i) for i in created_raw.get("results", [])]
    except Exception as e:
        print(f"    ⚠️  Confluence created pages error: {e}", file=sys.stderr)
        created_pages = []

    # Pages updated (contributor) this week, excluding ones just created
    cql_updated = (
        f'contributor = "{account_id}" AND type = page '
        f'AND lastModified >= "{WEEK_START}" AND lastModified <= "{WEEK_END}"'
    )
    try:
        updated_raw = confluence.search_cql(cql_updated, limit=20)
        created_titles = {p["title"] for p in created_pages}
        updated_pages = [
            {**conf_page(i), "action": "updated"}
            for i in updated_raw.get("results", [])
            if i.get("title") not in created_titles
        ]
    except Exception as e:
        print(f"    ⚠️  Confluence updated pages error: {e}", file=sys.stderr)
        updated_pages = []

    # Comments
    cql_comments = (
        f'creator = "{account_id}" AND type = comment '
        f'AND created >= "{WEEK_START}" AND created <= "{WEEK_END}"'
    )
    try:
        comments_raw = confluence.search_cql(cql_comments, limit=20)
        comment_count = comments_raw.get("totalSize", 0)
    except Exception as e:
        comment_count = 0

    all_conf_pages = created_pages + updated_pages
    print(f"    Confluence pages created : {len(created_pages)}")
    print(f"    Confluence pages updated : {len(updated_pages)}")

    # ── Write into metrics ────────────────────────────────────────────────────
    metrics["members"][name] = {
        "jira": {
            "assigned_total":    len(active),
            "closed_this_week":  len(closed),
            "points_this_week":  closed_pts,
            "active":            active,
            "closed_tickets":    closed,
        },
        "confluence": {
            "created":   len(created_pages),
            "updated":   len(updated_pages),
            "commented": comment_count,
            "pages":     all_conf_pages,
        },
    }

# ── Write back ────────────────────────────────────────────────────────────────
with open(args.out, "w") as f:
    json.dump(metrics, f, indent=2)

print(f"\n━━ Done ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
print(f"✅  Jira + Confluence data written to {args.out}")
print()
