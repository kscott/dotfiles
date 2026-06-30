---
name: beets-import
description: >
  Resolve beets failed-import albums on Secondo. Scans /mnt/data/downloads/music/ for
  .beets-failed markers, presents each failure with its reason, and walks through resolution
  (MB near-match, Discogs-only, or tag-based import). Use whenever an album failed to import
  automatically and needs manual intervention.
  Trigger on: "beets failed", "failed import", "resolve album", "beets-failed", "fix import".
---

# Beets Failed-Import Resolution

## Step 1 — Scan for failures

SSH to Secondo and list all failed albums:

```bash
ssh secondo.home "find /mnt/data/downloads/music -name '.beets-failed' | sort | while read f; do echo \"=== \$(dirname \$f | xargs basename) ===\"; cat \"\$f\"; echo; done"
```

Present each album with its folder name and failure reason. Let Ken pick which to resolve.

---

## Container path mapping

| Host | Container |
|---|---|
| `/mnt/data/downloads/music/<folder>/` | `/downloads/music/<folder>` |

Always use `-u abc` with `docker exec` — root is squashed to nobody on NFS.

---

## Case 1 — MB candidate below threshold

The `.beets-failed` marker contains MB candidates with confidence percentages.

Query MB to resolve the release UUID:
```bash
curl -s "https://musicbrainz.org/ws/2/release?query=artist:<artist>+release:<album>&fmt=json&limit=5" \
  -H "User-Agent: beets-homelab/1.0 (ken@optikos.net)"
```

Import with the UUID — `--search-id` presents `Apply/More/Skip/...` (not a numbered list), so pipe `A`:
```bash
echo 'A' | ssh secondo.home "docker exec -i -u abc beets beet import --copy --noincremental --search-id <uuid> '/downloads/music/<folder>'"
```

---

## Case 2 — Not in MusicBrainz, but on Discogs

Discogs token: `~/Notes/homelab/home-infrastructure.md` API tokens table.

```bash
curl -s "https://api.discogs.com/database/search?artist=<artist>&release_title=<album>&type=release&per_page=5&token=<discogs_token>" \
  -H "User-Agent: beets-homelab/1.0 (ken@optikos.net)"
```

Prefer FLAC/File release over CD/Vinyl when both exist. Import with the Discogs release ID:
```bash
printf 'I\n<discogs_id>\nA\n' | ssh secondo.home "docker exec -i -u abc beets beet import --copy --noincremental '/downloads/music/<folder>'"
```

---

## Case 3 — Not in MB or Discogs

AcoustID (chroma plugin) already ran during the original attempt — it maps to MB recording IDs only and can't help if the release isn't in MB.

Inspect embedded tags on every track:
```bash
ssh secondo.home "for f in /mnt/data/downloads/music/<folder>/*.flac; do echo \"--- \$(basename \$f) ---\"; metaflac --export-tags-to=- \"\$f\"; done"
```

Present the tags clearly, then ask Ken for direction:
- **Tags look good** → import with `-A` (uses embedded tags as-is)
- **Tags wrong but fixable** → fix with `metaflac --set-tag KEY=value` or `metaflac --remove-tag KEY`, then `-A`
- **Tags empty or garbage** → no automated path; source correct metadata first

Import with existing tags:
```bash
ssh secondo.home "docker exec -u abc beets beet import --copy --noincremental -A '/downloads/music/<folder>'"
```

---

## After any successful import

Run art fetch/embed, trigger Plex rescan, swap the marker:

```bash
ssh secondo.home "docker exec -u abc beets beet fetchart -y album:'<album>' albumartist:'<artist>'"
ssh secondo.home "docker exec -u abc beets beet embedart -y album:'<album>' albumartist:'<artist>'"
curl -s "http://secondo.home:32400/library/sections/6/refresh?X-Plex-Token=shmYDQ52FuRArqZxXxJB"
ssh secondo.home "rm '/mnt/data/downloads/music/<folder>/.beets-failed'"
ssh secondo.home "printf 'Imported: %s\nTracks: <n>\n' \"\$(date '+%Y-%m-%d %H:%M')\" > '/mnt/data/downloads/music/<folder>/.beets-imported'"
```
