#!/usr/bin/env python3
"""TOR_FULL_SCAN — paragraph-level ToR tagging of every document's FULL text.

Motivation (user 2026-08-16): all existing ToR tags came from summary-level LLM
reading (first ~2500 chars) — the ToR5 deep scan (tor5_deep_scan.py) proved this
misses substantive relevance: 47 non-ToR5 docs carried collusion evidence. So the
whole site's ToR associations must be rebuilt from FULL-text, paragraph-level
reading: split each doc into chunks, ask the LLM which ToR tasks each chunk
relates to (semantic, not keyword), then aggregate to document level.

Output: data/tor_full.json
  {title: {
     "chunks": [{"id": n, "tor_tags": ["ToR1: ...", ...], "evidence": "..."}],
     "doc_tor_tags": ["ToR1: ...", ...],      # any chunk hit
     "tor_chunk_counts": {"ToR1: ...": 3, ...},
     "ok": true, "provider": "..."}}

Concurrency: 3 providers w/ failover (hkbu → poe → openrouter), <=3 workers,
1s pacing, checkpoint every 10. Reuses the provider stack from tor5_deep_scan.
"""
import argparse, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")

TOR_ALL = [
    "ToR1: Causes & Circumstances of Fire",
    "ToR2: Fire Service Installations & Equipment",
    "ToR3: Building Maintenance & Renovation Works",
    "ToR4: Supervision, Roles & Responsibilities",
    "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)",
    "ToR6: Adequacy of Laws & Penalties",
    "ToR7: Recommendations & Improvement Measures",
    "General / Other",
]

CHUNK_CHARS = 2000   # target chunk size
OVERLAP = 150        # small overlap to avoid cutting a passage mid-sentence

# ---------------- provider stack (shared with tor5_deep_scan) ----------------

PROVIDERS = []
_provider_lock = threading.Lock()
_provider_down_until = {}


def _read_creds():
    with open(CREDS) as f:
        return f.read()


def load_providers():
    global PROVIDERS
    content = _read_creds()
    def grab(pat):
        m = re.search(pat, content, re.I)
        return m.group(1).strip() if m else None
    hkbu_key = grab(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)")
    poe_key = grab(r"poe_API_key\s*=\s*(sk-[A-Za-z0-9_-]+)")
    or_key = grab(r"newOpenRouterKey\s*=\s*(sk-or-v1-[A-Za-z0-9_-]+)")
    ps = []
    if hkbu_key:
        ps.append({"name": "hkbu", "base": "https://genai.hkbu.edu.hk/general/rest/deployments",
                   "model": "gpt-4.1-mini", "headers": {"api-key": hkbu_key},
                   "path": "/chat/completions?api-version=2024-02-01", "max_tokens": 900})
    if poe_key:
        ps.append({"name": "poe", "base": "https://api.poe.com/v1",
                   "model": "ChatGPT-4o-mini", "headers": {"Authorization": "Bearer " + poe_key},
                   "path": "/chat/completions", "max_tokens": 900})
    if or_key:
        ps.append({"name": "openrouter", "base": "https://openrouter.ai/api/v1",
                   "model": "deepseek/deepseek-chat", "headers": {"Authorization": "Bearer " + or_key},
                   "path": "/chat/completions", "max_tokens": 1200})
    if not ps:
        sys.exit("No LLM API keys found in " + CREDS)
    PROVIDERS = ps


def _provider_usable(p):
    with _provider_lock:
        until = _provider_down_until.get(p["name"], 0)
    return time.time() >= until


def _mark_provider(p, down_seconds=300):
    with _provider_lock:
        _provider_down_until[p["name"]] = time.time() + down_seconds
    print(f"[provider] {p['name']} 429-limited; cooling down {down_seconds}s", flush=True)


SYSTEM_PROMPT = (
    "You are an investigative research assistant for journalists covering the Hong Kong "
    "Independent Committee on the Fire at Wang Fuk Court (大埔宏福苑). "
    "You are given a CHUNK of an inquiry document (witness statement, hearing transcript, "
    "expert report, closing address, notice, etc.). "
    "Decide which of the Committee's Terms of Reference this chunk is substantively related to. "
    "Choose by SUBSTANCE, not keywords: a chunk can relate to a ToR even if the exact task "
    "phrasing never appears. Consider evidence about: the fire's cause and spread (ToR1); "
    "fire-service installations/equipment such as alarms, sprinklers and their upkeep (ToR2); "
    "building maintenance and renovation works (ToR3); supervision, roles and responsibilities "
    "of departments/companies/persons (ToR4); systemic issues — collusion, bid-rigging, "
    "conflicts of interest, tender irregularities (ToR5); adequacy of laws and penalties (ToR6); "
    "recommendations and improvement measures (ToR7). A chunk may relate to several ToR or none.\n"
    "Reply ONLY with compact JSON:\n"
    '{"tor_tags": ["ToR1: Causes & Circumstances of Fire", ...], '
    '"evidence": "one sentence: the strongest concrete fact in this chunk and which ToR it '
    'supports", "toR_numbers": ["ToR1", "ToR5"]}\n'
    "Rules: tor_tags must be a subset of exactly: " + str(TOR_ALL) + ".\n"
    "If the chunk is procedural boilerplate (a date header, a list of parties, a notice of "
    "arrangements), tor_tags=[] and evidence=''.\n"
    "Do not add any text outside the JSON object."
)

USER_TEMPLATE = (
    "Document: {title}\n\nChunk {cid} of this document (text):\n{text}\n\n"
    "Which Terms of Reference does this chunk relate to?"
)


