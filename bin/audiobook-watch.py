#!/usr/bin/env python3
"""
audiobook-watch.py — Auto-process newly arrived audiobooks

Runs on a polling LaunchAgent (StartInterval, not WatchPaths — WatchPaths
was tested live against the NFS-mounted inbox and missed real events, so
it isn't trustworthy as the trigger). Each run:
  1. Retries anything left over in Processing/ from a prior failed run
     (self-heals transient failures — see sweep_processing)
  2. Scans INBOX for stable, fully-arrived items
  3. For each: determines the author from embedded tags (never guessed),
     stages it under Processing/<Author>/, runs join (if it's a raw
     multi-file folder)/tags/rename, and moves the finished .m4b(s) to
     Queue/<Author>/

Stability check is stateless across invocations (no in-process sleep):
an item is only processed once its size+mtime are unchanged from the
previous run, recorded in STATE_FILE — a slow copy just gets caught
stable on a later poll.

Failure handling: an item that fails partway through (join/tags/rename,
or a naming conflict) is NOT retried from the inbox — it's already been
moved into Processing/, which is exactly why sweep_processing exists to
pick it back up on the next run. A macOS notification fires once per
stuck item (tracked in NOTIFIED_FILE) rather than every 5 minutes, and
clears once the item actually succeeds. A no-artist-tag item is left in
place in the inbox (can't stage it without an author) and also gets a
one-time notification rather than a silent forever-repeating log line.

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
STATE_FILE    = Path("/tmp/audiobook-watch-state.json")
NOTIFIED_FILE = Path("/tmp/audiobook-watch-notified.json")
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


def load_notified() -> set:
    if not NOTIFIED_FILE.exists():
        return set()
    try:
        return set(json.loads(NOTIFIED_FILE.read_text()))
    except Exception:
        return set()


def save_notified(notified: set):
    NOTIFIED_FILE.write_text(json.dumps(sorted(notified)))


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


def needs_join(author_dir: Path) -> bool:
    """True if anything under author_dir isn't already a plain .m4b — i.e. join hasn't run yet."""
    for entry in author_dir.iterdir():
        if entry.is_dir() or entry.suffix.lower() != ".m4b":
            return True
    return False


def run_pipeline(author_dir: Path, author: str) -> bool:
    """Join (if needed)/tags/rename an already-staged Processing/<Author>/ folder, then move to Queue.
    Idempotent — safe to call repeatedly on a folder that's already partially done."""
    if needs_join(author_dir):
        if not run_script("audiobook-join.py", author, "join"):
            return False
    if not run_script("audiobook-tags.py", author, "tags"):
        return False
    if not run_script("audiobook-rename.py", author, "rename"):
        return False

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
        pass  # leftover files (e.g. a conflict) — fine, next sweep handles it

    if moved:
        notify("Audiobook ready", f"{author} — {', '.join(moved)}")
        return True
    return False


def process_item(item: Path, args, notified: set) -> str:
    """Returns one of: 'processed', 'no_author', 'error'."""
    author = detect_author(item)
    if not author:
        key = f"no_author:{item}"
        log.warning("SKIP (no artist tag): %s — needs manual handling", item.name)
        if key not in notified:
            notify("Audiobook needs attention", f"{item.name} has no artist tag — needs manual handling")
            notified.add(key)
        return "no_author"

    log.info("PROCESSING: %s  [author=%s]", item.name, author)
    if not args.fix:
        log.info("  WOULD stage under Processing/%s/", author)
        return "processed"

    author_dir = PROCESSING / author
    author_dir.mkdir(parents=True, exist_ok=True)

    dest = author_dir / item.name
    if dest.exists():
        log.error("  CONFLICT: %s already exists in Processing/%s/ — leaving in inbox", item.name, author)
        return "error"
    shutil.move(str(item), str(dest))
    log.info("  staged -> Processing/%s/%s", author, item.name)

    ok = run_pipeline(author_dir, author)
    key = f"stuck:{author_dir}"
    if ok:
        notified.discard(key)
        return "processed"
    if key not in notified:
        notify("Audiobook processing failed", f"{author} — check {LOG_FILE.name}")
        notified.add(key)
    return "error"


def sweep_processing(args, notified: set) -> tuple:
    """Retry anything left over in Processing/ from a prior failed run — this is what makes
    a transient failure (e.g. Calibre DB briefly unmounted) self-heal instead of staying stuck
    forever, since a failed item is no longer visible to the inbox scan once it's been moved."""
    retried = fixed = still_stuck = 0
    if not PROCESSING.exists():
        return retried, fixed, still_stuck
    for author_dir in sorted(d for d in PROCESSING.iterdir() if d.is_dir() and not d.name.startswith(".")):
        author = author_dir.name
        retried += 1
        log.info("RETRY (stuck in Processing): %s", author)
        if not args.fix:
            log.info("  WOULD retry pipeline for Processing/%s/", author)
            continue
        key = f"stuck:{author_dir}"
        if run_pipeline(author_dir, author):
            fixed += 1
            notified.discard(key)
        else:
            still_stuck += 1
            if key not in notified:
                notify("Audiobook still stuck", f"{author} — check {LOG_FILE.name}")
                notified.add(key)
    return retried, fixed, still_stuck


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
    notified = load_notified()

    retried, fixed, still_stuck = sweep_processing(args, notified)
    if retried:
        log.info("Processing/ sweep: %d retried, %d fixed, %d still stuck", retried, fixed, still_stuck)

    arrivals = discover_arrivals(INBOX)
    log.info("Found %d candidate item(s) in inbox", len(arrivals))

    processed = skipped_unstable = skipped_no_author = errors = 0

    for item in arrivals:
        if not is_stable(item, state):
            log.info("SKIP (still copying): %s", item.name)
            skipped_unstable += 1
            continue

        result = process_item(item, args, notified)
        if result == "processed":
            processed += 1
            if args.fix:
                state.pop(str(item), None)  # item moved out of inbox; entry is now stale
        elif result == "no_author":
            skipped_no_author += 1
        else:
            errors += 1

    save_state(state)
    save_notified(notified)
    log.info("=== Done [%s]: %d processed, %d unstable, %d no-author, %d errors, "
             "%d stuck-retried (%d fixed) ===",
             mode, processed, skipped_unstable, skipped_no_author, errors, retried, fixed)
    if not args.fix and processed > 0:
        log.info("    Run with --fix to apply.")


if __name__ == "__main__":
    main()
