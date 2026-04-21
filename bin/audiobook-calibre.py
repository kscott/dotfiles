#!/usr/bin/env python3
"""
audiobook-calibre.py — Manage Calibre series data for the audiobook archive

Subcommands:
  set   "Book Title" --series "Name" --index N
          Set (or fix) the series and position for a book in Calibre.
          Title match is case-insensitive; partial matches are shown for confirmation.

  audit [--author "Name"]
          Gap analysis between the archive and Calibre:
            - M4B files not found in Calibre
            - Calibre books (by archive authors) with no corresponding M4B

  check [--author "Name"]
          Calibre data quality problems:
            - Books sharing the same series + index (duplicate positions)
            - Authors with multiple series names that look like the same series

Usage:
  audiobook-calibre.py set "The Proving Ground" --series "Mickey Haller" --index 8
  audiobook-calibre.py audit
  audiobook-calibre.py audit --author "Michael Connelly"
  audiobook-calibre.py check
  audiobook-calibre.py check --author "Mark Greaney"
"""

import argparse
import re
import sqlite3
import sys
import uuid
from pathlib import Path

ARCHIVE    = Path("/Volumes/Attic/Audiobooks/Archive")
CALIBRE_DB = Path("/Volumes/Friday/Calibre/metadata.db")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _title_sort(title: str) -> str:
    m = re.match(r'^(The|A|An) (.+)$', title, re.IGNORECASE)
    return (m.group(2) + ', ' + m.group(1)) if m else title


def open_db() -> sqlite3.Connection:
    if not CALIBRE_DB.exists():
        print(f"Calibre DB not found: {CALIBRE_DB}", file=sys.stderr)
        sys.exit(1)
    con = sqlite3.connect(str(CALIBRE_DB))
    con.create_function('title_sort', 1, _title_sort)
    con.create_function('uuid4', 0, lambda: str(uuid.uuid4()))
    return con


def _short(title: str) -> str:
    for sep in (":", " — ", " - A ", "/"):
        if sep in title:
            return title[:title.index(sep)].strip()
    return title.strip()


# ── set ───────────────────────────────────────────────────────────────────────

def cmd_set(args):
    con = open_db()
    cur = con.cursor()
    query = args.title.lower()

    # Find matching books
    rows = cur.execute("""
        SELECT b.id, b.title, group_concat(a.name, ', ')
        FROM books b
        JOIN books_authors_link bal ON b.id = bal.book
        JOIN authors a ON bal.author = a.id
        GROUP BY b.id
        HAVING lower(b.title) LIKE ?
        ORDER BY b.title
    """, (f"%{query}%",)).fetchall()

    if not rows:
        print(f"No books found matching: {args.title!r}")
        con.close()
        sys.exit(1)

    if len(rows) > 1:
        print(f"Multiple matches for {args.title!r}:")
        for bid, title, authors in rows:
            print(f"  [{bid}] {title} — {authors}")
        print("Be more specific.")
        con.close()
        sys.exit(1)

    bid, title, authors = rows[0]

    # Get or create the series
    row = cur.execute('SELECT id FROM series WHERE name=?', (args.series,)).fetchone()
    if row:
        sid = row[0]
    else:
        cur.execute('INSERT INTO series (name, sort) VALUES (?, ?)',
                    (args.series, _title_sort(args.series)))
        sid = cur.lastrowid
        print(f"Created series: {args.series!r}")

    # Show current state
    current = cur.execute("""
        SELECT s.name, b.series_index
        FROM books b
        LEFT JOIN books_series_link bsl ON b.id = bsl.book
        LEFT JOIN series s ON bsl.series = s.id
        WHERE b.id = ?
    """, (bid,)).fetchone()
    cur_series, cur_idx = current if current else (None, None)

    print(f"Book:    {title} — {authors}")
    if cur_series:
        print(f"Before:  {cur_series} #{cur_idx}")
    else:
        print(f"Before:  (no series)")
    print(f"After:   {args.series} #{args.index}")

    # Apply
    cur.execute('DELETE FROM books_series_link WHERE book=?', (bid,))
    cur.execute('INSERT INTO books_series_link (book, series) VALUES (?,?)', (bid, sid))
    cur.execute('UPDATE books SET series_index=? WHERE id=?', (args.index, bid))
    con.commit()
    con.close()
    print("Done.")


# ── Shared: load archive M4Bs and Calibre index ───────────────────────────────

