---
name: transcribe
description: >
  Transcribe a Zoom meeting recording into a speaker-attributed transcript and a
  decision-focused summary, saved as two markdown files in the output folder.
  Takes a Zoom recording folder (containing the .m4a/.mp4 and ideally the
  .transcript.vtt) or a single audio file. Auto-detects meeting title and
  attendees from Google Calendar using the Zoom filename's UTC timestamp. Uses
  whisper-cpp large-v3-turbo for transcription and the Zoom VTT for speaker
  attribution. Maintains a glossary at `~/ai/transcribe-glossary.md` to
  correct recurring misrecognitions automatically.

  USE THIS SKILL when the user asks to "transcribe meeting", "transcribe this
  zoom", "make a transcript from this recording", "summarize this meeting
  recording", "process this zoom recording", or similar. Triggered by
  `/transcribe <path>`.
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion
---

# Transcribe

Base directory for this skill: `~/.claude/skills/transcribe`

End-to-end Zoom meeting processing: produces an attributed transcript and a decision-focused summary as two markdown files.

## Input

Single positional argument: a path to either a folder or a file.

- **Folder** (preferred): contains the Zoom recording (`*.m4a` or `*.mp4`) and ideally the auto-generated `*.transcript.vtt`. Folder name is often the meeting title.
- **File**: an audio/video file. Skill looks for a sibling `*.transcript.vtt`. If none, runs whisper-only without speaker attribution.

## Process

### 1. Locate input files

- If `$ARGS` is a folder: find the first audio file (`.m4a`, `.mp4`, `.mp3`, `.wav`) and first `*.transcript.vtt`.
- If `$ARGS` is a file: use it; look for a sibling `*.transcript.vtt`.
- If no audio found: stop and report. Do not invent a path.

### 2. Pull meeting context from Google Calendar

- Parse the Zoom filename for its timestamp: `GMT(\d{8})-(\d{6})_Recording` → UTC datetime (e.g., `GMT20260527-173311` → 2026-05-27 17:33:11 UTC).
- Query `mcp__claude_ai_Google_Calendar__list_events` for events overlapping that time (±30 min window). Use Ken's primary calendar.
- Pick the best match: closest start time, longest overlap.
- Extract: event title, attendees. Prefer `displayName`; fall back to email local-part if no display name.

**Fallback if no calendar match:** use the folder name (or file stem) as the title; ask Ken inline for the attendee roster. Don't proceed without a roster — speaker validation depends on it.

### 3. Confirm with Ken (one round)

Show:

