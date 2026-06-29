---
name: homelab
description: >
  Full context for Ken's homelab: network, home automation, Home Assistant, Apple Home, and all
  open punch-list items. Use whenever the topic is OPNsense config, home network, Home Assistant,
  Apple Home automations, Zigbee/Matter/Thread devices, NAS, Plex, or any infrastructure work.
  Trigger on: "homelab", "home assistant", "HA", "Apple Home", "OPNsense", "network", "ceiling light",
  "smart home", "Orbi", "NAS", "Protectli", "Acropolis", "Agora", "Quarto", "vault".
---

# Homelab — Operating Guide

Read these three files at the start of every homelab session — don't derive config from memory:

```
~/Notes/homelab/home-infrastructure.md   — architecture, devices, credentials, documented fixes
~/Notes/homelab/homelab-punch-list.md    — open tasks
~/Notes/homelab/ha-entities.md           — all HA entity IDs (check here before looking up in HA)
```

---

## Architecture principles

**Apple Home is the primary UI.** HA handles what Apple Home can't:
- ZHA devices (Aqara T1M ceiling light via ZBT-2)
- Scroll wheel controls (Bilresa)
- Future: garage door (blaQ), cameras (Frigate)

HA exposes devices back to Apple Home via **HomeKit Bridge**.

**Network:** OPNsense (Protectli V1410) → 2.5GbE switch → Acropolis (AP mode, trusted WiFi 192.168.1.x) + Agora (router mode, IoT 192.168.3.x). All trusted devices on same subnet — mDNS works natively.

**HAOS:** KVM VM on Quarto (iMac 2012), 192.168.1.30. Web UI: `http://homeassistant.home:8123`

---

## Key devices and IPs

| Device | IP | Notes |
|---|---|---|
| OPNsense (Protectli) | 192.168.1.1 | root / opnsense |
| NAS (vault) | 192.168.1.2 | Unraid; root / kds007 |
| Primo (Home Mac) | 192.168.1.10 | Daily driver |
| HAOS | 192.168.1.30 | Home Assistant OS on Quarto |
| Acropolis (WiFi 7 AP) | 192.168.1.195 | admin / qavqos-cevke9-hogvuN; use IP directly |
| Agora (IoT WiFi) | orbilogin.com | admin / WXMW9cwxZkcHgijX |

Full device/IP table and credentials in `home-infrastructure.md`.

---

## Common operations

### HA entity IDs
Always check `ha-entities.md` first. Never guess entity IDs — they're non-obvious and the doc has the gotchas too (Samsung TV source list, HomeKit Bridge stripping transitions, etc.).

### HomeKit Bridge — exposing new entities
New entity types (scripts, scenes) are NOT auto-exposed. Add the domain:
**Settings → Devices & Services → HomeKit Bridge → Configure → Domains to include**
Then reload the integration.

### Developer Tools
Hidden by default. Enable: **Profile → Advanced Mode**
Direct URL: `http://homeassistant.home:8123/developer-tools/state`

### OPNsense paths that differ from docs
OPNsense 25.7 UI may differ from training data. Search current docs before guiding. Key paths:
- DHCP static leases: **Services → Dnsmasq DNS & DHCP → Hosts**
- DNS host overrides: **Services → Unbound DNS → Host Overrides**
- Firewall rules: **Firewall → Rules → [interface]**
- Static routes: **System → Routes**

### HA Scripts (Settings → Automations & Scenes → Scripts)
Not Settings → Scripts directly — it's under Automations & Scenes.

---

## Beets failed-import resolution

Albums land in `/mnt/data/downloads/music/<folder>/.beets-failed` when beets can't auto-match.
The marker contains the full candidate list with confidence percentages.

**Case 1 — MB candidate present but below threshold (e.g. 74.3%)**

Query MB API to get the UUID:
```bash
curl -s "https://musicbrainz.org/ws/2/release?query=artist:<artist>+release:<album>&fmt=json" \
  -H "User-Agent: beets-homelab/1.0 (ken@optikos.net)"
```
Then import with the UUID — `--search-id` shows `Apply/More/Skip/...` prompt, not a numbered list:
```bash
echo 'A' | docker exec -i -u abc beets beet import --copy --noincremental --search-id <uuid> '<container_path>'
```

**Case 2 — Not in MusicBrainz, but on Discogs**


Query Discogs (token in home-infrastructure.md API table):
```bash
curl -s "https://api.discogs.com/database/search?artist=<artist>&release_title=<album>&type=release&per_page=5" \
  -H "User-Agent: beets-homelab/1.0 (ken@optikos.net)"
```
Prefer FLAC/File release over CD/Vinyl when both exist. Then import with the Discogs ID:
```bash
printf 'I\n<discogs_id>\nA\n' | docker exec -i -u abc beets beet import --copy --noincremental '<container_path>'
```

**After any successful import:**
```bash
rm '<folder>/.beets-failed'
printf "Imported: $(date '+%Y-%m-%d %H:%M')\nTracks: <n>\n" > '<folder>/.beets-imported'
docker exec -u abc beets beet fetchart album:'<album>' artist:'<artist>'
docker exec -u abc beets beet embedart -y album:'<album>' artist:'<artist>'
curl -s "http://localhost:32400/library/sections/6/refresh?X-Plex-Token=shmYDQ52FuRArqZxXxJB"
```

**Case 3 — Not in MusicBrainz, not in Discogs**
AcoustID fingerprinting (chroma plugin) already ran during the first import attempt — it maps
to MB recording IDs only, so it can't help if the release isn't in MB.

First, display all embedded tags for every track in the folder:
```bash
for f in /mnt/data/downloads/music/<folder>/*.flac; do
  echo "--- $f ---"
  metaflac --export-tags-to=- "$f"
done
```
Present the tags clearly, then ask for direction:
- Tags look good → import with `-A`
- Tags wrong but fixable → fix with `metaflac --set-tag` or `metaflac --remove-tag`, then `-A`
- Tags empty or garbage → no automated path; human must source correct metadata

Import with existing tags:
```bash
docker exec -u abc beets beet import --copy --noincremental -A '<container_path>'
```

Container path = `/downloads/music/<folder-name>` (maps to `/mnt/data/downloads/music/` on host).

---

## Documented fixes — don't re-derive these

| Problem | Fix |
|---|---|
| Light snaps on then transitions (HomeKit Bridge strips transition on automation triggers) | Use an HA script with `brightness_pct` + `transition` set; expose via HomeKit Bridge; trigger from Apple Home automation |
| Scenes don't fade — they define end state only | Pass transition when calling `scene.turn_on`; or use a script instead |
| Apple TV not discovered in HA | Entry was `"source":"ignore"` in core.config_entries; fixed via jq in web terminal |
| DHCP static reservations | Dnsmasq administers all DHCP; leases work fine. Add static reservations in Services → Dnsmasq DNS & DHCP → Hosts. Kea is inactive. |
| Plexamp "No servers found" after sign-out/sign-in | Visit app.plex.tv in browser on the affected device and sign in — Plexamp picks up the refreshed session automatically. |
