#!/usr/bin/env python3
"""OCR the scanned documents (no text layer) so they become searchable.

The 27 scanned PDFs (Adobe ClearScan) carry no embedded text — only page numbers.
For each page image of each scanned doc, transcribe the page with the HKBU GenAI
vision model (gpt-4.1-mini), falling back to tesseract (chi_tra+eng) if the LLM
fails after retries. When every page of a doc is done, its data/markdown/{slug}.md
is rewritten with the OCR text inserted between the --- Page N --- markers, so the
normal pipeline (tor_full_scan, search_build, build_site, tc_site) picks it up.

State / checkpoints:
  data/ocr/{slug}_p{NNN}.json   per-page results (text + source)
  data/ocr_merged.json          slugs whose markdown has been rewritten
  data/ocr_summary.json         per-doc status (pages done / chars / source)

Usage: nohup python3 codes/ocr_scanned.py > data/ocr_scan.log 2>&1 &
"""
import base64, io, json, os, re, ssl, subprocess, sys, time
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as bs

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl._create_unverified_context()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
DATA = os.path.join(ROOT, "data")
IMG_DIR = os.path.join(DATA, "images")
OCR_DIR = os.path.join(DATA, "ocr")
MD_DIR = os.path.join(DATA, "markdown")
MERGE_PATH = os.path.join(DATA, "ocr_merged.json")
SUMMARY_PATH = os.path.join(DATA, "ocr_summary.json")
CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")

MAX_EDGE = 2048       # downscale long edge (pages are 2480x3507)
JPEG_Q = 90
MAX_RETRY = 4
MAX_TOKENS = 2200
SLEEP = 0.4

OCR_PROMPT = (
    "You are transcribing a scanned page from an official document of the Hong Kong "
    "Independent Committee on the Fire at Wang Fuk Court (大埔宏福苑). "
    "Transcribe ALL text on this page faithfully, keeping the original language "
    "(English and/or Traditional Chinese), the paragraph structure, headings, and "
    "signatures or stamps where readable. Render tables and lists in markdown. "
    "Do not add commentary, headings, or [translated] notes of your own. "
    "If the page is blank or contains only a page number, reply with exactly: [blank]"
)


def _api_key():
    content = open(CREDS).read()
    m = re.search(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)", content, re.I)
    if not m:
        sys.exit("no HKBU key in " + CREDS)
    return m.group(1).strip()


ENDPOINT = ("https://genai.hkbu.edu.hk/general/rest/deployments/gpt-4.1-mini/"
            "chat/completions?api-version=2024-02-01")
API_KEY = _api_key()


def downscale(path):
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        m = max(w, h)
        if m > MAX_EDGE:
            im = im.resize((int(w * MAX_EDGE / m), int(h * MAX_EDGE / m)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=JPEG_Q)
        b64 = base64.b64encode(buf.getvalue()).decode()
    return "image/jpeg", b64


def call_llm_ocr(b64):
    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": OCR_PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        "max_tokens": MAX_TOKENS,
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "api-key": API_KEY}, method="POST")
    with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
        resp = json.loads(r.read().decode())
    return (resp["choices"][0]["message"]["content"] or "").strip()


def ocr_tesseract(path):
    r = subprocess.run(["tesseract", path, "stdout", "-l", "chi_tra+eng", "--psm", "4"],
                       capture_output=True, text=True, timeout=180)
    return (r.stdout or "").strip()


def llm_ocr_with_retry(b64):
    last = None
    for attempt in range(MAX_RETRY):
        try:
            return call_llm_ocr(b64), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(3 + attempt * 5)
                continue
            raise
        except Exception as e:
            last = str(e)[:120]
            time.sleep(3 + attempt * 4)
    return None, last


def page_images(doc):
    """(page_num, filename) list covering the doc's pages (best image per page)."""
    slug = bs.slug_of(doc)
    files = [f for f in os.listdir(IMG_DIR) if f.startswith(slug + "_")]
    inv_imgs = bs.IMAGE_INV.get("images", {}) if isinstance(bs.IMAGE_INV.get("images", {}), dict) else {}
    by_page = {}
    for f in files:
        m = re.search(r"_p(\d+)_img(\d+)", f)
        if not m:
            continue
        pg, img = int(m.group(1)), int(m.group(2))
        label = (inv_imgs.get(f) or {}).get("label", "")
        score = {"page_scan": 3, "photo": 2, "diagram": 1, "blank": 0, "junk_tiny": 0}.get(label, 1)
        cur = by_page.get(pg)
        if cur is None or score > cur[0]:
            by_page[pg] = (score, f, img)
    return [(pg, by_page[pg][1]) for pg in sorted(by_page)]


def page_result_path(slug, pg):
    return os.path.join(OCR_DIR, f"{slug}_p{pg:03d}.json")


