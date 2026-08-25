#!/usr/bin/env python3
"""Journalist-style QA walkthrough of the Wang Fuk Court site.

Simulates a journalist asking real questions, checking whether the site can
answer them. Reports: page health, search results for key queries, doc page
integrity (ToC anchors, full text, images), ToR narratives, and any console
errors / broken links found along the way.
"""
import json, sys, re
from playwright.sync_api import sync_playwright

BASE = "https://wangfukcourtfirereport.simonsays.hk"
console_errors, page_errors, broken = [], [], []

QUERIES = [
    ("Was the fire caused by smoking?", "smoking"),
    ("Were the sprinklers or alarms working?", "sprinkler"),
    ("Why did the fire spread so fast?", "foam"),
    ("Was there bid-rigging in the renovation?", "bid-rig"),
    ("Who is responsible for supervision?", "supervision"),
    ("What were the committee's recommendations?", "recommendation"),
]

DOC_PAGES = [
    "/doc/Final-Investigation-Report-of-IFITF.html",
    "/doc/Consolidated-Expert-Report-of-Prof-Usmani-_-Prof-Jiang-Fire-Engineering-Experts-for-the-IC-Redacted.html",
    "/doc/Witness-Statement-Law_Kwok_Shui.html",
    "/doc/Witness-Statement-3-Leung_Ping_Kay.html",
    "/doc/Closing-Address-Gov.html",
]


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1440, "height": 1000})
        pg.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: page_errors.append(str(e)))
        pg.on("response", lambda r: broken.append((r.status, r.url)) if r.status >= 400 and "simonsays.hk" in r.url else None)
        r = {}

        # 1. Core pages
        core = {}
        for path in ["/", "/documents.html", "/tor.html", "/work.html", "/news.html", "/about.html"]:
            resp = pg.goto(BASE + path, wait_until="networkidle", timeout=60000)
            core[path] = resp.status
        r["core_pages"] = core

        # 2. Journalist questions -> search on the documents page
        pg.goto(BASE + "/documents.html", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(1500)
        r["search_queries"] = {}
        for q, term in QUERIES:
            pg.fill("#map-search", term)
            pg.wait_for_timeout(700)
            rows = pg.locator(".doc-row").count()
            count_txt = pg.locator("#doc-count").inner_text()
            first_titles = [t.strip() for t in pg.locator(".doc-row .row-title").all_inner_texts()[:3]]
            r["search_queries"][q] = {"term": term, "rows": rows, "count": count_txt, "first": first_titles}
        pg.fill("#map-search", "")

        # 3. Doc page integrity
        r["doc_pages"] = {}
        for path in DOC_PAGES:
            resp = pg.goto(BASE + path, wait_until="networkidle", timeout=60000)
            info = {"status": resp.status}
            if resp.status == 200:
                info["title"] = pg.title()[:80]
                info["summary_len"] = len(pg.locator(".summary").first.inner_text()) if pg.locator(".summary").count() else 0
                info["cross_summaries"] = pg.locator(".cross-sum").count()
                info["toc_anchors"] = pg.locator("a[href^='#page-']").count()
                info["full_text_len"] = len(pg.locator(".full-doc").inner_text()) if pg.locator(".full-doc").count() else 0
                info["images"] = pg.locator(".img-gallery img").count()
                info["pdf_links"] = pg.locator("a[href$='.pdf'], a[href*='/pdf/']").count()
                info["has_type_badge"] = pg.locator(".type-badge").count() > 0
                info["has_news_card"] = pg.locator("a[href*='news.html#theme']").count()
            r["doc_pages"][path] = info

        # 4. ToR pages: narrative presence
        r["tor_pages"] = {}
        for path in ["/tor/ToR1.html", "/tor/ToR4.html", "/tor/ToR5.html", "/tor/ToR6.html"]:
            resp = pg.goto(BASE + path, wait_until="networkidle", timeout=60000)
            info = {"status": resp.status}
            if resp.status == 200:
                info["sections"] = pg.locator(".tor-section, section.block .card").count()
                info["citations"] = pg.locator(".cite-ref").count()
                info["docs_list"] = pg.locator("details").count()
                info["work_line"] = pg.locator(".page-head .doc-sub").inner_text()[:60] if pg.locator(".page-head .doc-sub").count() else ""
            r["tor_pages"][path] = info

        # 5. About page credits
        pg.goto(BASE + "/about.html", wait_until="networkidle", timeout=60000)
        r["about_email"] = "simonwanghkteacher@gmail.com" in pg.content()
        r["about_disclaimer"] = "private individual" in pg.content() and "educational purposes" in pg.content()

        r["console_errors"] = console_errors[:10]
        r["page_errors"] = page_errors[:10]
        r["broken_responses"] = sorted(set(broken))[:15]
        b.close()
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
