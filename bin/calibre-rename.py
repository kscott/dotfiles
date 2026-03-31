#!/usr/bin/env python3
"""
calibre-rename.py — Rename audiobooks using Calibre series data

Output format:
  Series NN - Title.m4b   (series books)
  Title.m4b               (standalones)

Title is taken from Calibre, stripped at the colon (subtitles like
"A Thriller" or "A Sigma Force Novel" add no value when the series
prefix is already there).

Default: dry run. Pass --fix to apply renames.
Pass --author "Name" to limit to one author folder.
"""

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ARCHIVE = Path("/Volumes/Attic/Audiobooks/Archive")
CALIBRE_DB = Path("/Volumes/Friday/Calibre/metadata.db")

# Alternate/regional title mappings and legacy stem overrides: audiobook title → Calibre title
TITLE_ALIASES = {
    "running blind": "the visitor",                   # Lee Child UK/US title difference
    "vince flynn - novel 01 term limits 1998 001-end": "term limits",  # legacy Audible packaging
    "the first commandent": "the first commandment",  # filename typo (Brad Thor)
    "the night manger": "the night manager",          # filename typo (Le Carré)
    # Legacy format: "Author, Last - (Series ##) Title (Year) (Bitrate) Narrator"
    "grippando, james - (js 11) black horizon (2014) (64k) jonathan davis": "black horizon",
}

# Author folders to skip entirely — leave all files as-is.
SKIP_AUTHORS = {
    "Audible",      # miscellaneous/one-offs, not worth renaming
    "Tim Alberta",  # not in Calibre
}


# ── Calibre ───────────────────────────────────────────────────────────────────

def load_calibre(db_path: Path) -> dict:
    """
    Returns a lookup dict keyed by lowercase short title (before colon).
    Value: list of (canonical_title, series_name, series_index, author) tuples.
    Multiple entries per key are possible — disambiguate by author.
    """
    con = sqlite3.connect(str(db_path))
    rows = con.execute("""
        SELECT b.title, s.name, b.series_index,
               group_concat(a.name, ', ') as authors
        FROM books b
        LEFT JOIN books_series_link bsl ON b.id=bsl.book
        LEFT JOIN series s ON bsl.series=s.id
        JOIN books_authors_link bal ON b.id=bal.book
        JOIN authors a ON bal.author=a.id
        GROUP BY b.id
    """).fetchall()
    con.close()

    index = {}
    for title, series, idx, authors in rows:
        entry = (title, series, idx, authors)
        short = _short_title(title).lower()
        index.setdefault(short, []).append(entry)
        # Also index under punctuation-normalised key so "Self defense" → "Self-Defense",
        # "Dr Death" → "Dr. Death", etc. can still match.
        # Index under normalised key: remove apostrophes, hyphens/periods → spaces.
        # "Serpent's Tooth" → "serpents tooth", "Self-Defense" → "self defense"
        norm = re.sub(r"'", '', short)
        norm = re.sub(r'[.\-]', ' ', norm)
        norm = re.sub(r' +', ' ', norm).strip()
        if norm != short:
            index.setdefault(norm, []).append(entry)

        # Index "title + series" for audiobooks that embed the series name in the filename.
        # e.g. "The Eye of the World Wheel of Time" → entry for WoT #1
        if series:
            series_lower = series.lower()
            for combined in [f"{short} {series_lower}",
                             f"{short} {re.sub(r'^the ', '', series_lower)}"]:
                if combined != short:
                    index.setdefault(combined, []).append(entry)

    # Add reverse-alias keys so alternate/regional titles can find Calibre entries.
    # e.g. "running blind" → same entry as "the visitor"
    for alias_key, calibre_key in TITLE_ALIASES.items():
        if calibre_key in index:
            index.setdefault(alias_key, []).extend(index[calibre_key])
    return index


def _short_title(title: str) -> str:
    """Strip subtitle after colon, em-dash, or slash (alternate titles)."""
    for sep in (":", " — ", " - A ", "/"):
        if sep in title:
            return title[:title.index(sep)].strip()
    return title.strip()


def _series_from_subtitle(title: str) -> str:
    """
    Extract series name from subtitles like 'A Sigma Force Novel',
    'A Scot Harvath Thriller', 'A Gray Man Novel'.
    Returns empty string if no match.
    """
    m = re.search(r':\s*[Aa]n?\s+(.+?)\s+(?:Novel|Thriller|Mystery|Book)\b', title)
    if m:
        return m.group(1).strip()
    return ""


