#!/usr/bin/env python3
"""
Minimal RAG (retrieval-augmented generation) over the Wang Fuk Court fire inquiry corpus.

Retrieval: BM25-style keyword scoring over each document's title, themes, key points
and summary (all precomputed in data/index.json + data/analysis.json).

Generation: sends the question + top-k retrieved document summaries to the HKBU GenAI
gateway and returns a cited answer.

Usage:
  python3 codes/rag_query.py "Did the sprinklers work on the night of the fire?"
  python3 codes/rag_query.py --top-k 5 "What did the Competition Commission find about bid-rigging?"

This is the prototype behind the "RAG / Karpathy llm-wiki" exploration (plan L41): the
"llm wiki" is the per-document summaries + ToR narratives the pipeline already generates;
this script turns the corpus into a queryable knowledge base for journalists.
"""
import argparse, json, math, os, re, sys
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS = os.path.expanduser("~/Documents/FITE/GoogleAccess.md")
BASE = "https://genai.hkbu.edu.hk/general/rest/deployments"
API_VERSION = "2024-02-01"


def load_corpus():
    idx = json.load(open(os.path.join(ROOT, "data", "index.json")))["docs"]
    ana = json.load(open(os.path.join(ROOT, "data", "analysis.json")))
    docs = []
    for d in idx:
        a = ana.get(d["title"], {})
        docs.append({
            "title": d["title"],
            "url": d.get("url", ""),
            "summary": d.get("summary", ""),
            "text": " ".join([
                d.get("title", ""),
                " ".join(a.get("themes", [])),
                " ".join(a.get("key_points", [])),
                d.get("summary", ""),
            ]).lower(),
            "tor": a.get("tor_tags") or d.get("related_to_tor") or [],
        })
    return docs


def tokenize(s):
    return re.findall(r"[a-z0-9]{3,}", s.lower())


def bm25(query, docs, k1=1.5, b=0.75, top_k=5):
    q_tokens = tokenize(query)
    N = len(docs)
    doc_lens = [len(tokenize(d["text"])) for d in docs]
    avg = (sum(doc_lens) / N) if N else 1
    scores = []
    for d, L in zip(docs, doc_lens):
        tokens = tokenize(d["text"])
        tf = {t: tokens.count(t) for t in set(tokens)}
        idf = {}
        for t in q_tokens:
            n = sum(1 for x in docs if t in tokenize(x["text"]))
            idf[t] = math.log(1 + (N - n + 0.5) / (n + 0.5)) if n else 0
        score = sum(
            idf[t] * (tf.get(t, 0) * (k1 + 1)) / (tf.get(t, 0) + k1 * (1 - b + b * L / avg))
            for t in q_tokens
        )
        scores.append(score)
    ranked = sorted(zip(docs, scores), key=lambda x: -x[1])[:top_k]
    return [(d, s) for d, s in ranked if s > 0]


def ask(query, top_k):
    docs = load_corpus()
    hits = bm25(query, docs, top_k=top_k)
    if not hits:
        print("No documents matched the query.")
        return
    context = "\n\n".join(
        f"[{i+1}] {d['title']} (ToR: {', '.join(d['tor'][:3])})\n{d['summary'][:800]}"
        for i, (d, _) in enumerate(hits)
    )
    with open(CREDS) as f:
        m = re.search(r"HKBU Gen AI API Key=\s*([A-Za-z0-9-]+)", f.read(), re.I)
    system = (
        "You are a research assistant for journalists covering the Hong Kong Independent "
        "Committee on the Wang Fuk Court fire. Answer the question using ONLY the retrieved "
        "document summaries below. Cite documents by [n]. If the evidence is insufficient, "
        "say so. Be concise (max 150 words)."
    )
    resp = requests.post(
        f"{BASE}/gpt-4.1-mini/chat/completions?api-version={API_VERSION}",
        json={
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"QUESTION: {query}\n\nRETRIEVED DOCUMENTS:\n{context}"},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        },
        headers={"api-key": m.group(1)},
        timeout=120,
    )
    resp.raise_for_status()
    answer = resp.json()["choices"][0]["message"]["content"]
    print("Q:", query)
    print("\nA:", answer)
    print("\nSources:")
    for i, (d, s) in enumerate(hits, 1):
        print(f"  [{i}] {d['title']} (score {s:.2f}) — {d['url']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--top-k", type=int, default=4)
    args = ap.parse_args()
    ask(args.query, args.top_k)


if __name__ == "__main__":
    main()
