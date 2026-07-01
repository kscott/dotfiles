#!/usr/bin/env python3
"""
backup-folder.py — parameterized folder → encrypted-DMG backup.

Usage:
    backup-folder.py <job>      # run the backup for <job>  (ai | notes)
    backup-folder.py doctor     # health-check every job (no backup performed)

One script drives every backup job; per-job settings live in JOBS below.
For each job it: mounts an AES-256 encrypted DMG in ~/Backups (passphrase read
from the login keychain), rsyncs SOURCE into current/, saves deleted/changed
files to backups/TIMESTAMP/, mirrors the DMG to iCloud as an offsite copy after
a sync with changes, prunes backup folders older than BACKUP_TTL_DAYS, trims the
log, prevents concurrent runs via a lock file, and guarantees unmount on exit.

Run every 30 minutes via launchd (com.kenscott.backup-<job>.plist), which passes
the job name as the sole argument.
"""

import atexit
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

# --- Shared config ---
HOME = Path.home()
KEYCHAIN_SERVICE = "backup-dmg"       # login-keychain generic-password holding the DMG passphrase
BACKUP_TTL_DAYS = 60
LOG_MAX_LINES = 1000
BACKUP_INTERVAL_SEC = 1800            # launchd cadence; used by doctor for freshness
RSYNC_EXCLUDES = ["--exclude=.DS_Store", "--exclude=*.pyc", "--exclude=__pycache__"]

# --- Per-job config ---
# Paths are relative to HOME unless absolute. Add a new job by adding an entry here
# and a matching com.kenscott.backup-<job>.plist launch agent.
JOBS = {
    "ai": {
        "source": "ai",
        "dmg": "Backups/ai-folder-backup.dmg",
        "icloud": "Library/Mobile Documents/com~apple~CloudDocs/Backups/ai-folder-backup.dmg",
        "size": "500m",
        "volname": "ai-backup",
        "log": "logs/backup-ai.log",
        "lock": "/tmp/backup-ai.lock",
        "notify_title": "AI Backup Failed",
        "notify_group": "ai-backup-failure",
        "label": "com.kenscott.backup-ai",
    },
    "notes": {
        "source": "Notes",
        "dmg": "Backups/notes-folder-backup.dmg",
        "icloud": "Library/Mobile Documents/com~apple~CloudDocs/Backups/notes-folder-backup.dmg",
        "size": "250m",
        "volname": "notes-backup",
        "log": "logs/backup-notes.log",
        "lock": "/tmp/backup-notes.lock",
        "notify_title": "Notes Backup Failed",
        "notify_group": "notes-backup-failure",
        "label": "com.kenscott.backup-notes",
    },
}

CFG = None  # set by main() before any job work


def build_cfg(job):
    j = JOBS[job]
    def resolve(p):
        p = Path(p)
        return p if p.is_absolute() else HOME / p
    volname = j["volname"]
    mount = Path(f"/Volumes/{volname}")
    return SimpleNamespace(
        job=job,
        source=resolve(j["source"]),
        dmg=resolve(j["dmg"]),
        icloud=resolve(j["icloud"]),
        size=j["size"],
        volname=volname,
        mount=mount,
        dest=mount / "current",
        backup_base=mount / "backups",
        log=resolve(j["log"]),
        lock=Path(j["lock"]),
        error_log=HOME / f"logs/backup-{job}-error.log",
        notify_title=j["notify_title"],
        notify_group=j["notify_group"],
        label=j["label"],
    )


# --- Logging ---
def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    CFG.log.parent.mkdir(parents=True, exist_ok=True)
    with open(CFG.log, "a") as f:
        f.write(line + "\n")


def trim_log():
    if not CFG.log.exists():
        return
    lines = CFG.log.read_text().splitlines()
    if len(lines) > LOG_MAX_LINES:
        log(f"Trimming log from {len(lines)} to {LOG_MAX_LINES} lines")
        CFG.log.write_text("\n".join(lines[-LOG_MAX_LINES:]) + "\n")


# --- Failure notification ---
def notify_failure(msg):
    """Surface a backup failure in Notification Center so it can't fail silently
    (this job once failed every 30 min for a month unnoticed). Prefers
    terminal-notifier (brew); falls back to osascript. -ignoreDnD pierces Focus.
    Never let a notification problem mask the original error."""
    body = msg.replace("\n", " ")[:240]
    tn = shutil.which("terminal-notifier")
    if tn:
        try:
            subprocess.run([
                tn, "-title", CFG.notify_title, "-message", body,
                "-sound", "Basso", "-ignoreDnD", "-group", CFG.notify_group,
            ], capture_output=True, timeout=15)
            return
        except Exception:
            pass
    try:
        safe = body.replace("\\", "").replace('"', "'")
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe}" with title "{CFG.notify_title}" sound name "Basso"'],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass


