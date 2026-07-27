#!/usr/bin/env python3
"""Fetch a Wikipedia photo for each species and render it as a watercolor.

Not AI-generated: this applies a painterly watercolor *effect* (edge-preserving
color washes, boosted pigment, subtle paper texture, and edges feathered into
white) to each bird's Wikipedia photo. Results are cached as small JPEGs in
watercolors/ (committed, so they sync across machines) and embedded into the
landing page.

Usage:
    fetch_watercolors.py [--force]   # --force re-renders even if cached
"""
import argparse
import io
import os
import sys

import catalog_clips as cc
from analyze_recording import load_catalog, CATALOG_PATH

UA = ("BirdSongCatalog/1.0 (personal bird-ID project; "
      "contact jimmy.eck.ai@gmail.com)")
OUT_WIDTH = 520


def wikipedia_image_url(common_name, requests):
    title = common_name.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    if r.status_code != 200:
        return None
    data = r.json()
    if str(data.get("type", "")).endswith("not_found"):
        return None
    return (data.get("originalimage") or data.get("thumbnail") or {}).get("source")


def watercolor(pil):
    """Render a PIL image as a watercolor painting on white paper."""
    import cv2
    import numpy as np
    from PIL import Image

    pil = pil.convert("RGB")
    w, h = pil.size
    pil = pil.resize((OUT_WIDTH, max(1, int(h * OUT_WIDTH / w))))
    bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR).astype("uint8")

    # Soft color washes without hard outlines.
    sm = cv2.edgePreservingFilter(bgr, flags=cv2.RECURS_FILTER,
                                  sigma_s=60, sigma_r=0.4)
    sm = cv2.bilateralFilter(sm, 9, 60, 60)
    sm = cv2.medianBlur(sm, 5)

    # Boost pigment vibrancy.
    hsv = cv2.cvtColor(sm, cv2.COLOR_BGR2HSV).astype("float32")
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.28, 0, 255)
    hsv[..., 2] = np.clip(hsv[..., 2] * 1.05, 0, 255)
    sm = cv2.cvtColor(hsv.astype("uint8"), cv2.COLOR_HSV2BGR)

    # Airy wash: lift toward white.
    white = np.full_like(sm, 255)
    sm = cv2.addWeighted(sm, 0.82, white, 0.18, 0)

    rgb = cv2.cvtColor(sm, cv2.COLOR_BGR2RGB).astype("float32")
    H, W = rgb.shape[:2]

    # Faint paper texture.
    rng = np.random.default_rng(7)
    tex = rng.normal(0, 1, (H, W)).astype("float32")
    tex = cv2.GaussianBlur(tex, (0, 0), 1.2)
    tex = tex / (np.abs(tex).max() + 1e-6)
    rgb *= (1.0 + 0.05 * tex[..., None])
    rgb = np.clip(rgb, 0, 255)

    # Feather the edges into white paper (smoothstep vignette).
    yy, xx = np.mgrid[0:H, 0:W]
    dx = np.minimum(xx, W - 1 - xx) / (W * 0.5)
    dy = np.minimum(yy, H - 1 - yy) / (H * 0.5)
    d = np.minimum(dx, dy)
    a = np.clip((d - 0.04) / 0.16, 0, 1)
    a = a * a * (3 - 2 * a)
    a = a[..., None]
    out = rgb * a + 255 * (1 - a)
    return Image.fromarray(out.astype("uint8"))


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch + watercolor species photos.")
    p.add_argument("--force", action="store_true",
                   help="Re-render even if a cached watercolor exists.")
    args = p.parse_args(argv)

    import requests
    from PIL import Image

    catalog = load_catalog(CATALOG_PATH)
    os.makedirs(cc.ART_DIR, exist_ok=True)

    made = cached = failed = 0
    failures = []
    for name in sorted(catalog["species"]):
        out = cc.art_path(name)
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
            art = watercolor(Image.open(io.BytesIO(raw)))
            buf = io.BytesIO()
            art.save(buf, format="JPEG", quality=88, optimize=True)
            with open(out, "wb") as f:
                f.write(buf.getvalue())
            made += 1
            print(f"  painted {name} ({len(buf.getvalue()) // 1024} KB)")
        except Exception as e:
            failed += 1
            failures.append(f"{name} ({e})")

    print(f"Watercolors: {made} created, {cached} cached, {failed} unavailable.")
    if failures:
        print("  Unavailable (page will show a fallback bird icon):")
        for f in failures:
            print(f"    - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
