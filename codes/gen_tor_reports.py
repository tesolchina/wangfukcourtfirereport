#!/usr/bin/env python3
"""
Generate per-ToR editorial reports (plan: tor/ToR*.html as full multi-section reports).

For each ToR, sends the tagged documents (title + themes + key points from
data/analysis.json) to the HKBU GenAI gateway, which:
  1. proposes 3-5 themes that together answer the ToR question,
  2. writes a 2-paragraph narrative per theme synthesising the documents,
  3. cites documents by exact title.

Writes data/tor_reports.json (checkpointed per ToR).

Usage: python3 codes/gen_tor_reports.py [--tor ToR1] [--all]
"""
import argparse, json, os, re, sys, time
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
BASE = "https://genai.hkbu.edu.hk/general/rest/deployments"
API_VERSION = "2024-02-01"

TOR_KEYS = ["ToR1", "ToR2", "ToR3", "ToR4", "ToR5", "ToR6", "ToR7", "General"]

SYSTEM = (
    "You are an editorial research assistant for journalists covering the Hong Kong Independent "
    "Committee on the Wang Fuk Court fire. You produce structured research reports from inquiry "
    "documents. Reply with ONLY valid JSON, no markdown fences."
)


def api_key():
    with open(CREDS) as f:
        m = re.search(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)", f.read(), re.I)
    if not m:
        sys.exit("HKBU Gen AI key not found")
    return m.group(1)


def build_prompt(tag, docs):
    lines = []
    for i, d in enumerate(docs, 1):
        a = d["a"]
        themes = ", ".join((a.get("themes") or [])[:3])
        kps = "; ".join((a.get("key_points") or [])[:2])
        lines.append(f"{i}. {d['title']} | themes: {themes} | key points: {kps}")
    doclist = "\n".join(lines)
    return f"""INQUIRY ToR: {tag}

Below are the inquiry documents relevant to this ToR, with LLM-extracted themes and key points.

{doclist}

TASK — produce a research report answering this ToR question, as JSON:
{{
  "overview": "1-2 sentence overview of what the documents show about this ToR question",
  "sections": [
    {{
      "theme": "short theme title (e.g. 'How the fire started and spread')",
      "narrative": "TWO paragraphs (~60-80 words each) synthesising what the relevant documents show about this theme. Attribute claims to documents with bracketed numbers referring to the numbered list above, e.g. [1][4].",
      "doc_titles": ["exact titles from the list above that support this section"]
    }}
  ]
}}

RULES:
- Identify 3 to 5 distinct themes that together answer the ToR question.
- Every entry in "doc_titles" MUST be an exact title from the numbered list above.
- A document may appear in multiple sections.
- Base everything strictly on the provided document information; do not invent facts, numbers or names.
- Output ONLY the JSON object."""


def gen_report(tag, docs, model="gpt-4.1-mini"):
    prompt = build_prompt(tag, docs)
    resp = requests.post(
        f"{BASE}/{model}/chat/completions?api-version={API_VERSION}",
        json={"messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": prompt}],
              "temperature": 0.3, "max_tokens": 4000},
        headers={"api-key": api_key()},
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(json)?\s*", "", content.strip())
    content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tor", choices=TOR_KEYS, default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="gpt-4.1-mini")
    args = ap.parse_args()

    idx = json.load(open(os.path.join(ROOT, "data", "index.json")))["docs"]
    ana = json.load(open(os.path.join(ROOT, "data", "analysis.json")))
    tag_of = {("ToR" + t.split(":")[0].replace("ToR", "")): t for _, t, _ in []}
    # build ToR key -> tag map from analysis tor_tags values
    tag_by_key = {
        "ToR1": "ToR1: Causes & Circumstances of Fire",
        "ToR2": "ToR2: Fire Service Installations & Equipment",
        "ToR3": "ToR3: Building Maintenance & Renovation Works",
        "ToR4": "ToR4: Supervision, Roles & Responsibilities",
        "ToR5": "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)",
        "ToR6": "ToR6: Adequacy of Laws & Penalties",
        "ToR7": "ToR7: Recommendations & Improvement Measures",
        "General": "General / Other",
    }

    out_path = os.path.join(ROOT, "data", "tor_reports.json")
    reports = {}
    if os.path.exists(out_path):
        reports = json.load(open(out_path))
        print(f"Resuming: {len(reports)} reports already generated")

    keys = [args.tor] if args.tor else TOR_KEYS
    for key in keys:
        if key in reports and not args.all:
            print(f"skip {key} (exists)")
            continue
        tag = tag_by_key[key]
        docs = []
        for d in idx:
            a = ana.get(d["title"], {})
            try:
                ftags = json.load(open("data/tor_full_tags.json")).get(d["title"], {}).get("tor_tags") or []
            except Exception:
                ftags = []
            tags = ftags or a.get("tor_tags") or d.get("related_to_tor") or []
            if tag in tags:
                docs.append({"title": d["title"], "url": d.get("url"), "a": a})
        docs.sort(key=lambda x: x["title"].lower())
        print(f"[{key}] generating report over {len(docs)} docs ...")
        for attempt in range(3):
            try:
                report = gen_report(tag, docs, args.model)
                report["_docs"] = len(docs)
                reports[key] = report
                json.dump(reports, open(out_path, "w"), ensure_ascii=False, indent=1)
                print(f"  -> {len(report.get('sections', []))} sections")
                break
            except Exception as e:
                print(f"  attempt {attempt}: {type(e).__name__}: {str(e)[:120]}")
                time.sleep(4)
        time.sleep(1)
    print(f"Saved {len(reports)} reports -> {out_path}")


if __name__ == "__main__":
    main()
