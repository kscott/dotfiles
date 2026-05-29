#!/usr/bin/env python3
"""
calibre-update-metadata.py — Fetch and apply metadata + covers for ebooks in Calibre

Uses Google Books API (no key required). Calibre must be closed when running update.

Subcommands:
  list [--since DATE]
          Show recently added books with cover and series status.
          Default: books added since the start of today (UTC).

  update [--since DATE] [--ids ID [ID ...]] [--dry-run] [--delay N]
          Fetch metadata from Google Books and apply to Calibre.
          Sets: description, publisher, pub date, tags, series, series index, cover.
          Does not overwrite series if one is already set.
          Does not modify authors (preserves Calibre's name/sort format).

Usage:
  calibre-update-metadata.py list
  calibre-update-metadata.py list --since 2026-05-18
  calibre-update-metadata.py update --since 2026-05-18
  calibre-update-metadata.py update --ids 6203 6204 6205
  calibre-update-metadata.py update --dry-run --since 2026-05-18
  calibre-update-metadata.py update --since 2026-05-18 --delay 2
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

CALIBRE          = Path("/Applications/calibre.app/Contents/MacOS")
GOOGLE_BOOKS_API = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY_SEARCH = "https://openlibrary.org/search.json"
OPEN_LIBRARY_WORKS  = "https://openlibrary.org"
APPLE_BOOKS_API  = "https://itunes.apple.com/search"
REC_FILE_DEFAULT = Path.home() / "Notes/personal/book-recommendations.md"

# ── Rec file series lookup ─────────────────────────────────────────────────────

def load_series_lookup(rec_file: Path) -> dict[str, tuple[str, float]]:
    """Parse numbered series lists from the rec file → {norm_title: (series, index)}."""
    lookup = {}
    if not rec_file.exists():
        return lookup

    section_re = re.compile(r'^### .+ — (.+?) \(need all\)', re.IGNORECASE)
    bold_re    = re.compile(r'\*\*(.+?) (?:series|duology|trilogy)\*\*.*\(need all\)', re.IGNORECASE)
    item_re    = re.compile(r'^(\d+)\.\s+\*?([^*(←\n]+?)\*?\s*(?:\(\d{4}\))?(?:\s*←.*)?$')

    current_series = None
    for line in rec_file.read_text().splitlines():
        line = line.strip()
        m = section_re.match(line)
        if m:
            current_series = m.group(1).strip()
            continue
        m = bold_re.search(line)
        if m:
            current_series = m.group(1).strip()
            continue
        if line.startswith("### ") and "need all" not in line:
            current_series = None
            continue
        if current_series:
            m = item_re.match(line)
            if m:
                idx   = int(m.group(1))
                title = re.sub(r'\*+', '', m.group(2)).strip().rstrip("*").strip()
                key   = _norm_title(title)
                lookup[key] = (current_series, float(idx))

    return lookup


# ── Series parsing (fallback) ──────────────────────────────────────────────────

def _norm_title(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[^a-z0-9 ]', '', s)
    s = re.sub(r'\b(the|a|an)\b ', '', s)
    return re.sub(r'\s+', ' ', s).strip()


SERIES_PATTERNS = [
    # "(Millennium #1)" or "(Gabriel Allon, #18)"
    r'\(([^)]+?)[,\s]+#(\d+(?:\.\d+)?)\)',
    # "(Gabriel Allon Book 18)"
    r'\(([^)]+?)\s+[Bb]ook\s+(\d+(?:\.\d+)?)\)',
    # "Series Name, Book 5" (in title/subtitle)
    r'([^,(]+?),\s+[Bb]ook\s+(\d+(?:\.\d+)?)',
    # "(Series Name, Volume 3)" or "Vol. 3"
    r'\(([^)]+?),\s+[Vv]ol(?:ume)?\.?\s+(\d+(?:\.\d+)?)\)',
]

_SKIP_SERIES_NAMES = {"a", "an", "the", "novel", "book", "series", "thriller", ""}


def parse_series(title: str) -> tuple[str, float] | None:
    """Return (series_name, series_index) parsed from title, or None."""
    combined = title.strip()
    for pattern in SERIES_PATTERNS:
        m = re.search(pattern, combined)
        if m:
            name = m.group(1).strip().rstrip(",").strip()
            if name.lower() in _SKIP_SERIES_NAMES:
                continue
            return name, float(m.group(2))
    return None


# ── Shared helpers ────────────────────────────────────────────────────────────

def _clean_search_title(title: str) -> str:
    """Strip subtitle noise for cleaner API matching."""
    t = title
    t = re.sub(
        r'\s*[:\-–—]+\s*[Aa]n?\s+[\w ]{0,25}(?:novel(?:la)?|thriller|story|tale|book)\s*$',
        '', t, flags=re.IGNORECASE,
    ).strip()
    t = re.sub(r'\s*\([^)]*\)\s*$', '', t).strip()
    if ':' in t:
        pre = t[:t.index(':')].strip()
        if len(pre.split()) <= 2:
            t = pre
    return t or title


def _title_words(title: str) -> set[str]:
    return {w for w in re.sub(r'[^a-z0-9 ]', '', title.lower()).split() if len(w) > 3}


def _author_last(authors: str) -> str:
    return authors.split("&")[0].strip().split()[-1] if authors else ""


# ── Google Books API ───────────────────────────────────────────────────────────

def google_books_search(title: str, authors: str) -> dict | None:
    """Return normalized metadata dict from Google Books, or None. None on 429."""
    query = f'intitle:"{_clean_search_title(title)}" inauthor:"{_author_last(authors)}"'
    params = urllib.parse.urlencode({
        "q": query,
        "maxResults": 3,
        "printType": "books",
        "langRestrict": "en",
    })
    url = f"{GOOGLE_BOOKS_API}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "calibre-update-metadata/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("  ⚠ Google Books rate limited — falling back to Open Library", file=sys.stderr)
            return "RATE_LIMITED"
        print(f"    API error: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"    API error: {e}", file=sys.stderr)
        return None

    items = data.get("items", [])
    if not items:
        return None

    title_lower = _clean_search_title(title).lower()
    for item in items:
        vol_title = item.get("volumeInfo", {}).get("title", "").lower()
        if title_lower in vol_title or vol_title in title_lower:
            return _normalize_google(item["volumeInfo"])
    return _normalize_google(items[0]["volumeInfo"])


def _normalize_google(vol: dict) -> dict:
    image_links = vol.get("imageLinks", {})
    cover_url = None
    for key in ("extraLarge", "large", "medium", "small", "thumbnail", "smallThumbnail"):
        url = image_links.get(key)
        if url:
            url = re.sub(r"&?zoom=\d+", "", url)
            url = re.sub(r"&?edge=curl", "", url)
            url = re.sub(r"&?source=gbs_api", "", url)
            url = url.rstrip("&")
            if "books.google.com" in url:
                url += f"&fife=w{COVER_WIDTH}"
            cover_url = url
            break

    pubdate = vol.get("publishedDate", "").strip()
    return {
        "title":       vol.get("title", ""),
        "description": vol.get("description", "").strip(),
        "publisher":   vol.get("publisher", "").strip(),
        "publishedDate": pubdate[:4] if re.match(r"\d{4}", pubdate) else "",
        "categories":  vol.get("categories", [])[:5],
        "cover_url":   cover_url,
    }


# ── Open Library fallback ──────────────────────────────────────────────────────

def open_library_search(title: str, authors: str) -> dict | None:
    """Open Library fallback — used when Google Books is rate-limited."""
    author_token = _author_last(authors)
    search_title = _clean_search_title(title)
    params = urllib.parse.urlencode({
        "title": search_title,
        "author": author_token,
        "limit": 5,
        "fields": "key,title,author_name,first_publish_year,publisher,subject,cover_i",
        "lang": "eng",
    })
    try:
        req = urllib.request.Request(
            f"{OPEN_LIBRARY_SEARCH}?{params}",
            headers={"User-Agent": "calibre-update-metadata/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"    API error: {e}", file=sys.stderr)
        return None

    docs = data.get("docs", [])
    if not docs:
        return None

    query_words = _title_words(search_title)
    author_words = {w for w in re.sub(r'[^a-z0-9 ]', '', authors.lower()).split() if len(w) > 3}
    best = None
    for doc in docs:
        if not (query_words & _title_words(doc.get("title", ""))):
            continue
        doc_author_text = " ".join(doc.get("author_name", [])).lower()
        doc_author_words = {w for w in re.sub(r'[^a-z0-9 ]', '', doc_author_text).split() if len(w) > 3}
        # Accept if author words overlap, or if OL didn't return author_name at all
        if not doc_author_words or (author_words & doc_author_words):
            best = doc
            break
    if best is None:
        return None

    description = ""
    work_key = best.get("key")
    if work_key:
        try:
            req = urllib.request.Request(
                f"{OPEN_LIBRARY_WORKS}{work_key}.json",
                headers={"User-Agent": "calibre-update-metadata/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                work_data = json.loads(resp.read())
            desc = work_data.get("description", "")
            if isinstance(desc, dict):
                desc = desc.get("value", "")
            description = desc.strip()
        except Exception:
            pass

    cover_id = best.get("cover_i")
    publishers = best.get("publisher", [])
    return {
        "title":       best.get("title", ""),
        "description": description,
        "publisher":   publishers[0] if publishers else "",
        "publishedDate": str(best.get("first_publish_year", "")),
        "categories":  best.get("subject", [])[:5],
        "cover_url":   f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
    }


def apple_books_cover_url(title: str, authors: str) -> str | None:
    """Return a high-res cover URL from Apple Books, or None."""
    term = f"{_clean_search_title(title)} {_author_last(authors)}"
    params = urllib.parse.urlencode({"term": term, "entity": "ebook", "country": "US", "limit": 5})
    try:
        req = urllib.request.Request(
            f"{APPLE_BOOKS_API}?{params}",
            headers={"User-Agent": "calibre-update-metadata/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception:
        return None

    query_words = _title_words(_clean_search_title(title))
    author_words = {w for w in re.sub(r'[^a-z0-9 ]', '', authors.lower()).split() if len(w) > 3}
    for result in data.get("results", []):
        if not (query_words & _title_words(result.get("trackName", ""))):
            continue
        result_author_words = {
            w for w in re.sub(r'[^a-z0-9 ]', '', result.get("artistName", "").lower()).split()
            if len(w) > 3
        }
        if not author_words or (author_words & result_author_words):
            artwork = result.get("artworkUrl100", "")
            if artwork:
                return re.sub(r'/\d+x\d+\w*\.jpg$', '/1400x2100bb.jpg', artwork)
    return None


# Persistent rate-limit flag — avoids spamming the message per book
_google_rl = [False]


def fetch_metadata(title: str, authors: str) -> dict | None:
    """Google Books for metadata, Apple Books for cover. Falls back to OL on GB rate limit."""
    result = None
    if not _google_rl[0]:
        result = google_books_search(title, authors)
        if result == "RATE_LIMITED":
            _google_rl[0] = True
            print("  ⚠ Google Books rate limited — switching to Open Library for metadata")
            result = None
    if result is None:
        result = open_library_search(title, authors)
    if result:
        apple_url = apple_books_cover_url(title, authors)
        if apple_url:
            result["cover_url"] = apple_url
    return result


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Parse width, height from JPEG SOF marker. Returns None if not parseable."""
    import struct
    if data[:2] != b'\xff\xd8':
        return None
    i = 2
    while i < len(data) - 8:
        if data[i] != 0xff:
            break
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = struct.unpack('>H', data[i + 5:i + 7])[0]
            w = struct.unpack('>H', data[i + 7:i + 9])[0]
            return w, h
        seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
        i += 2 + seg_len
    return None


