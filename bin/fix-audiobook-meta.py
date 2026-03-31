#!/usr/bin/env python3
"""
fix-audiobook-meta.py — Audit and repair existing M4B files

For each M4B under ARCHIVE, checks and optionally fixes:
  1. Missing metadata  — genre, year, artist, title, album (from iTunes)
  2. Missing cover art — downloads from iTunes if absent
  3. Filename cleanup  — proposes a cleaner name based on iTunes title +
                         series/book-number from collectionName

Default mode is dry run: prints a report of what would change.
Pass --fix to apply all changes (re-mux + rename).
Pass --author "Name" to limit to one author folder.
Pass --no-rename to skip filename proposals entirely.

Usage:
  fix-audiobook-meta.py                       # dry run, all authors
  fix-audiobook-meta.py --author "Vince Flynn"
  fix-audiobook-meta.py --fix                 # apply everything
  fix-audiobook-meta.py --fix --no-rename     # fix metadata/cover only
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ARCHIVE = Path("/Volumes/Attic/Audiobooks/Archive")
LOG_FILE = Path("/tmp/audiobook-meta-fix.log")


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


# ── ffprobe helpers ───────────────────────────────────────────────────────────

def probe_tag(m4b: Path, tag: str) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", f"format_tags={tag}",
         "-of", "default=nw=1:nk=1", str(m4b)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def has_cover(m4b: Path) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "stream=codec_type",
         "-of", "default=nw=1:nk=1", str(m4b)],
        capture_output=True, text=True,
    )
    return "video" in r.stdout


def existing_meta(m4b: Path) -> dict:
    return {
        "title":  probe_tag(m4b, "title"),
        "artist": probe_tag(m4b, "artist"),
        "album":  probe_tag(m4b, "album"),
        "genre":  probe_tag(m4b, "genre"),
        "year":   probe_tag(m4b, "date"),
        "cover":  has_cover(m4b),
    }


# ── iTunes ────────────────────────────────────────────────────────────────────

def fetch_itunes(title: str, author: str) -> dict:
    """Return dict with keys: title, artist, year, genre, art_url, series, series_num."""
    query = urllib.parse.quote(f"{title} {author}")
    url = (
        f"https://itunes.apple.com/search"
        f"?term={query}&media=audiobook&entity=audiobook&limit=5&country=us"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fix-audiobook-meta/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if not results:
            return {}
        res = results[0]
        info = {
            "title":      res.get("trackName", ""),
            "artist":     res.get("artistName", ""),
            "year":       res.get("releaseDate", "")[:4],
            "genre":      res.get("primaryGenreName", ""),
            "art_url":    res.get("artworkUrl100", "").replace("100x100bb", "600x600bb"),
            "collection": res.get("collectionName", ""),
            "series":     "",
            "series_num": "",
        }
        # Parse series name + book number from collectionName
        # Patterns: "Series Name, Book 3" / "Series Name #3" / "Series Name Book 3"
        col = info["collection"]
        m = re.search(r"^(.*?)(?:,\s*|\s+)(?:Book|#)\s*(\d+)", col, re.IGNORECASE)
        if m:
            info["series"]     = m.group(1).strip()
            info["series_num"] = m.group(2).strip()
        return info
    except Exception:
        return {}


def fetch_cover(art_url: str) -> Path | None:
    if not art_url:
        return None
    try:
        req = urllib.request.Request(art_url, headers={"User-Agent": "fix-audiobook-meta/1.0"})
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


# ── Filename proposal ─────────────────────────────────────────────────────────

def proposed_filename(current: Path, itunes: dict) -> str | None:
    """
    Return a cleaner filename (no extension) or None if no improvement found.

    Priority:
      1. Series N - Title    (if iTunes has series + number)
      2. Title               (if iTunes title differs meaningfully from current stem)
      3. None                (current name is already clean)
    """
    if not itunes:
        return None

    clean_title = itunes.get("title", "").strip()
    if not clean_title:
        return None

    series     = itunes.get("series", "").strip()
    series_num = itunes.get("series_num", "").strip()

    if series and series_num:
        candidate = f"{series} {series_num} - {clean_title}"
    else:
        candidate = clean_title

    # Sanitise: replace characters that are problematic in filenames
    candidate = re.sub(r'[:/\\]', '-', candidate).strip()

    # Only propose if it's actually different from the current stem
    current_stem = current.stem.strip()
    if candidate.lower() == current_stem.lower():
        return None

    return candidate


# ── Re-mux ────────────────────────────────────────────────────────────────────

def remux(m4b: Path, itunes: dict, cover_path: Path | None) -> bool:
    """Re-mux m4b in place with updated metadata and optional cover. Audio copied."""
    tmp = m4b.with_suffix(".fix-tmp.m4b")

    meta_lines = [";FFMETADATA1"]
    for key, tag in [
        ("title",  "title"),
        ("artist", "artist"),
        ("artist", "album_artist"),
        ("title",  "album"),
        ("genre",  "genre"),
        ("year",   "date"),
    ]:
        val = itunes.get(key, "")
        if val:
            meta_lines.append(f"{tag}={_esc(val)}")
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
        cmd += ["-map", "0:a", "-c:a", "copy"]
        # Preserve existing cover if present
        cmd += ["-map", "0:v?", "-c:v", "copy"]

    cmd += ["-map_metadata", str(meta_idx), str(tmp)]

    with open(LOG_FILE, "ab") as lf:
        result = subprocess.run(cmd, stdout=lf, stderr=lf)

    Path(meta_file.name).unlink(missing_ok=True)

    if result.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.rename(m4b)
        return True
    else:
        tmp.unlink(missing_ok=True)
        return False


def _esc(s: str) -> str:
    return (str(s).replace("\\", "\\\\").replace("=", "\\=")
                  .replace(";", "\\;").replace("#", "\\#").replace("\n", "\\\n"))


# ── Per-file audit ────────────────────────────────────────────────────────────

def audit(m4b: Path, args) -> bool:
    """Audit one file. Returns True if any change was made (or would be made)."""
    book_name   = m4b.stem
    author_name = m4b.parent.name

    meta = existing_meta(m4b)

    needs_meta  = not (meta["genre"] and meta["year"] and meta["artist"] and meta["title"])
    needs_cover = not meta["cover"]
    changed     = False

    # Always fetch iTunes so we can propose a rename even on complete files
    itunes = fetch_itunes(book_name, author_name)

    # Merge: prefer existing values, fill gaps from iTunes
    merged = {
        "title":  meta["title"]  or itunes.get("title",  book_name),
        "artist": meta["artist"] or itunes.get("artist", author_name),
        "genre":  meta["genre"]  or itunes.get("genre",  "Audiobook"),
        "year":   meta["year"]   or itunes.get("year",   ""),
        "series":     itunes.get("series", ""),
        "series_num": itunes.get("series_num", ""),
    }

    cover_path = None
    if needs_cover:
        art_url = itunes.get("art_url", "")
        if art_url:
            cover_path = fetch_cover(art_url) if args.fix else None

    # Filename proposal
    new_stem = None
    if not args.no_rename:
        new_stem = proposed_filename(m4b, {**itunes, **{"title": merged["title"],
                                                         "series": merged["series"],
                                                         "series_num": merged["series_num"]}})

    # Nothing to do
    if not needs_meta and not needs_cover and not new_stem:
        return False

    # Report
    log.info("--- %s", book_name)
    if needs_meta:
        missing = [k for k in ("genre", "year", "artist", "title") if not meta[k]]
        log.info("  META:   missing %s → %s",
                 ", ".join(missing),
                 " | ".join(f"{k}={merged[k]}" for k in missing if merged.get(k)))
    if needs_cover:
        log.info("  COVER:  %s", "will download" if itunes.get("art_url") else "not found on iTunes")
    if new_stem:
        log.info("  RENAME: %s → %s", m4b.name, new_stem + ".m4b")

    if not args.fix:
        return True   # dry run — reported, not applied

    # Apply
    if needs_meta or needs_cover:
        ok = remux(m4b, merged, cover_path)
        if cover_path:
            cover_path.unlink(missing_ok=True)
        if ok:
            log.info("  ✓ metadata/cover updated")
            changed = True
        else:
            log.info("  ✗ remux failed")
            return False

    if new_stem:
        new_path = m4b.parent / (new_stem + ".m4b")
        if new_path.exists():
            log.info("  RENAME skipped — target already exists: %s", new_path.name)
        else:
            m4b.rename(new_path)
            log.info("  ✓ renamed → %s", new_path.name)
            changed = True

    return changed


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix",       action="store_true",
                        help="Apply changes (default is dry run)")
    parser.add_argument("--no-rename", action="store_true",
                        help="Skip filename proposals")
    parser.add_argument("--author",    metavar="NAME",
                        help="Limit to one author folder")
    args = parser.parse_args()

    setup_logging()
    mode = "LIVE" if args.fix else "DRY RUN"
    log.info("=== fix-audiobook-meta started [%s] ===", mode)
    log.info("Archive: %s", ARCHIVE)

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
        m4bs = sorted(author_dir.glob("*.m4b"))
        for m4b in m4bs:
            try:
                changed = audit(m4b, args)
                if changed:
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
