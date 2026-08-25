#!/usr/bin/env python3
"""TOR_AGGREGATE — collapse paragraph-level ToR tags (data/tor_full.json) into
document-level tags and write them where the site builders read them.

Strategy (user 2026-08-16): existing tor_tags came from summary-level reading and
under-tag; full-text paragraph-level scan (codes/tor_full_scan.py) is authoritative.
We do NOT overwrite data/analysis.json (it is the original record); instead we
write:

  data/tor_full_tags.json   {title: {"tor_tags": [full tag strings...],
                                      "tor_chunk_counts": {...},
                                      "n_chunks": int}}

and the builders (build_site.py, tc_site.py, search_build.py, work_ledger.py)
are updated to prefer tor_full_tags.json when present, falling back to
analysis.json tor_tags.

Also prints a before/after comparison so we can see how many docs each ToR
gained, and which docs moved.
"""
import json, os, re, sys
from collections import Counter

DATA = "data"
TOR_ALL = [
    "ToR1: Causes & Circumstances of Fire",
    "ToR2: Fire Service Installations & Equipment",
    "ToR3: Building Maintenance & Renovation Works",
    "ToR4: Supervision, Roles & Responsibilities",
    "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)",
    "ToR6: Adequacy of Laws & Penalties",
    "ToR7: Recommendations & Improvement Measures",
    "General / Other",
]


def main():
    full = json.load(open(os.path.join(DATA, "tor_full.json")))
    ana = json.load(open(os.path.join(DATA, "analysis.json")))

    out = {}
    stats = {}
    n_fallback = 0
    for title, rec in full.items():
        tags = rec.get("doc_tor_tags") or []
        # normalize: keep full strings that are in TOR_ALL
        tags = [t for t in tags if t in TOR_ALL]
        # Small/low-text docs (scanned PDFs, short letters) often yield empty
        # full-text tags even though they are substantive. Fall back to the
        # summary-level analysis tags for those, flagged as secondary, so we
        # never lose information (e.g. ToR5 evidence in short contractor replies).
        fallback_from_ana = False
        if not tags:
            ana_tags = [t for t in (ana.get(title, {}).get("tor_tags") or []) if t in TOR_ALL]
            if ana_tags:
                tags = ana_tags
                fallback_from_ana = True
                n_fallback += 1
        out[title] = {
            "tor_tags": tags,
            "tor_chunk_counts": rec.get("tor_chunk_counts") or {},
            "n_chunks": len(rec.get("chunks") or []),
            "ok": rec.get("ok", False),
            "fallback_from_analysis": fallback_from_ana,
        }
        stats[title] = set(tags)

    with open(os.path.join(DATA, "tor_full_tags.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # comparison with analysis.json tags
    print("=== ToR doc counts: full-text vs summary (analysis.json) ===")
    old_c = Counter()
    new_c = Counter()
    gained = {t: [] for t in TOR_ALL}
    lost = {t: [] for t in TOR_ALL}
    for title in ana:
        old = set(ana[title].get("tor_tags") or [])
        new = stats.get(title, set())
        for t in TOR_ALL:
            if t in old:
                old_c[t] += 1
            if t in new:
                new_c[t] += 1
            if t in new and t not in old:
                gained[t].append(title)
            if t in old and t not in new:
                lost[t].append(title)
    for t in TOR_ALL:
        print(f"  {t}: {old_c.get(t,0)} -> {new_c.get(t,0)}  "
              f"(+{len(gained[t])} gained, -{len(lost[t])} lost)")
    print(f"\nscanned docs: {len(full)} (ok={sum(1 for r in full.values() if r.get('ok'))}) "
          f"| fallback-to-analysis tags for {n_fallback} low-text docs")

    # print some gained examples for ToR5 (the letter's key claim)
    print("\n=== docs GAINED by ToR5 (now tagged, were not) ===")
    for t in gained["ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)"][:15]:
        print("  +", t[:90])
    print("\n=== docs LOST by ToR5 (were tagged, now not) ===")
    for t in lost["ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)"][:15]:
        print("  -", t[:90])
    print("\nsaved -> data/tor_full_tags.json")


if __name__ == "__main__":
    main()
