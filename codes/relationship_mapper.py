#!/usr/bin/env python3
"""
Relationship Mapper + Visual Framework for Journalists

- Generates short summary + ToC for each document
- Heuristically maps documents to the Committee's Terms of Reference (ToR)
- Produces:
  - data/index.json (machine readable)
  - data/relationships.md (with Mermaid diagram + tables)

Run after full processing + descriptions:
  python relationship_mapper.py
"""

import json
from pathlib import Path
from datetime import datetime
import re

# Project root: works whether this script lives at the project root or in codes/
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent if _HERE.name == "codes" else _HERE
BASE = ROOT
DATA = BASE / "data"
MANIFEST = DATA / "manifest.json"
OUT_INDEX = DATA / "index.json"
OUT_MD = DATA / "relationships.md"

TOR_CATEGORIES = [
    ("ToR1: Causes & Circumstances of Fire", ["fire", "cause", "spread", "origin", "circumstance"]),
    ("ToR2: Fire Service Installations & Equipment", ["fire service", "fsd", "installation", "equipment", "hydrant", "sprinkler"]),
    ("ToR3: Building Maintenance & Renovation Works", ["maintenance", "renovation", "repair", "building work", "contractor", "material"]),
    ("ToR4: Supervision, Roles & Responsibilities", ["supervision", "role", "responsibility", "authorised", "officer", "contractor"]),
    ("ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)", ["collusion", "bid-rig", "conflict", "interest", "cartel", "corruption", "icac", "competition"]),
    ("ToR6: Adequacy of Laws & Penalties", ["law", "regulation", "penalty", "legislation", "enforcement"]),
    ("ToR7: Recommendations & Improvement Measures", ["recommend", "improvement", "measure", "submission", "expert report"]),
]

def get_summary(md_path: Path, max_len: int = 350) -> str:
    if not md_path.exists():
        return ""
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    # Remove page markers and metadata
    text = re.sub(r'--- Page \d+ ---', '', text)
    text = re.sub(r'## Metadata[\s\S]*?---', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text[:max_len].replace('\n', ' ').strip() + "..."

def get_toc(md_path: Path) -> list[str]:
    if not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    pages = re.findall(r'--- Page (\d+) ---', text)
    # Simple ToC: list page numbers + first heading-ish line after each
    toc = []
    for p in pages[:8]:  # cap
        toc.append(f"Page {p}")
    return toc

def classify_tor(title: str, link_text: str) -> list[str]:
    text = (title + " " + link_text).lower()
    matches = []
    for cat, keywords in TOR_CATEGORIES:
        if any(kw in text for kw in keywords):
            matches.append(cat)
    if not matches:
        matches.append("General / Other")
    return matches

def main():
    m = json.load(open(MANIFEST))
    pdfs = m.get("pdfs", [])

    index = []
    for p in pdfs:
        if not p.get("md_path"):
            continue
        md_path = DATA / p["md_path"]
        title = p.get("link_text", Path(p["local_path"]).stem)
        summary = get_summary(md_path)
        toc = get_toc(md_path)
        tors = classify_tor(title, p.get("link_text", ""))

        entry = {
            "title": title,
            "url": p["url"],
            "local_md": p["md_path"],
            "pages": p.get("num_pages", 0),
            "images": p.get("num_images", 0),
            "summary": summary,
            "toc": toc,
            "related_to_tor": tors,
            "described": bool(p.get("images") and any(i.get("description") for i in p.get("images", [])))
        }
        index.append(entry)

    # Save machine index
    json.dump({"generated": datetime.now().isoformat(), "docs": index}, open(OUT_INDEX, "w"), indent=2, ensure_ascii=False)

    # Build Mermaid + human report
    lines = ["# Fire Inquiry Document Relationship Map\n"]
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    lines.append("## Terms of Reference Framework\n")

    for cat, _ in TOR_CATEGORIES + [("General / Other", [])]:
        docs = [d for d in index if cat in d["related_to_tor"]]
        lines.append(f"### {cat} ({len(docs)} docs)")
        for d in docs[:5]:
            lines.append(f"- [{d['title'][:80]}]({d['local_md']}) — {d['pages']}p, {d['images']} images")
        lines.append("")

    # Simple Mermaid graph (docs grouped by ToR)
    lines.append("## Visual Map (Mermaid)\n")
    lines.append("```mermaid")
    lines.append("graph TD")
    lines.append("    ToR[Independent Committee<br/>Terms of Reference]")

    for cat, _ in TOR_CATEGORIES:
        safe = cat.split(":")[0].replace(" ", "_")
        lines.append(f"    {safe}[{cat}]")
        lines.append(f"    ToR --> {safe}")

    # Add a few example docs
    for i, d in enumerate(index[:12]):
        nid = f"D{i}"
        short = d["title"][:40].replace('"', "'").replace("\n", " ")
        lines.append(f'    {nid}["{short}..."]')
        for cat in d["related_to_tor"]:
            safe = cat.split(":")[0].replace(" ", "_")
            lines.append(f"    {safe} --> {nid}")

    lines.append("```")

    lines.append("\n## How to use for journalists")
    lines.append("- Start from a ToR category above")
    lines.append("- Click into individual docs for full MD + images + (future) descriptions")
    lines.append("- Use the index.json for programmatic search / RAG")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(f"Index written: {OUT_INDEX}")
    print(f"Relationship map: {OUT_MD}")
    print(f"Documents mapped: {len(index)}")

if __name__ == "__main__":
    main()
