# Claude — Ken Scott (global rules, all sessions)

These apply regardless of working directory. Project-specific context lives in `~/ai/CLAUDE.md`.

---

## Session wrap-up (`/wrap`)

The `/wrap` skill has `disable-model-invocation: true` — the Skill tool will error. When that happens:
**Read `~/.claude/skills/wrap/SKILL.md` directly and follow its instructions exactly.**

Do not improvise. Do not substitute manual `doing done` calls or hand-written session log entries.

Always do both steps — `doing done` CLI entry AND session log update. Never one without the other.

**Time rounding:** Round to the nearest 15 minutes (:00, :15, :30, :45) before writing anything.
- 9:34pm → 9:30pm
- 6:52pm → 7:00pm
Both the `--back` value and the session log header must use rounded times.

---

## `doing` CLI rules

- **Never edit `doing.md` directly.** Always use `doing done`, `doing now`, `doing tag`, etc. Direct edits bypass UUID tracking and corrupt the backup chain.
- **Never use `doing undo`.** It doesn't remove individual entries — it restores to a prior snapshot and will likely corrupt unrelated entries. If an entry is wrong, acknowledge it and ask Ken how to handle it.

---

## Code display

When Ken asks to "show", "print", or "display" a file: output it as a fenced markdown code block with the correct language tag (e.g. ` ```swift `), not as Read tool output. Read tool output is plain line-numbered text with no syntax highlighting.

---

## sed is permanently banned

Never use `sed` via the Bash tool — for any reason, on any file, in any project.

A Claude session at work ran a sed command that destroyed days of work. No backup. No Read first. Just data loss and "oops." A PreToolUse hook in `~/.claude/settings.json` blocks sed mechanically. The hook is the enforcement; this rule is the reason.

**Use the Edit tool for all file modifications.** If the instinct is to reach for sed, stop. There is no exception.

---

## Tools and workarounds

When an old tool version is causing problems or requiring workarounds, flag it and update via brew before engineering around the limitation.

---

## How Ken works

- He does not want to repeat himself. If something has been said and recorded, apply it without being reminded.
- Attention is respect. Anticipate preferences; don't wait to be asked for things already known.
- The right path matters even when a shortcut produces the same result (CLI over direct edit, skill over manual steps).
- Standard: Tony Stark and Jarvis. Every time he has to re-explain something already in memory is a step away from that.
