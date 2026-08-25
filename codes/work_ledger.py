#!/usr/bin/env python3
"""Work ledger: estimate the person-hours behind each document and roll them up
per Terms of Reference.

Model (transparent, deterministic):
  work_hours(doc) = base_hours(doc_type) + pages * PAGE_REVIEW_HOURS
  base_hours reflects the characteristic effort of each type of work:
  interviewing + drafting a witness statement, running + preparing a hearing,
  expert analysis, legal submissions, routine notices, etc.
  pages * PAGE_REVIEW_HOURS covers reading/checking each page.

Per-ToR attribution: a document tagged with N ToRs splits its hours equally
among them (proportional view, sums to the grand total). The full-attribution
view (each tagged ToR receives the document's full hours) is also recorded.

No LLM calls. Reads: index.json, analysis.json, doc_meta.json.
Writes: data/work_ledger.json
"""
import json, os, re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

TYPE_BASE_HOURS = {
    "witness_statement": 12.0,     # interview + drafting + checking a statement
    "hearing_transcript": 8.0,     # one session of oral evidence + its preparation
    "expert_report": 60.0,         # expert analysis + drafting + review
    "investigation_report": 120.0, # inter-departmental investigation effort
    "opening_address": 24.0,       # counsel preparation
    "closing_address": 40.0,       # closing submissions (one ran to 627 pages)
    "submission": 10.0,            # legal submission / representation
    "letter": 4.0,                 # correspondence and reply
    "notice": 1.5,                 # routine notice
    "press_release": 2.0,
    "procedural": 2.0,             # lists, rules, directions
    "recommendation": 16.0,        # recommendations document
    "minutes": 3.0,                # minutes of a meeting
    "other": 4.0,
}
PAGE_REVIEW_HOURS = 0.12           # ≈ 50 minutes per 7 pages of review/checking

# title-based fallback for docs whose doc_meta is not yet classified
TITLE_HINT = [
    ("Witness Statement", "witness_statement"),
    ("Transcript", "hearing_transcript"),
    ("Expert Report", "expert_report"),
    ("Investigation Report", "investigation_report"),
    ("Closing Address", "closing_address"),
    ("Opening Address", "opening_address"),
    ("Recommendation", "recommendation"),
    ("Submission", "submission"),
    ("Reply", "letter"),
    ("Notice", "notice"),
    ("Press Release", "press_release"),
    ("Minutes", "minutes"),
]


def doc_type_of(title, meta):
    t = (meta.get("doc_type") or "").strip()
    if t in TYPE_BASE_HOURS:
        return t
    for frag, typ in TITLE_HINT:
        if frag.lower() in title.lower():
            return typ
    return "other"


def main():
    idx = json.load(open(os.path.join(DATA, "index.json")))["docs"]
    ana = json.load(open(os.path.join(DATA, "analysis.json")))
    try:
        meta = json.load(open(os.path.join(DATA, "doc_meta.json")))
    except Exception:
        meta = {}

    docs = {}
    tot = defaultdict(float)   # by type: hours
    by_type = defaultdict(lambda: {"count": 0, "pages": 0, "hours": 0.0})
    tor_split = defaultdict(float)
    tor_full = defaultdict(float)
    tor_count = defaultdict(int)
    tor_pages = defaultdict(int)

    for d in idx:
        title = d["title"]
        pages = d.get("pages") or 0
        typ = doc_type_of(title, meta.get(title, {}))
        base = TYPE_BASE_HOURS.get(typ, 4.0)
        hours = round(base + pages * PAGE_REVIEW_HOURS, 1)
        tags = ana.get(title, {}).get("tor_tags") or d.get("related_to_tor") or ["General / Other"]
        # full-text paragraph-level tags (data/tor_full_tags.json) override summary tags
        try:
            ftags = json.load(open(os.path.join(DATA, "tor_full_tags.json"))).get(title, {}).get("tor_tags")
            if ftags:
                tags = ftags
        except Exception:
            pass
        tags = [t for t in tags if t]
        docs[title] = {
            "type": typ, "pages": pages, "base_hours": base,
            "page_hours": round(pages * PAGE_REVIEW_HOURS, 1),
            "hours": hours, "tor_tags": tags,
        }
        by_type[typ]["count"] += 1
        by_type[typ]["pages"] += pages
        by_type[typ]["hours"] += hours
        n = max(1, len(tags))
        for t in tags:
            tor_split[t] += hours / n
            tor_full[t] += hours
            tor_count[t] += 1
            tor_pages[t] += pages

    total_hours = sum(v["hours"] for v in docs.values())

    out = {
        "model": {
            "type_base_hours": TYPE_BASE_HOURS,
            "page_review_hours_per_page": PAGE_REVIEW_HOURS,
            "note": ("work_hours = base_hours(type) + pages * page_review_hours; "
                     "ToR attribution splits a multi-tagged document equally among its tags"),
        },
        "total_hours": round(total_hours, 1),
        "total_person_days": round(total_hours / 8, 1),
        "total_docs": len(docs),
        "by_type": {k: {**v, "hours": round(v["hours"], 1)} for k, v in sorted(by_type.items(), key=lambda x: -x[1]["hours"])},
        "by_tor": {k: {"docs": tor_count[k], "pages": tor_pages[k],
                       "hours_split": round(tor_split[k], 1), "hours_full": round(tor_full[k], 1)}
                   for k in sorted(tor_split, key=lambda x: -tor_split[x])},
        "top_docs": sorted(docs.items(), key=lambda x: -x[1]["hours"])[:20],
        "docs": docs,
    }
    with open(os.path.join(DATA, "work_ledger.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print(f"docs: {len(docs)}  total hours: {round(total_hours,1):,}  person-days: {round(total_hours/8,1):,}")
    print("by type (hours):", {k: round(v['hours']) for k, v in sorted(by_type.items(), key=lambda x: -x[1]['hours'])})
    print("by ToR (hours_split):", {k: round(v) for k, v in sorted(tor_split.items(), key=lambda x: -x[1])})
    print("saved -> data/work_ledger.json")


if __name__ == "__main__":
    main()
