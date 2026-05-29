#!/usr/bin/env python3
"""
Merge FluidAudio diarization JSON with whisper-cpp JSON into an attributed transcript.
Usage: python3 merge_transcript.py <diarize.json> <whisper.json> <speaker_map>
  speaker_map: comma-separated SPEAKER_ID=Name pairs, e.g. "2=Jasmine,3=Ken"
Outputs markdown to stdout: **Name** _M:SS_ paragraphs.
"""

import sys
import json


def load_diarize(path):
    with open(path) as f:
        return json.load(f)["segments"]


def load_whisper(path):
    with open(path) as f:
        data = json.load(f)
    return [
        {
            "start": seg["offsets"]["from"] / 1000.0,
            "end":   seg["offsets"]["to"]   / 1000.0,
            "text":  seg["text"].strip(),
        }
        for seg in data.get("transcription", [])
    ]


def assign_speaker(start, end, turns, speaker_map):
    overlap = {}
    for t in turns:
        o = min(end, t["endTimeSeconds"]) - max(start, t["startTimeSeconds"])
        if o > 0:
            sid = str(t["speakerId"])
            overlap[sid] = overlap.get(sid, 0) + o
    if not overlap:
        return "Unknown"
    best = max(overlap, key=overlap.get)
    return speaker_map.get(best, f"SPEAKER_{best}")


def main():
    if len(sys.argv) < 4:
        print("Usage: merge_transcript.py <diarize.json> <whisper.json> <2=Jasmine,3=Ken>", file=sys.stderr)
        sys.exit(1)

    speaker_map = {}
    for pair in sys.argv[3].split(","):
        sid, name = pair.strip().split("=")
        speaker_map[sid.strip()] = name.strip()

    turns = load_diarize(sys.argv[1])
    segments = load_whisper(sys.argv[2])

    lines = [
        (seg["start"], seg["end"], assign_speaker(seg["start"], seg["end"], turns, speaker_map), seg["text"])
        for seg in segments
    ]

    # Group consecutive same-speaker segments
    grouped = []
    for start, end, speaker, text in lines:
        if grouped and grouped[-1][2] == speaker:
            grouped[-1] = (grouped[-1][0], end, speaker, grouped[-1][3] + " " + text)
        else:
            grouped.append((start, end, speaker, text))

    for start, _, speaker, text in grouped:
        mins, secs = divmod(int(start), 60)
        print(f"**{speaker}** _{mins}:{secs:02d}_\n\n{text}\n")


if __name__ == "__main__":
    main()
