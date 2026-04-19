#!/usr/bin/env python3
"""
Rank must-hear missing albums by personal relevance using Plex play history.
Scores each missing album on: artist familiarity, genre affinity, decade affinity,
and how many curated lists cite it.
"""

import re, sqlite3, os, sys, urllib.request, xml.etree.ElementTree as ET
from collections import defaultdict

# Reuse music-gap config
sys.path.insert(0, os.path.dirname(__file__))
NOTES_DIR   = '/Users/ken/Notes/personal'
BEETS_DB    = '/tmp/beets_data.db'
PLEX_SERVER = 'http://192.168.1.35:32400'
PLEX_CONFIG = os.path.expanduser('~/.config/plex/config')

# ---------------------------------------------------------------------------
# Shared normalization (duplicated from music-gap.py for standalone use)
# ---------------------------------------------------------------------------

def normalize(s):
    s = s.lower().strip()
    s = re.sub(r'\s*[\(\[]\d{4}[^\)\]]*[\)\]]', '', s)
    s = re.sub(r'^(the |a |an )', '', s)
    s = re.sub(r"[^\w\s]", '', s)
    return re.sub(r'\s+', ' ', s).strip()

def norm_artist(s):
    s = s.strip()
    if re.match(r'^[A-Z][a-z]+,\s+[A-Z]', s) and '&' not in s and len(s.split(',')) == 2:
        parts = s.split(',', 1)
        s = parts[1].strip() + ' ' + parts[0].strip()
    return normalize(s)

def tokens(s):
    return {w for w in normalize(s).split() if len(w) > 2}

def artist_match(a, b):
    at, bt = tokens(a), tokens(b)
    if not at or not bt: return False
    overlap = at & bt
    if not overlap: return False
    if len(overlap) == 1:
        word = next(iter(overlap))
        if len(word) <= 5 and len(at) > 1 and len(bt) > 1:
            return False
    return True

# ---------------------------------------------------------------------------
# Plex play data
# ---------------------------------------------------------------------------

