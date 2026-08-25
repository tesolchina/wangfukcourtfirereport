#!/usr/bin/env python3
"""Build a mini full-text search engine index over all 243 documents.

- Tokenizer: jieba (Chinese word segmentation) + English words, lowercased,
  stopword-filtered. Title tokens get a field boost (3x) at query time.
- Inverted index (term -> postings [docId, tf]) with document frequencies,
  serialised compactly as parallel arrays for fast JSON load.
- BM25 ranking parameters (k1=1.5, b=0.75) applied client-side.
- Output: data/search_index.json  (docs meta + terms + df + postings + snippets)

Usage: python3 codes/search_build.py
"""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as bs

try:
    import jieba
    jieba.setLogLevel(60)
except ImportError:
    jieba = None

ROOT = bs.ROOT
DATA = bs.DATA
OUT = os.path.join(DATA, "search_index.json")

STOP = bs.STOPWORDS | set("""
said say says according including includes including also per via within among between under over
around after before during while where when why what which who whom whose however therefore moreover
also into onto upon again further since until unless because although though yet still only just
about above below across against along among around behind beside beyond down from inside into near
off onto outside over through throughout under up upon within without plus minus total number
exhibit exhibits annex annexes item items clause clauses schedule schedules""".split())

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def tokenize(text):
    """Tokenise: latin words (len>=2, not stop) + CJK as overlapping bigrams + singles.
    CJK bigrams keep both sides consistent so queries and index match without a
    shared segmenter."""
    toks = []
    for m in re.finditer(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower()):
        w = m.group(0)
        if w[0].isascii():
            if len(w) >= 2 and w not in STOP:
                toks.append(w)
        else:
            if len(w) == 1:
                toks.append(w)
            else:
                for i in range(len(w)):
                    toks.append(w[i])
                for i in range(len(w) - 1):
                    toks.append(w[i:i + 2])
    return toks


def main():
    docs_meta = []
    terms = {}          # term -> id
    df = []             # df[term_id]
    postings = []       # postings[term_id] = flat [docId, tf, docId, tf, ...]
    doc_fields = []     # per doc: title tokens (for boost)

    for d in bs.INDEX:
        doc_id = len(docs_meta)
        title = d["title"]
        a = bs.ana(d)
        cross = bs.doc_cross_summary(d)
        cross_txt = cross[1] if cross else ""
        body = " ".join([
            bs.clean_doc_text(d),
            d.get("summary") or "",
            cross_txt,
            *a.get("themes", []),
            *a.get("key_points", []),
        ])
        zh = ""
        if bs.CROSS_LANG.get(title, {}).get("direction") == "zh":
            zh = bs.CROSS_LANG[title].get("summary_zh", "")
        docs_meta.append({
            "id": doc_id, "num": bs.DOC_NUM.get(title, 0), "slug": bs.slug_of(d),
            "title": title, "type": bs.doc_type_label(d),
            "lang": bs.LANG_LABEL.get(bs.doc_language(d), "English"),
            "tor": bs.doc_tor_tags(d)[:2],
            "pages": d.get("pages") or 0, "images": d.get("images") or 0,
            "url": d.get("url", ""),
            "snippet": (bs.clean_doc_text(d) or d.get("summary") or "")[:360],
            "zh": zh[:200],
        })
        # title tokens (boosted field) + body tokens
        title_toks = tokenize(title)
        body_toks = tokenize(body)
        tf = {}
        for t in title_toks:
            tf[t] = tf.get(t, 0) + 3.0          # title boost x3
        for t in body_toks:
            tf[t] = tf.get(t, 0) + 1.0
        doc_fields.append((doc_id, title_toks))
        for t, f in tf.items():
            if t not in terms:
                terms[t] = len(terms)
                df.append(0)
                postings.append([])
            tid = terms[t]
            postings[tid].extend([doc_id, f])

    # compute df
    for tid, pl in enumerate(postings):
        seen = set()
        for i in range(0, len(pl), 2):
            seen.add(pl[i])
        df[tid] = len(seen)

    # compact serialisation: terms array + df array + postings array
    term_list = [None] * len(terms)
    for t, tid in terms.items():
        term_list[tid] = t

    avg_len = None  # not used in this simple BM25 (we use tf only + df idf)
    index = {
        "v": 1,
        "num_docs": len(docs_meta),
        "docs": docs_meta,
        "terms": term_list,
        "df": df,
        "postings": postings,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT) / 1e6
    print(f"terms: {len(terms):,}  docs: {len(docs_meta)}  index size: {size:.1f} MB")
    print("sample terms:", term_list[:8], "...", term_list[-5:] if len(term_list) > 5 else "")
    print("saved -> data/search_index.json")


if __name__ == "__main__":
    main()