def archive_m4bs(author: str | None) -> dict:
    """Returns {author_name: [Path, ...]} for all M4Bs in the archive."""
    result = {}
    if author:
        d = ARCHIVE / author
        if d.is_dir():
            result[author] = sorted(d.glob("*.m4b"))
    else:
        for d in sorted(ARCHIVE.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                m4bs = sorted(d.glob("*.m4b"))
                if m4bs:
                    result[d.name] = m4bs
    return result


def load_calibre_index(con: sqlite3.Connection) -> dict:
    """
    Returns lookup dict: lowercase short title → list of
    (book_id, full_title, series_name, series_index, authors).
    """
    rows = con.execute("""
        SELECT b.id, b.title, s.name, b.series_index,
               group_concat(a.name, ', ')
        FROM books b
        LEFT JOIN books_series_link bsl ON b.id = bsl.book
        LEFT JOIN series s ON bsl.series = s.id
        JOIN books_authors_link bal ON b.id = bal.book
        JOIN authors a ON bal.author = a.id
        GROUP BY b.id
    """).fetchall()

    index = {}
    for bid, title, series, idx, authors in rows:
        key = _short(title).lower()
        index.setdefault(key, []).append((bid, title, series, idx, authors))
    return index


def calibre_match(index: dict, stem: str) -> tuple | None:
    """Try to find a Calibre entry for the given file stem. Returns first match or None."""
    # Strip series prefix: "Gray Man 10 - Relentless" → "relentless"
    candidates = [_short(stem).lower()]
    m = re.search(r'\d+(?:\.\d+)?\s*-\s*(.+)$', stem)
    if m:
        candidates.append(m.group(1).strip().lower())

    for key in candidates:
        if key in index:
            return index[key][0]  # (bid, title, series, idx, authors)
    return None


def calibre_books_by_author(con: sqlite3.Connection, author_name: str) -> list:
    """Return Calibre books whose author name matches the folder name.

    Requires ALL words in the folder name to appear in the author string —
    avoids false matches on shared first names (e.g. "Michael Gear" vs "Michael Connelly").
    """
    folder_words = set(author_name.lower().split())
    rows = con.execute("""
        SELECT b.id, b.title, s.name, b.series_index,
               group_concat(a.name, ', ')
        FROM books b
        LEFT JOIN books_series_link bsl ON b.id = bsl.book
        LEFT JOIN series s ON bsl.series = s.id
        JOIN books_authors_link bal ON b.id = bal.book
        JOIN authors a ON bal.author = a.id
        GROUP BY b.id
    """).fetchall()

    results = []
    for bid, title, series, idx, authors in rows:
        author_words = set(authors.lower().split())
        if folder_words <= author_words:  # all folder words present in author string
            results.append((bid, title, series, idx, authors))
    return results


# ── audit ─────────────────────────────────────────────────────────────────────

def cmd_audit(args):
    con = open_db()
    index = load_calibre_index(con)
    m4bs_by_author = archive_m4bs(args.author)

    not_in_calibre = 0
    not_in_archive = 0

    print("=== audiobook-calibre audit ===\n")

    # M4Bs with no Calibre match
    for author, m4bs in m4bs_by_author.items():
        author_issues = []
        for m4b in m4bs:
            if calibre_match(index, m4b.stem) is None:
                author_issues.append(f"  NOT IN CALIBRE: {m4b.name}")
                not_in_calibre += 1
        if author_issues:
            print(f"[ {author} ]")
            for line in author_issues:
                print(line)

    # Calibre books with no corresponding M4B
    print()
    for author in m4bs_by_author:
        cal_books = calibre_books_by_author(con, author)
        archive_stems = {_short(m.stem).lower()
                         for m in m4bs_by_author[author]}
        # Also add stripped stems (no series prefix)
        for m in m4bs_by_author[author]:
            mm = re.search(r'\d+(?:\.\d+)?\s*-\s*(.+)$', m.stem)
            if mm:
                archive_stems.add(mm.group(1).strip().lower())

        missing = []
        for bid, title, series, idx, authors in cal_books:
            key = _short(title).lower()
            if key not in archive_stems:
                label = f"{series} #{int(idx)}" if series else "standalone"
                missing.append(f"  NOT IN ARCHIVE: {title} ({label})")
                not_in_archive += 1
        if missing:
            print(f"[ {author} — in Calibre, no M4B ]")
            for line in missing:
                print(line)

    con.close()
    print(f"\n=== Done: {not_in_calibre} files not in Calibre, "
          f"{not_in_archive} Calibre books with no M4B ===")


# ── check ─────────────────────────────────────────────────────────────────────

def cmd_check(args):
    con = open_db()
    m4bs_by_author = archive_m4bs(args.author)

    issues = 0
    print("=== audiobook-calibre check ===\n")

    for author in m4bs_by_author:
        cal_books = calibre_books_by_author(con, author)
        author_issues = []

        # Duplicate series positions
        seen_positions = {}
        for bid, title, series, idx, _ in cal_books:
            if not series:
                continue
            key = (series, idx)
            if key in seen_positions:
                author_issues.append(
                    f"  DUPLICATE: {series} #{int(idx)} — "
                    f"{seen_positions[key]!r} and {title!r}"
                )
                issues += 1
            else:
                seen_positions[key] = title

        # Series name variants that look like the same series
        series_names = list({b[2] for b in cal_books if b[2]})
        for i, s1 in enumerate(series_names):
            words1 = {w for w in re.split(r'\W+', s1.lower()) if len(w) >= 5}
            for s2 in series_names[i+1:]:
                words2 = {w for w in re.split(r'\W+', s2.lower()) if len(w) >= 5}
                if words1 & words2:
                    author_issues.append(
                        f"  SERIES CONFLICT: {s1!r} vs {s2!r}"
                    )
                    issues += 1

        if author_issues:
            print(f"[ {author} ]")
            for line in author_issues:
                print(line)

    con.close()
    print(f"\n=== Done: {issues} issue{'s' if issues != 1 else ''} found ===")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="Set series and index for a book")
    p_set.add_argument("title",    help="Book title (partial match)")
    p_set.add_argument("--series", required=True, metavar="NAME",  help="Series name")
    p_set.add_argument("--index",  required=True, metavar="N", type=float, help="Series position")

    p_audit = sub.add_parser("audit", help="Archive vs Calibre gap analysis")
    p_audit.add_argument("--author", metavar="NAME", help="Limit to one author folder")

    p_check = sub.add_parser("check", help="Calibre data quality problems")
    p_check.add_argument("--author", metavar="NAME", help="Limit to one author folder")

    args = parser.parse_args()

    if args.cmd == "set":
        cmd_set(args)
    elif args.cmd == "audit":
        cmd_audit(args)
    elif args.cmd == "check":
        cmd_check(args)


if __name__ == "__main__":
    main()
