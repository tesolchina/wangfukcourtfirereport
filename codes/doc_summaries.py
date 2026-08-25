#!/usr/bin/env python3
"""DOC_SUMMARIES — generate a proper 2–3 sentence narrative summary for every
document, using the LLM's deep-analysis key points + themes + document opening.

Why: doc pages currently show doc_full_summary() = the first ~350 words of the
extracted text. For long documents (closing addresses, transcripts, reports)
that is cover/TOC/intro boilerplate, not a summary. This script asks the LLM to
write a genuine summary from the key points it already extracted.

Output: data/doc_summaries.json  {title: {"summary": "...", "ok": bool}}
Consumers: build_site.doc_full_summary() prefers this when present.
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")

# ---------- provider stack (shared pattern: hkbu → poe → openrouter) ----------
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
                   "path": "/chat/completions?api-version=2024-02-01", "max_tokens": 400})
    if poe_key:
        ps.append({"name": "poe", "base": "https://api.poe.com/v1",
                   "model": "ChatGPT-4o-mini", "headers": {"Authorization": "Bearer " + poe_key},
                   "path": "/chat/completions", "max_tokens": 400})
    if or_key:
        ps.append({"name": "openrouter", "base": "https://openrouter.ai/api/v1",
                   "model": "deepseek/deepseek-chat", "headers": {"Authorization": "Bearer " + or_key},
                   "path": "/chat/completions", "max_tokens": 600})
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
    "You are a research assistant summarising Hong Kong inquiry documents for "
    "journalists. Write a concise 2–3 sentence summary of a document, in the "
    "document's own language. Base it on the key points and themes provided — do "
    "not invent details. Reply ONLY with a plain JSON object: "
    '{"summary": "2-3 sentences, neutral, factual."}'
)

USER_TEMPLATE = (
    "Document title: {title}\n"
    "Document type hint: {dtype}\n"
    "Key points from deep analysis:\n{kp}\n"
    "Themes: {th}\n"
    "First lines of the document:\n{opening}\n"
    "Write a 2-3 sentence summary."
)


def clean_text(md, max_chars=1200):
    t = re.sub(r"^#{1,6}\s*", "", md, flags=re.M)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()[:max_chars]


def call_llm(title, dtype, kp, themes, opening):
    user = USER_TEMPLATE.format(
        title=title, dtype=dtype,
        kp="\n".join("- " + k for k in kp[:6]) or "(none)",
        th=", ".join(themes[:5]) or "(none)",
        opening=opening or "(no extractable text — scanned document)",
    )
    last_err = None
    for p in PROVIDERS:
        if not _provider_usable(p):
            continue
        body = {"model": p["model"], "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ], "temperature": 0.3, "max_tokens": p["max_tokens"]}
        try:
            resp = requests.post(p["base"] + p["path"], json=body,
                                 headers=dict(p["headers"], **{"Content-Type": "application/json"}),
                                 timeout=120)
            if resp.status_code == 429:
                _mark_provider(p)
                last_err = f"429 from {p['name']}"
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(json)?\s*", "", content.strip())
            content = re.sub(r"\s*```$", "", content)
            parsed = json.loads(content)
            s = (parsed.get("summary") or "").strip()
            if s:
                return s
            last_err = "empty summary"
        except Exception as e:
            last_err = f"{p['name']}: {type(e).__name__}: {str(e)[:80]}"
            continue
    raise RuntimeError(f"all providers failed: {last_err}")


def process_one(d):
    title = d["title"]
    try:
        slug = os.path.splitext(os.path.basename(d.get("local_md", "")))[0]
        md_path = os.path.join("data", "markdown", f"{slug}.md")
        opening = ""
        if os.path.exists(md_path):
            opening = clean_text(open(md_path, encoding="utf-8", errors="ignore").read())
        ana = json.load(open("data/analysis.json")).get(title, {})
        meta = json.load(open("data/doc_meta.json")).get(title, {})
        kp = ana.get("key_points") or []
        themes = ana.get("themes") or []
        dtype = meta.get("doc_type_detail") or meta.get("doc_type") or ""
        s = call_llm(title, dtype, kp, themes, opening)
        return title, {"summary": s, "ok": True}
    except Exception as e:
        return title, {"summary": "", "ok": False, "note": f"{type(e).__name__}: {str(e)[:120]}"}


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--max_retries", type=int, default=4)
    ap.add_argument("--out", default="data/doc_summaries.json")
    args = ap.parse_args()

    docs = json.load(open("data/index.json"))["docs"]
    if args.limit:
        docs = docs[: args.limit]
    print(f"docs: {len(docs)} (workers={args.workers})")

    out_path = args.out
    results = {}
    if os.path.exists(out_path):
        results = json.load(open(out_path))
        print(f"resuming: {len(results)} done")
    todo = [d for d in docs if d["title"] not in results]

    load_providers()
    print(f"providers: {[p['name'] for p in PROVIDERS]}", flush=True)
    t0 = time.time()
    ok = fail = 0

    for round_no in range(args.max_retries):
        if not todo:
            break
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(process_one, d): d["title"] for d in todo}
            done = 0
            for fut in as_completed(futs):
                title, rec = fut.result()
                done += 1
                if rec["ok"]:
                    results[title] = rec
                    ok += 1
                else:
                    fail += 1
                    print(f"[{done}/{len(todo)}] FAIL {title[:60]}: {rec.get('note','')[:80]}", flush=True)
                if done % 10 == 0:
                    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
                    print(f"  [{done}/{len(todo)}] ok={ok} fail={fail} elapsed={time.time()-t0:.0f}s", flush=True)
                # gentle pacing
                time.sleep(0.3)
        json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)
        todo = [d for d in todo if d["title"] not in results]
        if todo and round_no < args.max_retries - 1:
            wait = 4 + round_no * 10
            print(f"retry round {round_no+1}: {len(todo)} left, sleeping {wait}s", flush=True)
            time.sleep(wait)

    print(f"done. ok={ok} fail={fail} total={len(results)}")
    json.dump(results, open(out_path, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
