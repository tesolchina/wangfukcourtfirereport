#!/usr/bin/env python3
"""Final check: any remaining empty pages across all 243 docs?"""
import os, re, sys
sys.path.insert(0, "codes")
import build_site as bs

MD_DIR = "data/markdown"
IMG_DIR = "data/images"
MIN_CHARS = 30

remaining = []
no_img_empty = []
total_pages = 0
no_md = []
for d in bs.INDEX:
    slug = bs.slug_of(d)
    md = os.path.join(MD_DIR, f"{slug}.md")
    if not os.path.exists(md):
        no_md.append(slug)
        continue
    t = open(md, encoding="utf-8", errors="ignore").read()
    pages = re.split(r"^--- Page (\d+) ---$", t, flags=re.M)
    page_files = {}
    for f in os.listdir(IMG_DIR):
        m = re.match(rf"^{re.escape(slug)}_p(\d+)_img(\d+)", f)
        if m:
            page_files.setdefault(int(m.group(1)), []).append(f)
    for i in range(1, len(pages), 2):
        n = int(pages[i])
        body = pages[i + 1].strip()
        total_pages += 1
        if len(body) < MIN_CHARS:
            if n in page_files:
                remaining.append((slug, n, len(body)))
            else:
                no_img_empty.append((slug, n, len(body)))

print("total page markers across all docs:", total_pages)
print("docs with no markdown at all:", len(no_md), no_md[:5])
print()
print("== empty pages WITH an image available (fixable):", len(remaining))
for s, n, c in remaining:
    print(f"  {s} p{n:03d} ({c} chars)")
print()
print("== empty/short pages with NO image (blank or scan-page):", len(no_img_empty))
for s, n, c in no_img_empty[:40]:
    print(f"  {s} p{n:03d} ({c} chars)")
if len(no_img_empty) > 40:
    print(f"  ... and {len(no_img_empty)-40} more")