def process_page(doc, pg, fname):
    """Transcribe one page image; returns (slug, pg, rec)."""
    rec = {"page": pg, "file": fname, "ok": False, "src": ""}
    path = os.path.join(IMG_DIR, fname)
    if not os.path.exists(path):
        rec["error"] = "missing image file"
        return bs.slug_of(doc), pg, rec
    try:
        mime, b64 = downscale(path)
        text, err = llm_ocr_with_retry(b64)
        if text:
            rec["text"] = text
            rec["src"] = "llm"
            rec["ok"] = True
            return bs.slug_of(doc), pg, rec
        # LLM failed -> tesseract fallback
        try:
            t = ocr_tesseract(path)
            if t:
                rec["text"] = t
                rec["src"] = "tesseract"
                rec["ok"] = True
                rec["llm_error"] = err
                return bs.slug_of(doc), pg, rec
        except Exception as e2:
            err = (err or "") + f" tesseract:{str(e2)[:80]}"
        rec["error"] = err
    except Exception as e:
        rec["error"] = str(e)[:160]
    return bs.slug_of(doc), pg, rec


def merge_into_markdown(slug, pages):
    """Rewrite {slug}.md inserting OCR text after each --- Page N --- marker."""
    md_path = os.path.join(MD_DIR, f"{slug}.md")
    if not os.path.exists(md_path):
        return False
    content = open(md_path, encoding="utf-8").read()
    def repl(m):
        pg = int(m.group(1))
        txt = (pages.get(pg) or {}).get("text", "").strip()
        if txt == "[blank]":
            txt = ""
        return f"--- Page {pg} ---\n\n{txt}\n" if txt else f"--- Page {pg} ---\n"
    new = re.sub(r"^--- Page (\d+) ---\s*$", repl, content, flags=re.M)
    if new == content:
        return False
    open(md_path, "w", encoding="utf-8").write(new)
    return True


def main():
    workers = int(os.environ.get("OCR_WORKERS", "3"))
    os.makedirs(OCR_DIR, exist_ok=True)
    merged = json.load(open(MERGE_PATH)) if os.path.exists(MERGE_PATH) else {}
    summary = json.load(open(SUMMARY_PATH)) if os.path.exists(SUMMARY_PATH) else {}

    docs = [d for d in bs.INDEX if bs.is_scanned_doc(d)]
    print(f"scanned docs: {len(docs)}", flush=True)

    for d in docs:
        slug = bs.slug_of(d)
        if slug in merged:
            print(f"[skip] {slug} already merged", flush=True)
            continue
        pages = page_images(d)
        exp = d.get("pages") or len(pages)
        todo = []
        for pg, fname in pages:
            rp = page_result_path(slug, pg)
            if os.path.exists(rp):
                rec = json.load(open(rp))
                if rec.get("ok"):
                    continue
            todo.append((pg, fname))
        print(f"[{slug}] pages: {len(pages)} done: {len(pages)-len(todo)} todo: {len(todo)}", flush=True)
        if not todo:
            ok_recs = {pg: json.load(open(page_result_path(slug, pg))) for pg, _ in pages
                       if os.path.exists(page_result_path(slug, pg)) and json.load(open(page_result_path(slug, pg))).get("ok")}
        else:
            ok_recs = {}
            done = 0
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(process_page, d, pg, fname): (pg, fname) for pg, fname in todo}
                for fut in as_completed(futs):
                    s, pg, rec = fut.result()
                    rp = page_result_path(slug, pg)
                    json.dump(rec, open(rp, "w"), ensure_ascii=False, indent=1)
                    if rec.get("ok"):
                        ok_recs[pg] = rec
                    done += 1
                    if done % 10 == 0:
                        print(f"  [{slug}] {done}/{len(todo)} done", flush=True)
                    time.sleep(SLEEP)
        # merge if we have text for every expected page
        if len(ok_recs) >= max(1, exp) or len(ok_recs) >= len(pages):
            if merge_into_markdown(slug, ok_recs):
                merged[slug] = {"pages": len(pages), "merged": time.strftime("%Y-%m-%dT%H:%M:%S")}
                json.dump(merged, open(MERGE_PATH, "w"), ensure_ascii=False, indent=1)
                chars = sum(len(r.get("text", "")) for r in ok_recs.values())
                srcs = {}
                for r in ok_recs.values():
                    srcs[r.get("src", "")] = srcs.get(r.get("src", ""), 0) + 1
                summary[slug] = {"pages": len(pages), "chars": chars, "sources": srcs,
                                 "done": time.strftime("%Y-%m-%dT%H:%M:%S")}
                json.dump(summary, open(SUMMARY_PATH, "w"), ensure_ascii=False, indent=1)
                print(f"[merge] {slug} merged: {len(pages)} pages, {chars} chars, {srcs}", flush=True)
            else:
                print(f"[warn] {slug} merge produced no change", flush=True)
        else:
            print(f"[wait] {slug} only {len(ok_recs)}/{max(exp, len(pages))} pages — will retry on next run", flush=True)

    print("done.", flush=True)


if __name__ == "__main__":
    main()
