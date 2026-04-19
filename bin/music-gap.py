#!/usr/bin/env python3
"""
Compare "must hear" album lists against music library (beets SQLite database).
Classical entries (with [Performer] notation) require performer match.
Falls back to Plex API for albums not found in beets.
"""

import re, sqlite3, os, urllib.request, xml.etree.ElementTree as ET
from collections import defaultdict

BEETS_DB    = '/tmp/beets_data.db'
NOTES_DIR   = '/Users/ken/Notes/personal'
PLEX_SERVER = 'http://192.168.1.35:32400'
PLEX_CONFIG = os.path.expanduser('~/.config/plex/config')

# Transliteration for composers stored in Cyrillic in MusicBrainz/beets
CYRILLIC_ALIASES = {
    'tchaikovsky': 'чайковский',
    'shostakovich': 'шостакович',
    'prokofiev': 'прокофьев',
    'stravinsky': 'стравинский',
    'rachmaninoff': 'рахманинов',
    'rachmaninov': 'рахманинов',
    'mussorgsky': 'мусоргский',
    'rimsky': 'римский',
    'scriabin': 'скрябин',
    'borodin': 'бородин',
    'khachaturian': 'хачатурян',
    'schnittke': 'шнитке',
    'gubaidulina': 'губайдулина',
}

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize(s):
    s = s.lower().strip()
    # Strip trailing year annotations like (1976), [1976], (2001 release date)
    s = re.sub(r'\s*[\(\[]\d{4}[^\)\]]*[\)\]]', '', s)
    # Strip leading articles
    s = re.sub(r'^(the |a |an )', '', s)
    # Remove all non-alphanumeric except spaces
    s = re.sub(r"[^\w\s]", '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def normalize_name(s):
    """Also handle 'Lastname, Firstname' inversion."""
    s = s.strip()
    # Invert only if comma is not part of a band name heuristic:
    # treat as inversion if it looks like "Word, Word" without "&" or obvious band name
    if re.match(r'^[A-Z][a-z]+,\s+[A-Z]', s) and '&' not in s and len(s.split(',')) == 2:
        parts = s.split(',', 1)
        s = parts[1].strip() + ' ' + parts[0].strip()
    return normalize(s)

def tokens(s):
    return {w for w in normalize_name(s).split() if len(w) > 2}

def composer_tokens(s):
    """Tokens for a composer name — also maps Latin spellings to Cyrillic aliases."""
    t = tokens(s)
    extra = set()
    for latin, cyrillic in CYRILLIC_ALIASES.items():
        if latin in t:
            # Add individual Cyrillic surname tokens too
            extra.update(w for w in cyrillic.split() if len(w) > 2)
    return t | extra

def long_words(nb):
    return [w for w in nb.split() if len(w) > 4]

# ---------------------------------------------------------------------------
# Load beets library into in-memory structures
# ---------------------------------------------------------------------------

def load_beets():
    db = sqlite3.connect(BEETS_DB)
    rows = db.execute(
        'SELECT albumartist, album, year FROM albums ORDER BY albumartist, album'
    ).fetchall()
    db.close()

    # Index: norm_album -> list of (albumartist, album, year, norm_artist)
    by_album   = defaultdict(list)
    by_artist  = defaultdict(list)   # norm_artist -> list of norm_album
    all_pairs  = []

    for artist, album, year in rows:
        na = normalize_name(artist)
        nb = normalize(album)
        entry = (artist, album, year, na, nb)
        all_pairs.append(entry)
        by_album[nb].append(entry)
        by_artist[na].append(nb)

    return all_pairs, by_album, by_artist

def load_plex():
    config = {}
    with open(PLEX_CONFIG) as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                config[k.strip()] = v.strip().strip('"\'')
    token   = config.get('PLEX_TOKEN', '')
    section = config.get('PLEX_SECTION_MUSIC', '1')
    url = f"{PLEX_SERVER}/library/sections/{section}/all?type=9&X-Plex-Token={token}"
    with urllib.request.urlopen(url, timeout=15) as resp:
        root = ET.fromstring(resp.read())

    plex_pairs   = []
    plex_by_album = defaultdict(list)
    for a in root.findall('Directory'):
        artist = a.get('parentTitle', '') or ''
        album  = a.get('title', '') or ''
        if not (artist and album):
            continue
        na = normalize_name(artist)
        nb = normalize(album)
        entry = (artist, album, na, nb)
        plex_pairs.append(entry)
        plex_by_album[nb].append(entry)

    return plex_pairs, plex_by_album

# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------

def artist_match(list_artist, beets_artist_norm):
    lt = tokens(list_artist)
    pt = tokens(beets_artist_norm)
    if not lt or not pt:
        return False
    overlap = lt & pt
    if not overlap:
        return False
    # Single short-token overlap is fine when the artist only has one token
    # (e.g. "ZZ Top" → only token is "top"). But block single short-token
    # overlap when both artists have multiple tokens and the shared word is a
    # common first name (e.g. "billie" shared between "Billie Holiday" and
    # "Billie Joe Armstrong + Norah Jones").
    if len(overlap) == 1:
        word = next(iter(overlap))
        if len(word) <= 5 and len(lt) > 1 and len(pt) > 1:
            return False
    return True

def album_fuzzy(nb, norm_b):
    """True if nb (list title) and norm_b (beets title) are close enough."""
    if nb == norm_b:
        return True
    if nb and nb in norm_b:   # list title is substring of beets title
        return True
    if norm_b and norm_b in nb:  # beets title is substring of list title
        return len(norm_b.split()) >= 2  # only if beets title is multi-word
    # Keyword overlap: 3+ long words all present
    lw = long_words(nb)
    if len(lw) >= 3 and all(w in norm_b for w in lw):
        return True
    # Partial key-word match for compilation/edition title variations
    # (e.g. "Complete Savoy Dial Studio Recordings" vs "Complete Savoy Dial Master Takes")
    if len(lw) >= 3 and sum(1 for w in lw if w in norm_b) >= 3:
        return True
    # "Highlights from X" / "Selections from X" satisfied by "Complete X" or full recording
    nb_stripped = re.sub(r'^(highlights? (from|of)|selections? from|sampler)\s+', '', nb).strip()
    if nb_stripped != nb and nb_stripped:
        lw2 = long_words(nb_stripped)
        if len(lw2) >= 2 and all(w in norm_b for w in lw2):
            return True
    return False

# ---------------------------------------------------------------------------
# Matching dispatch
# ---------------------------------------------------------------------------

def in_beets_simple(artist, album, all_pairs, by_album, by_artist):
    """Non-classical: match on album title + artist."""
    nb = normalize(album)
    lw = long_words(nb)
    distinctive = len(lw) >= 3

    # Fast path: look up by album title
    if nb in by_album:
        for ba, bb, yr, na, norm_b in by_album[nb]:
            if distinctive or artist_match(artist, na):
                return True

    # Slower path: iterate looking for partial/fuzzy album match
    for ba, bb, yr, na, norm_b in all_pairs:
        if not album_fuzzy(nb, norm_b):
            continue
        if distinctive or artist_match(artist, na):
            return True

    return False

def in_beets_classical(composer, work, performer, all_pairs, by_album, by_artist):
    """
    Classical: beets stores albumartist as 'Composer; Performer' or
    'Composer, Performer' — sometimes with Cyrillic composer names.
    Require: composer tokens in albumartist AND performer tokens in albumartist,
             AND album title matches work title.
    """
    comp_tok = composer_tokens(composer)   # includes Cyrillic aliases
    perf_tok  = tokens(performer) if performer else set()
    nb = normalize(work)
    # Strip edition subtitles before long-word matching
    # e.g. "Goldberg Variations (A State of Wonder: 1955 & 1981 Recordings)" → "Goldberg Variations"
    nb_core = re.sub(r'\s+\w.*$', nb, nb)   # fallback: use full
    nb_core = normalize(re.sub(r'\s*\([^)0-9][^)]*\)', '', work))  # strip non-year parentheticals
    # Also strip qualifiers that vary between editions
    nb_stripped = re.sub(r'\b(vol|volume|complete|no|op|bwv|k|book)\b.*', '', nb_core).strip()

    for ba, bb, yr, na, norm_b in all_pairs:
        a_tok = {w for w in na.split() if len(w) > 2}
        # Composer check (Latin or Cyrillic)
        if not comp_tok.intersection(a_tok):
            continue
        # Performer check (if specified)
        if perf_tok and not perf_tok.intersection(a_tok):
            continue
        # Album title / work match
        lw_core = long_words(nb_core)
        work_match = (nb_core == norm_b) or (nb_stripped and nb_stripped in norm_b)
        if not work_match and lw_core:
            work_match = all(w in norm_b for w in lw_core[:3])
        if work_match:
            return True

    return False

def in_plex(artist, work, plex_pairs, plex_by_album):
    """Plex fallback: match artist + album title. For classical, artist is the composer."""
    nb = normalize(work)
    lw = long_words(nb)
    distinctive = len(lw) >= 3

    if nb in plex_by_album:
        for pa, pb, na, norm_b in plex_by_album[nb]:
            if distinctive or artist_match(artist, na):
                return True

    for pa, pb, na, norm_b in plex_pairs:
        if not album_fuzzy(nb, norm_b):
            continue
        if distinctive or artist_match(artist, na):
            return True

    return False

def entry_in_library(entry_type, artist, work, performer,
                     all_pairs, by_album, by_artist,
                     plex_pairs, plex_by_album):
    if entry_type == 'classical':
        found = in_beets_classical(artist, work, performer, all_pairs, by_album, by_artist)
    else:
        found = in_beets_simple(artist, work, all_pairs, by_album, by_artist)
    if found:
        return True
    return in_plex(artist, work, plex_pairs, plex_by_album)

# ---------------------------------------------------------------------------
# Source file parsers  (unchanged from previous version)
# ---------------------------------------------------------------------------

def parse_1001(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = re.split(r'\s+[–—]\s+', line, maxsplit=1)
            if len(m) != 2:
                m = re.split(r'\s+-\s+', line, maxsplit=1)
            if len(m) == 2:
                entries.append(('simple', m[0].strip(), m[1].strip(), None))
    return entries

def parse_1000_recordings(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            performer = None
            m = re.search(r'\[([^\]]+)\]$', line)
            if m:
                performer = m.group(1).strip()
                line = line[:m.start()].strip()
            parts = re.split(r'\s+-\s+', line, maxsplit=1)
            if len(parts) != 2:
                continue
            artist, work = parts[0].strip(), parts[1].strip()
            if performer:
                entries.append(('classical', artist, work, performer))
            else:
                entries.append(('simple', artist, work, None))
    return entries

def parse_penguin(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'\s+x[\s\tx]*$', '', line).strip()
            m = line.split(':', 1)
            if len(m) == 2:
                artist = m[0].strip()
                rest = re.sub(r'\s*\[.*?\]', '', m[1]).strip()
                if rest:
                    entries.append(('simple', artist, rest, None))
    return entries

def parse_jazz_list(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^\d+\.\s+', '', line)
            m = re.split(r'\s+[–—-]\s+', line, maxsplit=1)
            if len(m) == 2:
                album_raw, artist_raw = m
                artist = re.sub(r'\s*\(.*?\)\s*$', '', artist_raw).strip()
                if artist and album_raw:
                    entries.append(('simple', artist, album_raw.strip(), None))
    return entries

def parse_new_music(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip().lstrip('*').strip()
            if not line or line.lower().startswith('upcoming'):
                continue
            m = re.split(r'\s+-\s+', line, maxsplit=1)
            if len(m) == 2:
                artist, album = m
                album = re.sub(r'\s*\(.*?\)\s*$', '', album).strip()
                entries.append(('simple', artist.strip(), album, None))
    return entries

def parse_rs500(path):
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            line = re.sub(r'^\d+\.\s+', '', line)
            m = re.split(r'\s+-\s+', line, maxsplit=1)
            if len(m) == 2:
                artist, album = m[0].strip(), m[1].strip()
                if artist and album:
                    entries.append(('simple', artist, album, None))
    return entries

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading beets library...")
    all_pairs, by_album, by_artist = load_beets()
    print(f"  {len(all_pairs)} albums in beets")
    print("Loading Plex library...")
    plex_pairs, plex_by_album = load_plex()
    print(f"  {len(plex_pairs)} albums in Plex\n")

    sources = [
        ('1001 Albums You Must Hear Before You Die',
         os.path.join(NOTES_DIR, '1001-albums-you-must-hear.md'),
         parse_1001),
        ('1000 Recordings to Hear Before You Die',
         os.path.join(NOTES_DIR, '1000-recordings-to-hear-before-you-die.md'),
         parse_1000_recordings),
        ('Penguin Guide Jazz Core Collection',
         os.path.join(NOTES_DIR, 'penguin-guide-jazz-core-collection.md'),
         parse_penguin),
        ('1000 Jazz Recordings',
         os.path.join(NOTES_DIR, '1000-jazz-recordings.md'),
         parse_jazz_list),
        ('50 Greatest Jazz Albums',
         os.path.join(NOTES_DIR, '50-greatest-jazz-albums.md'),
         parse_jazz_list),
        ('New Music to Find',
         os.path.join(NOTES_DIR, 'new-music-to-find.md'),
         parse_new_music),
        ('Rolling Stone 500 Greatest Albums',
         os.path.join(NOTES_DIR, 'rolling-stone-500-greatest-albums.md'),
         parse_rs500),
    ]

    report_lines = []
    report_lines.append('# Must-Hear Albums Missing from Plex\n')
    report_lines.append('Albums from curated lists not currently in the music library.')
    report_lines.append('Classical entries require matching performer, not just work title.\n')
    report_lines.append('*Source: beets database (MusicBrainz-normalized metadata)*\n')

    all_missing_by_source = []

    for title, path, parser in sources:
        entries = parser(path)
        missing = []
        found = 0
        for entry_type, artist, work, performer in entries:
            if entry_in_library(entry_type, artist, work, performer,
                                all_pairs, by_album, by_artist,
                                plex_pairs, plex_by_album):
                found += 1
            else:
                missing.append((entry_type, artist, work, performer))

        total = len(entries)
        all_missing_by_source.append(missing)
        print(f"{title}: {found}/{total} in library, {len(missing)} missing")

        report_lines.append(f'\n## {title}\n')
        report_lines.append(f'*{found} of {total} already in library — {len(missing)} missing*\n')
        for entry_type, artist, work, performer in sorted(missing, key=lambda x: normalize_name(x[1])):
            if entry_type == 'classical' and performer:
                report_lines.append(f'- {artist} — {work} [{performer}]')
            else:
                report_lines.append(f'- {artist} — {work}')
        report_lines.append('')

    # --- Deduplicated master list ---
    # Key = normalized (artist + album), stripping performer brackets
    from collections import defaultdict
    dedup = defaultdict(lambda: {'display': None, 'sources': []})
    for title, missing_list in zip([s[0] for s in sources], all_missing_by_source):
        for entry_type, artist, work, performer in missing_list:
            raw = f'{artist} — {work}'
            if entry_type == 'classical' and performer:
                raw += f' [{performer}]'
            key = normalize_name(artist) + ' ||| ' + normalize(work)
            if dedup[key]['display'] is None:
                dedup[key]['display'] = raw
            dedup[key]['sources'].append(title)

    # Short source labels
    source_labels = {
        '1001 Albums You Must Hear Before You Die': '1001',
        '1000 Recordings to Hear Before You Die': '1000rec',
        'Penguin Guide Jazz Core Collection': 'Penguin',
        '1000 Jazz Recordings': '1000jazz',
        '50 Greatest Jazz Albums': '50jazz',
        'New Music to Find': 'ToFind',
        'Rolling Stone 500 Greatest Albums': 'RS500',
    }

    dedup_sorted = sorted(dedup.values(), key=lambda x: normalize_name(x['display'].split(' — ')[0]))
    multi = [x for x in dedup_sorted if len(x['sources']) > 1]

    dedup_lines = ['\n## All Missing — Deduplicated\n']
    dedup_lines.append(f'*{len(dedup_sorted)} unique albums missing across all lists '
                       f'({len(multi)} cited by more than one list)*\n')
    for item in dedup_sorted:
        labels = ', '.join(source_labels.get(s, s) for s in item['sources'])
        dedup_lines.append(f'- {item["display"]}  `[{labels}]`')
    dedup_lines.append('')

    # Insert dedup section before the per-list sections
    insert_at = next(i for i, l in enumerate(report_lines) if l.startswith('\n## 1001'))
    report_lines[insert_at:insert_at] = dedup_lines

    out_path = os.path.join(NOTES_DIR, 'must-hear-missing-from-plex.md')
    with open(out_path, 'w') as f:
        f.write('\n'.join(report_lines) + '\n')
    print(f"\nUnique missing: {len(dedup_sorted)} ({len(multi)} cited by 2+ lists)")
    print(f"Written to: {out_path}")

if __name__ == '__main__':
    main()