def lookup(index: dict, title: str, author_folder: str):
    """
    Find a Calibre entry for the given title string.
    Tries full title, short title (before colon), and with/without
    leading article ("The", "A", "An") stripped or added.
    Returns (canonical_title, series_name, series_index) or None.
    """
    folder_words = set(author_folder.lower().split())
    short = _short_title(title)

    # Build candidate keys: short title, full title, article variants
    stripped = re.sub(r'^(the|a|an)\s+', '', short, flags=re.IGNORECASE).lower()
    # Comma-normalised variant: "Tinker, Tailor, Soldier, Spy" → "tinker tailor soldier spy"
    comma_norm = re.sub(r' +', ' ', re.sub(r',\s*', ' ', short.lower())).strip()
    key_list = [
        short.lower(),
        title.lower(),
        stripped,
        f"the {stripped}",   # "Skeleton Key" → try "the skeleton key"
        f"a {stripped}",
        re.sub(r' +', ' ', re.sub(r'[._\-]', ' ', re.sub(r"'", '', short.lower()))).strip(),
        comma_norm,
    ]

    # Handle legacy filenames with author/series/book-number prefixes.
    # Split on " - " and also "- " (catches "Author- Title" with no leading space).
    # For each segment, clean noise and try it as a title key.
    # Strip "by Author" suffix and " A Novel/Thriller/Mystery" genre labels, then add keys.
    # e.g. "Half Moon Bay by Jonathan Kellerman" → "Half Moon Bay"
    #      "Crime Scene A Novel by ..." → "Crime Scene"
    title_no_by = re.sub(r'\s+by\s+.*$', '', title, flags=re.IGNORECASE).strip()
    title_no_by = re.sub(r'\s+[Aa]n?\s+(Novel|Thriller|Mystery|Book)\b.*$', '',
                         title_no_by, flags=re.IGNORECASE).strip()
    if title_no_by != title and title_no_by:
        nb_short = _short_title(title_no_by)
        nb_stripped = re.sub(r'^(the|a|an)\s+', '', nb_short, flags=re.IGNORECASE).lower()
        key_list += [nb_short.lower(), nb_stripped,
                     f"the {nb_stripped}", f"a {nb_stripped}"]

    # Also extract title from "Series NN.NN-Title" (no spaces around hyphen after number)
    # e.g. "Reacher 04.00-Killing Floor" → "Killing Floor"
    m = re.match(r'^.+?\s+\d+(?:\.\d+)?-(.+)$', title)
    if m:
        tail = m.group(1).strip()
        if tail and not re.fullmatch(r'[\d\s]+', tail):
            seg = _short_title(tail)
            seg_stripped = re.sub(r'^(the|a|an)\s+', '', seg, flags=re.IGNORECASE).lower()
            seg_keys = [seg.lower(), seg_stripped]
            # Only add "the/a X" article variants for multi-word segments; single words
            # like "End" or "Spy" are too ambiguous and cause false-positive matches.
            if len(seg.split()) >= 2:
                seg_keys += [f"the {seg_stripped}", f"a {seg_stripped}"]
            key_list += seg_keys

    raw_parts = re.split(r'\s*-\s+|\s+-\s*|\s{2,}|,\s*|_', title)  # " - ", "- ", "  ", ", ", "_"
    for part in raw_parts:
        part = part.strip()
        # Skip pure numbers and "Book N" markers
        if re.fullmatch(r'[\d\s]+', part):
            continue
        if re.match(r'Book\s+\d+', part, re.IGNORECASE):
            continue
        # Strip parentheticals and trailing noise FIRST, then check for encoding tags
        clean_part = re.sub(r'\s*[\(\[].*?[\)\]]', '', part).strip()  # strip (parens) and [brackets]
        clean_part = re.sub(r'\s+\d{4}$', '', clean_part).strip()
        clean_part = re.sub(r'\s+\d+[Kk]\b.*$', '', clean_part, flags=re.IGNORECASE).strip()
        clean_part = re.sub(r'\s+Prequel\b.*$', '', clean_part, flags=re.IGNORECASE).strip()
        clean_part = re.sub(r'\s+Audio\s+Book\b.*$', '', clean_part, flags=re.IGNORECASE).strip()
        if len(clean_part) < 3:
            continue
        seg = _short_title(clean_part)
        seg_stripped = re.sub(r'^(the|a|an)\s+', '', seg, flags=re.IGNORECASE).lower()
        seg_keys = [seg.lower(), seg_stripped]
        if len(seg.split()) >= 2:
            seg_keys += [f"the {seg_stripped}", f"a {seg_stripped}"]
        key_list += seg_keys

    keys = dict.fromkeys(key_list)

    # Collect all unique candidates across all keys, preserving order.
    # Dedup key is (title, authors) so same-named books by different authors both appear.
    seen = {}
    for key in keys:
        for entry in index.get(key, []):
            entry_key = (entry[0], entry[3])  # (canonical title, authors)
            seen.setdefault(entry_key, entry)
    candidates = list(seen.values())

    if not candidates:
        return None

    # Prefer candidate whose author overlaps the folder name
    for t, s, i, authors in candidates:
        author_words = {w for a in authors.split(", ") for w in a.lower().split()}
        if folder_words & author_words:
            return t, s, i

    # Fall back to first
    t, s, i, _ = candidates[0]
    return t, s, i