def fetch_plex_plays():
    config = {}
    with open(PLEX_CONFIG) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                config[k.strip()] = v.strip().strip('"\'')
    token   = config.get('PLEX_TOKEN', '')
    section = config.get('PLEX_SECTION_MUSIC', '1')

    artist_plays  = defaultdict(int)  # normalized artist -> total plays
    decade_plays  = defaultdict(int)  # decade int -> total plays
    album_plays   = defaultdict(int)  # (norm_artist, norm_album) -> plays

    start, size = 0, 500
    total_fetched = 0
    while True:
        url = (f"{PLEX_SERVER}/library/sections/{section}/all"
               f"?type=10&X-Plex-Token={token}"
               f"&X-Plex-Container-Start={start}&X-Plex-Container-Size={size}")
        with urllib.request.urlopen(url, timeout=30) as r:
            root = ET.fromstring(r.read())
        total = int(root.get('totalSize', 0))
        for t in root.findall('Track'):
            plays = int(t.get('viewCount') or 0)
            if plays == 0:
                continue
            artist = t.get('grandparentTitle', '')
            album  = t.get('parentTitle', '')
            year   = t.get('parentYear') or t.get('year') or '0'
            na = norm_artist(artist)
            nb = normalize(album)
            try:
                decade = (int(year) // 10) * 10
            except ValueError:
                decade = 0
            artist_plays[na]          += plays
            decade_plays[decade]      += plays
            album_plays[(na, nb)]     += plays
        start += size
        total_fetched += size
        if start >= total:
            break

    return artist_plays, decade_plays, album_plays

# ---------------------------------------------------------------------------
# Beets genre data
# ---------------------------------------------------------------------------

def load_beets_genres():
    """Returns normalized_artist -> set of genres."""
    db = sqlite3.connect(BEETS_DB)
    artist_genres = defaultdict(set)
    for row in db.execute("SELECT albumartist, genre FROM albums WHERE genre != ''"):
        na = norm_artist(row[0])
        for g in re.split(r'[,;/]', row[1]):
            g = g.strip().lower()
            if g:
                artist_genres[na].add(g)
    db.close()
    return artist_genres

# ---------------------------------------------------------------------------
# Build normalized taste profile
# ---------------------------------------------------------------------------

def build_profile(artist_plays, decade_plays, artist_genres):
    max_artist = max(artist_plays.values()) if artist_plays else 1
    max_decade = max(decade_plays.values()) if decade_plays else 1

    # Genre affinity: weight genre by total plays of artists with that genre
    genre_plays = defaultdict(int)
    for na, plays in artist_plays.items():
        for g in artist_genres.get(na, []):
            genre_plays[g] += plays
    max_genre = max(genre_plays.values()) if genre_plays else 1

    return {
        'artist':  {a: p / max_artist for a, p in artist_plays.items()},
        'decade':  {d: p / max_decade  for d, p in decade_plays.items()},
        'genre':   {g: p / max_genre   for g, p in genre_plays.items()},
    }

# ---------------------------------------------------------------------------
# Score a missing album
# ---------------------------------------------------------------------------

JAZZ_LIST_LABELS = {'Penguin', '1000jazz', '50jazz'}
JAZZ_KEYWORDS    = {'jazz', 'bebop', 'blues', 'soul', 'funk', 'fusion', 'swing', 'bop'}
CLASSICAL_KEYWORDS = {'classical', 'orchestral', 'opera', 'symphony', 'chamber', 'baroque'}

def infer_genres(entry_type, artist, sources):
    genres = set()
    if entry_type == 'classical':
        genres.update(CLASSICAL_KEYWORDS)
    for src in sources:
        if any(lbl in src for lbl in ('Jazz', 'Penguin')):
            genres.update(JAZZ_KEYWORDS)
    return genres

def score_entry(entry_type, artist, work, sources, profile, artist_genres):
    na = norm_artist(artist)

    # Artist score: direct match first, then token overlap
    artist_score = profile['artist'].get(na, 0.0)
    if artist_score == 0:
        for pa, ps in profile['artist'].items():
            if artist_match(na, pa):
                artist_score = max(artist_score, ps)

    # Genre score: use beets genre for known artists, else infer from list membership
    known_genres = set()
    for pa in profile['artist']:
        if artist_match(na, pa):
            known_genres |= artist_genres.get(pa, set())
    if not known_genres:
        known_genres = infer_genres(entry_type, artist, sources)
    genre_score = max((profile['genre'].get(g, 0.0) for g in known_genres), default=0.0)

    # List count bonus (normalized: 1 list = 0, 4 lists = 1)
    list_bonus = (len(sources) - 1) / 3.0

    # Combine
    score = (artist_score * 4.0) + (list_bonus * 3.0) + (genre_score * 2.0)
    return round(score, 4)

# ---------------------------------------------------------------------------
# Reuse music-gap list parsers (inline minimal versions)
# ---------------------------------------------------------------------------

def parse_simple(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            m = re.split(r'\s+[–—-]\s+', line, maxsplit=1)
            if len(m) == 2:
                entries.append(('simple', m[0].strip(), m[1].strip(), None))
    return entries

def parse_1000_recordings(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            performer = None
            m = re.search(r'\[([^\]]+)\]$', line)
            if m:
                performer = m.group(1).strip()
                line = line[:m.start()].strip()
            parts = re.split(r'\s+-\s+', line, maxsplit=1)
            if len(parts) != 2: continue
            artist, work = parts
            entries.append(('classical' if performer else 'simple',
                            artist.strip(), work.strip(), performer))
    return entries

def parse_penguin(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            line = re.sub(r'\s+x[\s\tx]*$', '', line).strip()
            m = line.split(':', 1)
            if len(m) == 2:
                rest = re.sub(r'\s*\[.*?\]', '', m[1]).strip()
                if rest:
                    entries.append(('simple', m[0].strip(), rest, None))
    return entries

def parse_jazz(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            line = re.sub(r'^\d+\.\s+', '', line)
            m = re.split(r'\s+[–—-]\s+', line, maxsplit=1)
            if len(m) == 2:
                album, artist = m
                artist = re.sub(r'\s*\(.*?\)\s*$', '', artist).strip()
                if artist and album:
                    entries.append(('simple', artist, album.strip(), None))
    return entries

# ---------------------------------------------------------------------------
# Load missing albums from gap analysis output (already written)
# ---------------------------------------------------------------------------

def load_missing_from_report():
    """Parse the deduplicated section of must-hear-missing-from-plex.md."""
    path = os.path.join(NOTES_DIR, 'must-hear-missing-from-plex.md')
    missing = []
    in_dedup = False
    with open(path) as f:
        for line in f:
            line = line.rstrip()
            if line.startswith('## All Missing'):
                in_dedup = True
                continue
            if in_dedup and line.startswith('## '):
                break
            if not in_dedup or not line.startswith('- '):
                continue
            raw = line[2:].strip()
            # Extract source labels from backtick tag: `[1001, RS500]`
            src_match = re.search(r'`\[([^\]]+)\]`', raw)
            sources = [s.strip() for s in src_match.group(1).split(',')] if src_match else []
            # Remove the source tag from display
            display = re.sub(r'\s*`\[[^\]]+\]`', '', raw).strip()
            # Detect classical: trailing [Performer]
            entry_type = 'simple'
            pm = re.search(r'\s+\[([^\]]+)\]$', display)
            if pm:
                entry_type = 'classical'
                display_clean = display[:pm.start()].strip()
            else:
                display_clean = display
            # Split artist — work
            parts = re.split(r'\s+[–—]\s+', display_clean, maxsplit=1)
            if len(parts) != 2:
                parts = re.split(r'\s+-\s+', display_clean, maxsplit=1)
            if len(parts) != 2:
                continue
            artist, work = parts[0].strip(), parts[1].strip()
            missing.append({
                'display':    display,
                'artist':     artist,
                'work':       work,
                'entry_type': entry_type,
                'sources':    sources,
            })
    return missing

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Fetching Plex play history...")
    artist_plays, decade_plays, album_plays = fetch_plex_plays()
    total_plays = sum(artist_plays.values())
    print(f"  {total_plays:,} total plays across {len(artist_plays)} artists")

    print("Loading beets genre data...")
    artist_genres = load_beets_genres()

    print("Building taste profile...")
    profile = build_profile(artist_plays, decade_plays, artist_genres)

    # Top 10 artists and genres for transparency
    top_artists = sorted(profile['artist'].items(), key=lambda x: -x[1])[:10]
    top_genres  = sorted(profile['genre'].items(),  key=lambda x: -x[1])[:8]
    top_decades = sorted(profile['decade'].items(), key=lambda x: -x[1])[:6]

    print("\nTop artists by plays:")
    for a, s in top_artists: print(f"  {s:.2f}  {a}")
    print("\nTop genres:")
    for g, s in top_genres:  print(f"  {s:.2f}  {g}")
    print("\nTop decades:")
    for d, s in top_decades: print(f"  {s:.2f}  {d}s")

    print("\nLoading missing albums...")
    missing = load_missing_from_report()
    print(f"  {len(missing)} missing albums")

    print("Scoring...")
    scored = []
    for entry in missing:
        s = score_entry(
            entry['entry_type'], entry['artist'], entry['work'],
            entry['sources'], profile, artist_genres
        )
        scored.append((s, entry))

    scored.sort(key=lambda x: -x[0])

    # Load blurb cache
    blurb_cache = {}
    blurb_path = os.path.join(NOTES_DIR, 'album-blurbs.json')
    if os.path.exists(blurb_path):
        import json
        with open(blurb_path) as f:
            blurb_cache = json.load(f)

    def get_blurb(artist, album):
        def norm(s):
            s = s.lower().strip()
            s = re.sub(r'[^\w\s]', '', s)
            return re.sub(r'\s+', ' ', s).strip()
        key = f"{norm(artist)} ||| {norm(album)}"
        entry = blurb_cache.get(key, {})
        return entry.get('blurb') if entry else None

    def shorten(src):
        src = re.sub(r'1001 Albums.*', '1001', src)
        src = re.sub(r'1000 Recordings.*', '1000rec', src)
        src = re.sub(r'Penguin.*', 'Penguin', src)
        src = re.sub(r'1000 Jazz.*', '1000jazz', src)
        src = re.sub(r'50 Greatest.*', '50jazz', src)
        src = re.sub(r'Rolling.*', 'RS500', src)
        src = re.sub(r'New Music.*', 'NewMusic', src)
        return src

    # Write output
    out_path = os.path.join(NOTES_DIR, 'must-hear-ranked-by-relevance.md')
    lines = ['# Must-Hear Albums Ranked by Personal Relevance\n']
    lines.append('*Scored on: artist familiarity (4×), multi-list citations (3×), genre affinity (2×)*\n')
    lines.append(f'*Based on {total_plays:,} Plex plays across {len(artist_plays)} artists*\n')

    lines.append('\n## Top Artists in Your Library\n')
    for a, s in top_artists:
        lines.append(f'- {a} ({s:.0%} relative plays)')
    lines.append('\n## Top Genres\n')
    for g, s in top_genres:
        lines.append(f'- {g} ({s:.0%})')

    lines.append('\n---\n')
    lines.append('## Ranked Missing Albums\n')
    for i, (s, entry) in enumerate(scored, 1):
        src_short = ', '.join(sorted(set(shorten(src) for src in entry['sources'])))
        blurb = get_blurb(entry['artist'], entry['work'])
        lines.append(f"### {i}. {entry['display']}")
        lines.append(f"*Score: {s:.2f} — Lists: {src_short}*\n")
        if blurb:
            lines.append(f"{blurb}\n")
        else:
            lines.append('')

    with open(out_path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"\nWritten to: {out_path}")

if __name__ == '__main__':
    main()
