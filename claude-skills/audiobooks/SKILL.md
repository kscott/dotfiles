---
name: audiobooks
description: >
  Operating guide for Ken's audiobook library on the NAS: folder structure, processing pipeline
  (join → tag → rename), syncing to wife's iPhone via Finder/Apple Books, and queue management.
  Use this skill whenever the topic is: processing new audiobooks, tagging/renaming, moving books
  between Queue/Active/Archive, figuring out what's new vs heard, or syncing her phone.
  Trigger on: "audiobook", "process new book", "her phone", "she's out of books", "sync books".
---

# Audiobook Library — Operating Guide

**Her player:** Apple Books (iPhone). Books sync via **Finder** — Ken connects her phone, removes
finished books, syncs new ones. She has no visibility into the library; books appear by magic.
**His job:** maintain the queue and do the sync.

---

## Folder structure

All under `/Volumes/Attic/Audiobooks/` (NAS share, must be mounted):

| Folder | Meaning |
|---|---|
| `Queue/` | Tagged, ready to sync — not yet on her phone |
| `Active/` | Currently on her phone |
| `Archive/` | She's finished with these (also the scripts' working directory) |
| `Open Audible/` | OpenAudible app data; new Audible exports land in `books/` as `.m4b` |

> **Scripts hardcode `Archive/` as their working directory.** Process new books by temporarily placing them under `Archive/<Author>/`, running the scripts, then moving the result to `Queue/<Author>/`.

---

## Scripts

All in `~/bin/`. All default to **dry run** — pass `--fix` to apply. `--author "Name"` limits to one folder.

### `audiobook-join.py`
Converts a folder of MP3s (flat or CD subdirs) into a single M4B with chapter markers, cover art
(from iTunes API), and metadata. Input must be under `Archive/<Author>/<Book>/`.

```bash
audiobook-join.py --author "James Comey"   # dry run
audiobook-join.py --author "James Comey" --fix
```

Not needed when the source is already a single `.m4b` (e.g. OpenAudible exports, direct M4B downloads).

### `audiobook-tags.py`
Audits and repairs embedded tags on `.m4b` files in `Archive/`. Checks: genre, year, artist, title
(fetched from iTunes API); cover art (downloads from iTunes if missing, reformats PNG→JPEG if needed);
series grouping + sort_album (from Calibre DB).

```bash
audiobook-tags.py --author "James Comey"        # dry run
audiobook-tags.py --author "James Comey" --fix
```

### `audiobook-rename.py`
Renames `.m4b` files using Calibre series data. Output format:
- Series book: `Series NN - Title.m4b`
- Standalone: `Title.m4b`

Requires Calibre DB to be accessible (see below). Dry run first — shows proposed renames.

```bash
audiobook-rename.py --author "James Comey"        # dry run
audiobook-rename.py --author "James Comey" --fix
```

### `audiobook-calibre.py`
Manages Calibre series metadata. Use when a book isn't being renamed correctly (missing from Calibre
or wrong series/index).

```bash
audiobook-calibre.py set "FDR Drive" --series "Abby Cannon" --index 2
audiobook-calibre.py audit --author "James Comey"   # gaps between archive and Calibre
audiobook-calibre.py check --author "James Comey"   # duplicate positions, series name conflicts
```

---

## Dependencies

- **`/Volumes/Attic/`** — NAS share (audiobook library). Must be mounted.
- **`/Volumes/Friday/`** — Undici (MacBook Air M5) drive containing Calibre library at
  `/Volumes/Friday/Calibre/metadata.db`. Must be mounted for rename and calibre scripts.
  If not mounted: tags will skip series data, rename will fail.
- **ffmpeg / ffprobe** — required by join and tags scripts (`brew install ffmpeg`).

---

## Processing pipeline for new books

**Source is MP3 folder:**
1. Place folder under `Archive/<Author>/`
2. `audiobook-join.py --author "Name"` → dry run, then `--fix`
3. Continue to tagging below

**Source is already a single `.m4b` (OpenAudible export, direct download):**
1. Move `.m4b` to `Archive/<Author>/` (create author folder if new)
2. Skip join

**Tagging and renaming (both paths):**
```bash
audiobook-tags.py --author "Name"        # dry run
audiobook-tags.py --author "Name" --fix
audiobook-rename.py --author "Name"      # dry run
audiobook-rename.py --author "Name" --fix
```

3. If rename reports `NOT IN CALIBRE`: run `audiobook-calibre.py set` to add the book, then re-run rename.
4. Move the processed `.m4b`(s) from `Archive/<Author>/` to `Queue/<Author>/`.
5. Delete the source folder (MP3s or raw OpenAudible export).

**chapters.txt:** OpenAudible sometimes exports a `.chapters.txt` alongside the `.m4b`. Chapter
embedding from this file is not yet automated — note it exists but no action needed for now.

---

## When she says "I'm out of books"

1. Connect her phone to Ken's Mac via USB.
2. Open Finder → her iPhone → Books.
3. Note which books are finished (she'll have told you, or check Books "Finished" list on her phone).
4. Remove finished books from the Finder sync list → move those `.m4b` files from `Active/` to `Archive/`.
5. Drag books from `Queue/` into the Finder sync list → move those files from `Queue/` to `Active/`.
6. Sync.

---

## Script overlap / known gaps (as of 2026-06-22)

The scripts haven't been formally reviewed for overlap or gaps. Suspected issues:
- `audiobook-join.py` does its own metadata and cover art fetch (iTunes API) — duplicating what
  `audiobook-tags.py` also does. After joining, tags may need a second pass anyway.
- `audiobook-calibre.py audit` finds gaps between Archive and Calibre, but doesn't account for
  Queue — books in Queue are not in Archive yet.
- Scripts may need a `--path` or `--root` flag to support operating on Queue directly, rather than
  requiring a temporary Archive placement.

A script-reorg pass is deferred — capture findings here as they surface.