# ── Naming ────────────────────────────────────────────────────────────────────

def format_index(idx: float) -> str:
    if idx == int(idx):
        return f"{int(idx):02d}"
    # e.g. 12.5 → "12.5"
    return f"{idx:g}"


def make_filename(title: str, series: str, idx: float) -> str:
    clean = re.sub(r'[:/\\]', '-', _short_title(title)).strip()
    # Only use subtitle extraction when Calibre has a real series;
    # without it the index is just the default 1.0 and would be wrong.
    if not series:
        return clean
    series_clean = re.sub(r'[:/\\]', '-', series).strip()
    return f"{series_clean} {format_index(idx)} - {clean}"


# ── ffprobe ───────────────────────────────────────────────────────────────────

def probe_title(m4b: Path) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format_tags=title",
         "-of", "default=nw=1:nk=1", str(m4b)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix",    action="store_true", help="Apply renames (default: dry run)")
    parser.add_argument("--author", metavar="NAME",      help="Limit to one author folder")
    args = parser.parse_args()

    if not CALIBRE_DB.exists():
        print(f"Calibre DB not found: {CALIBRE_DB}", file=sys.stderr)
        sys.exit(1)

    calibre = load_calibre(CALIBRE_DB)
    mode = "LIVE" if args.fix else "DRY RUN"
    print(f"=== calibre-rename [{mode}] ===")
    print(f"Calibre: {sum(len(v) for v in calibre.values())} books indexed\n")

    if args.author:
        author_dirs = [ARCHIVE / args.author]
        if not author_dirs[0].is_dir():
            print(f"Author folder not found: {author_dirs[0]}", file=sys.stderr)
            sys.exit(1)
    else:
        author_dirs = sorted(
            d for d in ARCHIVE.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    renamed = already_correct = not_found = conflicts = 0

    for author_dir in author_dirs:
        if author_dir.name in SKIP_AUTHORS:
            continue
        m4bs = sorted(author_dir.glob("*.m4b"))
        if not m4bs:
            continue

        author_header_printed = False
        for m4b in m4bs:
            tag_title = probe_title(m4b)
            result = (
                (tag_title and lookup(calibre, tag_title, author_dir.name))
                or lookup(calibre, m4b.stem, author_dir.name)
            )

            if not result:
                if not author_header_printed:
                    print(f"[ {author_dir.name} ]")
                    author_header_printed = True
                print(f"  NOT IN CALIBRE: {m4b.name}")
                not_found += 1
                continue

            cal_title, cal_series, cal_idx = result
            new_stem = make_filename(cal_title, cal_series, cal_idx)
            new_name = new_stem + ".m4b"

            if new_name == m4b.name:
                already_correct += 1
                continue

            if not author_header_printed:
                print(f"[ {author_dir.name} ]")
                author_header_printed = True

            target = author_dir / new_name
            if target.exists() and target != m4b:
                print(f"  CONFLICT: {m4b.name} → {new_name}")
                conflicts += 1
                continue

            print(f"  {'→' if args.fix else '?'} {m4b.name}")
            print(f"    {new_name}")
            if args.fix:
                m4b.rename(target)
            renamed += 1

    print(f"\n=== Done [{mode}]: {renamed} {'renamed' if args.fix else 'to rename'}, "
          f"{already_correct} already correct, {not_found} not in Calibre, "
          f"{conflicts} conflicts ===")
    if not args.fix and renamed > 0:
        print("    Run with --fix to apply.")


if __name__ == "__main__":
    main()
