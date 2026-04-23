#!/usr/bin/env python3
"""
Runs Monday morning. Archives the previous ISO week's entries from
session-log.md into the appropriate monthly archive file.

Archive location: Productivity/Archive/session-logs/session-log-YYYY-MM.md
Week is assigned to the month of its Thursday (ISO 8601 convention).
"""

import sys
from datetime import date, timedelta
from pathlib import Path

HOME = Path.home()
PRODUCTIVITY = HOME / "Library/Mobile Documents/com~apple~CloudDocs/Productivity"
SESSION_LOG = PRODUCTIVITY / "session-log.md"
ARCHIVE_DIR = PRODUCTIVITY / "Archive/session-logs"
LOG = HOME / "logs/archive-session-log.log"


def trim_log():
    if LOG.exists():
        lines = LOG.read_text().splitlines(keepends=True)
        if len(lines) > 100:
            LOG.write_text("".join(lines[-100:]))


def main():
    trim_log()

    if not SESSION_LOG.exists() or SESSION_LOG.stat().st_size == 0:
        sys.exit(0)

    today = date.today()
    today_header = f"## {today.strftime('%Y-%m-%d')}"

    # The week belongs to the month containing its Thursday (ISO 8601 convention).
    # When run on Monday, today - 4 days = last Thursday.
    last_thursday = today - timedelta(days=4)
    archive_path = ARCHIVE_DIR / f"session-log-{last_thursday.strftime('%Y-%m')}.md"

    lines = SESSION_LOG.read_text().splitlines(keepends=True)

    split_index = next(
        (i for i, line in enumerate(lines) if line.startswith(today_header)),
        None,
    )

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    if split_index is None:
        # No entry for today — archive everything
        with archive_path.open("a") as f:
            f.writelines(lines)
        SESSION_LOG.write_text("")
    elif split_index > 0:
        # Archive everything before today's first entry
        with archive_path.open("a") as f:
            f.writelines(lines[:split_index])
        SESSION_LOG.write_text("".join(lines[split_index:]))


if __name__ == "__main__":
    main()
