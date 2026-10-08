#!/usr/bin/env python3
"""
Build data/index_zh.json - the Chinese-language corpus (parallel to index.json).

The committee's Chinese site (/chi/) links 80 PDFs the English pages never
link (26 hearing transcripts, 24 witness timetables, 8 notices, 6 lists of
involved parties, appointments, opening addresses, Rules of Procedure, a CC
press release and 2 witness-statement translations). This script turns the
crawler manifest entries for those files into site-ready index entries:

- title from the Chinese link text (fallback: markdown H1)
- en_counterpart URL where an English file with the same document identity
  exists (filename normalisation: strip (Chinese)/(Chi)/-Chinese/Translation)
- provisional ToR tags from a Chinese keyword map, clearly labelled
  (tagged_by: keyword-heuristic) - LLM semantic tagging is a later step
- summary = converted markdown content (same convention as index.json)

Run:  /usr/local/bin/python3 codes/build_zh_index.py
"""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MANIFEST = DATA / "manifest.json"
MD_DIR = DATA / "markdown"
OUT = DATA / "index_zh.json"

# Chinese keyword -> ToR tag (provisional; LLM tagging to follow)
KEYWORD_TOR = [
    (r"圍標|串通|合謀|勾結|操控|協調出價|圍飛", "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)"),
    (r"法例|罰則|刑罰|罰款|條例|法規|量刑", "ToR6: Adequacy of Laws & Penalties"),
    (r"建議|改善措施|改善|檢討", "ToR7: Recommendations & Improvement Measures"),
    (r"消防裝置|消防設備|消防泵|灑水|花灑|警鐘|消防喉", "ToR2: Fire Service Installations & Equipment"),
    (r"維修|工程|物料|棚架|棚網|翻新|外牆|發泡膠", "ToR3: Building Maintenance & Renovation Works"),
    (r"監督|監察|責任|負責|角色|註冊|授權|簽名|批核", "ToR4: Supervision, Roles & Responsibilities"),
    (r"起火|火勢|蔓延|死傷|傷亡|起因|焚燒|火警", "ToR1: Causes & Circumstances of Fire"),
]

CATEGORIES = [
    (r"transcript", "Hearing transcript (Chinese)"),
    (r"witness-timetable", "Witness timetable (Chinese)"),
    (r"notice", "Notice / directions (Chinese)"),
    (r"list-of-involved-parties", "List of involved parties (Chinese)"),
    (r"appointment", "Appointment of counsel / experts (Chinese)"),
    (r"opening-address", "Opening address (Chinese)"),
    (r"rules-of-procedure", "Rules of Procedure (Chinese)"),
    (r"press-release", "Press release (Chinese)"),
    (r"translation", "Witness statement translation (Chinese)"),
]


def category_of(name: str) -> str:
    low = name.lower()
    for pat, label in CATEGORIES:
        if re.search(pat, low):
            return label
    return "Other (Chinese)"


def tor_tags(text: str) -> list:
    tags = []
    for pat, tag in KEYWORD_TOR:
        if re.search(pat, text):
            tags.append(tag)
    return tags


def en_candidates(stem: str) -> list:
    """Candidate English filenames for a Chinese one, by language-token swap."""
    cands = [
        stem.replace("(Chinese)", "(English)"),
        stem.replace("(Chi)", "(Eng)"),
        stem.replace("-Chinese", "-English"),
        re.sub(r"^\(Chi\)-", "", stem),                      # Opening-Address-(Chi)-X -> Opening-Address-X
        stem.replace("Translation-", ""),                     # witness-statement translations
    ]
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def norm(s: str) -> str:
    return re.sub(r"[\s_-]+", "", s.lower())


def en_counterpart(name: str, en_urls: list) -> str | None:
    """Find the English file for a Chinese one by language-token substitution."""
    stem = re.sub(r"\.(pdf|PDF)$", "", name)
    en_names = {}
    for u in en_urls:
        en_names[norm(urlparse(u).path.rsplit("/", 1)[-1].replace(".pdf", ""))] = u
    for cand in en_candidates(stem):
        hit = en_names.get(norm(cand))
        if hit:
            return hit
    return None


def md_title(md_path: Path, fallback: str) -> str:
    if md_path.exists():
        for line in md_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return fallback


def main():
    m = json.loads(MANIFEST.read_text())
    en_urls = [p["url"] for p in m["pdfs"] if "/eng/" in p.get("found_on", "")]
    zh_entries_manifest = [p for p in m["pdfs"] if "/chi/" in p.get("found_on", "")]
    # keep only the files the EN site does not link (URL not among EN-found entries)
    en_url_set = set(en_urls)
    zh_only = [p for p in zh_entries_manifest if p["url"] not in en_url_set]

    docs = []
    matched = 0
    for p in sorted(zh_only, key=lambda x: x["url"]):
        fname = urlparse(p["url"]).path.rsplit("/", 1)[-1]
        stem = re.sub(r"\.pdf$", "", fname, flags=re.I)
        md_path = MD_DIR / f"{stem}.md"
        local_md = f"markdown/{stem}.md" if md_path.exists() else None
        text = ""
        if md_path.exists():
            text = md_path.read_text(encoding="utf-8", errors="ignore")
        counter = en_counterpart(fname, en_urls)
        if counter:
            matched += 1
        docs.append({
            "title": p.get("link_text") or md_title(md_path, fname),
            "url": p["url"],
            "local_md": local_md,
            "pages": p.get("num_pages", 0),
            "images": p.get("num_images", 0),
            "lang": "zh-Hant",
            "category": category_of(fname),
            "en_counterpart": counter,
            "related_to_tor": tor_tags(text or fname),
            "tagged_by": "keyword-heuristic (provisional; LLM tagging pending)",
            "summary": text,
        })

    payload = {
        "generated": datetime.now().isoformat(),
        "note": ("Chinese-language corpus linked only from the committee's /chi/ site. "
                 "Parallel to the 243-document English corpus in index.json; counts on "
                 "the EN site are unchanged. ToR tags are provisional keyword matches."),
        "counts": {"zh_docs": len(docs), "with_en_counterpart": matched},
        "docs": docs,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"wrote {OUT}: {len(docs)} docs, {matched} with EN counterpart")
    cats = {}
    for d in docs:
        cats[d["category"]] = cats.get(d["category"], 0) + 1
    for k, v in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")
    unmatched = [d["url"].rsplit("/", 1)[-1] for d in docs if not d["en_counterpart"]]
    print(f"no EN counterpart: {len(unmatched)}")
    for n in unmatched:
        print("   -", n)


if __name__ == "__main__":
    main()