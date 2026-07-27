#!/usr/bin/env python3
"""Show, per species, which artwork the mural will use and the exact filename to
save a hand-made (e.g. ChatGPT) watercolor as.

Drop custom images in custom_art/ named by the "SAVE CUSTOM AS" column below;
they take precedence over the auto-generated watercolors.

Usage:
    art_status.py
"""
import os

import catalog_clips as cc
from analyze_recording import load_catalog, CATALOG_PATH
from generate_catalog_html import DISPLAY_MIN_CONF


def max_conf(entry):
    cs = [g.get("confidence") or 0
          for s in entry.get("sessions", []) for g in s.get("songs", [])]
    return max(cs) if cs else 0.0


def main():
    catalog = load_catalog(CATALOG_PATH)
    rows = sorted(catalog["species"].items(), key=lambda kv: -max_conf(kv[1]))

    print(f"Custom art folder : {cc.CUSTOM_ART_DIR}")
    print(f"Accepted formats  : {', '.join(cc.ART_EXTS)}")
    print(f"Shown on mural    : species with confidence >= "
          f"{DISPLAY_MIN_CONF:.0%}\n")
    print(f"{'SPECIES':30} {'CONF':>5}  {'MURAL':6} {'USING':7} SAVE CUSTOM AS")
    print("-" * 78)
    need = 0
    for name, entry in rows:
        mc = max_conf(entry)
        shown = mc >= DISPLAY_MIN_CONF
        custom = cc.custom_art_path(name)
        auto_exists = os.path.exists(cc.art_path(name))
        using = "custom" if custom else ("auto" if auto_exists else "none")
        if shown and not custom:
            need += 1
        print(f"{name:30} {mc * 100:4.0f}%  {'yes' if shown else 'no':6} "
              f"{using:7} custom_art/{cc.species_slug(name)}.png")
    print("-" * 78)
    print(f"{need} mural species still on the auto watercolor (custom art would "
          f"upgrade them).")
    print("Style prompt: see ART_STYLE_PROMPT.md")


if __name__ == "__main__":
    main()
