#!/usr/bin/env python3
"""
audiobook-watch.py — Auto-process newly arrived audiobooks

Watches INBOX (where Secondo's MAM classifier drops completed audiobook
downloads) for stable, fully-arrived items. For each one:
  1. Determines the author from embedded tags (never guesses)
  2. Stages it under Processing/<Author>/
  3. Runs join (if it's a raw multi-file folder), tags, and rename
  4. Moves the finished .m4b(s) to Queue/<Author>/

Stability check is stateless across invocations (no in-process sleep):
an item is only processed once its size+mtime are unchanged from the
previous run, recorded in STATE_FILE. This fits a WatchPaths-triggered
LaunchAgent, which re-invokes the script on every filesystem event —
a slow copy just gets caught stable on a later trigger.

Default is dry run. Pass --fix to apply. Intended to always run with
--fix under the LaunchAgent; dry run is for manual sanity-checking.
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

INBOX      = Path("/Volumes/Vault/downloads/audiobooks")
PROCESSING = Path("/Volumes/Attic/Audiobooks/Processing")
QUEUE      = Path("/Volumes/Attic/Audiobooks/Queue")
STATE_FILE = Path("/tmp/audiobook-watch-state.json")
LOG_FILE   = Path("/tmp/audiobook-watch.log")

AUDIO_EXT = {".mp3", ".m4a", ".m4b"}
SCRIPTS_DIR = Path.home() / "bin"


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


# ── Stability tracking ───────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state))


def fingerprint(path: Path) -> list:
    """Total size + mtime across a file or directory tree — cheap stability signal."""
    if path.is_file():
        st = path.stat()
        return [st.st_size, st.st_mtime]
    total_size = 0.0
    latest_mtime = 0.0
    for f in path.rglob("*"):
        if f.is_file():
            st = f.stat()
            total_size += st.st_size
            latest_mtime = max(latest_mtime, st.st_mtime)
    return [total_size, latest_mtime]


def is_stable(path: Path, state: dict) -> bool:
    key = str(path)
    current = fingerprint(path)
    previous = state.get(key)
    state[key] = current
    return previous == current


# ── Inbox discovery ───────────────────────────────────────────────────────────

def has_audio(path: Path) -> bool:
    if path.is_file():
        return path.suffix.lower() in AUDIO_EXT
    return any(f.suffix.lower() in AUDIO_EXT for f in path.rglob("*") if f.is_file())


def discover_arrivals(inbox: Path) -> list:
    if not inbox.exists():
        return []
    items = []
    for entry in sorted(inbox.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file() and entry.suffix.lower() not in AUDIO_EXT:
            continue  # .nfo, .txt, checksums — not a book unit
        if not has_audio(entry):
            continue
        items.append(entry)
    return items


# ── Tagging ───────────────────────────────────────────────────────────────────

def probe_tag(path: Path, tag: str) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", f"format_tags={tag}",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()


def first_audio_file(path: Path) -> Path:
    if path.is_file():
        return path
    return sorted(f for f in path.rglob("*") if f.suffix.lower() in AUDIO_EXT)[0]


def detect_author(item: Path) -> str:
    """Read the embedded artist tag. Never guessed — an empty result means skip."""
    sample = first_audio_file(item)
    return probe_tag(sample, "artist").strip() or probe_tag(sample, "album_artist").strip()


# ── Pipeline steps ────────────────────────────────────────────────────────────

def run_script(name: str, author: str, log_ctx: str) -> bool:
    cmd = [str(SCRIPTS_DIR / name), "--root", str(PROCESSING), "--author", author, "--fix"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"\n--- {name} ({log_ctx}) ---\n{result.stdout}\n{result.stderr}\n")
    if result.returncode != 0:
        log.error("  %s FAILED (exit %d) — see %s", name, result.returncode, LOG_FILE)
        return False
    return True


def notify(title: str, message: str):
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{message}" with title "{title}"'],
            capture_output=True,
        )
    except Exception:
        pass


def process_item(item: Path, args) -> str:
    """Returns one of: 'processed', 'no_author', 'error'."""
    author = detect_author(item)
    if not author:
        log.warning("SKIP (no artist tag): %s — needs manual handling", item.name)
        return "no_author"

    log.info("PROCESSING: %s  [author=%s]", item.name, author)
    if not args.fix:
        log.info("  WOULD stage under Processing/%s/", author)
        return "processed"

    author_dir = PROCESSING / author
    author_dir.mkdir(parents=True, exist_ok=True)

    is_raw_folder = item.is_dir()
    dest = author_dir / item.name
    if dest.exists():
        log.error("  CONFLICT: %s already exists in Processing/%s/ — leaving in inbox", item.name, author)
        return "error"
    shutil.move(str(item), str(dest))
    log.info("  staged -> Processing/%s/%s", author, item.name)

    if is_raw_folder:
        if not run_script("audiobook-join.py", author, "join"):
            return "error"

    if not run_script("audiobook-tags.py", author, "tags"):
        return "error"
    if not run_script("audiobook-rename.py", author, "rename"):
        return "error"

    queue_author_dir = QUEUE / author
    queue_author_dir.mkdir(parents=True, exist_ok=True)

    moved = []
    for m4b in sorted(author_dir.glob("*.m4b")):
        target = queue_author_dir / m4b.name
        if target.exists():
            log.error("  CONFLICT: %s already exists in Queue/%s/ — left in Processing", m4b.name, author)
            continue
        shutil.move(str(m4b), str(target))
        moved.append(m4b.name)
        log.info("  QUEUED: %s/%s", author, m4b.name)

    try:
        author_dir.rmdir()
    except OSError:
        pass  # leftover files (e.g. a conflict) — fine, next run handles it

    if moved:
        notify("Audiobook ready", f"{author} — {', '.join(moved)}")
        return "processed"
    return "error"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix", action="store_true", help="Apply (default is dry run)")
    args = parser.parse_args()

    setup_logging()
    mode = "LIVE" if args.fix else "DRY RUN"
    log.info("=== audiobook-watch started [%s] ===", mode)

    if not INBOX.exists():
        log.error("Inbox not found (NAS not mounted?): %s", INBOX)
        sys.exit(1)

    state = load_state()
    arrivals = discover_arrivals(INBOX)
    log.info("Found %d candidate item(s) in inbox", len(arrivals))

    processed = skipped_unstable = skipped_no_author = errors = 0

    for item in arrivals:
        if not is_stable(item, state):
            log.info("SKIP (still copying): %s", item.name)
            skipped_unstable += 1
            continue

        result = process_item(item, args)
        if result == "processed":
            processed += 1
            if args.fix:
                state.pop(str(item), None)  # item moved out of inbox; entry is now stale
        elif result == "no_author":
            skipped_no_author += 1
        else:
            errors += 1

    save_state(state)
    log.info("=== Done [%s]: %d processed, %d unstable, %d no-author, %d errors ===",
             mode, processed, skipped_unstable, skipped_no_author, errors)
    if not args.fix and processed > 0:
        log.info("    Run with --fix to apply.")


if __name__ == "__main__":
    main()
