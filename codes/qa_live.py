#!/usr/bin/env python3
"""Playwright QA for the revamped Wang Fuk Court Fire Report site (live).
Checks core pages, console errors, doc-page galleries (images now uploaded),
ToR filter URL behavior, and map interactivity.
"""
import sys, json
from playwright.sync_api import sync_playwright

BASE = "https://wangfukcourtfirereport.simonsays.hk"

console_errors = []
page_errors = []

def check(page, path, wait_sel=None, timeout=30000):
    url = BASE + path
    try:
        resp = page.goto(url, wait_until="networkidle", timeout=timeout)
        status = resp.status if resp else None
        if wait_sel:
            page.wait_for_selector(wait_sel, timeout=10000)
        return {"url": url, "status": status, "ok": status == 200}
    except Exception as e:
        return {"url": url, "error": str(e)[:200], "ok": False}

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        report = {}

        # 1. Core pages
        report["core_pages"] = [
            check(page, "/"),
            check(page, "/map.html", "#map-svg svg, svg"),
            check(page, "/documents.html", "button[data-tor]"),
            check(page, "/tor.html"),
            check(page, "/tor/ToR1.html", "details"),
            check(page, "/about.html"),
            check(page, "/news.html"),
        ]

        # 2. Doc page with images: gallery renders, images actually load
        doc_path = "/doc/Supp-Witness-Statement-2-Lee_Kwok_Hung.html"
        r = check(page, doc_path, "img")
        report["doc_page"] = r
        if r.get("ok"):
            imgs = page.locator("img").all()
            img_status = []
            for i, img in enumerate(imgs[:8]):
                src = img.get_attribute("src") or ""
                # wait for load/naturalWidth
                ok = img.evaluate("el => el.complete && el.naturalWidth > 0")
                img_status.append({"i": i, "src": src[-60:], "loaded": ok})
            report["doc_gallery_imgs"] = img_status
            # full-text section present
            report["doc_has_details"] = page.locator("details").count() > 0
            report["doc_has_toc"] = page.locator("a[href^='#page-']").count() > 0
            report["doc_has_pdf_link"] = page.locator("a[href$='.pdf']").count() > 0

        # 3. ToR filter gives unique URL
        page.goto(BASE + "/documents.html", wait_until="networkidle")
        page.wait_for_selector("button[data-tor]", timeout=15000)
        buttons = page.locator("button[data-tor]")
        nb = buttons.count()
        report["tor_buttons_total"] = nb
        page.locator("button[data-tor]").nth(1).click()
        page.wait_for_timeout(400)
        report["tor_filter_url"] = page.url
        report["tor_rows_after_filter"] = page.locator(".doc-row, #doc-list > *, tr, li").count() if page.locator(".doc-row").count() else "n/a"

        # 4. Map: click a ToR node -> doc chips appear
        try:
            page.goto(BASE + "/map.html", wait_until="networkidle")
            page.wait_for_timeout(1500)
            svg_nodes = page.locator("svg [data-tor], svg .tor-node, svg g")
            report["map_svg_groups"] = svg_nodes.count()
            # click a ToR node (prefer [data-tor], force to skip overlapping SVG lines)
            clickable = page.locator("[data-tor]")
            report["map_clickable"] = clickable.count()
            if clickable.count() > 0:
                clickable.nth(1).click(force=True)
                page.wait_for_timeout(800)
                chips = page.locator(".doc-chip, [class*='chip'], [class*='doc-card'], [id*='panel'] a")
                report["map_chips_after_click"] = chips.count()
            else:
                circles = page.locator("svg circle")
                report["map_circles"] = circles.count()
                if circles.count() > 1:
                    circles.nth(1).click(force=True)
                    page.wait_for_timeout(800)
        except Exception as e:
            report["map_error"] = str(e)[:200]

        report["console_errors"] = console_errors[:15]
        report["page_errors"] = page_errors[:15]

        browser.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
