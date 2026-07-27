#!/usr/bin/env python3
"""Auto-generate watercolor bird portraits with the OpenAI Images API and save
them into custom_art/ (where they override the auto watercolors).

NOTE: this uses the OpenAI *Platform API* (platform.openai.com), which is billed
per image and is SEPARATE from a ChatGPT Pro subscription. You need an API key:

    export OPENAI_API_KEY="sk-..."
    ./venv/bin/python generate_art_openai.py            # mural birds missing art
    ./venv/bin/python generate_art_openai.py --dry-run  # show plan + cost, no calls
    ./venv/bin/python generate_art_openai.py --all --force --quality high

By default it only generates for mural species (confidence >= DISPLAY_MIN_CONF)
that don't already have custom art. For each bird it fetches the Wikipedia photo
as a reference and asks the model to repaint it as a watercolor (falling back to
text-only generation when no reference photo is available).

Rough cost per 1024x1024 image: low ~$0.02, medium ~$0.04, high ~$0.17.
"""
import argparse
import base64
import io
import os
import sys

import catalog_clips as cc
from analyze_recording import load_catalog, CATALOG_PATH
from generate_catalog_html import DISPLAY_MIN_CONF
from fetch_watercolors import wikipedia_image_url, UA

MODEL = "gpt-image-1"

# Per-style description of the {name} subject. Prompts are assembled from these
# plus a background clause (transparent cutout vs white paper).
STYLE_DESC = {
    "field-guide": (
        "a naturalistic vintage field-guide illustration of a {name}, in the style "
        "of a classic Audubon / Sibley bird plate: fine detailed brushwork, accurate "
        "plumage and markings, natural colours, a painted look with clean crisp edges"),
    "storybook": (
        "a painted storybook illustration of a {name}: warm, charming, slightly "
        "stylized, confident clean edges, rich but friendly colours"),
    "watercolor": (
        "a delicate watercolor painting of a {name}: loose soft washes, visible paper "
        "texture, gentle pigment bleeds, no hard outlines"),
    "flat": (
        "a bold flat vector illustration of a {name}: simple clean shapes, minimal "
        "shading, graphic and playful"),
}

TRANSPARENT_BG = ("The bird is fully isolated with no background, no scenery, no "
                  "perch, no shadow — a single bird cut out cleanly. ")
WHITE_BG = ("Plain white background with the edges softly feathering into the white, "
            "no frame, no border, no shadow. ")


def build_prompt(style, name, transparent, edit):
    desc = STYLE_DESC[style].format(name=name)
    bg = TRANSPARENT_BG if transparent else WHITE_BG
    lead = ("Repaint this bird as " + desc + ". Keep the bird's real colours and "
            "markings. ") if edit else (desc[0].upper() + desc[1:] + ". ")
    return (lead + "A single bird, natural pose. " + bg +
            "No text, no labels, no signature, no border.")


def max_conf(entry):
    cs = [g.get("confidence") or 0
          for s in entry.get("sessions", []) for g in s.get("songs", [])]
    return max(cs) if cs else 0.0


def species_label(entry):
    name = entry.get("common_name")
    sci = entry.get("scientific_name")
    return f"{name} ({sci})" if sci else name


def download_reference(name, requests, max_w=1024):
    """Fetch the Wikipedia photo for a species, downscaled to a temp PNG in
    memory. Returns (BytesIO, filename) or None."""
    from PIL import Image
    src = wikipedia_image_url(name, requests)
    if not src:
        return None
    raw = requests.get(src, headers={"User-Agent": UA}, timeout=30).content
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    if w > max_w:
        img = img.resize((max_w, max(1, int(h * max_w / w))))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    buf.name = cc.species_slug(name) + ".png"  # SDK infers type from name
    return buf


def targets(catalog, include_all, force):
    """Species to generate, best-confidence first."""
    rows = sorted(catalog["species"].items(), key=lambda kv: -max_conf(kv[1]))
    out = []
    for name, entry in rows:
        if not include_all and max_conf(entry) < DISPLAY_MIN_CONF:
            continue
        if not force and cc.custom_art_path(name):
            continue
        out.append((name, entry))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate watercolor art via OpenAI.")
    p.add_argument("--all", action="store_true",
                   help="Include all species, not just mural (>= threshold) ones.")
    p.add_argument("--force", action="store_true",
                   help="Regenerate even species that already have custom art.")
    p.add_argument("--quality", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--size", default="1024x1024")
    p.add_argument("--style", choices=sorted(STYLE_DESC), default="field-guide",
                   help="Art style (default: field-guide).")
    p.add_argument("--transparent", action="store_true",
                   help="Generate cutouts with a transparent background (PNG).")
    p.add_argument("--text-only", action="store_true",
                   help="Skip the reference photo; generate from text alone.")
    p.add_argument("--limit", type=int, default=None,
                   help="Only generate the first N targets (to cap cost).")
    p.add_argument("--dry-run", action="store_true",
                   help="List what would be generated (no API calls, no cost).")
    args = p.parse_args(argv)

    catalog = load_catalog(CATALOG_PATH)
    todo = targets(catalog, args.all, args.force)
    if args.limit is not None:
        todo = todo[:args.limit]

    if not todo:
        print("Nothing to generate: every selected species already has custom art.")
        print("Use --force to regenerate, or --all to include sub-threshold species.")
        return 0

    approx = {"low": 0.02, "medium": 0.04, "high": 0.17}[args.quality]
    print(f"Model: {MODEL} | style: {args.style} | "
          f"{'transparent' if args.transparent else 'white bg'} | "
          f"quality: {args.quality} | size: {args.size}")
    print(f"{len(todo)} image(s) to generate "
          f"(~${approx * len(todo):.2f} at ~${approx:.2f}/image):")
    for name, _ in todo:
        print(f"  - {name}  ->  custom_art/{cc.species_slug(name)}.png")

    if args.dry_run:
        print("\nDry run — no API calls made, no cost incurred.")
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("\nError: OPENAI_API_KEY is not set. "
                 "export OPENAI_API_KEY=\"sk-...\" and re-run.")

    import requests
    from openai import OpenAI
    client = OpenAI()
    os.makedirs(cc.CUSTOM_ART_DIR, exist_ok=True)

    extra = {}
    if args.transparent:
        extra = {"background": "transparent", "output_format": "png"}

    made = failed = 0
    for name, entry in todo:
        label = species_label(entry)
        out_path = os.path.join(cc.CUSTOM_ART_DIR, cc.species_slug(name) + ".png")
        try:
            ref = None if args.text_only else download_reference(name, requests)
            if ref is not None:
                resp = client.images.edit(
                    model=MODEL, image=ref, size=args.size, quality=args.quality,
                    prompt=build_prompt(args.style, label, args.transparent, True),
                    **extra)
                mode = "from photo"
            else:
                resp = client.images.generate(
                    model=MODEL, size=args.size, quality=args.quality,
                    prompt=build_prompt(args.style, label, args.transparent, False),
                    **extra)
                mode = "text-only"
            b64 = resp.data[0].b64_json
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(b64))
            made += 1
            print(f"  ✓ {name} ({mode}) -> {out_path}")
        except Exception as e:
            failed += 1
            print(f"  ✗ {name}: {e}")

    print(f"\nGenerated {made} image(s), {failed} failed.")
    if made:
        print("Now rebuild the page:  ./venv/bin/python generate_catalog_html.py "
              "(or ./save.sh)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
