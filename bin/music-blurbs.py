#!/usr/bin/env python3
"""
Fetch and cache one-sentence blurbs for must-hear missing albums.
Sources: Wikipedia (primary), Discogs (fallback).
Cache: ~/Notes/personal/album-blurbs.json
"""

import json, os, re, time, urllib.request, urllib.parse

NOTES_DIR  = '/Users/ken/Notes/personal'
CACHE_FILE = os.path.join(NOTES_DIR, 'album-blurbs.json')
PLEX_CONFIG = os.path.expanduser('~/.config/plex/config')

DISCOGS_TOKEN = 'gHlISYPPDanSrIxavZIBwQfFdrVZyDuBYYSAZXVd'
UA = 'MusicBlurbFetcher/1.0 (ken@optikos.net)'

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def cache_key(artist, album):
    def norm(s):
        s = s.lower().strip()
        s = re.sub(r'[^\w\s]', '', s)
        return re.sub(r'\s+', ' ', s).strip()
    return f"{norm(artist)} ||| {norm(album)}"

# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

def wiki_fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return None

def first_sentence(text):
    if not text:
        return None
    # Cut at first sentence boundary
    m = re.match(r'([^.!?]*(?:[.!?](?!\s*[a-z])[^.!?]*){0,1}[.!?])', text)
    if m:
        s = m.group(1).strip()
        if len(s) > 30:
            return s
    # Fallback: first 200 chars
    return text[:200].rsplit(' ', 1)[0] + '…' if len(text) > 200 else text

def fetch_wikipedia(artist, album):
    # Search Wikipedia
    query = urllib.parse.quote(f"{artist} {album} album")
    search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&srlimit=3"
    data = wiki_fetch(search_url)
    if not data:
        return None
    results = data.get('query', {}).get('search', [])
    for result in results:
        title = result.get('title', '')
        # Must look like an album article
        snippet = result.get('snippet', '').lower()
        if not any(w in snippet for w in ('album', 'recording', 'record', 'jazz', 'studio')):
            continue
        # Fetch summary
        safe_title = urllib.parse.quote(title.replace(' ', '_'))
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
        summary = wiki_fetch(summary_url)
        if not summary:
            continue
        extract = summary.get('extract', '')
        # Sanity check: artist or album name should appear
        if artist.split()[0].lower() not in extract.lower() and album.split()[0].lower() not in extract.lower():
            continue
        blurb = first_sentence(extract)
        if blurb:
            return blurb
    return None

# ---------------------------------------------------------------------------
# Discogs
# ---------------------------------------------------------------------------

def fetch_discogs(artist, album):
    query = urllib.parse.quote(f"{artist} {album}")
    url = f"https://api.discogs.com/database/search?q={query}&type=release&per_page=3"
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Authorization': f'Discogs token={DISCOGS_TOKEN}'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    results = data.get('results', [])
    for result in results:
        notes = result.get('notes') or result.get('community', {}).get('have')
        # Get the release details for notes
        rid = result.get('id')
        if not rid:
            continue
        detail_url = f"https://api.discogs.com/releases/{rid}"
        req2 = urllib.request.Request(detail_url, headers={
            'User-Agent': UA,
            'Authorization': f'Discogs token={DISCOGS_TOKEN}'
        })
        try:
            with urllib.request.urlopen(req2, timeout=10) as r2:
                detail = json.loads(r2.read())
        except Exception:
            continue
        notes = detail.get('notes', '').strip()
        if notes and len(notes) > 30:
            return first_sentence(notes)
        time.sleep(0.5)
    return None

# ---------------------------------------------------------------------------
# Load missing albums from ranked report
# ---------------------------------------------------------------------------

def load_missing():
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
            raw = re.sub(r'\s*`\[[^\]]+\]`', '', raw).strip()
            raw = re.sub(r'\s+\[[^\]]+\]$', '', raw).strip()
            parts = re.split(r'\s+[–—]\s+', raw, maxsplit=1)
            if len(parts) != 2:
                parts = re.split(r'\s+-\s+', raw, maxsplit=1)
            if len(parts) == 2:
                missing.append((parts[0].strip(), parts[1].strip()))
    return missing

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch album blurbs')
    parser.add_argument('--limit', type=int, default=0, help='Only fetch N new blurbs (0=all)')
    parser.add_argument('--delay', type=float, default=1.0, help='Seconds between requests')
    args = parser.parse_args()

    cache = load_cache()
    missing = load_missing()

    need = [(a, al) for a, al in missing if cache_key(a, al) not in cache]
    print(f"Total missing: {len(missing)} | Already cached: {len(cache)} | Need fetching: {len(need)}")

    if args.limit:
        need = need[:args.limit]
        print(f"Fetching up to {args.limit} blurbs this run")

    fetched = skipped = 0
    for i, (artist, album) in enumerate(need, 1):
        key = cache_key(artist, album)
        print(f"  [{i}/{len(need)}] {artist} — {album}", end=' ', flush=True)

        blurb = fetch_wikipedia(artist, album)
        source = 'wikipedia'
        if not blurb:
            time.sleep(args.delay)
            blurb = fetch_discogs(artist, album)
            source = 'discogs'

        if blurb:
            cache[key] = {'blurb': blurb, 'source': source}
            print(f'✓ {source}')
            fetched += 1
        else:
            cache[key] = {'blurb': None, 'source': None}
            print('–')
            skipped += 1

        save_cache(cache)
        time.sleep(args.delay)

    print(f"\nDone. Fetched: {fetched} | Not found: {skipped} | Cache total: {len(cache)}")

if __name__ == '__main__':
    main()
