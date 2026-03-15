#!/bin/bash
# sort-downloads.sh — Route completed downloads to the right inbox
# Usage: sort-downloads.sh <path>
#   Called by Transmission when a torrent completes (Preferences → Transfers → Management).
#
# If the Plex machine IP changes (e.g. after a reboot):
#   1. Find new IP on Plex machine: ipconfig getifaddr en0
#   2. Update ~/.ssh/config — change HostName under "Host plex"
#   3. Clear the old host key: ssh-keygen -R <old-ip>
#   4. Reconnect: ssh -o StrictHostKeyChecking=accept-new plex 'echo ok'
#   (Long-term fix: assign a static IP to the Plex machine in your router's DHCP settings)

CALIBREDB="/Applications/calibre.app/Contents/MacOS/calibredb"
VIDEO_INBOX="/Volumes/Media/Inbox"
MUSIC_INBOX="/Volumes/Music/Inbox"
LOG="$HOME/Library/Logs/sort-downloads.log"

# ── Logging ────────────────────────────────────────────────────────────────────

# Trim log entries older than 30 days (truncate in place to preserve tail -f)
if [[ -f "$LOG" ]]; then
    cutoff=$(date -v-30d '+%Y-%m-%d')
    trimmed=$(awk -v cutoff="$cutoff" '
        /^\[/ { if (substr($0,2,10) >= cutoff) print; next }
        { print }
    ' "$LOG")
    printf '%s\n' "$trimmed" > "$LOG"
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# ── Mount check ────────────────────────────────────────────────────────────────

check_mount() {
    local vol="$1"
    if ! mount | grep -q "on $vol "; then
        log "ERROR: $vol is not mounted — skipping"
        return 1
    fi
}

# ── Type detection ─────────────────────────────────────────────────────────────
# Returns: ebook | music | video | unknown

detect_type() {
    local path="$1"

    if find "$path" -type f \( -iname "*.epub" -o -iname "*.mobi" -o -iname "*.azw3" \) | grep -q .; then
        echo "ebook"; return
    fi

    if find "$path" -type f -iname "*.flac" | grep -q .; then
        echo "music"; return
    fi

    if find "$path" -type f \( -iname "*.mkv" -o -iname "*.avi" -o -iname "*.mp4" \
                              -o -iname "*.tar" -o -iname "*.tar.gz" -o -iname "*.tgz" \) | grep -q .; then
        echo "video"; return
    fi

    echo "unknown"
}

# ── Handlers ───────────────────────────────────────────────────────────────────

handle_ebook() {
    local path="$1"
    log "Ebook: $(basename "$path")"
    find "$path" -type f \( -iname "*.epub" -o -iname "*.mobi" -o -iname "*.azw3" \) | while read -r f; do
        log "  Adding to Calibre: $(basename "$f")"
        "$CALIBREDB" add "$f" 2>&1 | while read -r line; do log "    $line"; done
    done
}

handle_music() {
    local path="$1"
    check_mount "/Volumes/Music" || return 1

    # cue+FLAC: split before copying
    if find "$path" -type f -iname "*.cue" | grep -q .; then
        log "Music (cue+FLAC): $(basename "$path") — splitting tracks"
        find "$path" -type f -iname "*.cue" | while read -r cue; do
            dir="$(dirname "$cue")"
            flac="$(find "$dir" -maxdepth 1 -iname "*.flac" | head -1)"
            if [[ -n "$flac" ]]; then
                dest="$MUSIC_INBOX/$(basename "$dir")"
                mkdir -p "$dest"
                shnsplit -f "$cue" -o flac -d "$dest" "$flac" 2>&1 | while read -r line; do log "    $line"; done
                cuetag.sh "$cue" "$dest"/*.flac 2>&1 | while read -r line; do log "    $line"; done
                log "  Split to: $dest"
            else
                log "  WARNING: .cue found but no .flac in $(dirname "$cue")"
            fi
        done
    else
        log "Music: $(basename "$path") → $MUSIC_INBOX"
        cp -r "$path" "$MUSIC_INBOX/" && log "  Copied"
    fi

    log "Triggering beet import on plex"
    ssh plex 'PATH=/usr/local/bin:$PATH /usr/local/bin/beet import -q -I /Volumes/Music/Inbox' >> "$LOG" 2>&1
}

handle_video() {
    local path="$1"
    check_mount "/Volumes/Media" || return 1

    # Extract tar archives to a temp dir, then copy contents
    if find "$path" -type f \( -iname "*.tar" -o -iname "*.tar.gz" -o -iname "*.tgz" \) | grep -q .; then
        log "Video (tar archive): $(basename "$path") — extracting"
        tmpdir="$(mktemp -d)"
        find "$path" -type f \( -iname "*.tar" -o -iname "*.tar.gz" -o -iname "*.tgz" \) | while read -r archive; do
            log "  Extracting: $(basename "$archive")"
            tar -xf "$archive" -C "$tmpdir"
        done
        dest="$VIDEO_INBOX/$(basename "$path")"
        cp -r "$tmpdir" "$dest" && log "  Extracted to: $dest"
        rm -rf "$tmpdir"
    else
        log "Video: $(basename "$path") → $VIDEO_INBOX"
        cp -r "$path" "$VIDEO_INBOX/" && log "  Copied"
    fi

    log "Triggering sorttv on plex"
    ssh plex 'cd ~ && /usr/local/bin/perl bin/sorttv/sorttv.pl' >> "$LOG" 2>&1
}

# ── Main ───────────────────────────────────────────────────────────────────────

# Transmission passes path via environment variables; fall back to $1 for manual use
if [[ -n "$TR_TORRENT_DIR" && -n "$TR_TORRENT_NAME" ]]; then
    TARGET="$TR_TORRENT_DIR/$TR_TORRENT_NAME"
else
    TARGET="$1"
fi

if [[ -z "$TARGET" ]]; then
    echo "Usage: sort-downloads.sh <path>"
    exit 1
fi

if [[ ! -e "$TARGET" ]]; then
    log "ERROR: path does not exist: $TARGET"
    exit 1
fi

log "━━━━ Processing: $(basename "$TARGET")"
TYPE="$(detect_type "$TARGET")"
log "Detected type: $TYPE"

case "$TYPE" in
    ebook) handle_ebook "$TARGET" ;;
    music) handle_music "$TARGET" ;;
    video) handle_video "$TARGET" ;;
    *)     log "Unknown type — skipping: $(basename "$TARGET")" ;;
esac

log "Done: $(basename "$TARGET")"
