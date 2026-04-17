#!/usr/bin/env python3
"""Fetch Google Calendar metrics for team members and merge into metrics_data.json."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--members', required=True, help='Comma-separated names or ALL')
    p.add_argument('--start', required=True, help='YYYY-MM-DD')
    p.add_argument('--end', required=True, help='YYYY-MM-DD')
    p.add_argument('--out', required=True, help='Path to metrics_data.json')
    return p.parse_args()

def is_clockwise(summary):
    s = (summary or '').lower()
    return ('❇️' in s or 'clockwise' in s or
            'lunch' in s or 'focus time' in s or
            'headsdown' in s or 'heads down' in s or
            'heads-down' in s or 'do not book' in s or
            'deep work' in s)

def is_ooo(summary):
    s = (summary or '').lower()
    return any(kw in s for kw in ['out of office', 'ooo', 'vacation', 'pto', 'holiday'])

def is_focus_block(summary):
    s = (summary or '').lower()
    return any(kw in s for kw in ['focus time', 'focus block', 'deep work',
                                   'headsdown', 'heads down', 'heads-down', 'do not book'])

def event_duration_hours(event):
    start = event.get('start', {})
    end = event.get('end', {})
    if 'dateTime' not in start:
        return 0
    try:
        s = datetime.fromisoformat(start['dateTime'])
        e = datetime.fromisoformat(end['dateTime'])
        return (e - s).total_seconds() / 3600
    except Exception:
        return 0

def is_weekday(dt):
    return dt.weekday() < 5  # Mon–Fri

def fetch_squad_ooo(squad_calendar_id, members_by_first, start_date, end_date):
    """Return {full_name: set(date)} from squad calendar 'Firstname OOO' events."""
    from google_workspace import CalendarClient
    tz = ZoneInfo("America/Denver")
    try:
        cal = CalendarClient(calendar_id=squad_calendar_id)
        events = cal.get_events(
            start_date=datetime(start_date.year, start_date.month, start_date.day, tzinfo=tz),
            end_date=datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=tz)
        )
    except Exception as e:
        print(f"  ⚠️  Could not fetch squad calendar: {e}")
        return {}

    result = {}
    for event in events:
        summary = (event.get('summary') or '').strip()
        # Match "Firstname OOO" pattern
        if not summary.lower().endswith(' ooo') and not summary.lower().endswith('-ooo'):
            continue
        first = summary.rsplit(' ', 1)[0].strip()
        full_name = members_by_first.get(first.lower())
        if not full_name:
            continue

        start_info = event.get('start', {})
        end_info = event.get('end', {})

        # All-day event
        if 'date' in start_info and 'dateTime' not in start_info:
            try:
                s = datetime.strptime(start_info['date'], '%Y-%m-%d').date()
                e = datetime.strptime(end_info['date'], '%Y-%m-%d').date()
                d = s
                while d < e:
                    if is_weekday(datetime.combine(d, datetime.min.time())) and start_date <= d <= end_date:
                        result.setdefault(full_name, set()).add(d)
                    d += timedelta(days=1)
            except Exception:
                pass
        # Timed event — count the calendar date it falls on
        elif 'dateTime' in start_info:
            try:
                dt = datetime.fromisoformat(start_info['dateTime']).date()
                if is_weekday(datetime.combine(dt, datetime.min.time())) and start_date <= dt <= end_date:
                    result.setdefault(full_name, set()).add(dt)
            except Exception:
                pass
    return result


def fetch_member_calendar(calendar_id, start_date, end_date, member_name, squad_ooo_days=None):
    from google_workspace import CalendarClient

    tz = ZoneInfo("America/Denver")  # Ibotta is Mountain Time
    start_dt = datetime(start_date.year, start_date.month, start_date.day,
                        tzinfo=tz)
    end_dt = datetime(end_date.year, end_date.month, end_date.day,
                      23, 59, 59, tzinfo=tz)

    try:
        cal = CalendarClient(calendar_id=calendar_id)
        events = cal.get_events(start_date=start_dt, end_date=end_dt)
    except Exception as e:
        print(f"  ⚠️  Could not fetch calendar for {member_name}: {e}")
        return None

    # Seed OOO days from squad calendar (fallback source)
    ooo_days = set(squad_ooo_days or [])
    meeting_hours = 0.0
    meeting_count = 0

    # Count working days in range
    working_days = sum(1 for i in range((end_date - start_date).days + 1)
                       if is_weekday(start_date + timedelta(days=i)))

    for event in events:
        summary = event.get('summary', '')
        status = event.get('status', '')

        if status == 'cancelled':
            continue

        start_info = event.get('start', {})
        end_info = event.get('end', {})

        # All-day events
        if 'date' in start_info and 'dateTime' not in start_info:
            if is_ooo(summary) or event.get('eventType') == 'outOfOffice':
                # Count unique weekdays blocked
                try:
                    s = datetime.strptime(start_info['date'], '%Y-%m-%d').date()
                    e = datetime.strptime(end_info['date'], '%Y-%m-%d').date()
                    d = s
                    while d < e:
                        if is_weekday(datetime.combine(d, datetime.min.time())):
                            if start_date <= d <= end_date:
                                ooo_days.add(d)
                        d += timedelta(days=1)
                except Exception:
                    pass
            continue

        # Skip non-weekday events
        try:
            event_dt = datetime.fromisoformat(start_info['dateTime'])
            if not is_weekday(event_dt):
                continue
        except Exception:
            continue

        # Skip Clockwise / focus blocks
        if is_clockwise(summary) or is_focus_block(summary):
            continue

        # Check if member declined
        attendees = event.get('attendees', [])
        my_response = None
        for att in attendees:
            if att.get('email', '').lower() == calendar_id.lower():
                my_response = att.get('responseStatus')
                break
        if my_response == 'declined':
            continue

        # Skip solo events (organizer only, no attendees or just self)
        if len(attendees) <= 1 and not event.get('recurringEventId'):
            # Check if it has external attendees
            if len(attendees) == 0:
                continue

        hrs = event_duration_hours(event)
        if hrs > 0:
            meeting_hours += hrs
            meeting_count += 1

    ooo_count = len(ooo_days)
    available_hours = (working_days - ooo_count) * 8
    meeting_pct = round(meeting_hours / available_hours * 100) if available_hours > 0 else 0
    avg_hrs = round(meeting_hours / max(working_days - ooo_count, 1), 2)

    result = {
        'total_meeting_hours': round(meeting_hours, 2),
        'meeting_count': meeting_count,
        'available_hours': available_hours,
        'meeting_pct': meeting_pct,
        'avg_hrs_per_day': avg_hrs,
        'ooo_days': ooo_count,
        'working_days': working_days
    }

    print(f"  {member_name}: {meeting_hours:.1f}h meetings ({meeting_count} events), "
          f"{ooo_count} OOO days, {meeting_pct}% of available time")
    return result

def main():
    args = parse_args()

    with open(args.config) as f:
        config = json.load(f)

    all_members = config['members']
    if args.members.strip().upper() == 'ALL':
        selected = list(all_members.keys())
    else:
        selected = [m.strip() for m in args.members.split(',')]

    start = datetime.strptime(args.start, '%Y-%m-%d').date()
    end = datetime.strptime(args.end, '%Y-%m-%d').date()

    print(f"\n━━ Calendar Metrics Fetch ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"Members : {', '.join(selected)}")
    print(f"Range   : {args.start} → {args.end}")
    print(f"─────────────────────────────────────────────────────────────\n")

    try:
        with open(args.out) as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {'week': {'start': args.start, 'end': args.end}, 'members': {}}

    if 'members' not in data:
        data['members'] = {}

    # Build first-name → full-name map for squad calendar OOO parsing
    members_by_first = {n.split()[0].lower(): n for n in all_members}
    squad_cal_id = config.get('squad_calendar_id')
    squad_ooo = {}
    if squad_cal_id:
        squad_ooo = fetch_squad_ooo(squad_cal_id, members_by_first, start, end)
        if squad_ooo:
            print(f"  Squad calendar OOO found: { {k: [str(d) for d in v] for k, v in squad_ooo.items()} }\n")

    for name in selected:
        if name not in all_members:
            print(f"  ⚠️  {name} not found in config, skipping")
            continue
        cal_id = all_members[name].get('calendar_id', all_members[name]['email'])
        result = fetch_member_calendar(cal_id, start, end, name, squad_ooo_days=squad_ooo.get(name))
        if result:
            if name not in data['members']:
                data['members'][name] = {}
            data['members'][name]['calendar'] = result

    with open(args.out, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n✅  Calendar metrics written to {args.out}\n")

if __name__ == '__main__':
    main()
