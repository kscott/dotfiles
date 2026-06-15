---
name: log
description: Log a chunk of work to the doing CLI and the session log, and tidy any dirty personal repos. Use throughout the day (not just end of day) whenever Ken wants to capture what he just did — says /log, log it, log this, capture this, wrap up, done for now, or similar. Checks the calendar, writes the doing entry with correct time rounding, appends to the session log, and commits/pushes uncommitted changes in dotfiles/ai/Notes.
disable-model-invocation: true
---

## For Claude: if the Skill tool errors on this skill

`disable-model-invocation: true` means only Ken invokes this skill by typing `/log`.
If you attempted to invoke it via the Skill tool and got an error: **stop, do not read this file and proceed anyway.** Tell Ken the skill errored and ask him to type `/log` himself.

## Current Time
- Now: !`date "+%Y-%m-%d %H:%M"`
- Hostname: !`hostname`

## Session Log

You are logging a chunk of work for Ken Scott. This may run several times a day, not just at end of day. Complete all steps in order.

---

### Step 1: Check calendar

Use the hostname to determine which commands to run.

**Home Mac (Mac-mini):**

```bash
calendar personal today
```

**Work Mac (any other hostname):**

```bash
calendar work today
```

This shows today's events for the relevant calendar set. Ask the user which meetings they attended so they can be logged in doing.

---

### Step 2: doing CLI entry

Review what was accomplished. Write a concise doing entry (one line, imperative, specific).

**Before running the command, compute the time explicitly. Show your work:**

1. **Now:** read the current time from the `## Current Time` block above (e.g. 22:58)
2. **Rounded end:** round to nearest :00, :15, :30, or :45 (e.g. 22:58 → 23:00)
3. **Start time:** prefer what the user stated (e.g. "started at 9pm" → 21:00). Otherwise **read `~/.claude/work-clock`** with the Read tool — the `SessionStart` hook stamps session start there, and `/log` advances it at the end of each run, so it marks the start of *this* chunk. Use that time. Only if the file is missing *and* the user said nothing, ask.
4. **Rounded start:** round start to nearest :00, :15, :30, or :45
5. **`--back` value:** the rounded start time as a clock time (e.g. `--back 9pm`), NOT a duration

State the result before running:
> Start: 9:00pm — End: 11:00pm — `--back 9pm`

Then run:

```
doing done "<summary> @<tags>" --back <rounded-start-time> --section <section>
```

**Section and tagging:**

Always specify `--section` explicitly — never rely on the default.

| Work done | `--section` | Tags |
|---|---|---|
| Ibotta / work projects | `Work` | `@work` |
| Work meetings | `Work` | `@meeting @work @<group>` — e.g. `@content-squad`, `@retailer-distribution` |
| Personal / home tasks | `Home` | `@home` |
| Get Clear and other personal projects | `Home` | `@projects @get-clear` (or relevant project tag) |
| Trinity Council meeting | `Home` | `@meeting @trinity-council` |
| Trinity Council project work | `Home` | `@projects @trinity-council` |

**Tagging rules:**
- Meeting type (standup, 1:1, sprint review) goes in the entry title — not as a tag
- No sub-type tags like `@standup` or `@sprint-review` — redundant
- The group tag (e.g. `@content-squad`) is the clarifying data for work meetings
- If a session touched more than one project, write a separate `doing done` entry per project

**Example:**
```
doing done "Plex playlists, backup verify notification, library comparison doc @projects @home" --back 9pm --section Home
```

---

### Step 3: Session log

Append a new dated entry to:
`~/Library/Mobile Documents/com~apple~CloudDocs/Productivity/session-log.md`

Format:
```markdown
## YYYY-MM-DD (Weekday, ~H:MMam–H:MMpm) — Home Mac / Work Mac

**Focus:** One-line summary

**Completed:**
- Bullet list of what was done, specific enough to reconstruct context

**Pending:**
- Anything left open, blocked, or handed off
```

Append the new entry at the end of the file. The log is chronological, oldest first.

Both doing and session log are non-negotiable — never do one without the other.

---

### Step 4: Tidy working repos

Ken's working repos should not end a session with uncommitted work sitting in them. Check the standing personal repos **plus the current working folder** — most sessions happen inside a repo (e.g. `~/dev/manager-bot`), and that repo must be tidied too, not just the personal list. The loop resolves each path to its repo root and de-dupes, so the current folder is always covered even when it isn't in the standing list.

```bash
for p in ~/dotfiles ~/ai ~/Notes "$PWD"; do
  root=$(git -C "$p" rev-parse --show-toplevel 2>/dev/null) || { echo "=== $p (not a git repo on this machine — skip) ==="; continue; }
  case "|$seen|" in *"|$root|"*) continue;; esac   # already checked
  seen="$seen|$root"
  echo "=== $root ==="; git -C "$root" status --short
done
```

For any repo that's dirty:
1. Report the count of changed files (untracked folders expand — use `git -C <repo> status --short --untracked-files=all | wc -l` for the true file count).
2. Commit in **logical, per-topic groups** (one project/concern per commit — don't sweep everything into one commit), with concise messages. Add only the files for each group explicitly; never blind `git add -A` across unrelated work.
3. **Always push after committing — never ask whether to push.** Push the **current branch**, not always `main` (e.g. manager-bot lives on `kscott/manager-bot-content-customized`): `b=$(git -C <repo> symbolic-ref --short HEAD); git -C <repo> pull --rebase origin "$b" && git -C <repo> push origin "$b"`. If the rebase is blocked by *unrelated* unstaged changes you're not committing yet, `git stash push <those files>` first and `git stash pop` after.
4. End with `git status --short` empty for each repo.

End-of-day commit/push trailer (per global rules):
```
Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

Don't force-push or rewrite already-pushed history without asking. If something in the working tree looks unexpected (a deletion you didn't make, a file you don't recognize), surface it rather than committing it.

---

### Step 5: Confirm

Report what was logged: doing entries (times + summaries), the session log entry header, and the repo state (which repos were committed/pushed, and that all are now clean).

---

### Step 6: Reset the work clock

Write the **rounded end time** from Step 2 to `~/.claude/work-clock` so the next `/log` chunk starts where this one ended. (The `SessionStart` hook seeds this file at session start; each `/log` advances it.) Use the **Write tool** — Bash `>` redirects are blocked by the safety hook — with a single line in the hook's format, e.g. `2026-06-05 12:30 MDT`.

$ARGUMENTS
