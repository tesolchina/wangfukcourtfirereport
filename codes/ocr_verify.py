#!/usr/bin/env python3
"""Verify/correct tesseract OCR results using the HKBU gpt-4.1-mini vision model.

For every page whose OCR cache has src="tesseract", send the page image + the
tesseract text to the LLM and ask it to produce a corrected transcription.
Update the cache (src becomes "llm_verified") and re-merge into markdown.

Single-worker by default to avoid the HKBU gateway wedge. Run as:
  nohup python3 codes/ocr_verify.py > data/ocr_verify.log 2>&1 &

Environment:
  OCR_VERIFY_WORKERS  (default 1)  — parallel workers; keep at 1 to avoid 429
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "codes"))

import build_site as bs
import ocr_scanned as oc
import ocr_gaps as og

DATA = os.path.join(ROOT, "data")
OCR_DIR = os.path.join(DATA, "ocr")
MD_DIR = os.path.join(DATA, "markdown")
IMG_DIR = os.path.join(DATA, "images")

VERIFY_PROMPT = (
    "You are verifying and correcting an OCR transcription of a scanned page from an official "
    "document of the Hong Kong Independent Committee on the Fire at Wang Fuk Court (大埔宏福苑). "
    "Below is a tesseract OCR transcription of this page image. Tesseract often makes errors with "
    "Traditional Chinese characters, numbers, and punctuation. Please carefully compare the image "
    "to the tesseract text and produce a CORRECTED transcription that faithfully reflects what is "
    "actually on the page. Keep the original language (English and/or Traditional Chinese), "
    "paragraph structure, headings, and signatures/stamps where readable. Render tables and lists "
    "in markdown. Do not add commentary or headings of your own. If the page is blank or contains "
    "only a page number, reply with exactly: [blank]\n\n"
    "--- TESSERACT OCR TEXT (may contain errors) ---\n"
)


def find_tesseract_pages():
    """Return list of (slug, page_num, image_filename, cache_path) for tesseract-OCR'd pages."""
    out = []
    for fname in sorted(os.listdir(OCR_DIR)):
        if not fname.endswith(".json"):
            continue
        rp = os.path.join(OCR_DIR, fname)
        try:
            rec = json.load(open(rp))
        except Exception:
            continue
        if rec.get("src") != "tesseract" or not rec.get("ok"):
            continue
        # find the image file
        m = re.match(r"^(.+)_p(\d+)\.json$", fname)
        if not m:
            continue
        slug, pg = m.group(1), int(m.group(2))
        img_candidates = [f for f in os.listdir(IMG_DIR)
                          if f.startswith(f"{slug}_p{pg:03d}_img")]
        if not img_candidates:
            continue
        # prefer img001
        img = sorted(img_candidates)[0]
        out.append((slug, pg, img, rp, rec))
    return out


def verify_page(slug, pg, img_fname, cache_path, rec):
    """Send image + tesseract text to LLM, return corrected text or None."""
    img_path = os.path.join(IMG_DIR, img_fname)
    if not os.path.exists(img_path):
        return slug, pg, None, "missing image"
    try:
        mime, b64 = oc.downscale(img_path)
    except Exception as e:
        return slug, pg, None, f"downscale error: {e}"

    tess_text = rec.get("text", "")
    prompt = VERIFY_PROMPT + tess_text

    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        "max_tokens": oc.MAX_TOKENS,
        "temperature": 0.0,
    }
    req = __import__("urllib.request", fromlist=["Request"]).Request(
        oc.ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "api-key": oc.API_KEY}, method="POST")
    try:
        import ssl
        ctx = oc.CTX
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=180, context=ctx) as r:
            resp = json.loads(r.read().decode())
        corrected = (resp["choices"][0]["message"]["content"] or "").strip()
        return slug, pg, corrected, None
    except Exception as e:
        return slug, pg, None, str(e)[:160]


def main():
    workers = int(os.environ.get("OCR_VERIFY_WORKERS", "1"))
    pages = find_tesseract_pages()
    print(f"tesseract pages to verify: {len(pages)}", flush=True)
    if not pages:
        print("nothing to do.", flush=True)
        return

    by_slug = {}   # slug -> {pg: rec}
    done = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(verify_page, s, p, i, c, r): (s, p) for s, p, i, c, r in pages}
        for fut in as_completed(futs):
            slug, pg, corrected, err = fut.result()
            if corrected and len(corrected) >= 10 and corrected != "[blank]":
                # update cache
                rp = oc.page_result_path(slug, pg)
                rec = json.load(open(rp))
                rec["text"] = corrected
                rec["src"] = "llm_verified"
                rec["tesseract_text"] = rec.get("text", "")  # preserve original
                json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)
                by_slug.setdefault(slug, {})[pg] = rec
                done += 1
                print(f"[ok] {slug} p{pg:03d} verified ({len(corrected)} chars)", flush=True)
            elif corrected == "[blank]":
                rp = oc.page_result_path(slug, pg)
                rec = json.load(open(rp))
                rec["src"] = "llm_verified"
                rec["text"] = "[blank]"
                json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)
                done += 1
                print(f"[blank] {slug} p{pg:03d}", flush=True)
            else:
                fail += 1
                print(f"[fail] {slug} p{pg:03d}: {err}", flush=True)
            if (done + fail) % 10 == 0:
                print(f"  progress: {done+fail}/{len(pages)} (ok={done} fail={fail})", flush=True)
            time.sleep(oc.SLEEP)

    # re-merge verified text into markdown
    n_merged = 0
    for slug, pages_dict in by_slug.items():
        if og.merge_slug(slug, pages_dict):
            n_merged += 1
            print(f"[merge] {slug}: {len(pages_dict)} pages updated", flush=True)
    print(f"done. verified={done} fail={fail} docs_merged={n_merged}", flush=True)


if __name__ == "__main__":
    main()
