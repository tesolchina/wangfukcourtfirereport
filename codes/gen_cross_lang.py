#!/usr/bin/env python3
"""
Generate cross-language summaries for all inquiry documents (request L45).

For each doc in data/index.json:
  - if the doc is English-only / bilingual / unmarked -> produce a concise
    Traditional Chinese summary (summary_zh)
  - if the doc is Chinese-only -> produce a concise English summary (summary_en)

Writes data/cross_lang.json (checkpointed). Run in background:
  nohup python3 codes/gen_cross_lang.py > data/cross_lang_run.log 2>&1 &
"""
import argparse, json, os, re, sys, time
import requests

CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
BASE = "https://genai.hkbu.edu.hk/general/rest/deployments"
API_VERSION = "2024-02-01"

SYS_ZH = (
    "You are a bilingual research assistant. Write a concise Traditional Chinese summary "
    "(繁體中文, 2-4 sentences, ~60-90 Chinese characters) of the inquiry document described "
    "below, aimed at Hong Kong journalists and the public. Capture the document type, who it is "
    "from, and the key facts/claims. Reply with ONLY the summary text."
)
SYS_EN = (
    "You are a bilingual research assistant. Write a concise English summary (2-4 sentences) of "
    "the Chinese-language inquiry document described below, aimed at international journalists. "
    "Capture the document type, who it is from, and the key facts/claims. Reply with ONLY the "
    "summary text."
)


def api_key():
    with open(CREDS) as f:
        m = re.search(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)", f.read(), re.I)
    if not m:
        sys.exit("HKBU Gen AI key not found")
    return m.group(1)


def call(model, sysp, title, summary):
    resp = requests.post(
        f"{BASE}/{model}/chat/completions?api-version={API_VERSION}",
        json={
            "messages": [
                {"role": "system", "content": sysp},
                {"role": "user", "content": f"Title: {title}\n\nSummary:\n{summary[:1800]}"},
            ],
            "temperature": 0.3,
            "max_tokens": 220,
        },
        headers={"api-key": api_key()},
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--out", default="data/cross_lang.json")
    args = ap.parse_args()

    docs = json.load(open("data/index.json"))["docs"]
    out_path = args.out
    out = {}
    if os.path.exists(out_path):
        out = json.load(open(out_path))
        print(f"Resuming: {len(out)} docs done")

    def direction(d):
        t = d["title"].lower()
        if "(chinese only)" in t:
            return "en"
        if "(english only)" in t or "(english and chinese)" in t:
            return "zh"
        return "zh"  # unmarked -> treat as English, provide zh

    todo = [d for d in docs if d["title"] not in out]
    if args.limit:
        todo = todo[: args.limit]
    print(f"To process: {len(todo)} docs (model={args.model})")

    t0 = time.time()
    ok = fail = 0
    for i, d in enumerate(todo, 1):
        title = d["title"]
        direction_name = direction(d)
        sysp = SYS_ZH if direction_name == "zh" else SYS_EN
        field = "summary_zh" if direction_name == "zh" else "summary_en"
        for attempt in range(3):
            try:
                text = call(args.model, sysp, title, d.get("summary", ""))
                out[title] = {"direction": direction_name, field: text, "url": d.get("url")}
                ok += 1
                break
            except Exception as e:
                if attempt == 2:
                    fail += 1
                    print(f"[{i}] FAIL {title[:50]}: {type(e).__name__}: {str(e)[:100]}")
                else:
                    time.sleep(3 * (attempt + 1))
        if i % 10 == 0:
            json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
            print(f"[{i}/{len(todo)}] ok={ok} fail={fail} elapsed={time.time()-t0:.0f}s")

    json.dump(out, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"Done. ok={ok} fail={fail} total={len(out)} elapsed={time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
