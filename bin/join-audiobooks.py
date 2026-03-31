#!/usr/bin/env python3
"""
join-audiobooks.py — Convert multi-file audiobook folders to single M4B

Finds book folders under ARCHIVE, concatenates all audio files into a single
M4B with AAC audio, chapter markers at track boundaries, embedded cover art
(via iTunes Search API), and full metadata — all in one pass.

Structure handled:
  Author/Book/*.mp3          — flat folder
  Author/Book/CD1/*.mp3      — CD/Disc subdirectories
  Author/Book/*.disc/        — .disc folder naming
"""

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ARCHIVE = Path("/Volumes/Attic/Audiobooks/Archive")
LOG_FILE = Path("/tmp/audiobook-join.log")
AUDIO_EXT = {".mp3", ".mp4", ".m4a"}


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


# ── File discovery ────────────────────────────────────────────────────────────

def is_cd_dir(path: Path) -> bool:
    return bool(re.match(r"^(cd|disc|disk)\s*\d|\.disc$", path.name, re.IGNORECASE))


def get_audio_files(book_dir: Path) -> list:
    try:
        cd_dirs = sorted(
            d for d in book_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".") and is_cd_dir(d)
        )
        if cd_dirs:
            files = []
            for cd in cd_dirs:
                files += sorted(
                    f for f in cd.iterdir()
                    if f.is_file() and f.suffix.lower() in AUDIO_EXT
                )
            return files
        return sorted(
            f for f in book_dir.iterdir()
            if f.is_file() and f.suffix.lower() in AUDIO_EXT
        )
    except OSError:
        return []


