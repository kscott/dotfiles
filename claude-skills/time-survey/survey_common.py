"""Shared helpers for the time-survey skill: meeting classification,
seniority-band mapping, and largest-remainder rounding. Imported by
derive_time_survey.py and manager_row_from_doing.py."""

# A calendar/log event is a MEETING. Training / team-building / social events
# are Admin even when scheduled (per the survey definitions).
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
    """Classify a meeting/event title -> 'project' | 'nonproject' | 'admin'."""
    s = (summary or '').lower()
    for kw in ADMIN_EVENT_KW:
        if kw in s:
            return 'admin'
    if '/' in s and 'project' not in s:        # "Name / Name" => 1:1
        return 'nonproject'
    for kw in NONPROJECT_KW:
        if kw in s:
            return 'nonproject'
    for kw in PROJECT_KW:
        if kw in s:
            return 'project'
    return 'nonproject'    # ambiguous ad-hoc meetings are non-project by definition


def band_for(role):
    """Map a Workday/role title -> the survey's seniority column (or None to exclude)."""
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
        return None        # interns are excluded from the survey
    return 'Mid level'     # plain Engineer / Platform Engineer / Software Engineer


def round_to_100(d):
    """Largest-remainder rounding of a dict of floats summing to ~100 -> ints summing to 100."""
    floors = {k: int(v) for k, v in d.items()}
    rem = 100 - sum(floors.values())
    order = sorted(d, key=lambda k: d[k] - floors[k], reverse=True)
    for i in range(max(0, rem)):
        floors[order[i % len(order)]] += 1
    return floors


def as_count(v):
    return len(v) if isinstance(v, list) else (v or 0)


# ── Calendar meeting pull (shared by derive + manager overlay) ───────────────
def _is_weekday(dt):
    return dt.weekday() < 5


def _event_hours(ev):
    from datetime import datetime
    try:
        s = datetime.fromisoformat(ev['start']['dateTime'])
        e = datetime.fromisoformat(ev['end']['dateTime'])
        return max(0.0, (e - s).total_seconds() / 3600.0)
    except Exception:
        return 0.0


def pull_calendar_meetings(calendar_id, start_date, end_date):
    """Return counted meetings from a calendar as a list of dicts:
    {start, end (datetime), hours, kind ('project'|'nonproject'|'admin'), summary}.
    Applies the same skip rules as the team-metrics calendar fetcher. Lazy-imports
    the google-workspace lib so the doing-only path needs no calendar access."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from google_workspace import CalendarClient
    tz = ZoneInfo("America/Denver")
    s_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=tz)
    e_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=tz)
    cal = CalendarClient(calendar_id=calendar_id)
    out = []
    for ev in cal.get_events(start_date=s_dt, end_date=e_dt):
        if ev.get('status') == 'cancelled':
            continue
        st = ev.get('start', {})
        if 'date' in st and 'dateTime' not in st:        # all-day → not a meeting
            continue
        try:
            start = datetime.fromisoformat(st['dateTime'])
            end = datetime.fromisoformat(ev['end']['dateTime'])
        except Exception:
            continue
        if not _is_weekday(start):
            continue
        low = (ev.get('summary') or '').lower()
        if ev.get('eventType') in ('outOfOffice', 'focusTime'):
            continue
        if ev.get('transparency') == 'transparent' or ev.get('availability') == 'AVAILABILITY_FREE':
            continue
        if any(w in low for w in ('lunch', 'clockwise', 'focus time', 'heads down',
                                  'heads-down', 'do not book', 'deep work', 'no meeting')):
            continue
        atts = ev.get('attendees', [])
        mine = next((a.get('responseStatus') for a in atts
                     if a.get('email', '').lower() == (calendar_id or '').lower()), None)
        if mine == 'declined':
            continue
        if len(atts) == 0 and not ev.get('recurringEventId'):
            continue
        hrs = _event_hours(ev)
        if hrs <= 0:
            continue
        out.append({'start': start, 'end': end, 'hours': hrs,
                    'kind': classify_meeting(ev.get('summary', '')),
                    'summary': ev.get('summary', '')})
    return out
