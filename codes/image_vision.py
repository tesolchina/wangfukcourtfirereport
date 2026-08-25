#!/usr/bin/env python3
"""Vision pass over triaged images (data/image_inventory.json).

For every image that survived the heuristic triage (not junk_tiny/blank/low_value
and the first member of each duplicate group), call the HKBU GenAI vision model
(gpt-4.1-mini) to produce:
  - subject:       one-line factual description
  - type:          photo | diagram | document_page | logo | other
  - contains_photo:bool (page scans that contain a real photograph)
  - importance:    1-5
  - keep:          bool (worth showing in the doc gallery)
  - note:          why dropped, if keep=false

Results are written to data/image_descriptions.json keyed by filename, with
checkpoints every 25 images so the job can be resumed.

Usage: nohup python3 codes/image_vision.py > data/image_vision.log 2>&1 &
"""
import os, sys, json, base64, io, time, re
import urllib.request, urllib.error, ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl._create_unverified_context()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
IMG_DIR = os.path.join(DATA, "images")
INV_PATH = os.path.join(DATA, "image_inventory.json")
OUT_PATH = os.path.join(DATA, "image_descriptions.json")

ENDPOINT = ("https://genai.hkbu.edu.hk/general/rest/deployments/gpt-4.1-mini/"
            "chat/completions?api-version=2024-02-01")
API_KEY = "REPLACE_WITH_HKBU_GENAI_KEY"

MAX_EDGE = 1024      # downscale long edge before sending
JPEG_Q = 80
SLEEP = 0.35
MAX_RETRY = 4

PROMPT = """You are an expert analyst curating a public archive about the Wang Fuk Court fire inquiry (Hong Kong, Nov 2025). A machine extracted this image from an official inquiry PDF. Decide whether it adds value to a public gallery for journalists.

Reply with ONLY a JSON object, no markdown, exactly this shape:
{
  "subject": "one factual sentence describing what the image actually shows",
  "type": "photo|diagram|document_page|logo|other",
  "contains_photo": true or false,
  "importance": 1-5,
  "keep": true or false,
  "note": "short reason if keep is false, else empty string"
}

Rules:
- type=photo: a real photograph (fire scene, building, people, damaged equipment, evidence, documents as photos).
- type=diagram: chart, map, floor plan, schematic, table/figure, technical drawing.
- type=document_page: a full page of text/forms (scanned letter, form, transcript). Contains no photograph worth showing separately.
- type=logo: official seal, crest, letterhead logo, watermark.
- contains_photo=true only if a real photograph is visible in the image.
- importance: 5 = key evidence (fire scene, damaged fire-service equipment, cause evidence); 4 = important supporting evidence; 3 = useful context; 2 = minor; 1 = trivial.
- keep=false for: pure text pages (document_page without photo), logos/seals, decorative fragments, duplicates of trivial content.
- keep=true for: photos (scene/people/evidence/damage), meaningful diagrams/charts/maps/plans, and document pages that contain a real photo."""


def load_inv():
    with open(INV_PATH) as f:
        inv = json.load(f)
    summary = inv["summary"]
    images = inv["images"]
    keep_names = set(summary["keep"])          # unique (first of each dup group)
    cands = []
    for name, st in images.items():
        if name not in keep_names:
            continue
        if st["label"] in ("junk_tiny", "blank", "low_value", "unreadable"):
            continue
        cands.append(name)
    cands.sort()
    return cands, images


def load_existing():
    if os.path.exists(OUT_PATH):
        with open(OUT_PATH) as f:
            return json.load(f)
    return {}


def downscale(path):
    """Return (mime, base64) with the image downscaled to MAX_EDGE."""
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


def call_vision(b64):
    payload = {
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ]}],
        "max_tokens": 300,
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "api-key": API_KEY}, method="POST")
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        resp = json.loads(r.read().decode())
    return resp["choices"][0]["message"]["content"]


def parse_json(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def call_vision_with_retry(b64, retries=4):
    last = None
    for attempt in range(retries):
        try:
            return call_vision(b64)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 + attempt * 3)
                continue
            raise
        except Exception as e:
            last = str(e)[:100]
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"retries exhausted: {last}")


def process_one(name, images):
    """Describe one image; returns (name, rec)."""
    path = os.path.join(IMG_DIR, name)
    rec = {"file": name, "ok": False, "label": images[name]["label"],
           "reason": images[name]["reason"], "size": images[name]["size"],
           "w": images[name]["w"], "h": images[name]["h"]}
    if not os.path.exists(path):
        return name, rec
    try:
        mime, b64 = downscale(path)
        text = call_vision_with_retry(b64)
        parsed = parse_json(text)
        if not parsed:
            rec["error"] = "unparseable: " + text[:120]
        else:
            rec.update(parsed)
            rec["ok"] = True
    except Exception as e:
        rec["error"] = str(e)[:160]
    return name, rec


def main():
    workers = int(os.environ.get("IMAGE_VISION_WORKERS", "1"))
    cands, images = load_inv()
    existing = load_existing()
    todo = [c for c in cands if c not in existing or not existing[c].get("ok")]
    print(f"candidates: {len(cands)}, already done: {len(cands) - len(todo)}, to do: {len(todo)}, workers: {workers}", flush=True)

    ok = fail = 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_one, c, images): c for c in todo}
        for fut in as_completed(futs):
            name, rec = fut.result()
            existing[name] = rec
            if rec.get("ok"):
                ok += 1
            else:
                fail += 1
            done += 1
            if done % 50 == 0:
                with open(OUT_PATH, "w") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=1)
                print(f"  {done}/{len(todo)} ok={ok} fail={fail}", flush=True)

    with open(OUT_PATH, "w") as f:
        json.dump(existing, f, ensure_ascii=False, indent=1)
    print(f"done. ok={ok} fail={fail} total_described={len(existing)}", flush=True)


if __name__ == "__main__":
    main()