def clean_text(md):
    t = re.sub(r"^#{1,6}\s*", "", md, flags=re.M)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def chunk_text(text):
    """Split cleaned text into ~2000-char chunks with small overlap."""
    if len(text) <= CHUNK_CHARS:
        return [text] if text.strip() else []
    out = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_CHARS, n)
        # extend to a sentence boundary if possible
        if end < n:
            m = re.search(r"[.!?。！？；;]\s", text[end - 80:end + 80])
            if m:
                end = min(end - 80 + m.end(), n)
        out.append(text[start:end])
        if end >= n:
            break
        start = max(end - OVERLAP, start + 1)
    return out


def call_llm(title, cid, text):
    user = USER_TEMPLATE.format(title=title, cid=cid, text=text)
    last_err = None
    for p in PROVIDERS:
        if not _provider_usable(p):
            continue
        body = {
            "model": p["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
            "max_tokens": p["max_tokens"],
        }
        try:
            resp = requests.post(
                p["base"] + p["path"], json=body,
                headers=dict(p["headers"], **{"Content-Type": "application/json"}),
                timeout=120,
            )
            if resp.status_code == 429:
                _mark_provider(p)
                last_err = f"429 from {p['name']}"
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(json)?\s*", "", content.strip())
            content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            tags = [t for t in parsed.get("tor_tags", []) if t in TOR_ALL]
            return {
                "tor_tags": tags,
                "evidence": parsed.get("evidence", ""),
                "toR_numbers": parsed.get("toR_numbers", []),
            }
        except Exception as e:
            last_err = f"{p['name']}: {type(e).__name__}: {str(e)[:100]}"
            continue
    raise RuntimeError(f"all providers failed: {last_err}")


def process_one(args):
    d, md_path = args
    title = d["title"]
    try:
        with open(md_path, encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        chunks = chunk_text(clean_text(raw))
        if not chunks:
            return title, {"chunks": [], "doc_tor_tags": [], "tor_chunk_counts": {},
                           "ok": True, "provider": "", "note": "no text (scanned PDF?)"}
        out = []
        for i, c in enumerate(chunks, 1):
            parsed = call_llm(title, i, c)
            out.append({"id": i, "tor_tags": parsed["tor_tags"],
                        "evidence": parsed["evidence"]})
        # aggregate
        cnt = {}
        tags = []
        for ch in out:
            for t in ch["tor_tags"]:
                cnt[t] = cnt.get(t, 0) + 1
                if t not in tags:
                    tags.append(t)
        return title, {"chunks": out, "doc_tor_tags": tags,
                       "tor_chunk_counts": cnt, "ok": True, "provider": PROVIDERS[0]["name"]}
    except Exception as e:
        return title, {"chunks": [], "doc_tor_tags": [], "tor_chunk_counts": {},
                       "ok": False, "provider": "",
                       "note": f"ERROR: {type(e).__name__}: {str(e)[:150]}"}


_launch_clock = [0.0]
_lock = threading.Lock()


def _throttle(seconds):
    with _lock:
        wait = _launch_clock[0] - time.time()
        if wait > 0:
            time.sleep(wait)
        _launch_clock[0] = time.time() + seconds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="data/tor_full.json")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max_retries", type=int, default=4)
    args = ap.parse_args()

    index = json.load(open("data/index.json"))
    docs = index["docs"]
    todo = list(docs)
    if args.limit:
        todo = todo[: args.limit]
    print(f"Docs to full-scan: {len(todo)} (workers={args.workers})")

    out_path = args.out
    results = {}
    if os.path.exists(out_path):
        results = json.load(open(out_path))
        print(f"Resuming: {len(results)} already scanned")
    todo = [d for d in todo if d["title"] not in results]

    load_providers()
    print(f"Providers: {[p['name'] + ':' + p['model'] for p in PROVIDERS]}", flush=True)
    t0 = time.time()
    ok = fail = 0

    for round_no in range(args.max_retries):
        if not todo:
            break
        tasks = []
        for d in todo:
            md_path = os.path.join("data", d.get("local_md", ""))
            if not os.path.exists(md_path):
                md_path = os.path.join("data", "markdown", os.path.basename(d.get("local_md", "")))
            tasks.append((d, md_path))

        batch_ok = batch_fail = 0
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_one, t): t[0]["title"] for t in tasks}
            done = 0
            for fut in as_completed(futs):
                title, rec = fut.result()
                done += 1
                if rec["ok"]:
                    results[title] = rec
                    batch_ok += 1
                else:
                    batch_fail += 1
                    print(f"[{done}/{len(tasks)}] FAIL {title[:60]}: {rec['note'][:100]}", flush=True)
                if done % 5 == 0:
                    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
                    print(f"  [{done}/{len(tasks)}] ok={batch_ok} fail={batch_fail} "
                          f"elapsed={time.time()-t0:.0f}s", flush=True)
                _throttle(0.4)

        json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
        ok += batch_ok
        fail += batch_fail
        todo = [d for d in todo if d["title"] not in results]
        if todo and round_no < args.max_retries - 1:
            wait = 4 + round_no * 10
            print(f"Retry round {round_no + 1}: {len(todo)} left, sleeping {wait}s", flush=True)
            time.sleep(wait)

    print(f"\nDone. scanned={len(results)} ok={ok} fail={fail}")
    # summary: doc-level ToR counts
    from collections import Counter
    c = Counter()
    for v in results.values():
        for t in v.get("doc_tor_tags", []):
            c[t] += 1
    for t in TOR_ALL:
        print(f"  {t}: {c.get(t, 0)} docs")
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
