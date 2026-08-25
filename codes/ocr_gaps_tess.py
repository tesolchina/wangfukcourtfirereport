#!/usr/bin/env python3
"""OCR gap pages with tesseract FIRST (fast, local), writing results into the
same data/ocr/{slug}_p{NNN}.json cache that ocr_gaps.py consumes, and merging
into the markdown. Pages tesseract cannot transcribe (< 30 chars) are left
unmerged and un-cached as ok, so ocr_gaps.py's LLM pass retries them.

Usage: python3 codes/ocr_gaps_tess.py
"""
import json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "codes"))

import build_site as bs
import ocr_gaps as og
import ocr_scanned as oc

MD_DIR = os.path.join(ROOT, "data", "markdown")
OCR_DIR = os.path.join(ROOT, "data", "ocr")
MIN_CHARS = 30


def main():
    gaps = og.find_gaps()   # (doc, page_num, fname) — skips pages already cached ok
    print(f"gap pages for tesseract: {len(gaps)}", flush=True)
    ok_slugs = {}   # slug -> {page: rec}
    fail_pages = []
    for d, pg, fname in gaps:
        slug = bs.slug_of(d)
        path = os.path.join(ROOT, "data", "images", fname)
        t0 = time.time()
        try:
            r = subprocess.run(
                ["tesseract", path, "stdout", "-l", "chi_tra+eng", "--psm", "4"],
                capture_output=True, text=True, timeout=240)
            text = (r.stdout or "").strip()
        except Exception as e:
            text = ""
            print(f"[err] {slug} p{pg:03d} tesseract: {e}", flush=True)
        rec = {"page": pg, "file": fname, "ok": False, "src": ""}
        if len(text) >= MIN_CHARS:
            rec.update(text=text, src="tesseract", ok=True)
        else:
            rec["error"] = "tesseract produced < %d chars" % MIN_CHARS
            fail_pages.append((slug, pg))
        # persist cache even for failures so ocr_gaps.py skips re-trying tesseract
        rp = oc.page_result_path(slug, pg)
        json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)
        if rec["ok"]:
            ok_slugs.setdefault(slug, {})[pg] = rec
            print(f"[ok] {slug} p{pg:03d} {len(text)} chars ({time.time()-t0:.0f}s)", flush=True)
        else:
            print(f"[fail] {slug} p{pg:03d} ({time.time()-t0:.0f}s)", flush=True)

    # merge tesseract results into markdown (same function ocr_gaps.py uses)
    n_merged = 0
    for slug, pages in ok_slugs.items():
        if og.merge_slug(slug, pages):
            n_merged += 1
            print(f"[merge] {slug}: {len(pages)} pages filled", flush=True)
    print(f"done. transcribed={sum(len(v) for v in ok_slugs.values())} "
          f"docs_merged={n_merged} left_for_llm={len(fail_pages)}", flush=True)
    for slug, pg in fail_pages:
        print(f"  llm-retry: {slug} p{pg:03d}", flush=True)


if __name__ == "__main__":
    main()
