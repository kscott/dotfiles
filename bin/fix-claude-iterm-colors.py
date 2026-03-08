#!/usr/bin/env python3
"""Patch the Claude iTerm2 profile colors in the preferences plist."""

import plistlib
import shutil
from pathlib import Path

PLIST = Path.home() / "Library/Preferences/com.googlecode.iterm2.plist"
BACKUP = PLIST.with_suffix(".plist.bak")

def color(r, g, b, a=1.0):
    return {"Red Component": r, "Green Component": g, "Blue Component": b,
            "Alpha Component": a, "Color Space": "sRGB"}

G = 0x28 / 255  # gruvbox dark background #282828
FONT = "JetBrainsMonoNerdFontMono-Regular 14"

PATCHES = {
    # Font (Nerd Font Mono variant for starship icons)
    "Normal Font":        FONT,
    "Non Ascii Font":     FONT,
    # Gruvbox dark background
    "Background Color":   color(G, G, G),
    # Cursor text matches background
    "Cursor Text Color":  color(G, G, G),
    # ANSI 0 (black): gruvbox dark1 #3c3836
    "Ansi 0 Color":       color(0x3c/255, 0x38/255, 0x36/255),
    # ANSI 1 (red): gruvbox neutral_red #cc241d
    "Ansi 1 Color":       color(0xcc/255, 0x24/255, 0x1d/255),
    # ANSI 8 (bright black): gruvbox gray #928374
    "Ansi 8 Color":       color(0x92/255, 0x83/255, 0x74/255),
    # Selection: gruvbox dark2 #504945 (subtle, readable)
    "Selection Color":    color(0x50/255, 0x49/255, 0x45/255),
    # Transparency (from Local profile)
    "Transparency":       0.035260263830423355,
    # Blend (from Local profile)
    "Blend":              0.30000001192092896,
}

shutil.copy2(PLIST, BACKUP)
print(f"Backed up to {BACKUP}")

with open(PLIST, "rb") as f:
    data = plistlib.load(f)

profiles = data.get("New Bookmarks", [])
patched = False
for profile in profiles:
    if profile.get("Name") == "Claude":
        for key, value in PATCHES.items():
            profile[key] = value
        patched = True
        print("Patched Claude profile.")
        break

if not patched:
    print("ERROR: Claude profile not found!")
    raise SystemExit(1)

with open(PLIST, "wb") as f:
    plistlib.dump(data, f)

print("Done. Launch iTerm2.")
