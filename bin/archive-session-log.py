#!/usr/bin/env python3
"""
Runs Monday morning. Archives all complete ISO weeks from session-log.md
into the appropriate monthly archive files.

Archive location: Productivity/Archive/session-logs/session-log-YYYY-MM.md
Each week is assigned to the month containing its Thursday (ISO 8601 convention).

Handles catch-up correctly: if multiple weeks have accumulated (e.g. after the
script was failing), each week is routed to its own correct monthly archive.

iCloud Drive is inaccessible to launchd Python (TCC restriction). In live runs,
file I/O goes via osascript do shell script, which runs as the GUI user.

Usage:
  archive-session-log.py                         live run (launchd context)
  archive-session-log.py --dry-run               preview only, reads iCloud directly
  archive-session-log.py --dry-run --source FILE test against a specific file
"""

import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
SOURCE_OVERRIDE = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--source" and i+1 < len(sys.argv)), None)

if SOURCE_OVERRIDE and not DRY_RUN:
    print("ERROR: --source is only valid with --dry-run")
    sys.exit(1)

HOME = Path.home()
PRODUCTIVITY = HOME / "Library/Mobile Documents/com~apple~CloudDocs/Productivity"
SESSION_LOG = PRODUCTIVITY / "session-log.md"
ARCHIVE_DIR = PRODUCTIVITY / "Archive/session-logs"
LOG = HOME / "logs/archive-session-log.log"


def log(msg: str):
    line = f"[{date.today()}] {msg}\n"
    print(line, end="")
    with open(LOG, "a") as f:
        f.write(line)


def trim_log():
    if LOG.exists():
        lines = LOG.read_text().splitlines(keepends=True)
        if len(lines) > 100:
            LOG.write_text("".join(lines[-100:]))


def icloud_cp(src: Path, dst: Path) -> bool:
    """Copy via osascript do shell script — runs as GUI user, has iCloud Drive access."""
    script = f'do shell script "cp {shlex.quote(str(src))} {shlex.quote(str(dst))}"'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.returncode == 0


def week_monday(d: date) -> date:
    return d - timedelta(days=d.isocalendar().weekday - 1)


def archive_month(monday: date) -> str:
    """YYYY-MM for the archive a week belongs to, determined by that week's Thursday."""
    return (monday + timedelta(days=3)).strftime('%Y-%m')


def parse_header_date(line: str) -> date | None:
    if line.startswith("## ") and len(line) >= 13:
        try:
            return date.fromisoformat(line[3:13])
        except ValueError:
            return None
    return None


def read_session_log() -> list[str]:
    if SOURCE_OVERRIDE:
        return Path(SOURCE_OVERRIDE).read_text().splitlines(keepends=True)
    if DRY_RUN:
        return SESSION_LOG.read_text().splitlines(keepends=True)
    # Launchd context: stage via /tmp
    tmp_in = Path("/tmp/session-log-in.md")
    if not icloud_cp(SESSION_LOG, tmp_in):
        return []
    lines = tmp_in.read_text().splitlines(keepends=True)
    tmp_in.unlink(missing_ok=True)
    return lines


def write_archive(archive_path: Path, month_lines: list[str]):
    if DRY_RUN:
        return
    tmp_archive = Path(f"/tmp/session-log-{archive_path.stem[-7:]}.md")
    icloud_cp(archive_path, tmp_archive)  # fetch existing if present (ok if fails)
    with tmp_archive.open("a") as f:
        f.writelines(month_lines)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if not icloud_cp(tmp_archive, archive_path):
        log(f"ERROR: failed to write {archive_path.name} to iCloud")
        sys.exit(1)
    tmp_archive.unlink(missing_ok=True)


def write_session_log(new_lines: list[str]):
    if DRY_RUN:
        return
    tmp_out = Path("/tmp/session-log-out.md")
    tmp_out.write_text("".join(new_lines))
    if not icloud_cp(tmp_out, SESSION_LOG):
        log("ERROR: failed to write session-log.md back to iCloud")
        sys.exit(1)
    tmp_out.unlink(missing_ok=True)


def main():
    trim_log()

    if DRY_RUN:
        log("DRY RUN — no files will be modified")

    today = date.today()
    current_monday = week_monday(today)
    current_monday_str = current_monday.strftime('%Y-%m-%d')

    lines = read_session_log()
    if not lines:
        log("session-log.md is empty or not accessible — nothing to archive")
        return

    # Split: keep current week onwards in session-log, archive everything before
    split_index = next(
        (i for i, line in enumerate(lines)
         if line.startswith("## ") and len(line) >= 13 and line[3:13] >= current_monday_str),
        None,
    )

    if split_index == 0:
        log("No prior-week entries found — nothing to archive")
        return

    to_archive = lines if split_index is None else lines[:split_index]
    new_session = [] if split_index is None else lines[split_index:]

    # Group lines by ISO week, tracking first/last header per week
    weeks = []  # list of (week_monday_date, month_str, [lines])
    current_week_monday = None
    current_week_lines = []

    for line in to_archive:
        d = parse_header_date(line)
        if d is not None:
            wm = week_monday(d)
            if wm != current_week_monday:
                if current_week_lines:
                    weeks.append((current_week_monday, archive_month(current_week_monday), current_week_lines))
                current_week_monday = wm
                current_week_lines = []
        current_week_lines.append(line)
    if current_week_lines:
        weeks.append((current_week_monday, archive_month(current_week_monday), current_week_lines))

    if not weeks:
        log("No dateable entries found to archive")
        return

    # Group weeks by target archive file, preserving order
    by_month = defaultdict(list)
    for _, month, week_lines in weeks:
        by_month[month].extend(week_lines)

    # Process each week: report and write
    for wm, month, week_lines in weeks:
        entry_count = sum(1 for l in week_lines if l.startswith("## "))
        first = next((l.strip() for l in week_lines if l.startswith("## ")), "?")
        last = next((l.strip() for l in reversed(week_lines) if l.startswith("## ")), "?")
        archive_name = f"session-log-{month}.md"
        log(f"  {'[dry-run] ' if DRY_RUN else ''}week {wm} → {archive_name}  ({entry_count} entries)")
        log(f"    first: {first}")
        log(f"    last:  {last}")

    # Write archive files (one per month)
    for month, month_lines in sorted(by_month.items()):
        archive_path = ARCHIVE_DIR / f"session-log-{month}.md"
        write_archive(archive_path, month_lines)
        if not DRY_RUN:
            entry_count = sum(1 for l in month_lines if l.startswith("## "))
            log(f"Wrote {entry_count} entries to {archive_path.name}")

    # Write trimmed session log
    retained = sum(1 for l in new_session if l.startswith("## "))
    log(f"  {'[dry-run] ' if DRY_RUN else ''}retaining {retained} entries in session-log.md")
    write_session_log(new_session)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
