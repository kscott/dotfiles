#!/usr/bin/env python3
"""Build Ken's own (Manager column) time-survey row from his `doing` log.

`doing` is the best source for Ken's row: it's contemporaneous, time-stamped,
in his own words, and `--section Work` already excludes personal/home/Trinity/
homelab entries. `@meeting` tags split meeting vs. heads-down time.

Bucketing (per the skill's rules, from a manager's lens):
  - Entry with an explicit @ts-dev / @ts-proj / @ts-nonproj / @ts-admin tag
    -> that bucket wins (opt-in override, meant for the survey week).
  - @meeting entry -> classify title: Project vs Non-project (training/outings -> Admin).
  - Non-meeting Work entry -> Admin by default (board hygiene, briefs, planning,
    metrics, email/Slack are management, not shipped product). Counts as
    Development ONLY if tagged @ts-dev — being technical in approach is not Dev.

Durations are computed from date/end_date (the JSON time/duration fields are
unreliable). Percentages are the proportion of logged Work time per bucket,
normalized to 100% (handles overlaps and partial logging).

Usage:
  python3 manager_row_from_doing.py --start 2026-06-22 --end 2026-06-26 [--out f.json]
"""
import argparse, json, subprocess, sys
from datetime import datetime
from survey_common import classify_meeting, round_to_100, ADMIN_EVENT_KW

CATS = ['Development Activity', 'Project Meetings', 'Non-project meetings', 'Admin and other']
TS_TAG = {'ts-dev': 'Development Activity', 'ts-proj': 'Project Meetings',
          'ts-nonproj': 'Non-project meetings', 'ts-admin': 'Admin and other'}


