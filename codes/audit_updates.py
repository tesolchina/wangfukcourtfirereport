#!/usr/bin/env python3
"""
Update audit: compare live gov site against the Aug 2026 crawl manifest.

Checks:
1. Page discovery - fetch START_PAGES, collect internal .html links, report
   pages not present in the manifest (new sections since the crawl).
2. PDF revision check - GET (headers only) every manifest PDF URL and compare
   Content-Length against the manifest `size`; report changed/removed files.

Run:  python3 codes/audit_updates.py
"""

import json
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.ic-wangfukcourtfire.gov.hk/eng/"
DOMAIN = "ic-wangfukcourtfire.gov.hk"
ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI4News-FireReport-Crawler/0.1; +https://github.com/tesolchina/wangfukcourtfirereport)"
}
SLEEP = 0.3
START_PAGES = [
    "index.html", "documents.html", "transcripts.html", "notices.html",
    "press.html", "timetable.html", "membership.html", "secretariat.html",
]


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  warn: {url}: {e}")
        return ""


def discover_pages():
    seen = set()
    queue = list(START_PAGES)
    while queue:
        p = queue.pop(0)
        if p in seen:
            continue
        seen.add(p)
        html = fetch(urljoin(BASE, p))
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].split("#")[0]
            if not href or href.lower().startswith(("mailto:", "javascript:")):
                continue
            full = urljoin(BASE, href)
            if DOMAIN not in urlparse(full).netloc:
                continue
            path = urlparse(full).path
            if path.endswith(".html") and "/eng/" in path:
                rel = path.split("/eng/")[-1]
                if rel not in seen:
                    queue.append(rel)
        time.sleep(SLEEP)
    return seen


def check_pdfs(manifest):
    changed, gone, errors = [], [], []
    for i, entry in enumerate(manifest["pdfs"]):
        url = entry["url"]
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
            r.close()
            if r.status_code != 200:
                gone.append((url, r.status_code))
                continue
            cl = r.headers.get("Content-Length")
            lm = r.headers.get("Last-Modified", "")
            if cl is not None and int(cl) != int(entry.get("size", -1)):
                changed.append((url, entry.get("size"), int(cl), lm))
        except Exception as e:
            errors.append((url, str(e)))
        if (i + 1) % 50 == 0:
            print(f"  ...checked {i + 1}/{len(manifest['pdfs'])}")
        time.sleep(SLEEP)
    return changed, gone, errors


def main():
    m = json.load(open(MANIFEST))
    known_pages = {urlparse(p["url"]).path.split("/eng/")[-1] for p in m.get("pages", [])}
    print(f"Manifest last_run: {m.get('last_run')}")
    print(f"Manifest pages: {len(known_pages)}, pdfs: {len(m['pdfs'])}")

    print("\n[1/2] Discovering live pages (BFS from start pages)...")
    live_pages = discover_pages()
    new_pages = sorted(p for p in live_pages if p not in known_pages)
    print(f"Live pages found: {len(live_pages)}")
    print(f"New pages not in manifest: {len(new_pages)}")
    for p in new_pages:
        print("  +", p)

    print("\n[2/2] Checking 243 PDFs for revisions (size diff)...")
    changed, gone, errors = check_pdfs(m)
    print(f"Changed (size differs): {len(changed)}")
    for url, old, new, lm in changed:
        print(f"  ~ {url}\n      old={old} new={new} last-modified={lm}")
    print(f"Removed/non-200: {len(gone)}")
    for url, code in gone:
        print(f"  x {url} -> HTTP {code}")
    print(f"Request errors: {len(errors)}")
    for url, e in errors[:10]:
        print(f"  ! {url}: {e}")

    print("\n=== SUMMARY ===")
    print(f"new pages: {len(new_pages)} | changed pdfs: {len(changed)} | "
          f"gone pdfs: {len(gone)} | errors: {len(errors)}")


if __name__ == "__main__":
    main()