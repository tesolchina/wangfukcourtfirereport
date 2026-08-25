#!/usr/bin/env python3
"""Regenerate cross-language summaries (data/cross_lang.json) using OFFICIAL
Chinese names/terms from the government committee site.

Improvements over gen_cross_lang.py:
  - injects data/official_zh_names.json (terms/people/companies) into the prompt
  - instructs: use ONLY the listed official Chinese names; keep any other name
    in English (never transliterate); use official terminology
  - parallel workers + checkpointing + retries (run one job at a time, <=4 workers)

Usage: nohup python3 codes/gen_cross_lang_v2.py > data/cross_lang_v2.log 2>&1 &
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
OUT_PATH = os.path.join(DATA, "cross_lang.json")
ENDPOINT = ("https://genai.hkbu.edu.hk/general/rest/deployments/gpt-4.1-mini/"
            "chat/completions?api-version=2024-02-01")
API_KEY = "REPLACE_WITH_HKBU_GENAI_KEY"

OFFICIAL = json.load(open(os.path.join(DATA, "official_zh_names.json")))


def fmt_map(d):
    return "\n".join(f"  - {en} = {zh}" for en, zh in d.items())


REFERENCE = (
    "Official Chinese names/terms to use (from the government committee website):\n"
    "KEY TERMS:\n" + fmt_map(OFFICIAL["terms"]) + "\n"
    "PEOPLE (official Chinese names):\n" + fmt_map(OFFICIAL["people"]) + "\n"
    "COMPANIES / ORGANISATIONS:\n" + fmt_map(OFFICIAL["companies"]) + "\n"
)

SYS_ZH = (
    "You are a bilingual research assistant for a public archive of the Wang Fuk Court fire "
    "inquiry. Write a concise Traditional Chinese (繁體中文) summary, 2-4 sentences (~60-90 "
    "Chinese characters), of the inquiry document described below, aimed at Hong Kong "
    "journalists and the public. Capture the document type, who it is from, and the key "
    "facts/claims.\n\n"
    "STRICT RULES:\n"
    + REFERENCE +
    "\n- Use ONLY the official Chinese names listed above. If a name (person, company, "
    "department) is NOT in the list, keep it in English — never invent a Chinese "
    "transliteration.\n"
    "- The estate is 大埔宏福苑 (never 旺角 or any other place name); the committee is "
    "就大埔宏福苑火災成立的獨立委員會.\n"
    "- Use official document terms: 證人供詞 (not 陳述書), 總結陳詞, 開場陳詞, 聽證會, "
    "專家報告, 簡報投影片, 改善建議.\n"
    "- Reply with ONLY the summary text."
)

SYS_EN = (
    "You are a bilingual research assistant for a public archive of the Wang Fuk Court fire "
    "inquiry. Write a concise English summary (2-4 sentences) of the Chinese-language inquiry "
    "document described below, aimed at international journalists. Capture the document type, "
    "who it is from, and the key facts/claims.\n"
    "The estate is Wang Fuk Court in Tai Po (大埔宏福苑); the committee is the Independent "
    "Committee in relation to the fire at Wang Fuk Court in Tai Po.\n"
    "Reply with ONLY the summary text."
)


def call(text, title, summary):
    payload = {
        "messages": [
            {"role": "system", "content": text},
            {"role": "user", "content": f"Title: {title}\n\nSummary:\n{summary[:1800]}"},
        ],
        "temperature": 0.3,
        "max_tokens": 260,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "api-key": API_KEY}, method="POST")
    with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
        resp = json.loads(r.read().decode())
    return resp["choices"][0]["message"]["content"].strip()


def process_one(doc, direction_name):
    title = doc["title"]
    sysp = SYS_ZH if direction_name == "zh" else SYS_EN
    field = "summary_zh" if direction_name == "zh" else "summary_en"
    rec = {"direction": direction_name, field: None, "url": doc.get("url")}
    for attempt in range(5):
        try:
            text = call(sysp, title, doc.get("summary", ""))
            if text and not text.startswith("["):
                rec[field] = text
                return title, rec, True
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(4 + attempt * 5)
                continue
        except Exception:
            time.sleep(2 + attempt * 3)
    return title, rec, False


def main():
    workers = int(os.environ.get("GEN_CL_WORKERS", "4"))
    docs = json.load(open(os.path.join(DATA, "index.json")))["docs"]
    existing = {}
    if os.path.exists(OUT_PATH):
        existing = json.load(open(OUT_PATH))

    def direction(d):
        t = d["title"].lower()
        if "(chinese only)" in t:
            return "en"
        return "zh"

    todo = docs  # regenerate ALL (overwrite) for consistency
    print(f"docs: {len(todo)} workers: {workers} (full regeneration)", flush=True)

    ok = fail = done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_one, d, direction(d)): d for d in todo}
        for fut in as_completed(futs):
            title, rec, ok_ = fut.result()
            existing[title] = rec
            if ok_:
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
