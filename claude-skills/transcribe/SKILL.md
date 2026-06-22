---
name: transcribe
description: >
  Transcribe a Zoom meeting recording into a speaker-attributed transcript and a
  decision-focused summary, saved as two markdown files in the output folder.
  Takes a Zoom recording folder (containing the .m4a/.mp4 and ideally the
  .transcript.vtt) or a single audio file. Auto-detects meeting title and
  attendees from Google Calendar using the Zoom filename's UTC timestamp. Uses
  whisper-cpp large-v3-turbo for transcription and the Zoom VTT for speaker
  attribution. Maintains a glossary at `~/.claude/transcribe-glossary.txt` to
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

- `which ffmpeg` — if missing: `brew install ffmpeg`
- FluidAudio CLI at `~/dev/FluidAudio/.build/arm64-apple-macosx/release/fluidaudiocli` — if missing:
  ```bash
  gh repo clone FluidInference/FluidAudio ~/dev/FluidAudio
  cd ~/dev/FluidAudio && swift build -c release --product fluidaudiocli
  ```
- Merge script at `~/.claude/skills/transcribe/merge_transcript.py` — no extra dependencies (stdlib only)
- Optional: `~/.claude/transcribe-glossary.txt` — custom vocab file for proper noun correction (see step 6)

### 5. Convert audio to whisper's expected format

```bash
ffmpeg -y -i <input-audio> -ar 16000 -ac 1 -c:a pcm_s16le /tmp/meeting.wav
```

Works transparently for `.m4a`, `.mp4`, `.mp3`, `.wav`.

### 6. Transcribe with FluidAudio (ANE-accelerated)

```bash
~/dev/FluidAudio/.build/arm64-apple-macosx/release/fluidaudiocli transcribe \
  /tmp/meeting.wav \
  --model-version v3 \
  --output-json /tmp/meeting_whisper.json
```

Add `--custom-vocab ~/.claude/transcribe-glossary.txt` if the glossary file exists — it corrects proper nouns (team names, project names, technical terms) via CTC rescoring. See **Custom Vocabulary** section below.

**Model options** (benchmarked on M4 Mac Mini, 57-min recording):

| Model | Speed | Quality | Use when |
|---|---|---|---|
| `v3` (default, 0.6B) | 356x real-time | Best | Always — best accuracy |
| `110m` (110M) | 578x real-time | Good | Speed-critical, shorter recordings |

**Do NOT use whisper-cpp for transcription** — 13x real-time vs 356x. FluidAudio Parakeet v3 is 27x faster with comparable quality on English speech.

The output JSON has the same segment structure as whisper-cpp — `merge_transcript.py` reads both formats.

### 7. Parse Zoom VTT or run FluidAudio diarization

**If a `*.transcript.vtt` was found:**

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

**If no VTT (audio-only recording):** use FluidAudio for diarization, then merge with whisper-cpp JSON.

**Step 1 — Diarize:**
```bash
~/dev/FluidAudio/.build/arm64-apple-macosx/release/fluidaudiocli process \
  /tmp/meeting.wav \
  --num-clusters <number-of-speakers> \
  --output /tmp/meeting_diarize.json
```

Uses Apple Neural Engine — very fast, no external dependencies.

**Step 2 — Identify speakers:**

Show the distribution and ask Ken to map each ID to a name before merging:
```bash
python3 -c "
import json
from collections import Counter
d = json.load(open('/tmp/meeting_diarize.json'))
counts = Counter(str(s['speakerId']) for s in d['segments'])
for sid, n in sorted(counts.items()):
    mins = sum(s['endTimeSeconds']-s['startTimeSeconds'] for s in d['segments'] if str(s['speakerId'])==sid)/60
    print(f'SPEAKER_{sid}: {n} segments, {mins:.1f} min')
"
```

IDs with <0.5 min total are usually noise artifacts — fold them into the nearest real speaker. For remaining ambiguous IDs, cross-reference with the whisper transcript by timestamp and ask Ken which is which (or he may have told you upfront — e.g. "female voice is X").

**Step 3 — Merge:**
```bash
python3 ~/.claude/skills/transcribe/merge_transcript.py \
  /tmp/meeting_diarize.json \
  /tmp/meeting_whisper.json \
  "<ID>=<Name>,<ID>=<Name>" \
  > /tmp/transcript_body.md
```

Speaker map format: `"ID=Name,ID=Name"` using the string IDs from the diarization JSON. Example: `"2=Jasmine,3=Ken"`. IDs are strings in the JSON, not integers.

### 8. Clean output and apply glossary

- Detect trailing hallucinations (repeated phrases at end of audio) — drop them.
- **Apply post-processing substitutions** from `~/.claude/transcribe-glossary.txt` to the final transcript text. This applies to ALL transcripts regardless of source — FluidAudio, Zoom VTT, or anything else. Read the file, apply each term substitution (and aliases → canonical form) to the transcript markdown before writing the output file.
- After the transcript is published, if Ken corrects a misrecognized name or term in conversation, propose adding it to `~/.claude/transcribe-glossary.txt`. The same file drives both the FluidAudio custom vocab (acoustic correction at transcription time) and this post-processing pass (text correction after the fact).

## Custom Vocabulary

FluidAudio supports CTC-based vocabulary boosting — it corrects proper nouns the ASR misrecognizes without retraining the model. Applied at transcription time via `--custom-vocab`.

**File:** `~/.claude/transcribe-glossary.txt`

**Format:** one term per line; optionally `term: alias1, alias2` for phonetic variants

```
# Format: one term per line
# Aliases: term: alias1, alias2
Ibotta
Titus
Shelbey: Shelby
Build Our Way Out: builder layout, builder way out
TypeScript: typescript, Typescript
```

**How it works:** uses a separate CTC encoder (97.5 MB, downloaded once) to score each vocab term against the audio, then replaces ASR output only when the acoustic evidence favors the vocab term. Guards against false positives on short/common words.

**When to update:** whenever Ken corrects a proper noun in conversation after a transcript is published. Propose the addition, confirm with Ken, then append to the file.

### 9. Write the transcript file

Path: `<output-folder>/<meeting-title> Transcript.md`

Header fields:

```markdown
# <Meeting Title> — Transcript

**Date:** <Weekday>, <Month Day, Year>
**Duration:** ~<N> minutes
**Source:** <audio-filename>; <vtt-filename if present>
**Method:** FluidAudio Parakeet v3 + FluidAudio speaker diarization (ANE) [if VTT: Zoom VTT speaker diarization]
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

- `~/.claude/transcribe-glossary.txt` — misrecognition glossary maintained by Claude. Applied automatically before publishing. Update it whenever a new consistent error is identified.
- `~/.claude/transcribe-glossary-trinity.txt` — Trinity UMC-specific vocab; use instead of the main glossary when transcribing Trinity meetings.

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
