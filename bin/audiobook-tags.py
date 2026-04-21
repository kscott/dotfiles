#!/usr/bin/env python3
"""
audiobook-tags.py — Audit and repair embedded tags in M4B files

For each M4B under ARCHIVE, checks and optionally fixes:
  1. Missing metadata  — genre, year, artist, title (from iTunes)
  2. Missing cover art — downloads from iTunes if absent
  3. Series tags       — grouping and sort-album from Calibre

Default mode is dry run. Pass --fix to apply.
Pass --author "Name" to limit to one author folder.

Usage:
  audiobook-tags.py                       # dry run, all authors
  audiobook-tags.py --author "Vince Flynn"
  audiobook-tags.py --fix
"""

import argparse
import json
import logging
import re
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ARCHIVE    = Path("/Volumes/Attic/Audiobooks/Archive")
CALIBRE_DB = Path("/Volumes/Friday/Calibre/metadata.db")
LOG_FILE   = Path("/tmp/audiobook-tags.log")

SKIP_ARTIST_NORM = {
    "James Bond",
}


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging():
    fmt = logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

log = logging.getLogger(__name__)


# ── Calibre ───────────────────────────────────────────────────────────────────

def load_calibre_series(db_path: Path) -> dict:
    """
    Returns a dict keyed by lowercase title (before colon) →
    (series_name, series_index) or None for standalones.
    """
    if not db_path.exists():
        return {}
    con = sqlite3.connect(str(db_path))
    rows = con.execute("""
        SELECT b.title, s.name, b.series_index
        FROM books b
        LEFT JOIN books_series_link bsl ON b.id = bsl.book
        LEFT JOIN series s ON bsl.series = s.id
    """).fetchall()
    con.close()

    index = {}
    for title, series, idx in rows:
        short = _short_title(title).lower()
        if series:
            index[short] = (series, idx)
    return index


def calibre_lookup(calibre: dict, stem: str) -> tuple | None:
    """Return (series_name, series_index) for a file stem, or None."""
    short = _short_title(stem).lower()
    if short in calibre:
        return calibre[short]
    # Try stripping series prefix from filename: "Gray Man 10 - Relentless" → "relentless"
    m = re.search(r'\d+(?:\.\d+)?\s*-\s*(.+)$', short)
    if m:
        tail = m.group(1).strip()
        if tail in calibre:
            return calibre[tail]
    return None


def format_index(idx: float) -> str:
    return f"{int(idx):02d}" if idx == int(idx) else f"{idx:g}"


# ── ffprobe helpers ───────────────────────────────────────────────────────────

