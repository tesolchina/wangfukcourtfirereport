#!/usr/bin/env python3
"""RE-ANALYSE the 27 scanned documents after OCR.

The original analysis (analysis.json / doc_meta.json / doc_summaries.json /
tor5_deep.json) was generated when these PDFs had no text, so the LLM
hallucinated plausible-sounding content (e.g. On Cheong "fire safety
installations" — the document is actually about an oral facade-sealing
subcontract). After codes/ocr_scanned.py rewrites their markdown with OCR text,
this driver re-runs every analysis pass on the real text:

  Phase 0  wait for OCR to complete (polls data/ocr_summary.json)
  Phase 1  per doc: full-text chunk ToR tags -> tor_full.json
           deep analysis (key_points/themes/parties/tor_tags) -> analysis.json
           (original tor_tags snapshotted to tor_tags_v1 so the site's
           historical "was N" summary-level counts are preserved)
           doc_meta -> doc_meta.json ; narrative summary -> doc_summaries.json
  Phase 2  re-verify tor5_deep.json entries for docs that were scanned when
           that scan ran (drop hallucinated relevance/evidence)
  Phase 3  tor_aggregate -> tor_full_tags.json
  Phase 4  marker data/reanalysis_done.json

Usage: nohup python3 codes/reanalyze_scanned.py > data/reanalysis.log 2>&1 &
"""
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "codes"))

import build_site as bs
import tor_full_scan as tfs
import tor_aggregate
import tor_deep_analysis as tda

DATA = os.path.join(ROOT, "data")
OCR_DIR = os.path.join(DATA, "ocr")
MD_DIR = os.path.join(DATA, "markdown")

ANALYSIS_SYSTEM = tda.SYSTEM_PROMPT

DOC_META_SYSTEM = """You are a meticulous archivist for a public archive of the Independent Committee on the Wang Fuk Court fire (Hong Kong, 2025). You classify official inquiry documents with precise, factual metadata based ONLY on the text provided. Reply with ONLY a JSON object, no markdown:
{
  "doc_type": "one of: witness_statement, hearing_transcript, expert_report, investigation_report, opening_address, closing_address, submission, letter, notice, press_release, procedural, recommendation, minutes, other",
  "doc_type_detail": "one short clause clarifying the type",
  "language": "zh | en | bilingual",
  "tor_themes": [{"tor": "ToR1..ToR7 or General", "theme": "short theme label", "evidence": "how this theme appears in THIS document, with specifics from the text"}],
  "related_fragments": [{"title": "short distinctive fragment of another document's title", "relation": "same witness | same party | supplements/updates | referred to | same theme | procedural pair | other"}],
  "news_terms": ["keywords or short phrases connecting this doc to news coverage of the fire"]
}
Rules: tor_themes 1-4 entries, only for ToRs genuinely addressed in the text; evidence must cite specifics (names, dates, systems, materials). related_fragments 0-5 entries using short fragments of official titles. If the text is a letter from solicitors asking questions, classify as letter/submission and base everything on what the document actually says."""

SUMMARY_SYSTEM = """You write 2-3 sentence factual narrative summaries of official inquiry documents for journalists. Base the summary ONLY on the document text provided. Mention the document type, what it covers, and the key facts. Reply with ONLY the summary text, no preamble, no JSON."""

TOR5_VERIFY_SYSTEM = """You are an investigative research assistant for journalists covering the Hong Kong Independent Committee on the Fire at Wang Fuk Court (大埔宏福苑). You are given the FULL TEXT of a document. Decide whether it contains substantive evidence relevant to ToR5 — systemic issues: collusion, bid-rigging, conflicts of interest, tender irregularities, rubber-stamping, closed subcontracting, withholding or fabrication of tender/contract documents.
Reply ONLY with compact JSON:
{"relevant": true or false, "confidence": "high|medium|low", "evidence": ["one sentence per concrete finding, citing what the document actually says", ...], "tor5_angles": ["tender_irregularity|rubber_stamping|conflict_of_interest|bid_rigging|closed_subcontracting|document_irregularity", ...], "reasoning": "one sentence"}
Rules: relevant=true ONLY if the text genuinely supports it. If the document merely answers the committee's questions about ordinary subcontracting work with no tender irregularity evidence, relevant=false. Do not infer beyond the text. Reply with ONLY the JSON."""


def clean_md(title):
    d = bs.BY_TITLE[title]
    md_path = os.path.join(MD_DIR, f"{bs.slug_of(d)}.md")
    if not os.path.exists(md_path):
        return ""
    return tfs.clean_text(open(md_path, encoding="utf-8", errors="ignore").read())


