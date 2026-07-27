#!/usr/bin/env python3
"""Fetch a Wikipedia photo for each species and render it as a pencil sketch.

Sketches are cached as small PNGs in sketches/ (committed, so they sync across
machines) and embedded into the landing page. Requires network access the first
time a species is seen; cached sketches are reused thereafter.

Usage:
    fetch_sketches.py [--force]   # --force re-fetches even if cached
"""
import argparse
import io
import os
import sys

import catalog_clips as cc
from analyze_recording import load_catalog, CATALOG_PATH

UA = ("BirdSongCatalog/1.0 (personal bird-ID project; "
      "contact jimmy.eck.ai@gmail.com)")
SKETCH_WIDTH = 360


def wikipedia_image_url(common_name, requests):
    """Return the best image URL for a species from the Wikipedia REST summary,
    or None if there's no article/image."""
    title = common_name.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if str(data.get("type", "")).endswith("not_found"):
        return None
    src = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
    return src


def pencil_sketch(img):
    """Convert a PIL image into a grayscale pencil sketch on white."""
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps

    img = img.convert("RGB")
    w, h = img.size
    img = img.resize((SKETCH_WIDTH, max(1, int(h * SKETCH_WIDTH / w))))
    gray = ImageOps.grayscale(img)
    inv = ImageOps.invert(gray)
    blur = inv.filter(ImageFilter.GaussianBlur(6))
    g = np.asarray(gray, dtype=np.float32)
    b = np.asarray(blur, dtype=np.float32)
    dodge = np.where(b >= 255, 255, np.minimum(255, g * 255.0 / (255.0 - b)))
    sk = Image.fromarray(dodge.astype("uint8"))
    return ImageOps.autocontrast(sk, cutoff=1)


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch + sketch species photos.")
    p.add_argument("--force", action="store_true",
                   help="Re-fetch even if a cached sketch exists.")
    args = p.parse_args(argv)

    import requests
    from PIL import Image

    catalog = load_catalog(CATALOG_PATH)
    os.makedirs(cc.SKETCHES_DIR, exist_ok=True)

    made = cached = failed = 0
    failures = []
    for name in sorted(catalog["species"]):
        out = cc.sketch_path(name)
        if os.path.exists(out) and not args.force:
            cached += 1
            continue
        try:
            src = wikipedia_image_url(name, requests)
            if not src:
                failed += 1
                failures.append(f"{name} (no Wikipedia image)")
                continue
            raw = requests.get(src, headers={"User-Agent": UA}, timeout=30).content
            sk = pencil_sketch(Image.open(io.BytesIO(raw)))
            buf = io.BytesIO()
            sk.save(buf, format="PNG", optimize=True)
            with open(out, "wb") as f:
                f.write(buf.getvalue())
            made += 1
            print(f"  sketched {name} ({len(buf.getvalue()) // 1024} KB)")
        except Exception as e:  # network / decode errors -> skip, use fallback
            failed += 1
            failures.append(f"{name} ({e})")

    print(f"Sketches: {made} created, {cached} cached, {failed} unavailable.")
    if failures:
        print("  Unavailable (page will show a fallback bird icon):")
        for f in failures:
            print(f"    - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
