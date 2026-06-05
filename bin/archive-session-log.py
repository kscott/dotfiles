#!/usr/bin/env python3
"""
Runs Monday morning. Archives all complete ISO weeks from session-log.md
into the appropriate monthly archive files.

Archive location: Productivity/Archive/session-logs/session-log-YYYY-MM.md
Each week is assigned to the month containing its Thursday (ISO 8601 convention).

Handles catch-up correctly: if multiple weeks have accumulated (e.g. after the
script was failing), each week is routed to its own correct monthly archive.

iCloud Drive is inaccessible to launchd Python (TCC restriction). File I/O
on iCloud paths goes via osascript do shell script, which runs as the GUI
user and has the necessary access.
"""

import shlex
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

HOME = Path.home()
PRODUCTIVITY = HOME / "Library/Mobile Documents/com~apple~CloudDocs/Productivity"
SESSION_LOG = PRODUCTIVITY / "session-log.md"
ARCHIVE_DIR = PRODUCTIVITY / "Archive/session-logs"
LOG = HOME / "logs/archive-session-log.log"

TMP_SESSION = Path("/tmp/session-log.md")


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
    """Copy a file via osascript do shell script (runs as GUI user, has iCloud Drive access; launchd Python doesn't)."""
    script = f'do shell script "cp {shlex.quote(str(src))} {shlex.quote(str(dst))}"'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.returncode == 0


def week_monday(d: date) -> date:
    return d - timedelta(days=d.isocalendar().weekday - 1)


def archive_month(monday: date) -> str:
    """YYYY-MM for the archive a week belongs to, determined by that week's Thursday."""
    return (monday + timedelta(days=3)).strftime('%Y-%m')


def parse_header_date(line: str) -> date | None:
    """Extract date from a ## YYYY-MM-DD header line. Returns None if not parseable."""
    if line.startswith("## ") and len(line) >= 13:
        try:
            return date.fromisoformat(line[3:13])
        except ValueError:
            return None
    return None


def main():
    trim_log()

    today = date.today()
    current_monday = week_monday(today)
    current_monday_str = current_monday.strftime('%Y-%m-%d')

    if DRY_RUN:
        log("DRY RUN — no files will be modified")

    # Copy session log from iCloud to /tmp
    if not icloud_cp(SESSION_LOG, TMP_SESSION):
        log("session-log.md not found or not accessible — nothing to archive")
        return

    if not TMP_SESSION.exists() or TMP_SESSION.stat().st_size == 0:
        log("session-log.md is empty — nothing to archive")
        return

    lines = TMP_SESSION.read_text().splitlines(keepends=True)

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

    # Group lines by archive month, using each entry's own week's Thursday
    by_month = defaultdict(list)
    current_entry_month = None

    for line in to_archive:
        d = parse_header_date(line)
        if d is not None:
            current_entry_month = archive_month(week_monday(d))
        if current_entry_month is not None:
            by_month[current_entry_month].append(line)

    if not by_month:
        log("No dateable entries found to archive")
        return

    # Append each month's entries to the correct archive file
    for month in sorted(by_month.keys()):
        month_lines = by_month[month]
        entry_count = sum(1 for l in month_lines if l.startswith("## "))

        if DRY_RUN:
            first = next((l.strip() for l in month_lines if l.startswith("## ")), "?")
            last = next((l.strip() for l in reversed(month_lines) if l.startswith("## ")), "?")
            log(f"  would archive {entry_count} entries to session-log-{month}.md")
            log(f"    first: {first}")
            log(f"    last:  {last}")
            continue

        archive_path = ARCHIVE_DIR / f"session-log-{month}.md"
        tmp_archive = Path(f"/tmp/session-log-{month}.md")

        icloud_cp(archive_path, tmp_archive)  # fetch existing archive if present (ok if fails)

        with tmp_archive.open("a") as f:
            f.writelines(month_lines)

        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        if not icloud_cp(tmp_archive, archive_path):
            log(f"ERROR: failed to write session-log-{month}.md to iCloud")
            sys.exit(1)

        log(f"Archived {entry_count} entries to session-log-{month}.md")
        tmp_archive.unlink(missing_ok=True)

    if DRY_RUN:
        current_entry_count = sum(1 for l in new_session if l.startswith("## "))
        log(f"  would retain {current_entry_count} entries in session-log.md")
        TMP_SESSION.unlink(missing_ok=True)
        return

    # Write trimmed session log back to iCloud
    TMP_SESSION.write_text("".join(new_session))
    if not icloud_cp(TMP_SESSION, SESSION_LOG):
        log("ERROR: failed to write session-log.md back to iCloud")
        sys.exit(1)

    TMP_SESSION.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
