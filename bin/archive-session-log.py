#!/usr/bin/env python3
"""
Runs Monday morning. Archives the previous ISO week's entries from
session-log.md into the appropriate monthly archive file.

Archive location: Productivity/Archive/session-logs/session-log-YYYY-MM.md
Week is assigned to the month of its Thursday (ISO 8601 convention).

iCloud Drive is inaccessible to launchd Python (TCC restriction). File I/O
on iCloud paths goes via osascript do shell script, which runs as the GUI
user and has the necessary access.
"""

import shlex
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

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


def main():
    trim_log()

    today = date.today()

    # Find the Monday that started the current ISO week, then go back one full week
    # to get the prior week's Monday. The prior week's Thursday determines which
    # month that week belongs to (ISO 8601 convention).
    iso = today.isocalendar()
    current_week_monday = today - timedelta(days=iso.weekday - 1)
    prior_week_monday = current_week_monday - timedelta(weeks=1)
    prior_week_thursday = prior_week_monday + timedelta(days=3)
    archive_name = f"session-log-{prior_week_thursday.strftime('%Y-%m')}.md"
    archive_path = ARCHIVE_DIR / archive_name
    tmp_archive = Path(f"/tmp/{archive_name}")
    current_week_monday_str = current_week_monday.strftime('%Y-%m-%d')

    # Copy session log from iCloud to /tmp
    if not icloud_cp(SESSION_LOG, TMP_SESSION):
        log("session-log.md not found or not accessible — nothing to archive")
        return

    if not TMP_SESSION.exists() or TMP_SESSION.stat().st_size == 0:
        log("session-log.md is empty — nothing to archive")
        return

    lines = TMP_SESSION.read_text().splitlines(keepends=True)

    # Split at the first entry on or after this week's Monday — keep current week in session-log
    split_index = next(
        (i for i, line in enumerate(lines)
         if line.startswith("## ") and len(line) >= 13 and line[3:13] >= current_week_monday_str),
        None,
    )

    if split_index == 0:
        log("No prior-week entries found — nothing to archive")
        return

    to_archive = lines if split_index is None else lines[:split_index]
    new_session = [] if split_index is None else lines[split_index:]

    # Copy existing archive from iCloud to /tmp (if it exists) so we can append to it
    archive_in_icloud = icloud_cp(archive_path, tmp_archive)
    if archive_in_icloud and tmp_archive.exists():
        with tmp_archive.open("a") as f:
            f.writelines(to_archive)
    else:
        tmp_archive.write_text("".join(to_archive))

    # Write the trimmed session log to /tmp
    TMP_SESSION.write_text("".join(new_session))

    # Copy both back to iCloud
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    if not icloud_cp(tmp_archive, archive_path):
        log(f"ERROR: failed to write archive to iCloud ({archive_name})")
        sys.exit(1)
    if not icloud_cp(TMP_SESSION, SESSION_LOG):
        log("ERROR: failed to write session-log.md back to iCloud")
        sys.exit(1)

    entry_count = sum(1 for line in to_archive if line.startswith("## "))
    log(f"Archived {entry_count} entries to {archive_name}")

    tmp_archive.unlink(missing_ok=True)
    TMP_SESSION.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
