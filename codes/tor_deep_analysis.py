#!/usr/bin/env python3
"""
Deep LLM analysis of all FireReport documents.

For each doc in data/index.json, calls the HKBU GenAI gateway (Azure-style OpenAI
compatible) with the doc summary and asks the LLM to extract:
  - key_points   (<=6 bullets, each <=12 words)
  - themes       (<=4 short tags)
  - parties      (<=6 named entities: people/companies/orgs)
  - related_hints(<=4 phrases to help link related documents)
  - tor_tags     (refined ToR classification from the fixed tag set)

Writes data/analysis.json (checkpointed: already-analysed docs are skipped).
Usage: python3 tor_deep_analysis.py [--limit N] [--model gpt-4.1-mini]
"""
import argparse, json, os, re, sys, time
import requests

CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
BASE = "https://genai.hkbu.edu.hk/general/rest/deployments"
API_VERSION = "2024-02-01"
TOR_TAGS = [
    "ToR1: Causes & Circumstances of Fire",
    "ToR2: Fire Service Installations & Equipment",
    "ToR3: Building Maintenance & Renovation Works",
    "ToR4: Supervision, Roles & Responsibilities",
    "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)",
    "ToR6: Adequacy of Laws & Penalties",
    "ToR7: Recommendations & Improvement Measures",
    "General / Other",
]

SYSTEM_PROMPT = (
    "You are an investigative research assistant for journalists covering the Hong Kong "
    "Independent Committee on the Fire at Wang Fuk Court. You analyse inquiry documents. "
    "Reply ONLY with a compact JSON object of the form:\n"
    '{"key_points":["...", ...], "themes":["..."], "parties":["..."], '
    '"related_hints":["..."], "tor_tags":["..."]}\n'
    "- key_points: up to 6 bullet-style phrases, each <= 12 words, capturing the most "
    "important facts/claims in the document.\n"
    "- themes: up to 4 short topic tags (e.g. 'fire spread', 'sprinkler failure', "
    "'tender collusion', 'supervision gap').\n"
    "- parties: up to 6 named entities (persons, companies, organisations) mentioned.\n"
    "- related_hints: up to 4 phrases (titles or keywords) that this document is likely "
    "related to, to help connect documents.\n"
    f"- tor_tags: a subset of exactly these allowed values: {TOR_TAGS}. Choose ALL that apply.\n"
    "Do not add any text outside the JSON object."
)


def load_api_key():
    with open(CREDS) as f:
        content = f.read()
    m = re.search(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)", content, re.I)
    if not m:
        sys.exit("HKBU Gen AI key not found in " + CREDS)
    return m.group(1)


def call_llm(api_key, model, title, summary):
    user = (
        "Document title: " + title + "\n\n"
        "Document summary:\n" + summary[:2500]
    )
    body = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 500,
    }
    resp = requests.post(
        f"{BASE}/{model}/chat/completions?api-version={API_VERSION}",
        json=body,
        headers={"api-key": api_key},
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    # strip markdown fences if any
    content = re.sub(r"^```(json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content)
    parsed = json.loads(content)
    # validate tor_tags
    parsed["tor_tags"] = [t for t in parsed.get("tor_tags", []) if t in TOR_TAGS] or ["General / Other"]
    return parsed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--out", default="data/analysis.json")
    args = ap.parse_args()

    index = json.load(open("data/index.json"))
    docs = index["docs"]

    out_path = args.out
    analysis = {}
    if os.path.exists(out_path):
        analysis = json.load(open(out_path))
        print(f"Resuming: {len(analysis)} docs already analysed")

    api_key = load_api_key()
    todo = [d for d in docs if d["title"] not in analysis]
    if args.limit:
        todo = todo[: args.limit]
    print(f"To analyse: {len(todo)} docs (model={args.model})")

    t0 = time.time()
    ok = fail = 0
    for i, d in enumerate(todo, 1):
        title = d["title"]
        for attempt in range(3):
            try:
                parsed = call_llm(api_key, args.model, title, d.get("summary", ""))
                analysis[title] = {
                    "url": d.get("url"),
                    "pages": d.get("pages"),
                    "key_points": parsed["key_points"],
                    "themes": parsed["themes"],
                    "parties": parsed["parties"],
                    "related_hints": parsed["related_hints"],
                    "tor_tags": parsed["tor_tags"],
                }
                ok += 1
                break
            except Exception as e:
                if attempt == 2:
                    fail += 1
                    print(f"[{i}] FAIL {title[:60]}: {type(e).__name__}: {str(e)[:120]}")
                else:
                    time.sleep(3 * (attempt + 1))
        if i % 10 == 0:
            json.dump(analysis, open(out_path, "w"), ensure_ascii=False, indent=1)
            print(f"[{i}/{len(todo)}] ok={ok} fail={fail} elapsed={time.time()-t0:.0f}s")

    json.dump(analysis, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"Done. ok={ok} fail={fail} total_analysed={len(analysis)} elapsed={time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