# --- Passphrase ---
def get_passphrase():
    """Read the DMG passphrase from the login keychain. Fails loudly (which
    triggers notify_failure) rather than silently producing an unencrypted or
    unmountable image."""
    result = subprocess.run(
        ["security", "find-generic-password", "-w", "-s", KEYCHAIN_SERVICE],
        capture_output=True, text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"Could not read DMG passphrase from keychain (service '{KEYCHAIN_SERVICE}'): "
            f"{result.stderr.strip()}"
        )
    return result.stdout.rstrip("\n")


# --- Lock ---
def acquire_lock():
    if CFG.lock.exists():
        log("Another backup is already running — exiting")
        sys.exit(0)
    CFG.lock.touch()


def release_lock():
    CFG.lock.unlink(missing_ok=True)


# --- DMG ---
def dmg_is_mounted():
    result = subprocess.run(["mount"], capture_output=True, text=True)
    return str(CFG.mount) in result.stdout


def create_dmg():
    log(f"Creating encrypted DMG at {CFG.dmg} (size: {CFG.size})")
    CFG.dmg.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "hdiutil", "create",
        "-size", CFG.size,
        "-fs", "APFS",
        "-volname", CFG.volname,
        "-type", "UDIF",
        "-encryption", "AES-256",
        "-stdinpass",
        str(CFG.dmg),
    ], input=get_passphrase(), text=True, check=True)


def mount_dmg():
    if dmg_is_mounted():
        log("DMG already mounted — skipping attach")
        return
    log("Mounting DMG")
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        result = subprocess.run([
            "hdiutil", "attach", str(CFG.dmg),
            "-mountpoint", str(CFG.mount),
            "-nobrowse", "-quiet",
            "-stdinpass",
        ], input=get_passphrase(), text=True)
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
            ["hdiutil", "detach", str(CFG.mount), "-quiet"],
            capture_output=True,
        )


def copy_to_icloud():
    log("Copying DMG to iCloud for offsite safety")
    CFG.icloud.parent.mkdir(parents=True, exist_ok=True)
    # shutil.copy2 is blocked by TCC when run from launchd — Finder has iCloud access
    script = (
        f'tell application "Finder" to duplicate '
        f'POSIX file "{CFG.dmg}" '
        f'to folder POSIX file "{CFG.icloud.parent}" '
        f'with replacing'
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"osascript copy failed: {result.stderr.strip()}")
    log("iCloud copy complete")


# --- Rsync ---
def run_rsync(dry_run=False):
    cmd = ["rsync", "-ac", "--delete", "--itemize-changes"] + RSYNC_EXCLUDES
    if dry_run:
        cmd.append("--dry-run")
    cmd += [str(CFG.source) + "/", str(CFG.dest) + "/"]
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
        src = CFG.dest / filepath
        if src.is_file():
            dst = backup_dir / filepath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            saved += 1
    return saved


# --- Pruning ---
def prune_old_backups():
    if not CFG.backup_base.exists():
        return
    cutoff = datetime.now() - timedelta(days=BACKUP_TTL_DAYS)
    pruned = 0
    for entry in CFG.backup_base.iterdir():
        if entry.is_dir():
            mtime = datetime.fromtimestamp(entry.stat().st_mtime)
            if mtime < cutoff:
                shutil.rmtree(entry)
                pruned += 1
    remaining = sum(1 for e in CFG.backup_base.iterdir() if e.is_dir())
    if pruned:
        log(f"Pruned {pruned} backup folder(s) older than {BACKUP_TTL_DAYS} days")
    log(f"Backup folders retained: {remaining}")


# --- Backup run ---
def run_backup():
    log(f"Starting {CFG.job} folder backup")

    acquire_lock()
    atexit.register(release_lock)
    atexit.register(unmount_dmg)

    if not CFG.dmg.exists():
        create_dmg()

    mount_dmg()
    CFG.dest.mkdir(parents=True, exist_ok=True)

    # Step 1: dry run to find what will change or be deleted
    changes = parse_changes(run_rsync(dry_run=True))

    # Step 2: save those files to a timestamped backup folder
    if changes:
        backup_dir = CFG.backup_base / datetime.now().strftime("%Y-%m-%d_%H%M%S")
        saved = save_to_backup(changes, backup_dir)
        if saved:
            log(f"Saved {saved} file(s) to backups/{backup_dir.name}")
        elif backup_dir.exists():
            shutil.rmtree(backup_dir)

    # Step 3: run the actual sync
    log(f"Syncing {CFG.source} to DMG")
    run_rsync(dry_run=False)

    file_count = sum(1 for f in CFG.dest.rglob("*") if f.is_file())
    log(f"Sync complete — {file_count} current files on DMG")

    prune_old_backups()
    trim_log()
    log("Backup complete")

    # Step 4: unmount cleanly, then copy to iCloud if anything changed
    unmount_dmg()
    if changes:
        copy_to_icloud()


# --- Doctor ---
def _mark(state):
    return {True: "✓", False: "✗", None: "⚠"}[state]