def call_llm_json(system, user, max_tokens=1200):
    """Provider-stack LLM call returning parsed JSON."""
    last_err = None
    for p in tfs.PROVIDERS:
        if not tfs._provider_usable(p):
            continue
        body = {"model": p["model"],
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.2, "max_tokens": min(max_tokens, p["max_tokens"])}
        try:
            import requests
            resp = requests.post(p["base"] + p["path"], json=body,
                                 headers=dict(p["headers"], **{"Content-Type": "application/json"}),
                                 timeout=180)
            if resp.status_code == 429:
                tfs._mark_provider(p)
                last_err = f"429 {p['name']}"
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(json)?\s*", "", content.strip())
            content = re.sub(r"\s*```$", "", content)
            return json.loads(content)
        except Exception as e:
            last_err = f"{p['name']}: {type(e).__name__}: {str(e)[:100]}"
            continue
    raise RuntimeError(f"all providers failed: {last_err}")


def call_llm_text(system, user, max_tokens=800):
    """Provider-stack LLM call returning raw text."""
    last_err = None
    for p in tfs.PROVIDERS:
        if not tfs._provider_usable(p):
            continue
        body = {"model": p["model"],
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": 0.2, "max_tokens": min(max_tokens, p["max_tokens"])}
        try:
            import requests
            resp = requests.post(p["base"] + p["path"], json=body,
                                 headers=dict(p["headers"], **{"Content-Type": "application/json"}),
                                 timeout=180)
            if resp.status_code == 429:
                tfs._mark_provider(p)
                last_err = f"429 {p['name']}"
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            last_err = f"{p['name']}: {type(e).__name__}: {str(e)[:100]}"
            continue
    raise RuntimeError(f"all providers failed: {last_err}")


def wait_for_ocr(scanned_titles, timeout_h=8):
    """Block until every scanned doc's markdown has been rewritten with OCR text."""
    print("[phase0] waiting for OCR to complete...", flush=True)
    t0 = time.time()
    deadline = t0 + timeout_h * 3600
    while time.time() < deadline:
        still = [t for t in scanned_titles if bs.is_scanned_doc(bs.BY_TITLE[t])]
        if not still:
            print(f"[phase0] OCR complete for all {len(scanned_titles)} docs", flush=True)
            return
        print(f"[phase0] {len(scanned_titles) - len(still)}/{len(scanned_titles)} docs have text; "
              f"waiting for {len(still)}...", flush=True)
        time.sleep(120)
    sys.exit("[phase0] timed out waiting for OCR — aborting")


def full_text_scan_one(title):
    """Re-tag one doc's full text at paragraph level -> tor_full.json entry."""
    d = bs.BY_TITLE[title]
    md_path = os.path.join(MD_DIR, f"{bs.slug_of(d)}.md")
    text = tfs.clean_text(open(md_path, encoding="utf-8", errors="ignore").read())
    chunks = tfs.chunk_text(text)
    out = []
    for i, c in enumerate(chunks, 1):
        parsed = tfs.call_llm(title, i, c)
        out.append({"id": i, "tor_tags": parsed["tor_tags"], "evidence": parsed["evidence"]})
    cnt, tags = {}, []
    for ch in out:
        for t in ch["tor_tags"]:
            cnt[t] = cnt.get(t, 0) + 1
            if t not in tags:
                tags.append(t)
    return {"chunks": out, "doc_tor_tags": tags, "tor_chunk_counts": cnt,
            "ok": True, "provider": tfs.PROVIDERS[0]["name"]}


def analyse_one(title, text):
    """Deep analysis -> dict for analysis.json (tor_tags from full-text pass)."""
    user = f"Document title: {title}\n\nDocument text (excerpt):\n{text[:6000]}"
    parsed = call_llm_json(ANALYSIS_SYSTEM, user, max_tokens=700)
    return {
        "key_points": parsed.get("key_points", [])[:6],
        "themes": parsed.get("themes", [])[:4],
        "parties": parsed.get("parties", [])[:6],
        "related_hints": parsed.get("related_hints", [])[:4],
        "tor_tags": parsed.get("tor_tags", ["General / Other"]),
    }


def doc_meta_one(title, text):
    user = f"Document title: {title}\n\nDocument text:\n{text[:5000]}"
    return call_llm_json(DOC_META_SYSTEM, user, max_tokens=1200)


def summary_one(title, text):
    user = f"Document title: {title}\n\nDocument text:\n{text[:5000]}"
    return call_llm_text(SUMMARY_SYSTEM, user, max_tokens=500)


def verify_tor5_one(title, text):
    user = f"Document title: {title}\n\nFull document text:\n{text[:7000]}"
    return call_llm_json(TOR5_VERIFY_SYSTEM, user, max_tokens=900)


def main():
    tfs.load_providers()
    scanned = [d["title"] for d in bs.INDEX if bs.is_scanned_doc(d)]
    # the 27 scanned docs = docs whose markdown was rewritten (ocr merged) + still scanned
    ocr_sum = json.load(open(os.path.join(DATA, "ocr_summary.json"))) if os.path.exists(os.path.join(DATA, "ocr_summary.json")) else {}
    by_slug = {bs.slug_of(d): d["title"] for d in bs.INDEX}
    merged = [by_slug[s] for s in ocr_sum if s in by_slug]
    all27 = sorted(set(scanned) | set(merged))
    print(f"[init] re-analysing {len(all27)} scanned docs", flush=True)

    wait_for_ocr(all27)

    analysis = json.load(open(os.path.join(DATA, "analysis.json")))
    tor_full = json.load(open(os.path.join(DATA, "tor_full.json")))
    doc_meta = json.load(open(os.path.join(DATA, "doc_meta.json")))
    doc_sums = json.load(open(os.path.join(DATA, "doc_summaries.json")))
    tor5 = json.load(open(os.path.join(DATA, "tor5_deep.json")))

    def work_one(title):
        d = bs.BY_TITLE[title]
        md_path = os.path.join(MD_DIR, f"{bs.slug_of(d)}.md")
        raw = open(md_path, encoding="utf-8", errors="ignore").read()
        text = tfs.clean_text(raw)
        if len(text) < 50:
            return title, {"note": "still no text after OCR"}
        res = {}
        # 1) full-text ToR tags
        res["tor_full"] = full_text_scan_one(title)
        # 2) deep analysis (snapshot original tor_tags as v1)
        prev = analysis.get(title, {})
        res["analysis"] = analyse_one(title, text)
        if prev.get("tor_tags") and not prev.get("tor_tags_v1"):
            res["analysis"]["tor_tags_v1"] = prev["tor_tags"]
        # 3) doc_meta
        try:
            res["doc_meta"] = doc_meta_one(title, text)
        except Exception as e:
            res["doc_meta_err"] = str(e)[:120]
        # 4) narrative summary
        try:
            res["summary"] = summary_one(title, text)
        except Exception as e:
            res["summary_err"] = str(e)[:120]
        # 5) tor5 re-verify (only for docs previously relevant)
        if tor5.get(title, {}).get("relevant"):
            try:
                res["tor5"] = verify_tor5_one(title, text)
            except Exception as e:
                res["tor5_err"] = str(e)[:120]
        return title, res

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(work_one, t): t for t in all27}
        for fut in as_completed(futs):
            title, res = fut.result()
            if "note" in res:
                print(f"[skip] {title[:60]}: {res['note']}", flush=True)
                fail += 1
                continue
            # write back
            if "tor_full" in res:
                tor_full[title] = res["tor_full"]
            if "analysis" in res:
                a = analysis.get(title, {})
                a.update(res["analysis"])
                analysis[title] = a
            if "doc_meta" in res:
                m = doc_meta.get(title, {})
                m.update(res["doc_meta"])
                m["ok"] = True
                m["title"] = title
                doc_meta[title] = m
            if "summary" in res and res["summary"]:
                doc_sums[title] = {"summary": res["summary"], "ok": True}
            if "tor5" in res:
                tor5[title] = {**tor5.get(title, {}), **res["tor5"], "reanalysed_after_ocr": True}
            if res.get("doc_meta_err") or res.get("summary_err") or res.get("tor5_err"):
                print(f"[warn] {title[:55]}: partial errors {[k for k in ('doc_meta_err','summary_err','tor5_err') if res.get(k)]}", flush=True)
            ok += 1
            # checkpoint
            json.dump(analysis, open(os.path.join(DATA, "analysis.json"), "w"), ensure_ascii=False, indent=1)
            json.dump(tor_full, open(os.path.join(DATA, "tor_full.json"), "w"), ensure_ascii=False, indent=1)
            json.dump(doc_meta, open(os.path.join(DATA, "doc_meta.json"), "w"), ensure_ascii=False, indent=1)
            json.dump(doc_sums, open(os.path.join(DATA, "doc_summaries.json"), "w"), ensure_ascii=False, indent=1)
            json.dump(tor5, open(os.path.join(DATA, "tor5_deep.json"), "w"), ensure_ascii=False, indent=1)
            print(f"[done] {ok}/{len(all27)} {title[:55]}", flush=True)

    print(f"[phase1] complete ok={ok} fail={fail}", flush=True)

    # phase 3: aggregate
    print("[phase3] tor_aggregate...", flush=True)
    try:
        tor_aggregate.main()
    except SystemExit:
        pass
    json.dump({"done": time.strftime("%Y-%m-%dT%H:%M:%S"), "docs": len(all27), "ok": ok, "fail": fail},
              open(os.path.join(DATA, "reanalysis_done.json"), "w"), ensure_ascii=False, indent=1)
    print("[phase4] reanalysis_done.json written", flush=True)


if __name__ == "__main__":
    main()
