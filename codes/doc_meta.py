#!/usr/bin/env python3
"""Re-analysis pass: enrich every document with structured metadata.

For each of the 243 documents, one call to the HKBU GenAI gateway (gpt-4.1-mini)
classifies:
  doc_type          - witness_statement | hearing_transcript | expert_report |
                      investigation_report | opening_address | closing_address |
                      submission | letter | notice | press_release | procedural |
                      recommendation | minutes | other
  doc_type_detail   - one-line clarification
  language          - zh | en | bilingual (LLM judgment; heuristics refine it later)
  tor_themes        - how each relevant ToR theme appears in THIS document:
                      [{tor, theme, evidence}] (1-4 entries)
  related_fragments - short distinctive fragments of other docs' titles this doc
                      relates to, with the nature of the relation
  news_terms        - keywords/phrases that connect this doc to news coverage

Inputs per doc: title, summary (trimmed), key_points, themes, parties, tor_tags, toc.
Output: data/doc_meta.json keyed by title. Checkpointed + resume-safe; parallel workers.

Usage: IMAGE_VISION_WORKERS=5 nohup python3 codes/doc_meta.py > data/doc_meta.log 2>&1 &
"""
import os, sys, json, re, time
import urllib.request, urllib.error, ssl
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl._create_unverified_context()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT_PATH = os.path.join(DATA, "doc_meta.json")

ENDPOINT = ("https://genai.hkbu.edu.hk/general/rest/deployments/gpt-4.1-mini/"
            "chat/completions?api-version=2024-02-01")
API_KEY = "REPLACE_WITH_HKBU_GENAI_KEY"

SYSTEM = """You are a meticulous archivist for a public archive of the Independent Committee on the Wang Fuk Court fire (Hong Kong, 2025). You classify official inquiry documents with precise, factual metadata. Reply with ONLY a JSON object, no markdown.

JSON shape:
{
  "doc_type": "one of: witness_statement, hearing_transcript, expert_report, investigation_report, opening_address, closing_address, submission, letter, notice, press_release, procedural, recommendation, minutes, other",
  "doc_type_detail": "one short clause clarifying the type",
  "language": "zh | en | bilingual",
  "tor_themes": [
    {"tor": "ToR1..ToR7 or General", "theme": "short theme label", "evidence": "how this theme appears in THIS document, with specifics"}
  ],
  "related_fragments": [
    {"title": "short distinctive fragment of another document's title", "relation": "same witness | same party | supplements/updates | referred to | same theme | procedural pair | other"}
  ],
  "news_terms": ["keywords or short phrases that would connect this document to news coverage of the fire"]
}

Rules:
- doc_type must be one of the listed values.
- tor_themes: 1-4 entries, only for ToRs genuinely addressed in this document; evidence must be specific to this document (names, dates, systems, materials), not generic.
- related_fragments: 0-5 entries. Use SHORT distinctive fragments of official titles as they would appear in the Committee's document list (e.g. "Closing Address", "Victory Fire", "IFITF", "Usmani"). Never invent titles.
- news_terms: 1-5 entries, concrete (e.g. "fire alarms", "foam boards", "smoking workers", "tender collusion")."""


def load_docs():
    idx = json.load(open(os.path.join(DATA, "index.json")))["docs"]
    ana = json.load(open(os.path.join(DATA, "analysis.json")))
    out = []
    for d in idx:
        a = ana.get(d["title"], {})
        out.append({
            "title": d["title"],
            "summary": (d.get("summary") or "")[:800],
            "toc": (d.get("toc") or [])[:8],
            "key_points": (a.get("key_points") or [])[:3],
            "themes": (a.get("themes") or [])[:5],
            "parties": (a.get("parties") or [])[:5],
            "tor_tags": a.get("tor_tags") or d.get("related_to_tor") or [],
        })
    return out


def load_existing():
    if os.path.exists(OUT_PATH):
        return json.load(open(OUT_PATH))
    return {}


def build_prompt(doc):
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(doc, ensure_ascii=False)},
        ],
        "max_tokens": 600,
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


def process_one(doc):
    title = doc["title"]
    rec = {"title": title, "ok": False}
    for attempt in range(6):
        try:
            text = build_prompt(doc)
            parsed = parse_json(text)
            if not parsed:
                rec["error"] = "unparseable: " + text[:150]
                break
            rec.update(parsed)
            rec["ok"] = True
            break
        except urllib.error.HTTPError as e:
            rec["error"] = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(4 + attempt * 5)   # 4,9,14,19,24s backoff
                continue
            break
        except Exception as e:
            rec["error"] = str(e)[:150]
            time.sleep(2 + attempt * 2)
    return title, rec


def main():
    workers = int(os.environ.get("DOC_META_WORKERS", "5"))
    docs = load_docs()
    existing = load_existing()
    todo = [d for d in docs if d["title"] not in existing or not existing[d["title"]].get("ok")]
    print(f"docs: {len(docs)}, already done: {len(docs) - len(todo)}, to do: {len(todo)}, workers: {workers}", flush=True)

    ok = fail = done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_one, d): d for d in todo}
        for fut in as_completed(futs):
            title, rec = fut.result()
            existing[title] = rec
            if rec.get("ok"):
                ok += 1
            else:
                fail += 1
            done += 1
            if done % 25 == 0:
                with open(OUT_PATH, "w") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=1)
                print(f"  {done}/{len(todo)} ok={ok} fail={fail}", flush=True)

    with open(OUT_PATH, "w") as f:
        json.dump(existing, f, ensure_ascii=False, indent=1)
    print(f"done. ok={ok} fail={fail} total={len(existing)}", flush=True)


if __name__ == "__main__":
    main()
