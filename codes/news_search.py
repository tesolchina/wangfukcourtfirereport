#!/usr/bin/env python3
"""Gather news coverage on the Wang Fuk Court fire + inquiry via Brave Search API.
Saves raw results to data/news_raw.json for analysis (revamp item 8).
"""
import json, time, urllib.parse, urllib.request, urllib.error, os, ssl

API_KEY = "REPLACE_WITH_BRAVE_SEARCH_API_KEY"
OUT = "data/news_raw.json"

# Framework Python lacks system CA bundle; use certifi if present else unverified.
CTX = None
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl.create_unverified_context()

QUERIES = [
    "Wang Fuk Court fire Tai Po inquiry",
    "Wang Fuk Court fire Hong Kong",
    "王福苑火警 調查委員會",           # tentative Chinese name, will verify
    "大埔 火警 調查委員會 獨立調查",
    "Wang Fuk Court fire sprinkler",
    "Wang Fuk Court fire investigation committee report",
    "Wang Fuk Court fire SCMP",
    "Wang Fuk Court fire Hong Kong inquiry witnesses",
]

def brave_search(q, count=10):
    params = urllib.parse.urlencode({"q": q, "count": count, "search_lang": "zh-hans", "country": "hk"})
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X-Subscription-Token": API_KEY,
    })
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read().decode("utf-8"))

results = {}
for q in QUERIES:
    try:
        res = brave_search(q)
        web = res.get("web", {}).get("results", [])
        results[q] = [{
            "title": w.get("title"),
            "url": w.get("url"),
            "description": w.get("description"),
            "age": w.get("age"),
            "page_age": w.get("page_age"),
        } for w in web]
        print(f"[{len(web)}] {q}")
    except Exception as e:
        results[q] = []
        print(f"[ERR] {q}: {e}")
    time.sleep(1.0)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("saved ->", OUT)
