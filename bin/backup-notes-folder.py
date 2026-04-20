#!/usr/bin/env python3
"""
backup-notes-folder.py

Backs up ~/Notes to a DMG stored locally in ~/Backups.
- Mounts the DMG, rsyncs ~/Notes to current/, saves deleted/changed files to backups/TIMESTAMP/
- After a sync with changes, copies the DMG to iCloud as an offsite safety copy
- Prunes backup folders older than BACKUP_TTL_DAYS
- Trims log to LOG_MAX_LINES if needed
- Prevents concurrent runs via lock file
- Guarantees unmount on exit via atexit

Run every 30 minutes via launchd (com.kenscott.backup-notes.plist).
"""

import atexit
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# --- Config ---
HOME = Path.home()
DMG_PATH = HOME / "Backups/notes-folder-backup.dmg"
ICLOUD_BACKUP_PATH = HOME / "Library/Mobile Documents/com~apple~CloudDocs/Backups/notes-folder-backup.dmg"
DMG_SIZE = "250m"
DMG_VOLNAME = "notes-backup"
MOUNT_POINT = Path(f"/Volumes/{DMG_VOLNAME}")
SOURCE = HOME / "Notes"
DEST = MOUNT_POINT / "current"
BACKUP_BASE = MOUNT_POINT / "backups"
LOG_FILE = HOME / "logs/backup-notes.log"
LOCK_FILE = Path("/tmp/backup-notes.lock")
BACKUP_TTL_DAYS = 60
LOG_MAX_LINES = 1000

RSYNC_EXCLUDES = ["--exclude=.DS_Store", "--exclude=*.pyc", "--exclude=__pycache__"]

# --- Logging ---
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def trim_log():
    if not LOG_FILE.exists():
        return
    lines = LOG_FILE.read_text().splitlines()
    if len(lines) > LOG_MAX_LINES:
        log(f"Trimming log from {len(lines)} to {LOG_MAX_LINES} lines")
        LOG_FILE.write_text("\n".join(lines[-LOG_MAX_LINES:]) + "\n")

# --- Lock ---
def acquire_lock():
    if LOCK_FILE.exists():
        log("Another backup is already running — exiting")
        sys.exit(0)
    LOCK_FILE.touch()

def release_lock():
    LOCK_FILE.unlink(missing_ok=True)

# --- DMG ---
def dmg_is_mounted():
    result = subprocess.run(["mount"], capture_output=True, text=True)
    return str(MOUNT_POINT) in result.stdout

def create_dmg():
    log(f"Creating DMG at {DMG_PATH} (size: {DMG_SIZE})")
    DMG_PATH.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "hdiutil", "create",
        "-size", DMG_SIZE,
        "-fs", "APFS",
        "-volname", DMG_VOLNAME,
        "-type", "UDIF",
        str(DMG_PATH),
    ], check=True)

def mount_dmg():
    if dmg_is_mounted():
        log("DMG already mounted — skipping attach")
        return
    log("Mounting DMG")
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        result = subprocess.run([
            "hdiutil", "attach", str(DMG_PATH),
            "-mountpoint", str(MOUNT_POINT),
            "-nobrowse", "-quiet",
        ])
        if result.returncode == 0:
            return
        if attempt < max_attempts:
            log(f"Mount attempt {attempt} failed — retrying in 10s")
            time.sleep(10)
    raise RuntimeError(f"Failed to mount DMG after {max_attempts} attempts")

def unmount_dmg():
    if dmg_is_mounted():
        log("Unmounting DMG")
        subprocess.run(
            ["hdiutil", "detach", str(MOUNT_POINT), "-quiet"],
            capture_output=True,
        )

def copy_to_icloud():
    log("Copying DMG to iCloud for offsite safety")
    ICLOUD_BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(DMG_PATH), str(ICLOUD_BACKUP_PATH))
    log("iCloud copy complete")

# --- Rsync ---
def run_rsync(dry_run=False):
    cmd = ["rsync", "-ac", "--delete", "--itemize-changes"] + RSYNC_EXCLUDES
    if dry_run:
        cmd.append("--dry-run")
    cmd += [str(SOURCE) + "/", str(DEST) + "/"]
    result = subprocess.run(cmd, capture_output=True)
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if result.returncode not in (0, 24):  # 24 = partial transfer (vanished files), acceptable
        raise RuntimeError(f"rsync failed (exit {result.returncode}):\n{stderr}")
    return stdout.splitlines()

def parse_changes(lines):
    """Parse itemize-changes output into (action, filepath) pairs."""
    changes = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        indicator, filepath = parts[0], parts[1]
        if indicator.startswith("*deleting"):
            changes.append(("delete", filepath))
        elif indicator.startswith(">") or indicator.startswith("<"):
            changes.append(("change", filepath))
    return changes

def save_to_backup(changes, backup_dir):
    """Copy files about to be deleted or overwritten into backup_dir."""
    saved = 0
    for action, filepath in changes:
        src = DEST / filepath
        if src.is_file():
            dst = backup_dir / filepath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            saved += 1
    return saved

# --- Pruning ---
def prune_old_backups():
    if not BACKUP_BASE.exists():
        return
    cutoff = datetime.now() - timedelta(days=BACKUP_TTL_DAYS)
    pruned = 0
    for entry in BACKUP_BASE.iterdir():
        if entry.is_dir():
            mtime = datetime.fromtimestamp(entry.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(entry)
                pruned += 1
    remaining = sum(1 for e in BACKUP_BASE.iterdir() if e.is_dir())
    if pruned:
        log(f"Pruned {pruned} backup folder(s) older than {BACKUP_TTL_DAYS} days")
    log(f"Backup folders retained: {remaining}")

# --- Main ---
def main():
    log("Starting Notes folder backup")

    acquire_lock()
    atexit.register(release_lock)
    atexit.register(unmount_dmg)

    if not DMG_PATH.exists():
        create_dmg()

    mount_dmg()
    DEST.mkdir(parents=True, exist_ok=True)

    # Step 1: dry run to find what will change or be deleted
    changes = parse_changes(run_rsync(dry_run=True))

    # Step 2: save those files to a timestamped backup folder
    if changes:
        backup_dir = BACKUP_BASE / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        saved = save_to_backup(changes, backup_dir)
        if saved:
            log(f"Saved {saved} file(s) to backups/{backup_dir.name}")
        else:
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

    # Step 3: run the actual sync
    log("Syncing ~/Notes to DMG")
    run_rsync(dry_run=False)

    file_count = sum(1 for f in DEST.rglob("*") if f.is_file())
    log(f"Sync complete — {file_count} current files on DMG")

    prune_old_backups()
    trim_log()
    log("Backup complete")

    # Step 4: unmount cleanly, then copy to iCloud if anything changed
    unmount_dmg()
    if changes:
        copy_to_icloud()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"ERROR: {e}")
        sys.exit(1)
