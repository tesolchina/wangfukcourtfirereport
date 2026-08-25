#!/usr/bin/env python3
"""TOR5_DEEP_SCAN — does the document contain collusion/bid-rigging-relevant
evidence even when the keywords never appear?

Motivation (user 2026-08-16): the letter's ToR5 claim ("bid-rigging and
collusion in just 11 documents") is only as strong as the tagging. The 11 ToR5
tags came from summary-level LLM reading; documents that discuss tender
irregularities, contractor-owner relations, rubber-stamping, unusual pricing or
conflicts of interest WITHOUT the words 'collusion'/'bid-rigging' would be
missed. This scan re-reads the FULL text of every non-ToR5 document with a
focused prompt asking for substantive evidence, not keyword matches.

Output: data/tor5_deep.json  {title: {relevant, confidence, evidence[], reasoning, tor5_angles[]}}
Concurrency: <=4 workers with long backoff (gateway soft-ban lesson: one job at
a time, <=4-5 concurrent, backoff 4+n*5s, retries).
"""
import argparse, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")

# Multiple LLM providers with automatic failover (HKBU gateway rate-limits hard;
# Poe + OpenRouter act as fallbacks so one provider's 429 doesn't stall the scan).
PROVIDERS = []
_provider_lock = __import__("threading").Lock()
_provider_down_until = {}   # name -> epoch time when provider re-enabled


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
                   "path": "/chat/completions?api-version=2024-02-01", "max_tokens": 600})
    if poe_key:
        ps.append({"name": "poe", "base": "https://api.poe.com/v1",
                   "model": "ChatGPT-4o-mini", "headers": {"Authorization": "Bearer " + poe_key},
                   "path": "/chat/completions", "max_tokens": 600})
    if or_key:
        ps.append({"name": "openrouter", "base": "https://openrouter.ai/api/v1",
                   "model": "deepseek/deepseek-chat", "headers": {"Authorization": "Bearer " + or_key},
                   "path": "/chat/completions", "max_tokens": 800})
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


def load_api_key():
    return _read_creds()  # kept for compatibility; providers loaded separately


SYSTEM_PROMPT = (
    "You are an investigative research assistant for journalists covering the Hong Kong "
    "Independent Committee on the Fire at Wang Fuk Court (大埔宏福苑). "
    "Your task is to find EVIDENCE relevant to ToR 5 — systemic issues including collusion, "
    "bid-rigging, conflicts of interest and tender irregularities in the estate renovation works. "
    "IMPORTANT: you must look at the SUBSTANCE of the document, not just keywords. A document can "
    "be highly relevant to ToR 5 even if it never uses words like 'collusion', 'bid-rigging' or "
    "'cartel'. Indicators of relevance include (but are not limited to):\n"
    "- descriptions of how renovation contractors were selected or tenders run\n"
    "- repeated/suspicious pricing, identical bids, or unusually low quotes\n"
    "- contractors doing little or no work yet being paid/approved\n"
    "- officials or engineers approving work without inspection (rubber-stamping)\n"
    "- relationships/overlaps between contractors, subcontractors, consultants and owners' "
    "corporation members\n"
    "- missing, altered or fabricated documents (quotations, meeting minutes, notices)\n"
    "- an unqualified person performing licensed work (e.g. electricians, fire-service "
    "contractors)\n"
    "- complaints by residents or others about the tender or selection process\n\n"
    "Reply ONLY with a compact JSON object:\n"
    '{"relevant": true|false, "confidence": "high|medium|low", '
    '"evidence": ["short quote or precise paraphrase with context (max 2-3 per item)"], '
    '"reasoning": "one sentence: what the evidence shows and why it matters for ToR 5", '
    '"tor5_angles": ["one of: tender_irregularity|no_work_but_paid|unqualified_person|'
    'rubber_stamping|conflict_of_interest|doc_fraud|other"]}\n'
    "- relevant=true ONLY if the document contains concrete facts/claims about such conduct "
    "(not mere background about fire safety). If the document is not relevant, "
    "relevant=false with evidence=[] and a one-line reasoning.\n"
    "Do not add any text outside the JSON object."
)

