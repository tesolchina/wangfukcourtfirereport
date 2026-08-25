#!/usr/bin/env python3
"""Playwright QA for the Wang Fuk Court Fire Report site.
Checks: console errors, mermaid render, ToR filter button visibility bug,
menu links, about section, per-ToR narratives, and takes screenshots.
"""
import sys, json
from playwright.sync_api import sync_playwright

URL = "https://wangfukcourtfirereport.simonsays.hk/"

console_errors = []
page_errors = []

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        report = {}

        # 1. Title + HTTPS
        report["title"] = page.title()
        report["url"] = page.url

        # 2. Mermaid rendered?
        svg = page.query_selector("#mermaid-diagram svg")
        report["mermaid_svg"] = bool(svg)
        if svg:
            report["mermaid_nodes"] = page.locator("#mermaid-diagram .node").count()

        # 3. Menu links
        nav_links = page.locator("nav a").all_inner_texts()
        report["nav_links"] = [t.strip() for t in nav_links if t.strip()]

        # 4. About / credits
        about = page.query_selector("#about")
        report["about_section"] = bool(about)
        report["email_present"] = "simonwanghkteacher@gmail.com" in (page.content() or "")

        # 5. ToR filter buttons + invisible-button bug
        page.wait_for_selector("#documents button[data-tor]", timeout=15000)
        buttons = page.locator("#documents button[data-tor]")
        count = buttons.count()
        report["tor_buttons_total"] = count
        report["tor_buttons"] = buttons.all_inner_texts()

        bug_results = []
        for i in range(count):
            b = buttons.nth(i)
            label = (b.inner_text() or "").strip()[:40]
            before = b.bounding_box()
            b.click()
            page.wait_for_timeout(400)
            after = b.bounding_box()
            visible = b.is_visible()
            bg = b.evaluate("el => getComputedStyle(el).backgroundColor")
            color = b.evaluate("el => getComputedStyle(el).color")
            doc_count = page.locator("#doc-grid .doc-card").count()
            bug_results.append({
                "label": label,
                "clicked_visible": visible,
                "bg": bg, "color": color,
                "bbox_before": before, "bbox_after": after,
                "docs_after_click": doc_count,
            })
        report["button_click_test"] = bug_results

        # 6. Screenshots
        page.screenshot(path="/tmp/fr_fullpage.png", full_page=True)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(300)
        page.screenshot(path="/tmp/fr_top.png")
        report["screenshots"] = ["/tmp/fr_fullpage.png", "/tmp/fr_top.png"]

        report["console_errors"] = console_errors[:20]
        report["page_errors"] = page_errors[:20]

        browser.close()

    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