def _last_completion(logfile):
    """Timestamp of the most recent 'Backup complete' line, or None."""
    if not logfile.exists():
        return None
    for line in reversed(logfile.read_text().splitlines()):
        if "Backup complete" in line and line.startswith("["):
            try:
                return datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
    return None


def _git(source, *args):
    return subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True)


def doctor_job(job):
    """Return True if all checks pass (no ✗). ⚠ warnings don't fail."""
    cfg = build_cfg(job)
    print(f"\n[{job}]  source={cfg.source}")
    checks = []  # (state, label, detail)

    # 1. Source is a local-only git repo (custody invariant)
    if not cfg.source.is_dir():
        checks.append((False, "source folder", "missing"))
    else:
        inside = _git(cfg.source, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            checks.append((None, "source is a git repo", "not a git repo"))
        else:
            branch = _git(cfg.source, "symbolic-ref", "--short", "HEAD").stdout.strip() or "?"
            remotes = _git(cfg.source, "remote").stdout.split()
            if remotes:
                checks.append((False, "local-only repo", f"has remote(s): {', '.join(remotes)} — work data must stay off remotes"))
            else:
                checks.append((True, "local-only repo", f"no remote (branch {branch})"))

    # 2. Encrypted DMG present
    if not cfg.dmg.exists():
        checks.append((False, "DMG present", f"missing: {cfg.dmg}"))
    else:
        enc = subprocess.run(["hdiutil", "isencrypted", str(cfg.dmg)], capture_output=True, text=True)
        is_enc = "encrypted: YES" in enc.stdout
        checks.append((is_enc if is_enc else False, "DMG encrypted", "AES-256" if is_enc else "NOT encrypted"))

    # 3. Passphrase resolvable from keychain
    try:
        get_passphrase()
        checks.append((True, "keychain passphrase", f"service '{KEYCHAIN_SERVICE}' readable"))
    except Exception as e:
        checks.append((False, "keychain passphrase", str(e)))

    # 4. iCloud offsite copy present + encrypted
    if not cfg.icloud.exists():
        checks.append((None, "iCloud offsite copy", "missing (created after next sync with changes)"))
    else:
        enc = subprocess.run(["hdiutil", "isencrypted", str(cfg.icloud)], capture_output=True, text=True)
        ok = "encrypted: YES" in enc.stdout
        checks.append((ok if ok else False, "iCloud copy encrypted", "AES-256" if ok else "NOT encrypted"))

    # 5. launchd agent loaded
    loaded = subprocess.run(["launchctl", "list", cfg.label], capture_output=True).returncode == 0
    checks.append((True if loaded else None, "launchd agent loaded", cfg.label if loaded else "not loaded"))

    # 6. Logging healthy — fresh, recent success, bounded, no errors
    if not cfg.log.exists():
        checks.append((False, "log file", f"missing: {cfg.log}"))
    else:
        n_lines = len(cfg.log.read_text().splitlines())
        # A few lines ("Backup complete", "Unmounting DMG", ...) are logged after
        # trim_log() each run, so steady state sits slightly over the cap. Only
        # flag genuinely unbounded growth (trim broken).
        bounded = n_lines <= LOG_MAX_LINES + 25
        checks.append((bounded, "log bounded", f"{n_lines} lines (cap {LOG_MAX_LINES})"))
        last = _last_completion(cfg.log)
        if last is None:
            checks.append((None, "recent completion", "no 'Backup complete' line yet"))
        else:
            age = (datetime.now() - last).total_seconds()
            fresh = age <= 2 * BACKUP_INTERVAL_SEC + 300  # ~allow one missed run
            mins = int(age // 60)
            checks.append((True if fresh else None, "recent completion",
                           f"{mins} min ago" + ("" if fresh else " — stale (asleep or not running?)")))
    if cfg.error_log.exists() and cfg.error_log.stat().st_size > 0:
        checks.append((False, "stderr log empty", f"{cfg.error_log.stat().st_size} bytes — see {cfg.error_log}"))
    else:
        checks.append((True, "stderr log empty", "0 bytes"))

    for state, label, detail in checks:
        print(f"  {_mark(state)} {label}" + (f" — {detail}" if detail else ""))
    return not any(state is False for state, _, _ in checks)


def run_doctor():
    print("backup-folder doctor")
    all_ok = True
    for job in JOBS:
        if not doctor_job(job):
            all_ok = False
    print(f"\n{'All checks passed.' if all_ok else 'FAILURES present — see ✗ above.'}")
    return 0 if all_ok else 1


# --- Main ---
def main():
    global CFG
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args else 2)

    if args[0] == "doctor":
        sys.exit(run_doctor())

    job = args[0]
    if job not in JOBS:
        print(f"Unknown job '{job}'. Known jobs: {', '.join(JOBS)} (or 'doctor').", file=sys.stderr)
        sys.exit(2)

    CFG = build_cfg(job)
    try:
        run_backup()
    except Exception as e:
        log(f"ERROR: {e}")
        notify_failure(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