USER_TEMPLATE = (
    "Document title: {title}\n\nDocument text (first ~7000 chars):\n{text}\n\n"
    "Does this document contain evidence relevant to ToR 5 (collusion, bid-rigging, conflicts of "
    "interest, tender irregularities) even if those exact words never appear?"
)


def load_api_key():
    with open(CREDS) as f:
        content = f.read()
    m = re.search(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)", content, re.I)
    if not m:
        sys.exit("HKBU Gen AI key not found in " + CREDS)
    return m.group(1)


def clean_text(md, max_chars=7000):
    """Strip markdown noise and collapse whitespace."""
    t = re.sub(r"^#{1,6}\s*", "", md, flags=re.M)          # headings
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)             # images
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)         # links -> text
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()[:max_chars]


def call_llm(api_key, model, title, text):
    user = USER_TEMPLATE.format(title=title, text=text)
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
                p["base"] + p["path"],
                json=body,
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
            parsed.setdefault("relevant", False)
            parsed.setdefault("confidence", "low")
            parsed.setdefault("evidence", [])
            parsed.setdefault("reasoning", "")
            parsed.setdefault("tor5_angles", [])
            return parsed
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
        text = clean_text(raw)
        parsed = call_llm(None, None, title, text)
        return title, {
            "relevant": parsed["relevant"],
            "confidence": parsed["confidence"],
            "evidence": parsed["evidence"],
            "reasoning": parsed["reasoning"],
            "tor5_angles": parsed["tor5_angles"],
            "provider": parsed.get("_provider", ""),
            "ok": True,
        }
    except Exception as e:
        return title, {
            "relevant": False,
            "confidence": "low",
            "evidence": [],
            "reasoning": f"ERROR: {type(e).__name__}: {str(e)[:150]}",
            "tor5_angles": [],
            "provider": "",
            "ok": False,
        }


_launch_clock = [0.0]
import threading

_lock = threading.Lock()


def _throttle(seconds):
    """Space out submissions to avoid the HKBU gateway rate limit (429)."""
    with _lock:
        wait = _launch_clock[0] - time.time()
        if wait > 0:
            time.sleep(wait)
        _launch_clock[0] = time.time() + seconds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="gpt-4.1-mini")
    ap.add_argument("--out", default="data/tor5_deep.json")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max_retries", type=int, default=4)
    args = ap.parse_args()

    index = json.load(open("data/index.json"))
    docs = index["docs"]
    analysis = json.load(open("data/analysis.json"))

    # target = docs NOT tagged ToR5 (the ones keyword/summary reading missed)
    todo = []
    for d in docs:
        tags = analysis.get(d["title"], {}).get("tor_tags", [])
        if any("ToR5" in t for t in tags):
            continue
        todo.append(d)
    if args.limit:
        todo = todo[: args.limit]
    print(f"Non-ToR5 docs to deep-scan: {len(todo)} (workers={args.workers})")

    out_path = args.out
    results = {}
    if os.path.exists(out_path):
        results = json.load(open(out_path))
        print(f"Resuming: {len(results)} already scanned")
    todo = [d for d in todo if d["title"] not in results]

    api_key = load_api_key()
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
                    print(f"[{done}/{len(tasks)}] FAIL {title[:60]}: {rec['reasoning'][:100]}")
                if done % 10 == 0:
                    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
                    print(f"  [{done}/{len(tasks)}] ok={batch_ok} fail={batch_fail} elapsed={time.time()-t0:.0f}s")
                # gentle pacing so we never burst past the gateway rate limit
                _throttle(1.0)

        json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
        ok += batch_ok
        fail += batch_fail

        # retry failed ones after backoff
        todo = [d for d in todo if d["title"] not in results]
        if todo and round_no < args.max_retries - 1:
            wait = 4 + round_no * 10
            print(f"Retry round {round_no+1}: {len(todo)} left, sleeping {wait}s")
            time.sleep(wait)

    # summary
    rel = [t for t, r in results.items() if r.get("relevant")]
    print(f"\nDone. scanned={len(results)} ok={ok} fail={fail}")
    print(f"RELEVANT (evidence of ToR5-type conduct despite no ToR5 tag): {len(rel)}")
    from collections import Counter
    ang = Counter()
    for t, r in results.items():
        if r.get("relevant"):
            for a in r.get("tor5_angles", []):
                ang[a] += 1
    print("angles:", dict(ang))
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
