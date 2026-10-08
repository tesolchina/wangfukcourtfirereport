#!/usr/bin/env python3
"""
Coverage audit part 2:
1. Chinese site (/chi/) PDF list vs English manifest - any docs we don't have?
   (The committee's Chinese pages link PDFs the English pages never link.)
2. Non-PDF internal file links (docx/xlsx/images/media) on all eng + chi pages.
3. Dated content on index/notices/press pages published after the Aug 16 crawl
   (note: page-footer "Last revision date" lines will also match).

Run:  python3 codes/audit_coverage2.py
"""

import json
import re
import time
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

CRAWL_DATE = (2026, 8, 16)  # date of the manifest crawl; dates after this are flagged

ENG = "https://www.ic-wangfukcourtfire.gov.hk/eng/"
CHI = "https://www.ic-wangfukcourtfire.gov.hk/chi/"
DOMAIN = "ic-wangfukcourtfire.gov.hk"
ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "manifest.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI4News-FireReport-Crawler/0.1; +https://github.com/tesolchina/wangfukcourtfirereport)"
}
SLEEP = 0.3
PAGES = ["index.html", "documents.html", "transcripts.html", "notices.html",
         "press.html", "timetable.html", "membership.html", "secretariat.html"]


def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  warn: {url}: {e}")
        return ""


def links_on(base, page):
    html = fetch(urljoin(base, page))
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0]
        if not href or href.lower().startswith(("mailto:", "javascript:")):
            continue
        full = urljoin(base, href)
        if DOMAIN in urlparse(full).netloc:
            out.append((full, a.get_text(strip=True)[:60]))
    return out


def main():
    m = json.load(open(MANIFEST))
    eng_pdfs = {p["url"] for p in m["pdfs"]}

    print("[1/3] Chinese site (/chi/) PDF coverage...")
    chi_pdfs = set()
    for p in PAGES:
        for url, _ in links_on(CHI, p):
            if ".pdf" in url.lower():
                chi_pdfs.add(url)
        time.sleep(SLEEP)
    print(f"  chi PDF links: {len(chi_pdfs)}")
    chi_only = sorted(u for u in chi_pdfs if u not in eng_pdfs)
    print(f"  Chinese-site PDFs NOT in our manifest: {len(chi_only)}")
    for u in chi_only[:20]:
        print("   +", u)
    # same doc, different path? compare basenames
    eng_names = {urlparse(u).path.rsplit("/", 1)[-1].lower() for u in eng_pdfs}
    chi_only_names = {urlparse(u).path.rsplit("/", 1)[-1].lower() for u in chi_only}
    same_name_diff_path = sorted(chi_only_names & eng_names)
    truly_new = sorted(chi_only_names - eng_names)
    print(f"  of which same filename (path differs only): {len(same_name_diff_path)}")
    print(f"  genuinely new filenames: {len(truly_new)}")
    for n in truly_new[:20]:
        print("   *", n)

    print("\n[2/3] Non-PDF internal file links (eng + chi)...")
    ext_re = re.compile(r"\.(docx?|xlsx?|pptx?|zip|mp4|mp3|jpg|jpeg|png|gif)$", re.I)
    non_pdf = set()
    for base in (ENG, CHI):
        for p in PAGES:
            for url, _ in links_on(base, p):
                if ext_re.search(urlparse(url).path):
                    non_pdf.add(url)
            time.sleep(SLEEP)
    print(f"  non-PDF file links: {len(non_pdf)}")
    for u in sorted(non_pdf)[:20]:
        print("   ~", u)

    print("\n[3/3] Dated content on index/notices/press (post 2026-08-16)...")
    date_re = re.compile(r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", re.I)
    months = {m_: i for i, m_ in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], 1)}
    for page in ["index.html", "notices.html", "press.html", "documents.html", "transcripts.html"]:
        html = fetch(urljoin(ENG, page))
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        hits = []
        for d, mon, y in date_re.findall(text):
            try:
                if (int(y), months[mon.capitalize()], int(d)) > CRAWL_DATE:
                    hits.append(f"{d} {mon} {y}")
            except (KeyError, ValueError):
                continue
        hits = sorted(set(hits))
        print(f"  {page}: {len(hits)} post-crawl dates {hits[:10]}")
        time.sleep(SLEEP)


if __name__ == "__main__":
    main()