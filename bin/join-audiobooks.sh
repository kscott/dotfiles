#!/opt/homebrew/bin/bash
# join-audiobooks.sh — Convert multi-file audiobook folders to single M4B
#
# Finds book folders under ARCHIVE, concatenates all audio files into a single
# M4B with AAC audio, chapter markers at track boundaries, embedded cover art
# (via iTunes Search API), and full metadata — all in one pass.
#
# Structure handled:
#   Author/Book/*.mp3          — flat folder
#   Author/Book/CD1/*.mp3      — CD/Disc subdirectories
#   Author/Book/*.disc/        — .disc folder naming

ARCHIVE="/Volumes/Attic/Audiobooks/Archive"
LOG="/tmp/audiobook-join.log"
ERRORS=0
SUCCESS=0
SKIPPED=0

log()  { local msg="$(date '+%H:%M:%S') $1"; echo "$msg" | tee -a "$LOG"; }
logq() { echo "$(date '+%H:%M:%S') $1" >> "$LOG"; }

# ── Helpers ───────────────────────────────────────────────────────────────────

is_cd_dir() {
    basename "$1" | grep -qiE "^(cd|disc|disk)\s*[0-9]|\.disc$"
}

get_audio_files() {
    local dir="$1"
    local has_cd=false

    while IFS= read -r -d '' subdir; do
        if is_cd_dir "$subdir"; then
            has_cd=true
            break
        fi
    done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)

    if $has_cd; then
        while IFS= read -r -d '' cd_dir; do
            if is_cd_dir "$cd_dir"; then
                find "$cd_dir" -maxdepth 1 -type f \
                    \( -name "*.mp3" -o -name "*.mp4" -o -name "*.m4a" \) | sort
            fi
        done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null | sort -z)
    else
        find "$dir" -maxdepth 1 -type f \
            \( -name "*.mp3" -o -name "*.mp4" -o -name "*.m4a" \) | sort
    fi
}

# Search iTunes for audiobook metadata. Outputs: art_url, year, genre (one per line).
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

# Build an FFMETADATA chapter file from a list of audio files.
# Each file becomes one chapter; titles derived from filenames by stripping
# the common prefix shared across all tracks.
build_chapter_metadata() {
    local filelist="$1"
    local title="$2"
    local author="$3"
    local genre="$4"
    local year="$5"
    local outfile="$6"

    python3 - "$filelist" "$title" "$author" "$genre" "$year" "$outfile" <<'PYEOF'
import sys, os, subprocess, re

filelist_path, title, author, genre, year, outfile = sys.argv[1:]

with open(filelist_path) as f:
    files = [line.rstrip('\n') for line in f if line.strip()]

if not files:
    sys.exit(1)

basenames = [os.path.splitext(os.path.basename(p))[0] for p in files]

prefix = basenames[0]
for name in basenames[1:]:
    while not name.startswith(prefix):
        prefix = prefix[:-1]
        if not prefix:
            break
prefix = re.sub(r'[\s\-_\.]+$', '', prefix)

def clean_title(basename, idx):
    t = basename
    if prefix:
        t = t[len(prefix):]
    t = re.sub(r'^[\s\-_\.]+', '', t).strip()
    if re.fullmatch(r'\d+', t):
        t = f'Chapter {int(t)}'
    return t or f'Chapter {idx}'

def escape_ffmeta(s):
    return (s.replace('\\', '\\\\')
             .replace('=',  '\\=')
             .replace(';',  '\\;')
             .replace('#',  '\\#')
             .replace('\n', '\\\n'))

def get_duration_ms(path):
    r = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
         '-of', 'default=nw=1:nk=1', path],
        capture_output=True, text=True
    )
    try:
        return int(float(r.stdout.strip()) * 1000)
    except Exception:
        return 0

lines = [';FFMETADATA1',
         f'title={escape_ffmeta(title)}',
         f'artist={escape_ffmeta(author)}',
         f'album_artist={escape_ffmeta(author)}',
         f'album={escape_ffmeta(title)}',
         f'genre={escape_ffmeta(genre or "Audiobook")}']
if year:
    lines.append(f'date={escape_ffmeta(year)}')
lines.append('')

pos_ms = 0
for i, (path, basename) in enumerate(zip(files, basenames), 1):
    dur_ms = get_duration_ms(path)
    if dur_ms <= 0:
        continue
    end_ms = pos_ms + dur_ms
    chapter_title = clean_title(basename, i)
    lines += ['[CHAPTER]',
              'TIMEBASE=1/1000',
              f'START={pos_ms}',
              f'END={end_ms}',
              f'title={escape_ffmeta(chapter_title)}',
              '']
    pos_ms = end_ms

with open(outfile, 'w') as f:
    f.write('\n'.join(lines))
PYEOF
}

# ── Main ──────────────────────────────────────────────────────────────────────

log "=== Audiobook join started ==="
log "Archive: $ARCHIVE"

declare -A book_dirs

while IFS= read -r d; do
    if [[ "$(dirname "$d")" == "$ARCHIVE" ]]; then
        continue
    fi
    if ! is_cd_dir "$d"; then
        book_dirs["$d"]=1
    fi
done < <(
    find "$ARCHIVE" -type f \( -name "*.mp3" -o -name "*.mp4" -o -name "*.m4a" \) \
        | sed 's|/[^/]*$||' | sort -u
)

