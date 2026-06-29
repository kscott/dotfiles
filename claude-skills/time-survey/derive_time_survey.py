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

TZ = ZoneInfo("America/Denver")

# ── Meeting classification ──────────────────────────────────────────────────
# A calendar event with others is a MEETING. Training / team-building / social
# events are Admin even though they're scheduled (per the survey definitions).
ADMIN_EVENT_KW = ['training', 'workshop', 'hackathon', 'hack-a-thon', 'team building',
                  'team-building', 'offsite', 'off-site', 'outing', 'celebration',
                  'party', 'social', 'happy hour', 'lunch', 'coffee', 'onboarding',
                  'orientation', 'myr', 'mid-year', 'learning', 'book club', 'rockies',
                  'game', 'volunteer']
NONPROJECT_KW = ['1:1', '1-1', 'one on one', 'standup', 'stand-up', 'all-hands',
                 'all hands', 'town hall', 'office hours', 'retro', 'skip level',
                 'skip-level', 'first team', 'em weekly', ' ems', 'staff meeting',
                 'welcome', 'intro', 'hangout', 'check-in', 'check in', 'demo']
PROJECT_KW = ['backlog', 'refinement', 'planning', 'sprint', 'kanban', 'scrum',
              'design', 'architecture', 'arch ', 'code review', 'working session',
              'data contract', 'kickoff', 'migration', 'bowo', 'ipn', 'retailer',
              'configcat', 'selection router', 'gsi', 'spike', 'incident',
              'postmortem', 'post-mortem', 'rca', 'epic', 'roadmap', 'review',
              'discussion', 'sync', 'estimation', 'pairing']


def classify_meeting(summary):
    s = (summary or '').lower()
    for kw in ADMIN_EVENT_KW:
        if kw in s:
            return 'admin'
    # "Name / Name" titles are almost always 1:1s
    if '/' in s and 'project' not in s:
        return 'nonproject'
    for kw in NONPROJECT_KW:
        if kw in s:
            return 'nonproject'
    for kw in PROJECT_KW:
        if kw in s:
            return 'project'
    return 'nonproject'   # ambiguous ad-hoc meetings are non-project by definition


def is_weekday(dt):
    return dt.weekday() < 5


def event_hours(ev):
    try:
        s = datetime.fromisoformat(ev['start']['dateTime'])
        e = datetime.fromisoformat(ev['end']['dateTime'])
        return max(0.0, (e - s).total_seconds() / 3600.0)
    except Exception:
        return 0.0


def pull_meeting_split(calendar_id, start_date, end_date):
    """Return (project_h, nonproject_h, admin_event_h) from the live calendar,
    applying the same skip rules as the team-metrics calendar fetcher."""
    from google_workspace import CalendarClient
    s_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=TZ)
    e_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=TZ)
    cal = CalendarClient(calendar_id=calendar_id)
    events = cal.get_events(start_date=s_dt, end_date=e_dt)
    proj = nonproj = admin_ev = 0.0
    for ev in events:
        if ev.get('status') == 'cancelled':
            continue
        st = ev.get('start', {})
        if 'date' in st and 'dateTime' not in st:        # all-day → not a meeting
            continue
        try:
            dt = datetime.fromisoformat(st['dateTime'])
        except Exception:
            continue
        if not is_weekday(dt):
            continue
        summ = ev.get('summary', '')
        low = summ.lower()
        et = ev.get('eventType')
        if et in ('outOfOffice', 'focusTime'):
            continue
        if ev.get('transparency') == 'transparent' or ev.get('availability') == 'AVAILABILITY_FREE':
            continue
        if any(w in low for w in ('lunch', 'clockwise', 'focus time', 'heads down',
                                  'heads-down', 'do not book', 'deep work', 'no meeting')):
            continue
        atts = ev.get('attendees', [])
        mine = next((a.get('responseStatus') for a in atts
                     if a.get('email', '').lower() == calendar_id.lower()), None)
        if mine == 'declined':
            continue
        if len(atts) == 0 and not ev.get('recurringEventId'):
            continue
        hrs = event_hours(ev)
        if hrs <= 0:
            continue
        kind = classify_meeting(summ)
        if kind == 'project':
            proj += hrs
        elif kind == 'admin':
            admin_ev += hrs
        else:
            nonproj += hrs
    return proj, nonproj, admin_ev


def overhead_meeting_split(total_meeting_h, working_days):
    """Fallback when no calendar pull: model non-project overhead as daily
    standup + a weekly 1:1, rest of meeting time → project."""
    nonproj = min(total_meeting_h, 0.4 * working_days + 0.75)
    proj = max(0.0, total_meeting_h - nonproj)
    return proj, nonproj, 0.0


def as_count(v):
    return len(v) if isinstance(v, list) else (v or 0)


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


def round_to_100(d):
    """Largest-remainder rounding of a dict of floats summing to ~100."""
    floors = {k: int(v) for k, v in d.items()}
    rem = 100 - sum(floors.values())
    order = sorted(d, key=lambda k: d[k] - floors[k], reverse=True)
    for i in range(rem):
        floors[order[i % len(order)]] += 1
    return floors


def band_for(role):
    r = (role or '').lower()
    if 'manager' in r:
        return 'Manager'
    if 'distinguished' in r:
        return 'Distinguished'
    if 'principal' in r:
        return 'Principal'
    if 'staff' in r:
        return 'Staff'
    if 'senior' in r:
        return 'Senior'
    if 'intern' in r:
        return None        # interns excluded from the survey
    return 'Mid level'     # plain Engineer / Platform Engineer


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
