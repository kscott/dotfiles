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

## Source of truth: config changes happen on Primo, in the repo

All homelab configuration lives in the `homelab` git repo (`~/dev/homelab` on Primo → cloned to `/opt/homelab` on Secondo, Quarto, etc.). **Edit config in the repo on Primo first, commit, push, then pull it down to the target machine.** Never hand-edit a running machine's config over SSH as a standalone fix — even a "quick fix" becomes untracked drift the moment it's not also in the repo.

If a config file that should change isn't tracked in the repo yet (e.g. `/etc/netplan/*.yaml`, a systemd unit, a sysctl drop-in), that's a sign it belongs there — add it to the repo as part of the fix, don't just edit it live and move on.

Before ending a session that touched any machine's config, confirm the repo clone on every machine you touched is clean and pushed — not just the local/Primo copy. Drift hides on the remote clone (found twice: Quarto's Prometheus/docker-compose changes sat uncommitted for days; Secondo's WiFi/routing changes weren't in the repo at all).

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

Use the `/beets-import` skill — it handles all three cases (MB near-match, Discogs-only, tag-based).

---

## Documented fixes — don't re-derive these

| Problem | Fix |
|---|---|
| Light snaps on then transitions (HomeKit Bridge strips transition on automation triggers) | Use an HA script with `brightness_pct` + `transition` set; expose via HomeKit Bridge; trigger from Apple Home automation |
| Scenes don't fade — they define end state only | Pass transition when calling `scene.turn_on`; or use a script instead |
| Apple TV not discovered in HA | Entry was `"source":"ignore"` in core.config_entries; fixed via jq in web terminal |
| DHCP static reservations | Dnsmasq administers all DHCP; leases work fine. Add static reservations in Services → Dnsmasq DNS & DHCP → Hosts. Kea is inactive. |
| Plexamp "No servers found" after sign-out/sign-in | Visit app.plex.tv in browser on the affected device and sign in — Plexamp picks up the refreshed session automatically. |
