#!/usr/bin/env python3
"""Triage the 8,785 extracted images: measure every image, classify by value,
group exact duplicates, and produce data/image_inventory.json for the vision pass.

Classes (heuristic):
  junk_tiny   - very small (thumbnail/icon/fragment)
  blank       - near-uniform white/black (empty scan or noise)
  low_value   - near-uniform color (divider, swatch, mostly-empty)
  page_scan   - A4-ish aspect, grayscale-ish, large: full-page reproduction
  photo       - larger, high variance, natural colours (likely scene/evidence photo)
  diagram     - larger, not page-like, moderate complexity (charts/maps/schematics)
  logo        - small-ish with transparent/simple colours (repeated across docs)

Exact-duplicate groups are keyed by md5; the first (alphabetical) member is kept.

Usage: python3 codes/image_triage.py > data/image_triage.log 2>&1
"""
import os, sys, glob, hashlib, json
from collections import Counter

try:
    from PIL import Image
except ImportError:
    print("PIL not available", file=sys.stderr); sys.exit(1)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "data", "images")
OUT = os.path.join(ROOT, "data", "image_inventory.json")

MIN_KEEP_DIM = 96          # smaller -> junk
MIN_KEEP_BYTES = 1024
BLANK_STD = 8.0            # stddev below this -> near-uniform
BLANK_MEAN_HI = 250.0      # bright blank
BLANK_MEAN_LO = 6.0        # dark blank
PAGE_ASPECT = 0.7071
PAGE_ASPECT_TOL = 0.20
PAGE_MIN_BYTES = 24576     # a real page scan is usually > 24KB
PAGE_MIN_DIM = 512

def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def classify(p, st):
    """st = dict(w,h,size,mean,std,aspect,gray_std, ncolors_est) -> (label, reason)"""
    w, h, size = st["w"], st["h"], st["size"]
    if w < MIN_KEEP_DIM or h < MIN_KEEP_DIM or size < MIN_KEEP_BYTES:
        return "junk_tiny", f"{w}x{h} {size}B"
    if st["std"] < BLANK_STD:
        if st["mean"] > BLANK_MEAN_HI:
            return "blank", f"white mean={st['mean']:.0f} std={st['std']:.1f}"
        if st["mean"] < BLANK_MEAN_LO:
            return "blank", f"black mean={st['mean']:.0f} std={st['std']:.1f}"
        return "low_value", f"uniform std={st['std']:.1f}"
    aspect = st["aspect"]
    page_like = abs(aspect - PAGE_ASPECT) < PAGE_ASPECT_TOL and size >= PAGE_MIN_BYTES and min(w, h) >= PAGE_MIN_DIM
    if page_like and st["gray_std"] < 18:
        return "page_scan", f"A4-ish {w}x{h} grayscale"
    if st["ncolors_est"] <= 32:
        return "diagram", f"few colours {w}x{h}"
    if size >= 32768 and min(w, h) >= 400:
        return "photo", f"{w}x{h} {size//1024}KB"
    return "diagram", f"{w}x{h} {size//1024}KB"

def main():
    files = sorted(glob.glob(os.path.join(IMG_DIR, "*")))
    print(f"scanning {len(files)} images", flush=True)
    inv, dup = {}, {}
    counts = Counter()
    for i, p in enumerate(files):
        rel = os.path.basename(p)
        try:
            with Image.open(p) as im:
                im.load()
                w, h = im.size
                gray = im.convert("L")
                px = list(gray.resize((64, 64)).getdata())
                mean = sum(px) / len(px)
                var = sum((v - mean) ** 2 for v in px) / len(px)
                std = var ** 0.5
                # colour channel spread (saturation proxy)
                if im.mode in ("RGB", "RGBA"):
                    r = list(im.convert("RGB").resize((48, 48)).getdata())
                    ch = [[v[0] for v in r], [v[1] for v in r], [v[2] for v in r]]
                    gray_std = max(sum((x - sum(chk) / len(chk)) ** 2 for x in chk) / len(chk) for chk in ch) ** 0.5
                    ncolors = len(set(r))
                else:
                    gray_std = std
                    ncolors = len(set(px))
                size = os.path.getsize(p)
                st = {"w": w, "h": h, "size": size,
                      "aspect": w / h if h else 0,
                      "mean": mean, "std": std, "gray_std": gray_std,
                      "ncolors_est": ncolors}
                label, reason = classify(p, st)
                h = md5(p)
                st.update({"md5": h, "label": label, "reason": reason, "dup_group": None})
        except Exception as e:
            st = {"w": 0, "h": 0, "size": os.path.getsize(p), "aspect": 0,
                  "mean": 0, "std": 0, "gray_std": 0, "ncolors_est": 0,
                  "label": "unreadable", "reason": str(e)[:60], "md5": "", "dup_group": None}
        counts[st["label"]] += 1
        inv[rel] = st
        if st["md5"]:
            dup.setdefault(st["md5"], []).append(rel)
        if (i + 1) % 1000 == 0:
            print(f"  {i+1}/{len(files)}", flush=True)

    # assign duplicate groups (keep first alphabetical member)
    gid = 0
    keep = set()
    for h, members in dup.items():
        if len(members) > 1:
            gid += 1
            for m in members:
                inv[m]["dup_group"] = gid
            keep.add(min(members))
    for m in inv:
        if inv[m]["dup_group"] is None:
            keep.add(m)

    summary = {
        "total": len(files),
        "by_label": dict(counts),
        "dup_groups": gid,
        "unique_images": len(keep),
        "keep": sorted(keep),
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "images": inv}, f, ensure_ascii=False, indent=1)
    print("by_label:", dict(counts))
    print(f"duplicate groups: {gid}; unique images: {len(keep)}")
    print(f"saved -> {OUT}")

if __name__ == "__main__":
    main()