def fetch_doing(start, end):
    rng = f"{start} to {end} 11:59pm"
    r = subprocess.run(['doing', 'show', '--section', 'Work', '--from', rng, '--output', 'json'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"doing failed: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(r.stdout)
    return data.get('items', data if isinstance(data, list) else [])


def hours(item):
    try:
        s = datetime.fromisoformat(item['date'])
        e = datetime.fromisoformat(item['end_date'])
        return max(0.0, (e - s).total_seconds() / 3600.0)
    except Exception:
        return 0.0


def clean_title(title):
    """Strip doing's trailing @tag / @done(...) annotations before classifying —
    otherwise a timestamp like @done(... 11:15) matches the '1:1' keyword."""
    return title.split(' @')[0].strip()


def bucket(item):
    tags = [t.lower() for t in item.get('tags', [])]
    title = clean_title(item.get('title', ''))
    low = title.lower()
    for tag, cat in TS_TAG.items():        # explicit override wins
        if tag in tags:
            return cat
    if 'meeting' in tags:
        kind = classify_meeting(title)
        return {'project': 'Project Meetings', 'nonproject': 'Non-project meetings',
                'admin': 'Admin and other'}[kind]
    # non-meeting Work entry
    if any(kw in low for kw in ADMIN_EVENT_KW):
        return 'Admin and other'
    return 'Admin and other'    # manager default; Dev only via explicit @ts-dev


MEETING_CAT = {'project': 'Project Meetings', 'nonproject': 'Non-project meetings',
               'admin': 'Admin and other'}


def item_window(it):
    try:
        return (datetime.fromisoformat(it['date']), datetime.fromisoformat(it['end_date']))
    except Exception:
        return None


def already_logged(cm, windows):
    """True if a calendar meeting overlaps a logged doing meeting by >50% of the
    SHORTER of the two windows (doing and calendar durations often differ)."""
    cm_dur = (cm['end'] - cm['start']).total_seconds()
    if cm_dur <= 0:
        return True
    for ws, we in windows:
        ov = (min(cm['end'], we) - max(cm['start'], ws)).total_seconds()
        shorter = min(cm_dur, (we - ws).total_seconds())
        if ov > 0 and shorter > 0 and ov / shorter > 0.5:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True)
    ap.add_argument('--end', required=True)
    ap.add_argument('--calendar', help="calendar id (e.g. ken.scott@ibotta.com). When set, uses "
                                        "the full-week ANCHOR model: meetings come from the calendar "
                                        "(complete), the rest of the week is non-meeting work split "
                                        "Dev/Admin by the doing ratio. Needs the google-workspace lib.")
    ap.add_argument('--hours', type=float, default=40.0,
                    help="working hours in the week (default 40; subtract FTO/holidays)")
    ap.add_argument('--out')
    args = ap.parse_args()

    items = fetch_doing(args.start, args.end)

    if not args.calendar:
        # doing-only: proportional over logged Work time
        sums = {c: 0.0 for c in CATS}
        detail = []
        for it in items:
            h = hours(it)
            if h <= 0:
                continue
            c = bucket(it)
            sums[c] += h
            detail.append((round(h, 2), c, clean_title(it.get('title', ''))[:70]))
        total = sum(sums.values())
        if total <= 0:
            print("No timed Work entries found.", file=sys.stderr); sys.exit(1)
        pct = round_to_100({c: sums[c] / total * 100 for c in CATS})
        print(f"\n=== Manager row (doing only) · {args.start} → {args.end} ===")
        print(f"  {total:.1f}h logged Work time\n")
        _emit(detail, pct, sums)
        _write(args, pct)
        return

    # ── Anchor model ────────────────────────────────────────────────────────
    # Non-meeting Dev/Admin ratio comes from doing; meeting hours come from the
    # (complete) calendar; the rest of the ~40h week is non-meeting time.
    from survey_common import pull_calendar_meetings
    doing_dev = doing_admin = 0.0
    for it in items:
        if 'meeting' in [t.lower() for t in it.get('tags', [])]:
            continue                      # meetings come from the calendar in anchor mode
        h = hours(it)
        if h <= 0:
            continue
        if bucket(it) == 'Development Activity':
            doing_dev += h
        else:
            doing_admin += h
    dev_ratio = doing_dev / (doing_dev + doing_admin) if (doing_dev + doing_admin) else 0.0

    s = datetime.strptime(args.start, '%Y-%m-%d').date()
    e = datetime.strptime(args.end, '%Y-%m-%d').date()
    proj_h = nonproj_h = admin_mtg_h = 0.0
    mtg_detail = []
    for cm in pull_calendar_meetings(args.calendar, s, e):
        if cm['kind'] == 'project':
            proj_h += cm['hours']
        elif cm['kind'] == 'admin':
            admin_mtg_h += cm['hours']
        else:
            nonproj_h += cm['hours']
        mtg_detail.append((round(cm['hours'], 2), MEETING_CAT[cm['kind']], cm['summary'][:70]))
    total_mtg = proj_h + nonproj_h + admin_mtg_h
    non_meeting = max(0.0, args.hours - total_mtg)

    sums = {
        'Development Activity': non_meeting * dev_ratio,
        'Project Meetings': proj_h,
        'Non-project meetings': nonproj_h,
        'Admin and other': admin_mtg_h + non_meeting * (1 - dev_ratio),
    }
    pct = round_to_100({c: sums[c] / args.hours * 100 for c in CATS})

    print(f"\n=== Manager row (calendar-anchored, {args.hours:.0f}h week) · {args.start} → {args.end} ===")
    print(f"  meetings from calendar: {total_mtg:.1f}h ({len(mtg_detail)} mtgs) · "
          f"non-meeting: {non_meeting:.1f}h · doing Dev/Admin ratio: {dev_ratio*100:.0f}%/{(1-dev_ratio)*100:.0f}%\n")
    for h, c, t in sorted(mtg_detail, key=lambda x: x[1]):
        print(f"  {h:>5.2f}h  [{c.split()[0]:<11}]  {t}")
    print(f"  {non_meeting:>5.2f}h  [non-meeting]  split Dev/Admin from doing ({doing_dev:.1f}h dev / {doing_admin:.1f}h admin logged)")
    print("\n  Manager column:")
    for c in CATS:
        print(f"    {c:<22} {pct[c]:>3}%   ({sums[c]:.1f}h)")
    _write(args, pct)


def _emit(detail, pct, sums):
    for h, c, t in sorted(detail, key=lambda x: x[1]):
        print(f"  {h:>5.2f}h  [{c.split()[0]:<11}]  {t}")
    print("\n  Manager column:")
    for c in CATS:
        print(f"    {c:<22} {pct[c]:>3}%   ({sums[c]:.1f}h)")


def _write(args, pct):
    if args.out:
        json.dump({c: pct[c] for c in CATS}, open(args.out, 'w'), indent=2)
        print(f"\n  wrote {args.out} (feed to fill_survey.py as the Manager entry)")


if __name__ == '__main__':
    main()