- Meeting title
- Time (in Ken's local timezone)
- Attendees pulled from calendar
- Proposed output folder (ask if not obvious from context)

Do not proceed until confirmed.

### 4. Verify dependencies (silent if all present)

- `which whisper-cli ffmpeg` — if either missing: `brew install whisper-cpp ffmpeg`
- Model at `~/.cache/whisper-cpp/models/ggml-large-v3-turbo.bin` — if missing:
  ```bash
  mkdir -p ~/.cache/whisper-cpp/models
  curl -L -o ~/.cache/whisper-cpp/models/ggml-large-v3-turbo.bin \
       https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
  ```

### 5. Convert audio to whisper's expected format

```bash
ffmpeg -y -i <input-audio> -ar 16000 -ac 1 -c:a pcm_s16le /tmp/meeting.wav
```

Works transparently for `.m4a`, `.mp4`, `.mp3`, `.wav`.

### 6. Run whisper-cli

```bash
whisper-cli \
  -m ~/.cache/whisper-cpp/models/ggml-large-v3-turbo.bin \
  -f /tmp/meeting.wav \
  -l en \
  -otxt \
  -of /tmp/meeting_whisper
```

Run in background; on Apple Silicon expect ~1 min per 30 min of audio with Metal acceleration.

### 7. Parse Zoom VTT (if available)

If a `*.transcript.vtt` was found:

```bash
# Get unique speakers first to validate against attendee roster
python3 ~/.claude/skills/transcribe/parse_vtt.py --speakers <vtt-path>

# Then produce the attributed paragraphs
python3 ~/.claude/skills/transcribe/parse_vtt.py <vtt-path> > /tmp/meeting_attributed.md
```

**Speaker validation (important):**
- Compare VTT speaker labels against the calendar attendee list.
- Any label that doesn't match an attendee may be a Zoom conference room (room device joins are labeled with the room name). See [[feedback_zoom_vtt_room_labels]].
- Stop and ask Ken: "VTT has `<unknown-label>` — who is that? A person, or a conference room?"
- Don't publish wrong attribution.

If no VTT: use whisper's txt output as a single unattributed prose block. Note in the transcript header that no speaker attribution was available.

### 8. Clean output and apply glossary

- Strip leading whitespace from each line of whisper's txt output.
- Detect trailing hallucinations (whisper sometimes repeats a phrase 20+ times when fed silence) — drop them.
- **Apply glossary substitutions** from `~/ai/transcribe-glossary.md`. This file is maintained by Claude (you), not the user — read it on every run, apply confident substitutions to the transcript text (both the VTT-attributed paragraphs and any whisper-only prose).
- **After the transcript is published**, if the user catches a new consistent misrecognition in conversation, propose adding it to the glossary. Update `~/ai/transcribe-glossary.md` with the new entry under the appropriate section (confident vs. review-only).

### 9. Write the transcript file

Path: `<output-folder>/<meeting-title> Transcript.md`

Header fields:

```markdown
# <Meeting Title> — Transcript

**Date:** <Weekday>, <Month Day, Year>
**Duration:** ~<N> minutes
**Source:** <audio-filename>; <vtt-filename if present>
**Method:** Zoom VTT speaker diarization + whisper-cpp large-v3-turbo (if no VTT: whisper only, unattributed)
**Attendees:** <from calendar; note any room-label corrections>

> Note: Auto-generated. Minor misrecognitions possible on proper names and acronyms.

---
```

Body: attributed paragraphs from the VTT parser (or whisper prose if no VTT).

### 10. Write the summary file

Path: `<output-folder>/<meeting-title> Summary.md`

Read the transcript and write a decision-focused summary with these sections:

- **TL;DR** (one paragraph)
- **Starting state / context**
- **Decision arc and reasoning** — credit specific people for key framings and analogies
- **Implementation specifics** (if relevant)
- **Action items** grouped by owner, with concrete first steps
- **Decisions and resolutions table** (one row per question answered)

Style: capture *reasoning chains*, not just conclusions. Note when a particular person's framing was the unlock. Quote-worthy lines preserved in italics.

### 11. Report back

Tell Ken:
- Both file paths
- One-line summary of what was decided (or what the meeting was about, if no decisions)

## Memory dependencies

- [[feedback_zoom_vtt_room_labels]] — Zoom labels conference rooms as speakers; verify unfamiliar labels before publishing attributed transcripts.
- [[feedback_consistent_with_stated_rules]] — when a stale attribution gets corrected, audit downstream artifacts (summary, action items) for inherited errors.

## External files

- `~/ai/transcribe-glossary.md` — misrecognition glossary maintained by Claude. Applied automatically before publishing. Update it whenever a new consistent error is identified.

## Troubleshooting

- **Whisper hallucinations at end** (repeated phrases like "Thanks for watching"): audio had trailing silence. Strip the repeated lines.
- **VTT label doesn't match any attendee**: likely a Zoom conference room. Ask Ken who was in the room before publishing.
- **MP4 instead of audio-only**: ffmpeg conversion handles it transparently — no separate extraction step needed.
- **Calendar lookup returns no match**: fall back to folder name for title; ask Ken inline for attendees.
- **Multiple calendar events at the same time**: present the candidates, let Ken pick.
- **Folder doesn't contain a Zoom-format filename** (no `GMT...Recording` pattern): ask Ken for the date/time directly; don't guess from file mtime.

## Output convention

Two markdown files, side-by-side in the output folder:
- `<Meeting Title> Transcript.md`
- `<Meeting Title> Summary.md`

If Ken later asks to combine, that's a follow-up — don't do it preemptively.
