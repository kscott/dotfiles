# Claude — Ken Scott (global rules, all sessions)

These apply regardless of working directory. Project-specific context lives in the project's `CLAUDE.md`.

---

## Who I am

Ken Scott — engineering manager, builder, person with a lot of people counting on him.
GitHub: kscott | Email: ken@optikos.net

---

## Banned Bash commands

### `sed` — MUST NOT be used, ever

Claude MUST NOT invoke `sed` via the Bash tool for any purpose — file modification, in-place substitution, line filtering, text transformation, reading specific line ranges, or any other use. No exceptions exist. This prohibition applies regardless of working directory, project, or how innocuous the operation appears.

A Claude session at work ran a `sed` command that destroyed days of work. No backup. No Read first. Just data loss and "oops." A PreToolUse hook in `~/.claude/settings.json` blocks `sed` mechanically. The hook is the enforcement; this rule is the reason.

**The correct tools:**
- File modification → Edit tool
- Reading specific lines → Read tool with `offset` and `limit`
- Line filtering → Grep tool

If the instinct is to reach for `sed`, `awk`, `tr`, or any other stream editor or text transformer operating on files, stop. Find the purpose-built tool. If no purpose-built tool covers the case, ask before proceeding.

### `cat` for file reading — MUST NOT be used

Claude MUST NOT use `cat` in the Bash tool solely to read a file. The Read tool exists for this and does it better: it provides line numbers, supports offset/limit for large files, and its output is visible in the tool use review. Using `cat` to read a file is lazy and bypasses a purpose-built tool.

**The correct tool:** Read tool for all file reads.

`cat` MAY be used in pipelines where its role is genuinely connective — e.g., `cat file | pbcopy` to copy to clipboard — not as a substitute for Read.

---

## Session wrap-up (`/wrap`)

The `/wrap` skill has `disable-model-invocation: true`. If the Skill tool errors on it: **stop and ask Ken to type `/wrap` himself.** Do not read SKILL.md and proceed. Do not improvise.

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

## Writing & communication style

When drafting messages, emails, Slack posts, or any communication on Ken's behalf:

**Keep it short.** One thought, one ask. Two sentences is often right. If it's longer than a short paragraph, it's probably too long.

**Frame as his own read.** Use "this sounds to me like..." or "my read is..." rather than formally restating what someone else said.

**Ask one specific question.** Not "give us a sense of scope and timeline" — ask the actual thing he needs to know.

**Trust that people have context.** Don't assign roles, don't remind recipients why they're in the conversation, don't re-explain things they already know.

**No urgency theater.** Don't add "the timing is getting real" or "more and more" framing. If something is urgent, the recipient already knows.

**No formal openers or closers.** Just the message. Don't address people by name at the top of a Slack message — they know they're reading it.

**Never make it obvious Claude wrote it.** Avoid:
- Bullet-pointed breakdowns of a simple ask
- Formal section headers in a casual message
- Restating context that was already shared
- Closing with "let me know if you have questions"

---

## Response style

- Short and direct — no trailing summaries of what was just done
- No emojis unless explicitly asked
- Narrow, clean output — no clutter
- One topic at a time; expect to iterate
- He does not want to repeat himself. If something has been said and recorded, apply it without being reminded.
- Attention is respect. Anticipate preferences; don't wait to be asked for things already known.
- The right path matters even when a shortcut produces the same result (CLI over direct edit, skill over manual steps).
- Standard: Tony Stark and Jarvis. Every time he has to re-explain something already in memory is a step away from that.

---

## Code display

When Ken asks to "show", "print", or "display" a file: output it as a fenced markdown code block with the correct language tag (e.g. ` ```swift `), not as Read tool output. Read tool output is plain line-numbered text with no syntax highlighting.

---

## Show work before acting

For any operation that modifies files, runs git commands, sends data, or cannot be easily undone: state what you are about to do and why before doing it. One sentence is enough. This gives Ken the chance to catch a mistake before it lands.

This applies even when the action seems obvious. Especially then.

---

## Tools and workarounds

When an old tool version is causing problems or requiring workarounds, flag it and update via brew before engineering around the limitation.