def download_image(url: str, dest: Path, min_short_side: int = 500) -> bool:
    """Download a cover image. Rejects placeholders, square (audiobook) covers, and small images."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "calibre-update-metadata/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if len(data) < 5000:
            return False
        dims = _jpeg_dimensions(data)
        if dims:
            w, h = dims
            if w == h:          # square = audiobook cover
                return False
            if min(w, h) < min_short_side:
                return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


# ── calibredb helpers ──────────────────────────────────────────────────────────

def calibredb(*args) -> tuple[int, str, str]:
    cmd = [str(CALIBRE / "calibredb")] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = "\n".join(
        line for line in result.stderr.splitlines()
        if not line.startswith("Failed to initialize plugin")
    )
    return result.returncode, result.stdout.strip(), stderr.strip()


def get_books(since: str | None = None, ids: list[int] | None = None) -> list[dict]:
    rc, stdout, stderr = calibredb(
        "list", "--for-machine", "-f", "id,title,authors,last_modified,series,cover"
    )
    if rc != 0:
        if "Another calibre program" in stderr:
            print("Calibre is open — close it and run again.", file=sys.stderr)
        else:
            print(f"calibredb error: {stderr}", file=sys.stderr)
        sys.exit(1)

    books = json.loads(stdout)

    if ids:
        id_set = set(ids)
        books = [b for b in books if b["id"] in id_set]
    elif since:
        books = [b for b in books if b.get("last_modified", "") >= since]

    return books


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_list(args):
    since = args.since or str(date.today())
    books = get_books(since=since)

    if not books:
        print(f"No books found since {since}.")
        return

    print(f"{'ID':>5}  Cover  Series  Title — Author")
    print("─" * 72)
    for b in books:
        cover  = "✓" if b.get("cover") else "·"
        series = "✓" if b.get("series") else "·"
        label  = f"{b['title'][:40]} — {b['authors'][:25]}"
        print(f"[{b['id']:>5}]   {cover}      {series}   {label}")
    print(f"\n{len(books)} book(s) since {since}")


def cmd_update(args):
    since = args.since
    ids   = args.ids

    if not since and not ids:
        print("Specify --since DATE or --ids. Example: --since 2026-05-18", file=sys.stderr)
        sys.exit(1)

    books = get_books(since=since, ids=ids)
    if not books:
        print("No books match.")
        return

    rec_file = Path(args.rec_file) if args.rec_file else REC_FILE_DEFAULT
    series_lookup = load_series_lookup(rec_file)
    if series_lookup:
        print(f"Loaded {len(series_lookup)} series entries from rec file.")

    prefix = "DRY RUN — " if args.dry_run else ""
    print(f"{prefix}Processing {len(books)} book(s)...\n")

    ok = skipped = failed = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        cover_dir = Path(tmpdir)

        for i, book in enumerate(books):
            book_id  = book["id"]
            title    = book["title"]
            authors  = book["authors"]
            has_series = bool(book.get("series"))

            print(f"[{book_id}] {title} — {authors}")

            if args.dry_run:
                print("  (dry run)")
                skipped += 1
                continue

            vol = fetch_metadata(title, authors)
            if not vol:
                print("  ✗ No match found")
                failed += 1
                time.sleep(args.delay)
                continue

            found_title = vol.get("title", "")
            print(f"  → matched: {found_title[:60]}")

            # Build field updates
            fields: list[str] = []

            description = vol.get("description", "").strip()
            if description:
                fields += ["-f", f"comments:{description}"]

            publisher = vol.get("publisher", "").strip()
            if publisher:
                fields += ["-f", f"publisher:{publisher}"]

            pubdate = vol.get("publishedDate", "").strip()
            if pubdate:
                fields += ["-f", f"pubdate:{pubdate[:4]}-01-01"]

            categories = vol.get("categories", [])
            if categories:
                fields += ["-f", f"tags:{','.join(categories[:5])}"]

            # Series — only set if not already present in Calibre
            series_info = None
            if not has_series:
                # Rec file is authoritative; fall back to Google Books subtitle parsing
                title_key = _norm_title(title)
                if title_key in series_lookup:
                    sname, sidx = series_lookup[title_key]
                    series_info = (sname, sidx)
                    print(f"  → series (rec): {sname} #{int(sidx)}")
                else:
                    series_info = parse_series(found_title)
                    if series_info:
                        sname, sidx = series_info
                        print(f"  → series (parsed): {sname} #{sidx}")
                if series_info:
                    sname, sidx = series_info
                    fields += ["-f", f"series:{sname}", "-f", f"series_index:{sidx}"]

            # Cover
            cover_path = cover_dir / f"cover_{book_id}.jpg"
            cover_ok = False
            cover_url = vol.get("cover_url")
            if cover_url:
                cover_ok = download_image(cover_url, cover_path)
                if cover_ok:
                    fields += ["-f", f"cover:{cover_path}"]

            if not fields:
                print("  · Nothing new to set")
                skipped += 1
                time.sleep(args.delay)
                continue

            rc, _, stderr = calibredb("set_metadata", str(book_id), *fields)
            if rc == 0:
                notes = []
                if cover_ok:
                    notes.append("cover")
                if series_info:
                    notes.append("series")
                suffix = f" ({', '.join(notes)})" if notes else ""
                print(f"  ✓ Updated{suffix}")
                ok += 1
            else:
                print(f"  ✗ set_metadata failed: {stderr}")
                failed += 1

            if i < len(books) - 1:
                time.sleep(args.delay)

    print(f"\nDone: {ok} updated, {skipped} skipped, {failed} failed")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="Show recently added books")
    p_list.add_argument("--since", metavar="DATE",
                        help="ISO date filter (default: today)")

    p_update = sub.add_parser("update", help="Fetch and apply metadata + covers")
    p_update.add_argument("--since", metavar="DATE",
                          help="Process books added since DATE (ISO format)")
    p_update.add_argument("--ids", nargs="+", type=int, metavar="ID",
                          help="Specific Calibre book IDs to update")
    p_update.add_argument("--dry-run", action="store_true",
                          help="Show which books would be processed, without changing anything")
    p_update.add_argument("--delay", type=float, default=1.5, metavar="SEC",
                          help="Seconds between Google Books API calls (default: 1.5)")
    p_update.add_argument("--rec-file", metavar="PATH",
                          help=f"Rec file for series lookup (default: {REC_FILE_DEFAULT})")

    args = parser.parse_args()
    if args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "update":
        cmd_update(args)


if __name__ == "__main__":
    main()
