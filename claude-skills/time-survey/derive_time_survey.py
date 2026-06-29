#!/usr/bin/env python3
"""Derive Engineering Time Study percentages from observed data.

FALLBACK for when a team member doesn't self-report their split. Reads a
team-metrics `metrics_data.json` (GitHub / Jira / on-call signals) and pulls
each person's calendar to classify meeting time, then estimates the four
survey buckets:

  Development Activity | Project Meetings | Non-project meetings | Admin & other

These are ESTIMATES to sanity-check or stand in for a missing self-report —
not ground truth. Self-reported numbers always win when available.

Run (calendar pull needs the google-workspace lib):

  uv run --with "google-workspace @ git+ssh://git@github.com/Ibotta/google-workspace-py.git" \\
    --with requests python3 derive_time_survey.py \\
    --metrics ~/ai/team-metrics/metrics_data.json \\
    --config  ~/ai/team-metrics/team_config.json \\
    --start 2026-06-22 --end 2026-06-26 \\
    --out /tmp/time_survey_derived.json

Add --no-calendar to skip the pull and use a recurring-overhead meeting model
(less accurate, but works with no calendar access).
"""
import argparse, json, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from survey_common import classify_meeting, band_for, round_to_100, as_count

TZ = ZoneInfo("America/Denver")


def pull_meeting_split(calendar_id, start_date, end_date):
    """(project_h, nonproject_h, admin_event_h) from the live calendar."""
    from survey_common import pull_calendar_meetings
    proj = nonproj = admin_ev = 0.0
    for m in pull_calendar_meetings(calendar_id, start_date, end_date):
        if m['kind'] == 'project':
            proj += m['hours']
        elif m['kind'] == 'admin':
            admin_ev += m['hours']
        else:
            nonproj += m['hours']
    return proj, nonproj, admin_ev


def overhead_meeting_split(total_meeting_h, working_days):
    """Fallback when no calendar pull: model non-project overhead as daily
    standup + a weekly 1:1, rest of meeting time → project."""
    nonproj = min(total_meeting_h, 0.4 * working_days + 0.75)
    proj = max(0.0, total_meeting_h - nonproj)
    return proj, nonproj, 0.0


def dev_ratio(role, prs, jira, on_call):
    """Fraction of NON-meeting time that is hands-on Development for this person."""
    if 'manager' in (role or '').lower():
        return 0.15
    signal = (as_count(prs.get('opened')) + as_count(prs.get('prs_merged'))
              + 0.5 * as_count(prs.get('reviews_given')) + as_count(jira.get('closed_this_week')))
    r = 0.85 if signal >= 5 else 0.75 if signal >= 2 else 0.55
    if on_call:
        r = min(0.90, r + 0.05)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--metrics', required=True)
    ap.add_argument('--config', required=True)
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--out')
    ap.add_argument('--no-calendar', action='store_true')
    args = ap.parse_args()

    metrics = json.load(open(args.metrics))
    config = json.load(open(args.config))
    roles = {n: m.get('role', '') for n, m in config.get('members', {}).items()}
    cal_ids = {n: m.get('calendar_id') or m.get('email') for n, m in config.get('members', {}).items()}
    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()

    people = {}
    for name, m in metrics.get('members', {}).items():
        cal = m.get('calendar', {})
        avail = cal.get('available_hours') or 40
        total_mtg = cal.get('total_meeting_hours', 0)
        wd = cal.get('working_days', 5)
        if args.no_calendar:
            proj, nonproj, admin_ev = overhead_meeting_split(total_mtg, wd)
        else:
            try:
                proj, nonproj, admin_ev = pull_meeting_split(cal_ids.get(name, name), start, end)
            except Exception as e:
                print(f"  ⚠️  calendar pull failed for {name}: {e}; using overhead model", file=sys.stderr)
                proj, nonproj, admin_ev = overhead_meeting_split(total_mtg, wd)
        meetings = proj + nonproj + admin_ev
        non_meeting = max(0.0, avail - meetings)
        r = dev_ratio(roles.get(name, ''), m.get('prs', {}), m.get('jira', {}),
                      m.get('on_call', {}).get('is_on_call'))
        development = non_meeting * r
        admin = non_meeting * (1 - r) + admin_ev
        raw = {
            'Development Activity': development / avail * 100,
            'Project Meetings': proj / avail * 100,
            'Non-project meetings': nonproj / avail * 100,
            'Admin and other': admin / avail * 100,
        }
        people[name] = {'band': band_for(roles.get(name, '')), 'role': roles.get(name, ''),
                        'pct': round_to_100(raw), 'avail_h': avail}

    # group by band, average the per-person percentages
    bands = {}
    for name, p in people.items():
        b = p['band']
        if not b:
            continue
        bands.setdefault(b, []).append(p['pct'])
    band_avg = {}
    for b, lst in bands.items():
        avg = {k: sum(x[k] for x in lst) / len(lst) for k in lst[0]}
        band_avg[b] = round_to_100(avg)

    out = {'week': {'start': args.start, 'end': args.end},
           'people': people, 'band_avg': band_avg}
    if args.out:
        json.dump(out, open(args.out, 'w'), indent=2)

    # human-readable
    cats = ['Development Activity', 'Project Meetings', 'Non-project meetings', 'Admin and other']
    print(f"\n=== Derived time-survey estimate · {args.start} → {args.end} ===\n")
    print("Per person:")
    for name, p in sorted(people.items(), key=lambda kv: (kv[1]['band'] or 'z', kv[0])):
        pc = p['pct']
        print(f"  {name:24} [{p['band'] or 'excluded'}]  "
              f"Dev {pc['Development Activity']:>3}%  Proj {pc['Project Meetings']:>3}%  "
              f"NonProj {pc['Non-project meetings']:>3}%  Admin {pc['Admin and other']:>3}%")
    print("\nBy seniority band (what would go in the sheet):")
    for b, pc in band_avg.items():
        print(f"  {b:14} Dev {pc['Development Activity']:>3}%  Proj {pc['Project Meetings']:>3}%  "
              f"NonProj {pc['Non-project meetings']:>3}%  Admin {pc['Admin and other']:>3}%")


if __name__ == '__main__':
    main()
