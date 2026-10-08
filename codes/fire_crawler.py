#!/usr/bin/env python3
"""
FireReport Crawler for Independent Committee on Wang Fuk Court Fire
https://www.ic-wangfukcourtfire.gov.hk/eng/

Step 1: Crawl site, discover all pages + PDFs
Step 2: Download all PDFs (idempotent)
Step 3: (future) Convert to MD + extract images + LLM descriptions

Usage (with correct python that has the libs):
  /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 fire_crawler.py
  or
  /usr/local/bin/python3 fire_crawler.py
"""

import os
import json
import time
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# Config
BASE_URL = "https://www.ic-wangfukcourtfire.gov.hk/eng/"
CHI_BASE_URL = "https://www.ic-wangfukcourtfire.gov.hk/chi/"  # Chinese site: links 80 PDFs the EN pages never link (issue #4)
DOMAIN = "ic-wangfukcourtfire.gov.hk"
# Project root: works whether this script lives at the project root or in codes/
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent if _HERE.name == "codes" else _HERE
DATA_DIR = ROOT / "data"
PDF_DIR = DATA_DIR / "pdfs"
MANIFEST = DATA_DIR / "manifest.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI4News-FireReport-Crawler/0.1; +https://github.com/tesolchina/wangfukcourtfirereport)"
}
TIMEOUT = 30
SLEEP = 0.3  # polite crawling

# Main entry pages to start from
START_PAGES = [
    "index.html",
    "documents.html",
    "transcripts.html",
    "notices.html",
    "press.html",
    "timetable.html",
    "membership.html",
    "secretariat.html",
]

def safe_filename(url: str, title: str = "") -> str:
    """Create a safe local filename from URL or title."""
    parsed = urlparse(url)
    name = unquote(os.path.basename(parsed.path))
    if not name or name == "/":
        name = "index.html"
    # Keep original extension for PDFs
    if not name.lower().endswith(".pdf") and ".pdf" in url.lower():
        name += ".pdf"
    # Sanitize
    name = "".join(c if c.isalnum() or c in "._- " else "_" for c in name)
    name = name.strip().replace(" ", "_")
    if len(name) > 120:
        # hash long names
        h = hashlib.md5(url.encode()).hexdigest()[:8]
        stem, ext = os.path.splitext(name)
        name = f"{stem[:80]}_{h}{ext}"
    return name

def is_internal(url: str) -> bool:
    return DOMAIN in urlparse(url).netloc

def fetch(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[WARN] fetch failed {url}: {e}")
        return None

def discover_links(html: str, base: str) -> set[str]:
    """Only return non-PDF internal links suitable for page crawling."""
    soup = BeautifulSoup(html, "html.parser")
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        full = urljoin(base, href)
        if is_internal(full) and not full.lower().endswith(".pdf"):
            # normalize
            full = full.split("#")[0]
            links.add(full)
    return links

def find_pdfs(html: str, base: str) -> list[dict]:
    """Return list of {url, text} for PDFs on the page."""
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip().lower()
        if ".pdf" in href:
            full = urljoin(base, a["href"])
            text = a.get_text(strip=True)[:150]
            results.append({"url": full, "link_text": text})
    return results

def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"pages": [], "pdfs": [], "last_run": None}

def save_manifest(manifest: dict):
    manifest["last_run"] = datetime.utcnow().isoformat() + "Z"
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

def download_pdf(url: str, dest: Path) -> bool:
    """Download if not exists. Return True if downloaded."""
    if dest.exists() and dest.stat().st_size > 100:
        return False
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        time.sleep(SLEEP)
        return True
    except Exception as e:
        print(f"[ERROR] download failed {url}: {e}")
        return False

def crawl():
    print("=== FireReport Crawler ===")
    print(f"Target: {BASE_URL}")
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    visited = set(p["url"] for p in manifest.get("pages", []))
    pdf_index = {p["url"]: p for p in manifest.get("pdfs", [])}

    # Seed both language sites: the lang switch is JS-only (href="#"), so the
    # Chinese pages are never discovered from the English pages and vice versa.
    to_visit = [urljoin(BASE_URL, p) for p in START_PAGES]
    to_visit += [urljoin(CHI_BASE_URL, p) for p in START_PAGES]
    all_pages = set(to_visit)
    all_pdfs = []

    # Phase 1: discover pages and PDFs
    print("\n[1/2] Discovering pages and PDFs...")
    while to_visit:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        if url.lower().endswith(".pdf"):
            continue  # PDFs are handled via find_pdfs only

        print(f"  Visiting: {url}")
        html = fetch(url)
        if not html:
            continue

        # record page
        page_entry = {
            "url": url,
            "title": "",
            "discovered_at": datetime.utcnow().isoformat() + "Z"
        }
        soup = BeautifulSoup(html, "html.parser")
        if soup.title:
            page_entry["title"] = soup.title.string.strip()

        if url not in [p["url"] for p in manifest["pages"]]:
            manifest["pages"].append(page_entry)

        # find more pages
        new_links = discover_links(html, url)
        for link in new_links:
            if link not in all_pages and is_internal(link):
                all_pages.add(link)
                to_visit.append(link)

        # find PDFs on this page
        pdfs_on_page = find_pdfs(html, url)
        for pdf in pdfs_on_page:
            if pdf["url"] not in pdf_index:
                fname = safe_filename(pdf["url"], pdf["link_text"])
                dest = PDF_DIR / fname
                pdf_entry = {
                    "url": pdf["url"],
                    "local_path": str(dest.relative_to(DATA_DIR)),
                    "link_text": pdf["link_text"],
                    "found_on": url,
                    "downloaded": False,
                    "size": 0
                }
                manifest["pdfs"].append(pdf_entry)
                pdf_index[pdf["url"]] = pdf_entry
                all_pdfs.append(pdf_entry)

        time.sleep(SLEEP)

    print(f"  Discovered {len(manifest['pages'])} pages, {len(manifest['pdfs'])} PDFs")

    # Phase 2: download PDFs
    print("\n[2/2] Downloading PDFs (skipping existing)...")
    downloaded = 0
    for entry in manifest["pdfs"]:
        if entry.get("downloaded"):
            continue
        dest = DATA_DIR / entry["local_path"]
        if download_pdf(entry["url"], dest):
            entry["downloaded"] = True
            entry["size"] = dest.stat().st_size if dest.exists() else 0
            downloaded += 1
            print(f"  ✓ {dest.name} ({entry['size']//1024} KB)")
        else:
            if dest.exists():
                entry["downloaded"] = True
                entry["size"] = dest.stat().st_size

    save_manifest(manifest)

    print(f"\n=== Done ===")
    print(f"Pages: {len(manifest['pages'])}")
    print(f"PDFs discovered: {len(manifest['pdfs'])}")
    print(f"Newly downloaded this run: {downloaded}")
    print(f"Manifest: {MANIFEST}")
    print(f"PDFs dir: {PDF_DIR}")

if __name__ == "__main__":
    crawl()