while IFS= read -r -d '' d; do
    if is_cd_dir "$d"; then
        local_count=$(find "$d" -maxdepth 1 -type f \
            \( -name "*.mp3" -o -name "*.mp4" -o -name "*.m4a" \) | wc -l)
        if [[ $local_count -gt 0 ]]; then
            parent=$(dirname "$d")
            book_dirs["$parent"]=1
            unset "book_dirs[$d]"
        fi
    fi
done < <(find "$ARCHIVE" -type d -print0)

log "Found ${#book_dirs[@]} book directories to process"

while IFS= read -r book_dir; do
    book_name=$(basename "$book_dir")
    author_dir=$(dirname "$book_dir")
    author_name=$(basename "$author_dir")
    output="$author_dir/${book_name}.m4b"

    if [[ -f "$output" ]]; then
        log "SKIP (exists): $book_name"
        (( SKIPPED++ )) || true
        continue
    fi

    filelist=$(mktemp)
    get_audio_files "$book_dir" > "$filelist"

    count=$(wc -l < "$filelist" | tr -d ' ')

    if [[ "$count" -eq 0 ]]; then
        log "SKIP (no audio): $book_name"
        (( SKIPPED++ )) || true
        rm "$filelist"
        continue
    fi

    log "JOINING ($count files): $book_name"

    itunes_meta=$(fetch_itunes_meta "$book_name" "$author_name")
    art_url=$(echo "$itunes_meta"      | sed -n '1p')
    release_year=$(echo "$itunes_meta" | sed -n '2p')
    genre=$(echo "$itunes_meta"        | sed -n '3p')

    coverfile=$(mktemp /tmp/cover-XXXXXX)
    got_cover=false
    fetch_cover "$art_url" "$coverfile" && got_cover=true

    metafile=$(mktemp /tmp/meta-XXXXXX)
    if ! build_chapter_metadata "$filelist" "$book_name" "$author_name" \
            "${genre:-Audiobook}" "$release_year" "$metafile"; then
        log "  WARN: chapter build failed — encoding without chapters"
        printf ';FFMETADATA1\ntitle=%s\nartist=%s\nalbum_artist=%s\nalbum=%s\ngenre=%s\n' \
            "$book_name" "$author_name" "$author_name" "$book_name" \
            "${genre:-Audiobook}" > "$metafile"
        [[ -n "$release_year" ]] && echo "date=$release_year" >> "$metafile"
    fi

    concatfile=$(mktemp)
    while IFS= read -r f; do
        printf "file '%s'\n" "${f//\'/\'\\\'\'}" >> "$concatfile"
    done < "$filelist"
    rm "$filelist"

    if $got_cover; then
        ffmpeg -y -f concat -safe 0 -i "$concatfile" \
            -i "$metafile" \
            -i "$coverfile" \
            -map 0:a -map 2 \
            -map_metadata 1 \
            -c:a aac -b:a 64k \
            -c:v mjpeg \
            -disposition:v attached_pic \
            -metadata:s:v title="Album cover" \
            -metadata:s:v comment="Cover (front)" \
            "$output" >> "$LOG" 2>&1
    else
        ffmpeg -y -f concat -safe 0 -i "$concatfile" \
            -i "$metafile" \
            -map 0:a \
            -map_metadata 1 \
            -c:a aac -b:a 64k \
            "$output" >> "$LOG" 2>&1
    fi
    ffmpeg_status=$?
    rm -f "$concatfile" "$metafile" "$coverfile"


    if [[ $ffmpeg_status -ne 0 ]]; then
        log "FAILED: $book_name (exit $ffmpeg_status)"
        (( ERRORS++ )) || true
        rm -f "$output"
        continue
    fi

    log "SUCCESS: $book_name ($($got_cover && echo "cover embedded" || echo "no cover found"))"
    (( SUCCESS++ )) || true
    rm -rf "$book_dir"
    logq "  DELETED source: $book_dir"

done < <(printf '%s\n' "${!book_dirs[@]}" | sort)

log "=== Done: $SUCCESS joined, $SKIPPED skipped, $ERRORS failed ==="

# ── Pass 2: flatten — move all M4Bs up to Author/ level ──────────────────────

log "=== Flatten pass ==="
FLATTENED=0

while IFS= read -r m4b; do
    local rel="${m4b#"$ARCHIVE/"}"
    local depth
    depth=$(echo "$rel" | tr '/' '\n' | wc -l | tr -d ' ')
    [[ "$depth" -le 2 ]] && continue   # already at Author/Book.m4b

    local author_dir book_name target
    author_dir="$ARCHIVE/$(echo "$rel" | cut -d/ -f1)"
    book_name=$(basename "$m4b")
    target="$author_dir/$book_name"

    [[ "$m4b" == "$target" ]] && continue

    if [[ -f "$target" ]]; then
        logq "FLATTEN SKIP (conflict): $book_name"
        continue
    fi

    mv "$m4b" "$target"
    logq "FLATTEN: $book_name → $(basename "$author_dir")/"
    (( FLATTENED++ )) || true

    # Remove now-empty parent folders (but not the author dir itself)
    local parent
    parent=$(dirname "$m4b")
    while [[ "$parent" != "$author_dir" && "$parent" != "$ARCHIVE" ]]; do
        find "$parent" -name ".DS_Store" -delete 2>/dev/null
        rmdir "$parent" 2>/dev/null || break
        parent=$(dirname "$parent")
    done

done < <(find "$ARCHIVE" -name "*.m4b" -type f | sort)

log "=== Flatten done: $FLATTENED files moved ==="
