#!/usr/bin/env python3
"""Parse a Zoom-generated VTT file into speaker-attributed markdown paragraphs.

Zoom's auto-generated transcript VTT has one cue per spoken segment with a
"Speaker Name: text" body. This script:
- Reads the VTT
- Groups consecutive same-speaker segments into single paragraphs
- Outputs markdown with **Speaker Name:** prefix per turn

Usage:
    parse_vtt.py <vtt-path> [--cap-seconds N]

The --cap-seconds option drops any cue starting after N seconds — useful when
the recording continued past the actual meeting end and contains dead air.
"""
import re
import sys
from pathlib import Path


def t_to_sec(ts: str) -> float:
    h, m, s = ts.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse(vtt_path: str, cap_seconds: float | None = None) -> str:
    vtt = Path(vtt_path).read_text()
    cues = []
    blocks = re.split(r"\n\n+", vtt.strip())
    for block in blocks[1:]:  # skip WEBVTT header
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d+:\d+:\d+\.\d+)\s+-->\s+(\d+:\d+:\d+\.\d+)", lines[1])
        if not m:
            continue
        start = t_to_sec(m.group(1))
        if cap_seconds is not None and start > cap_seconds:
            break
        body = "\n".join(lines[2:])
        sm = re.match(r"^([A-Z][a-zA-Z\.\- ]+?):\s*(.*)", body, re.DOTALL)
        if sm:
            speaker = sm.group(1).strip()
            text = sm.group(2).strip().replace("\n", " ")
            cues.append((start, speaker, text))

    grouped: list[tuple[str, str]] = []
    for _start, speaker, text in cues:
        if grouped and grouped[-1][0] == speaker:
            grouped[-1] = (speaker, grouped[-1][1] + " " + text)
        else:
            grouped.append((speaker, text))

    out = []
    for speaker, text in grouped:
        text = re.sub(r"\s+", " ", text).strip()
        out.append(f"**{speaker}:** {text}\n")
    return "\n".join(out)


def list_speakers(vtt_path: str) -> list[str]:
    vtt = Path(vtt_path).read_text()
    speakers = set(re.findall(r"^([A-Z][a-zA-Z\.\- ]+?):", vtt, re.MULTILINE))
    return sorted(speakers)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    if args[0] == "--speakers":
        for s in list_speakers(args[1]):
            print(s)
        sys.exit(0)

    vtt_path = args[0]
    cap = None
    if "--cap-seconds" in args:
        idx = args.index("--cap-seconds")
        cap = float(args[idx + 1])
    print(parse(vtt_path, cap))
