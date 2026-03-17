# Skill Ideas

Skills that aren't built yet but may grow into something. Promote to a full skill when the workflow crystallizes.

---

## /council
**Trinity Council agenda + PDF generation**

Fill in the agenda template (`~/Documents/Trinity Council/Trinity Council Agenda Template.md`) with the current date, open in Marked, offer to export PDF using the pandoc + weasyprint pipeline.

PDF command:
```bash
pandoc <file> --standalone -o /tmp/out.html && cp -r ~/Documents/Trinity\ Council/assets /tmp/assets && weasyprint /tmp/out.html <output.pdf>
```

---

## /playlist
**Natural language Plex playlist creation**

"Make me something for a rainy Sunday afternoon" → queries Plex music library (192.168.0.34:32400, token in ~/.config/plex/credentials), selects artists that fit the mood, creates a playlist via the Plex API.

Could also support: `/playlist refresh Guitar Heroes` to regenerate an existing playlist with new random tracks.

---

## /bike
**Quick route lookup**

Look up a bike route from `~/Notes/personal/bike-rides.md` by keyword or distance.
e.g. `/bike 40` → shows ~40 mile options. `/bike reverse` → shows REV variants.

---

## /pdf
**Generic pandoc + weasyprint PDF export**

Convert any markdown file to a styled PDF. Used for Trinity Council docs but could apply anywhere.
```bash
pandoc $FILE --standalone -o /tmp/out.html && weasyprint /tmp/out.html $OUTPUT
```

---

## /plex-compare
**Re-run Plex library comparison**

Re-export and diff old vs. current Plex library when new exports are available. Updates `~/Notes/personal/plex-library-comparison.md`.

---
