#!/opt/homebrew/bin/bash
# fix-audiobook-meta.sh — Backfill metadata and cover art on existing M4B files
#
# Iterates all M4Bs under ARCHIVE. Skips files that already have genre, year,
# and cover art. For the rest: searches iTunes, downloads cover, re-muxes with
# updated tags (audio stream is copied, not re-encoded).
#
# Run once to clean up legacy files. After that, join-audiobooks.sh handles
# everything in a single pass at conversion time.

ARCHIVE="/Volumes/Attic/Audiobooks/Archive"
LOG="/tmp/audiobook-meta-fix.log"
SUCCESS=0
SKIPPED=0
ERRORS=0

log()  { local msg="$(date '+%H:%M:%S') $1"; echo "$msg" | tee -a "$LOG"; }
logq() { echo "$(date '+%H:%M:%S') $1" >> "$LOG"; }

fetch_itunes_meta() {
    local title="$1"
    local author="$2"

    local query
    query=$(python3 -c "
import urllib.parse, sys
print(urllib.parse.quote(sys.argv[1] + ' ' + sys.argv[2]))
" "$title" "$author" 2>/dev/null)
    [[ -z "$query" ]] && return 1

    local url="https://itunes.apple.com/search?term=${query}&media=audiobook&entity=audiobook&limit=5"
    local json
    json=$(curl -s --max-time 10 "$url" 2>/dev/null)
    [[ -z "$json" ]] && return 1

    python3 -c "
import sys, json
data = json.load(sys.stdin)
results = data.get('results', [])
if not results:
    sys.exit(1)
r = results[0]
art = r.get('artworkUrl100', '').replace('100x100bb', '600x600bb')
year = r.get('releaseDate', '')[:4]
genre = r.get('primaryGenreName', '')
print(art)
print(year)
print(genre)
" <<< "$json" 2>/dev/null
}

fetch_cover() {
    local art_url="$1"
    local outfile="$2"
    [[ -z "$art_url" ]] && return 1
    curl -s --max-time 15 "$art_url" -o "$outfile" 2>/dev/null
    [[ -f "$outfile" && -s "$outfile" ]] && return 0 || return 1
}

fix_m4b() {
    local m4b="$1"
    local book_name
    book_name=$(basename "${m4b%.m4b}")
    local author_name
    author_name=$(basename "$(dirname "$m4b")")

    local existing_genre existing_year has_cover
    existing_genre=$(ffprobe -v quiet -show_entries format_tags=genre \
        -of default=nw=1:nk=1 "$m4b" 2>/dev/null)
    existing_year=$(ffprobe -v quiet -show_entries format_tags=date \
        -of default=nw=1:nk=1 "$m4b" 2>/dev/null)
    has_cover=$(ffprobe -v quiet -show_entries stream=codec_type \
        -of default=nw=1:nk=1 "$m4b" 2>/dev/null | grep -c "^video" || true)

    if [[ -n "$existing_genre" && -n "$existing_year" && "$has_cover" -gt 0 ]]; then
        logq "SKIP (complete): $book_name"
        (( SKIPPED++ )) || true
        return 0
    fi

    log "FIX: $book_name"

    local itunes_meta art_url release_year genre
    itunes_meta=$(fetch_itunes_meta "$book_name" "$author_name")
    art_url=$(echo "$itunes_meta"      | sed -n '1p')
    release_year=$(echo "$itunes_meta" | sed -n '2p')
    genre=$(echo "$itunes_meta"        | sed -n '3p')

    [[ -z "$genre" ]]        && genre="${existing_genre:-Audiobook}"
    [[ -z "$release_year" ]] && release_year="$existing_year"

    local tmp="${m4b%.m4b}-meta-tmp.m4b"
    local coverfile
    coverfile=$(mktemp /tmp/cover-XXXXXX)
    local got_cover=false
    [[ "$has_cover" -eq 0 ]] && fetch_cover "$art_url" "$coverfile" && got_cover=true

    local date_flag=()
    [[ -n "$release_year" ]] && date_flag=(-metadata "date=$release_year")

    local ffmpeg_status
    if $got_cover; then
        ffmpeg -y -i "$m4b" -i "$coverfile" \
            -map 0:a -map 1 \
            -c:a copy -c:v mjpeg \
            -disposition:v attached_pic \
            -metadata:s:v title="Album cover" \
            -metadata:s:v comment="Cover (front)" \
            -metadata title="$book_name" \
            -metadata artist="$author_name" \
            -metadata album_artist="$author_name" \
            -metadata album="$book_name" \
            -metadata genre="$genre" \
            "${date_flag[@]}" \
            "$tmp" >> "$LOG" 2>&1
    else
        ffmpeg -y -i "$m4b" \
            -map 0:a -c:a copy \
            -metadata title="$book_name" \
            -metadata artist="$author_name" \
            -metadata album_artist="$author_name" \
            -metadata album="$book_name" \
            -metadata genre="$genre" \
            "${date_flag[@]}" \
            "$tmp" >> "$LOG" 2>&1
    fi
    ffmpeg_status=$?
    rm -f "$coverfile"

    if [[ $ffmpeg_status -eq 0 && -s "$tmp" ]]; then
        mv "$tmp" "$m4b"
        log "  updated: $book_name"
        (( SUCCESS++ )) || true
    else
        rm -f "$tmp"
        log "  FAILED: $book_name"
        (( ERRORS++ )) || true
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

log "=== Metadata fix started ==="
log "Archive: $ARCHIVE"

while IFS= read -r m4b; do
    if [[ "$(dirname "$m4b")" == "$ARCHIVE" ]]; then
        continue
    fi
    fix_m4b "$m4b"
done < <(find "$ARCHIVE" -name "*.m4b" -type f | sort)

log "=== Done: $SUCCESS updated, $SKIPPED skipped, $ERRORS failed ==="
