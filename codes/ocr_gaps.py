#!/usr/bin/env python3
"""Second OCR pass: fill remaining EMPTY pages across all 243 docs.

The main pass (ocr_scanned.py) handled the 27 fully-scanned PDFs. But ~35 other
docs have individual pages with no extracted text (scanned letterheads,
slide pages, appendix pages) while an extracted image exists. This pass finds
every such (doc, page) and transcribes it with the same HKBU vision pipeline
(+ tesseract fallback), then merges the text back into the doc's markdown.

Pages that are genuinely blank stay blank (LLM replies "[blank]").

Usage: nohup python3 codes/ocr_gaps.py > data/ocr_gaps.log 2>&1 &
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "codes"))

import build_site as bs
import ocr_scanned as oc

DATA = os.path.join(ROOT, "data")
MD_DIR = os.path.join(DATA, "markdown")
MIN_CHARS = 30   # page bodies shorter than this count as empty


def find_gaps():
    out = []   # (doc, page_num, fname)
    for d in bs.INDEX:
        slug = bs.slug_of(d)
        md = os.path.join(MD_DIR, f"{slug}.md")
        if not os.path.exists(md):
            continue
        t = open(md, encoding="utf-8", errors="ignore").read()
        pages = re.split(r"^--- Page (\d+) ---$", t, flags=re.M)
        page_files = {}
        for f in os.listdir(os.path.join(DATA, "images")):
            m = re.match(rf"^{re.escape(slug)}_p(\d+)_img(\d+)", f)
            if m:
                page_files.setdefault(int(m.group(1)), []).append(f)
        for i in range(1, len(pages), 2):
            n = int(pages[i])
            body = pages[i + 1].strip()
            if len(body) >= MIN_CHARS:
                continue
            if n not in page_files:
                continue
            # already transcribed?
            rp = oc.page_result_path(slug, n)
            if os.path.exists(rp):
                rec = json.load(open(rp))
                if rec.get("ok") and len(rec.get("text", "")) >= MIN_CHARS and rec.get("text") != "[blank]":
                    continue
            # best image for this page (prefer page_scan/photo)
            inv_imgs = bs.IMAGE_INV.get("images", {}) if isinstance(bs.IMAGE_INV.get("images", {}), dict) else {}
            best = None; best_score = -1
            for f in page_files[n]:
                label = (inv_imgs.get(f) or {}).get("label", "")
                score = {"page_scan": 3, "photo": 2, "diagram": 1, "blank": 0, "junk_tiny": 0}.get(label, 1)
                if score > best_score:
                    best, best_score = f, score
            if best:
                out.append((d, n, best))
    return out


def merge_slug(slug, pages):
    """pages: {page_num: rec} — insert text into markdown for that slug."""
    md = os.path.join(MD_DIR, f"{slug}.md")
    if not os.path.exists(md):
        return False
    content = open(md, encoding="utf-8").read()
    def repl(m):
        pg = int(m.group(1))
        txt = (pages.get(pg) or {}).get("text", "").strip()
        if txt == "[blank]":
            txt = ""
        return f"--- Page {pg} ---\n\n{txt}\n" if txt else m.group(0)
    new = re.sub(r"^--- Page (\d+) ---\s*$", repl, content, flags=re.M)
    if new == content:
        return False
    open(md, "w", encoding="utf-8").write(new)
    return True


def main():
    workers = int(os.environ.get("OCR_WORKERS", "3"))
    gaps = find_gaps()
    print(f"empty pages to OCR: {len(gaps)} across {len(set(bs.slug_of(d) for d, _, _ in gaps))} docs", flush=True)

    by_slug = {}
    done = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(oc.process_page, d, pg, fname): (d, pg, fname) for d, pg, fname in gaps}
        for fut in as_completed(futs):
            slug, pg, rec = fut.result()
            rp = oc.page_result_path(slug, pg)
            json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)
            if rec.get("ok") and rec.get("text") != "[blank]":
                by_slug.setdefault(slug, {})[pg] = rec
                done += 1
            else:
                fail += 1
            if (done + fail) % 20 == 0:
                print(f"  {(done + fail)}/{len(gaps)} (ok={done} blank/fail={fail})", flush=True)
            time.sleep(oc.SLEEP)

    n_merged = 0
    for slug, pages in by_slug.items():
        if merge_slug(slug, pages):
            n_merged += 1
            print(f"[merge] {slug}: {len(pages)} pages filled", flush=True)
    print(f"done. transcribed={done} blank_or_fail={fail} docs_merged={n_merged}", flush=True)


if __name__ == "__main__":
    main()