def probe_tag(m4b: Path, tag: str) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", f"format_tags={tag}",
         "-of", "default=nw=1:nk=1", str(m4b)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def cover_codec(m4b: Path) -> str | None:
    """Return the codec name of the embedded cover stream, or None if absent."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_name,codec_type",
         "-of", "default=nw=1", str(m4b)],
        capture_output=True, text=True,
    )
    lines = r.stdout.strip().splitlines()
    codec = None
    for line in lines:
        if line.startswith("codec_name="):
            codec = line.split("=", 1)[1]
        elif line == "codec_type=video":
            return codec
    return None


def extract_cover(m4b: Path) -> Path | None:
    """Extract the embedded cover to a temp JPEG (converts PNG → JPEG if needed)."""
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.close()
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(m4b), "-map", "0:v", "-vframes", "1",
             "-f", "image2", tmp.name],
            capture_output=True,
        )
        if r.returncode == 0 and Path(tmp.name).stat().st_size > 0:
            return Path(tmp.name)
        Path(tmp.name).unlink(missing_ok=True)
        return None
    except Exception:
        return None


def existing_meta(m4b: Path) -> dict:
    codec = cover_codec(m4b)
    return {
        "title":      probe_tag(m4b, "title"),
        "artist":     probe_tag(m4b, "artist"),
        "album":      probe_tag(m4b, "album"),
        "genre":      probe_tag(m4b, "genre"),
        "year":       probe_tag(m4b, "date"),
        "grouping":   probe_tag(m4b, "grouping"),
        "sort_album": probe_tag(m4b, "sort_album"),
        "cover":      codec is not None,
        "cover_codec": codec,
    }


# ── iTunes ────────────────────────────────────────────────────────────────────

def fetch_itunes(title: str, author: str) -> dict:
    query = urllib.parse.quote(f"{title} {author}")
    url = (
        f"https://itunes.apple.com/search"
        f"?term={query}&media=audiobook&entity=audiobook&limit=5&country=us"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "audiobook-tags/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if not results:
            return {}
        res = results[0]
        return {
            "title":   res.get("trackName", ""),
            "artist":  res.get("artistName", ""),
            "year":    res.get("releaseDate", "")[:4],
            "genre":   res.get("primaryGenreName", ""),
            "art_url": res.get("artworkUrl100", "").replace("100x100bb", "600x600bb"),
        }
    except Exception:
        return {}


def fetch_cover(art_url: str) -> Path | None:
    if not art_url:
        return None
    try:
        req = urllib.request.Request(art_url, headers={"User-Agent": "audiobook-tags/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if not data:
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(data)
        tmp.close()
        return Path(tmp.name)
    except Exception:
        return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r'[^\w]', '', (s or '').lower())


def _short_title(title: str) -> str:
    for sep in (":", " — ", " - A ", "/"):
        if sep in title:
            return title[:title.index(sep)].strip()
    return title.strip()


def _strip_series_prefix(stem: str) -> str:
    m = re.search(r'\d+(?:\.\d+)?\s*-\s*(.+)$', stem)
    return m.group(1).strip() if m else stem


# ── Re-mux ────────────────────────────────────────────────────────────────────

def remux(m4b: Path, tags: dict, cover_path: Path | None) -> bool:
    tmp = m4b.with_suffix(".fix-tmp.m4b")

    meta_lines = [";FFMETADATA1"]
    for ffmpeg_tag, key in [
        ("title",       "title"),
        ("artist",      "artist"),
        ("album_artist","artist"),
        ("album",       "title"),
        ("genre",       "genre"),
        ("date",        "year"),
        ("grouping",    "grouping"),
        ("sort_album",  "sort_album"),
    ]:
        val = tags.get(key, "")
        if val:
            meta_lines.append(f"{ffmpeg_tag}={_esc(val)}")
    meta_lines.append("")

    meta_file = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    meta_file.write("\n".join(meta_lines))
    meta_file.close()

    cmd = ["ffmpeg", "-y", "-i", str(m4b)]
    if cover_path:
        cmd += ["-i", str(cover_path)]
    cmd += ["-i", meta_file.name]

    n_inputs = 3 if cover_path else 2
    meta_idx = n_inputs - 1

    if cover_path:
        cmd += ["-map", "0:a", "-map", "1",
                "-c:a", "copy", "-c:v", "mjpeg",
                "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)"]
    else:
        cmd += ["-map", "0:a", "-c:a", "copy",
                "-map", "0:v?", "-c:v", "copy"]

    cmd += ["-map_metadata", str(meta_idx), str(tmp)]

    with open(LOG_FILE, "ab") as lf:
        result = subprocess.run(cmd, stdout=lf, stderr=lf)

    Path(meta_file.name).unlink(missing_ok=True)

    if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.rename(m4b)
        return True
    tmp.unlink(missing_ok=True)
    return False


def _esc(s: str) -> str:
    return (str(s).replace("\\", "\\\\").replace("=", "\\=")
                  .replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n"))


# ── Per-file audit ────────────────────────────────────────────────────────────

def audit(m4b: Path, calibre: dict, args) -> bool:
    book_name   = m4b.stem
    author_name = m4b.parent.name

    meta   = existing_meta(m4b)
    itunes = fetch_itunes(book_name, author_name)

    clean_title  = itunes.get("title",  "").strip() or _strip_series_prefix(book_name)
    clean_artist = itunes.get("artist", "").strip() or author_name

    needs_meta           = not (meta["genre"] and meta["year"] and meta["artist"] and meta["title"])
    needs_cover          = not meta["cover"]
    needs_cover_reformat = meta["cover_codec"] not in (None, "mjpeg")
    title_dirty          = bool(meta["title"]  and _norm(meta["title"])  != _norm(clean_title))
    artist_dirty         = bool(author_name not in SKIP_ARTIST_NORM
                                and meta["artist"] and _norm(meta["artist"]) != _norm(clean_artist))
    needs_normalize      = title_dirty or artist_dirty

    # Series tags from Calibre
    cal = calibre_lookup(calibre, book_name)
    if cal:
        cal_series, cal_idx = cal
        desired_grouping   = cal_series
        desired_sort_album = f"{cal_series} {format_index(cal_idx)}"
    else:
        desired_grouping   = ""
        desired_sort_album = ""

    needs_series = bool(
        desired_grouping and (
            _norm(meta["grouping"])   != _norm(desired_grouping) or
            _norm(meta["sort_album"]) != _norm(desired_sort_album)
        )
    )

    if not any([needs_meta, needs_normalize, needs_cover, needs_cover_reformat, needs_series]):
        return False

    merged = {
        "title":      clean_title,
        "artist":     meta["artist"] if author_name in SKIP_ARTIST_NORM else clean_artist,
        "genre":      meta["genre"]  or itunes.get("genre", "Audiobook"),
        "year":       meta["year"]   or itunes.get("year",  ""),
        "grouping":   desired_grouping   or meta["grouping"],
        "sort_album": desired_sort_album or meta["sort_album"],
    }

    cover_path = None
    if needs_cover_reformat:
        cover_path = extract_cover(m4b) if args.fix else None
    elif needs_cover:
        art_url = itunes.get("art_url", "")
        if art_url:
            cover_path = fetch_cover(art_url) if args.fix else None

    log.info("--- %s", book_name)
    if needs_meta:
        missing = [k for k in ("genre", "year", "artist", "title") if not meta[k]]
        log.info("  META:   missing %s → %s",
                 ", ".join(missing),
                 " | ".join(f"{k}={merged[k]}" for k in missing if merged.get(k)))
    if needs_normalize:
        if title_dirty:
            log.info("  NORM:   title %r → %r", meta["title"], clean_title)
        if artist_dirty:
            log.info("  NORM:   artist %r → %r", meta["artist"], clean_artist)
    if needs_cover_reformat:
        log.info("  COVER:  reformat %s → mjpeg", meta["cover_codec"])
    elif needs_cover:
        log.info("  COVER:  %s", "will download" if itunes.get("art_url") else "not found on iTunes")
    if needs_series:
        log.info("  SERIES: grouping=%r sort-album=%r", desired_grouping, desired_sort_album)

    if not args.fix:
        return True

    ok = remux(m4b, merged, cover_path)
    if cover_path:
        cover_path.unlink(missing_ok=True)
    if ok:
        log.info("  ✓ updated")
        return True
    log.info("  ✗ remux failed")
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix",    action="store_true", help="Apply changes (default is dry run)")
    parser.add_argument("--author", metavar="NAME",      help="Limit to one author folder")
    args = parser.parse_args()

    setup_logging()
    mode = "LIVE" if args.fix else "DRY RUN"
    log.info("=== audiobook-tags started [%s] ===", mode)
    log.info("Archive: %s", ARCHIVE)

    calibre = load_calibre_series(CALIBRE_DB)
    if not calibre:
        log.warning("Calibre DB not found or empty — series tags will not be checked")

    if args.author:
        author_dirs = [ARCHIVE / args.author]
        if not author_dirs[0].exists():
            log.error("Author folder not found: %s", author_dirs[0])
            sys.exit(1)
    else:
        author_dirs = sorted(
            d for d in ARCHIVE.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    updated = skipped = errors = 0

    for author_dir in author_dirs:
        for m4b in sorted(author_dir.glob("*.m4b")):
            try:
                if audit(m4b, calibre, args):
                    updated += 1
                else:
                    skipped += 1
            except Exception as e:
                log.error("  ERROR: %s — %s", m4b.name, e)
                errors += 1

    log.info("=== Done [%s]: %d to update, %d already complete, %d errors ===",
             mode, updated, skipped, errors)
    if not args.fix and updated > 0:
        log.info("    Run with --fix to apply changes.")


if __name__ == "__main__":
    main()