def discover_books(archive: Path) -> list:
    books = []
    try:
        author_dirs = sorted(
            d for d in archive.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    except OSError:
        log.error("Cannot read archive: %s", archive)
        return []

    for author_dir in author_dirs:
        try:
            items = sorted(
                d for d in author_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
        except OSError:
            continue
        for item in items:
            if get_audio_files(item):
                books.append(item)

    return books


# ── iTunes metadata ───────────────────────────────────────────────────────────

def fetch_itunes_meta(title: str, author: str):
    query = urllib.parse.quote(f"{title} {author}")
    url = (
        f"https://itunes.apple.com/search"
        f"?term={query}&media=audiobook&entity=audiobook&limit=5&country=us"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "join-audiobooks/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        results = data.get("results", [])
        if not results:
            return None, None, None
        r = results[0]
        art = r.get("artworkUrl100", "").replace("100x100bb", "600x600bb")
        year = r.get("releaseDate", "")[:4]
        genre = r.get("primaryGenreName", "")
        return art or None, year or None, genre or None
    except Exception:
        return None, None, None


def fetch_cover(art_url: str):
    if not art_url:
        return None
    try:
        req = urllib.request.Request(art_url, headers={"User-Agent": "join-audiobooks/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if not data:
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(data)
        tmp.close()
        return Path(tmp.name)
    except Exception:
        return None


# ── Chapter metadata ──────────────────────────────────────────────────────────

def get_duration_ms(path: Path) -> int:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        return int(float(r.stdout.strip()) * 1000)
    except Exception:
        return 0


def escape_ffmeta(s: str) -> str:
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace(";", "\\;")
        .replace("#", "\\#")
        .replace("\n", "\\\n")
    )


def build_chapter_metadata(
    files: list, title: str, author: str, genre: str, year: str
) -> str:
    basenames = [f.stem for f in files]

    # Find common filename prefix across all tracks
    prefix = basenames[0] if basenames else ""
    for name in basenames[1:]:
        while not name.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                break
    prefix = re.sub(r"[\s\-_\.]+$", "", prefix)

    def clean_title(basename: str, idx: int) -> str:
        t = basename[len(prefix):] if prefix else basename
        t = re.sub(r"^[\s\-_\.]+", "", t).strip()
        if re.fullmatch(r"\d+", t):
            t = f"Chapter {int(t)}"
        return t or f"Chapter {idx}"

    lines = [
        ";FFMETADATA1",
        f"title={escape_ffmeta(title)}",
        f"artist={escape_ffmeta(author)}",
        f"album_artist={escape_ffmeta(author)}",
        f"album={escape_ffmeta(title)}",
        f"genre={escape_ffmeta(genre or 'Audiobook')}",
    ]
    if year:
        lines.append(f"date={escape_ffmeta(year)}")
    lines.append("")

    pos_ms = 0
    for i, (f, basename) in enumerate(zip(files, basenames), 1):
        dur_ms = get_duration_ms(f)
        if dur_ms <= 0:
            continue
        end_ms = pos_ms + dur_ms
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={pos_ms}",
            f"END={end_ms}",
            f"title={escape_ffmeta(clean_title(basename, i))}",
            "",
        ]
        pos_ms = end_ms

    return "\n".join(lines)


# ── Conversion ────────────────────────────────────────────────────────────────

def convert_book(book_dir: Path, output: Path) -> bool:
    author_name = book_dir.parent.name
    book_name = book_dir.name

    audio_files = get_audio_files(book_dir)
    if not audio_files:
        log.info("SKIP (no audio): %s", book_name)
        return False

    log.info("JOINING (%d files): %s", len(audio_files), book_name)

    art_url, year, genre = fetch_itunes_meta(book_name, author_name)
    cover_path = fetch_cover(art_url)

    meta_content = build_chapter_metadata(
        audio_files, book_name, author_name, genre or "Audiobook", year or ""
    )

    concat_file = None
    meta_file = None

    try:
        # Write concat demuxer file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            concat_file = Path(f.name)
            for af in audio_files:
                escaped = str(af).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # Write FFMETADATA file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            meta_file = Path(f.name)
            f.write(meta_content)

        # Build ffmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(meta_file),
        ]
        if cover_path:
            cmd += ["-i", str(cover_path)]
            cmd += ["-map", "0:a", "-map", "2"]
        else:
            cmd += ["-map", "0:a"]
        cmd += [
            "-map_metadata", "1",
            "-c:a", "aac", "-b:a", "64k",
        ]
        if cover_path:
            cmd += [
                "-c:v", "mjpeg",
                "-disposition:v", "attached_pic",
                "-metadata:s:v", "title=Album cover",
                "-metadata:s:v", "comment=Cover (front)",
            ]
        cmd.append(str(output))

        with open(LOG_FILE, "ab") as log_fh:
            result = subprocess.run(cmd, stdout=log_fh, stderr=log_fh)

        if result.returncode != 0:
            log.info("FAILED: %s (exit %d)", book_name, result.returncode)
            output.unlink(missing_ok=True)
            return False

        cover_status = "cover embedded" if cover_path else "no cover found"
        log.info("SUCCESS: %s (%s)", book_name, cover_status)
        return True

    finally:
        if concat_file:
            concat_file.unlink(missing_ok=True)
        if meta_file:
            meta_file.unlink(missing_ok=True)
        if cover_path:
            cover_path.unlink(missing_ok=True)


# ── Flatten pass ──────────────────────────────────────────────────────────────

def flatten_pass(archive: Path) -> int:
    flattened = 0
    for m4b in sorted(archive.rglob("*.m4b")):
        try:
            rel = m4b.relative_to(archive)
        except ValueError:
            continue
        if len(rel.parts) <= 2:
            continue  # Already at Author/Book.m4b

        author_dir = archive / rel.parts[0]
        target = author_dir / m4b.name

        if m4b == target:
            continue
        if target.exists():
            log.debug("FLATTEN SKIP (conflict): %s", m4b.name)
            continue

        m4b.rename(target)
        log.debug("FLATTEN: %s → %s/", m4b.name, rel.parts[0])
        flattened += 1

        # Remove now-empty parent folders (but not author dir or archive)
        parent = m4b.parent
        while parent != author_dir and parent != archive:
            try:
                for ds in parent.glob(".DS_Store"):
                    ds.unlink(missing_ok=True)
                parent.rmdir()
                parent = parent.parent
            except OSError:
                break

    return flattened


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--author", metavar="NAME", help="Limit to one author folder")
    args = parser.parse_args()

    setup_logging()
    log.info("=== Audiobook join started ===")
    log.info("Archive: %s", ARCHIVE)

    if not ARCHIVE.exists():
        log.error("Archive not found: %s", ARCHIVE)
        sys.exit(1)

    if args.author:
        author_dir = ARCHIVE / args.author
        if not author_dir.is_dir():
            log.error("Author folder not found: %s", author_dir)
            sys.exit(1)
        books = [b for b in discover_books(ARCHIVE) if b.parent == author_dir]
    else:
        books = discover_books(ARCHIVE)
    log.info("Found %d book directories to process", len(books))

    errors = skipped = success = 0

    for book_dir in books:
        author_dir = book_dir.parent
        output = author_dir / f"{book_dir.name}.m4b"

        if output.exists():
            log.info("SKIP (exists): %s", book_dir.name)
            skipped += 1
            continue

        ok = convert_book(book_dir, output)
        if ok:
            success += 1
            shutil.rmtree(book_dir, ignore_errors=True)
            log.debug("  DELETED source: %s", book_dir)
        elif output.exists():
            # convert_book already logged the failure and removed output
            errors += 1
        else:
            skipped += 1

    log.info("=== Done: %d joined, %d skipped, %d failed ===", success, skipped, errors)

    log.info("=== Flatten pass ===")
    flattened = flatten_pass(ARCHIVE)
    log.info("=== Flatten done: %d files moved ===", flattened)


if __name__ == "__main__":
    main()
