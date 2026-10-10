#!/usr/bin/env python3
"""
Build the revamped multi-page static site for the Wang Fuk Court Fire Report.

Reads data/index.json (243 docs) + data/analysis.json (243/243 LLM analysis) and
emits an interrelated set of HTML pages into site_out/:

  index.html        home: hero, stats, ToR cards, insights
  documents.html    searchable/filterable document index (?tor= param)
  tor.html          Terms of Reference index (narratives)
  about.html        credits + disclaimer
  news.html         news-coverage analysis (placeholder for item 8)
  doc/<slug>.html   one page per document (v1: summary, ToC, key points,
                    original PDF link, related docs, ToR tags)

Usage: python3 codes/build_site.py
"""
import json, os, re, html as htmlmod, datetime, glob
from urllib.parse import quote as urlquote
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "site_out")

INDEX = json.load(open(os.path.join(DATA, "index.json")))["docs"]
try:
    ZH_INDEX = json.load(open(os.path.join(DATA, "index_zh.json")))["docs"]
except (FileNotFoundError, KeyError):
    ZH_INDEX = []  # Chinese corpus optional; see codes/build_zh_index.py
ANALYSIS = json.load(open(os.path.join(DATA, "analysis.json")))
NEWS = json.load(open(os.path.join(DATA, "news_analysis.json")))


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

# Published letter + open-source press data (data/press.json)
PRESS = _load_json(os.path.join(DATA, "press.json"), {})

# Vision descriptions (data/image_descriptions.json) + triage inventory — may be
# empty/partial while codes/image_vision.py is running; the builder degrades
# gracefully to heuristic filtering.
IMAGE_DESC = _load_json(os.path.join(DATA, "image_descriptions.json"), {})
IMAGE_INV = _load_json(os.path.join(DATA, "image_inventory.json"), {})
_JUNK_LABELS = ("junk_tiny", "blank", "low_value", "unreadable")

# Enriched document metadata (data/doc_meta.json) — doc_type, language,
# per-ToR themes, related fragments, news terms. Empty/partial while
# codes/doc_meta.py is running.
DOC_META = _load_json(os.path.join(DATA, "doc_meta.json"), {})

# Work ledger (data/work_ledger.json) — estimated person-hours per doc/ToR.
WORK = _load_json(os.path.join(DATA, "work_ledger.json"), {})
WORK_BY_TITLE = WORK.get("docs", {})

LANG_LABEL = {"zh": "中文", "en": "English", "bilingual": "Bilingual"}
TYPE_LABEL = {
    "witness_statement": "Witness statement", "hearing_transcript": "Hearing transcript",
    "expert_report": "Expert report", "investigation_report": "Investigation report",
    "opening_address": "Opening address", "closing_address": "Closing address",
    "submission": "Legal submission", "letter": "Letter / reply",
    "notice": "Notice", "press_release": "Press release", "procedural": "Procedural",
    "recommendation": "Recommendation", "minutes": "Minutes", "other": "Other",
}

NEWS_THEME_KEYWORDS = {
    "T1": ["smoking", "cigarette", "ignition", "light well", "fire cause", "fire origin", "fire spread", "煙頭"],
    "T2": ["alarm", "sprinkler", "hydrant", "hose reel", "fire service installation", "water tank", "pump room", "消防", "警鐘"],
    "T3": ["foam", "styrofoam", "netting", "scaffold", "cladding", "window board", "棚網", "發泡"],
    "T4": ["inspection", "supervision", "rubber stamp", "labour department", "fire services department", "independent checking unit", "icu", "regulatory", "巡查", "監管"],
    "T5": ["collusion", "bid-rig", "tender", "proxy vote", "icac", "corruption", "connected interest", "competition", "圍標"],
    "T6": ["law", "penalty", "regulation", "ordinance", "honour system", "prosecution", "legislation", "法例"],
    "T7": ["reform", "recommendation", "smart tender", "improvement", "sweeping", "改革"],
}


def doc_language(doc):
    """Best-effort language: title markers, then LLM metadata, then default en."""
    t = doc["title"]
    if "(Chinese only)" in t:
        return "zh"
    if "(English only)" in t:
        return "en"
    m = DOC_META.get(t, {}).get("language")
    if m in LANG_LABEL:
        return m
    return "en"


def doc_type_label(doc):
    t = DOC_META.get(doc["title"], {}).get("doc_type") or "other"
    return TYPE_LABEL.get(t, t.replace("_", " ").title())


def doc_type_detail(doc):
    return (DOC_META.get(doc["title"], {}).get("doc_type_detail") or "").strip()


def doc_news_matches(doc, ana_cache=None):
    """Return list of (theme_id, theme_title) for news themes this doc supports.
    Match: doc news_terms (LLM) + key_points + themes against theme keywords."""
    meta = DOC_META.get(doc["title"], {})
    hay = " ".join([doc["title"], doc.get("summary") or "",
                     " ".join(meta.get("news_terms") or []),
                     " ".join((ana_cache or {}).get(doc["title"], {}).get("key_points", [])),
                     " ".join((ana_cache or {}).get(doc["title"], {}).get("themes", []))]).lower()
    out = []
    for th in NEWS.get("themes", []):
        kws = th.get("keywords") or []
        if any(k.lower() in hay for k in kws):
            out.append((th["id"], th["title"]))
    return out


STOPWORDS = set("""a an and are as at be by for from has have in is it its of on or that the this to was were with
would will can could should may might not no nor so than then there these they those their he she his her
we you your our mr mrs ms dr page pages appendix annex part section paragraph figure table per cent
committee independent court fire wang fuk court fire services department government inquiry investigation
report statement evidence witness information document documents hong kong tai po november december january
february march april may june july august september october november 2025 2026""".split())


def doc_terms(doc, cap=300):
    """Unique significant terms from the full text, for deep-text search."""
    txt = clean_doc_text(doc).lower()
    words = re.findall(r"[a-z0-9\u4e00-\u9fff]+", txt)
    terms = set()
    for w in words:
        if w in STOPWORDS or len(w) < 5:
            continue
        terms.add(w)
        if len(terms) >= cap:
            break
    return terms


# Journalistic hot topics — always indexed when present in a document
HOT_TERMS = """smoking cigarette ignition lightwell foam styrofoam netting scaffold cladding
hydrant hose reel sprinkler alarm pump tank fireproof evacuation casualty death deaths victim
victims dead toll missing injured arrest arrested charge charges manslaughter corruption collusion
tender tenders bid bidding proxy vote votes renovation maintenance inspection licence licensed
compensation buyout rebuild displacement tenants owner owners management committee corporation
witness hearsay timeline chronology sequence cause origin spread intensity burn firefighter firemen
rescue extinguisher extinguishing lockdown lockdowns stairwell staircase exit exits escape
electrical wiring fuse switch breaker power supply utility utilities water supply drainage
gas stove cooker kitchen cooking incense altar candle lantern paper carton box boxes debris
rubbish waste illegal obstruction blockage cladding facade curtain wall glass panel window windows
ladder crane hoist equipment machinery worker workers contractor subcontractor subcontractors
architect engineer consultant supervision supervisor inspector check checking approval approve
approved certified certification certificate standard compliance noncompliance fine fines penalty
penalties prosecution court tribunal lawsuit claim claims damages civil criminal disciplinary
regulation regulations law laws ordinance ordinance statute legislation guideline guidelines
policy policies scheme schemes fund funding subsidy subsidised public housing home ownership""".split()


def doc_search_terms(doc, cap=220):
    """Deep-text terms for search: hot topics guaranteed + most frequent others."""
    terms = doc_terms(doc)
    txt = clean_doc_text(doc).lower()
    freq = Counter(re.findall(r"[a-z0-9\u4e00-\u9fff]+", txt))
    hot = [t for t in HOT_TERMS if t in terms]
    others = [t for t in sorted(terms, key=lambda w: -freq.get(w, 0)) if t not in hot]
    return hot + others[: max(0, cap - len(hot))]


def resolve_doc_fragment(frag):
    """Resolve a short title fragment to a doc title or None (normalised matching)."""
    f = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (frag or "").lower())
    if len(f) < 4:
        return None
    for d in _DOC_ORDER:
        t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", d["title"].lower())
        if f in t:
            return d["title"]
    return None


CROSS_LANG = _load_json(os.path.join(DATA, "cross_lang.json"), {})


def clean_doc_text(doc):
    """Reflow a document's markdown into plain readable paragraphs (no page markers,
    no URL boilerplate, single-line breaks joined). Returns '' if no text."""
    slug = slug_of(doc)
    p = os.path.join(DATA, "markdown", f"{slug}.md")
    if not os.path.exists(p):
        return ""
    try:
        t = open(p, encoding="utf-8", errors="ignore").read()
    except Exception:
        return ""
    t = re.sub(r"^---\s*Page\s+\d+\s*---\s*$", "\n\n", t, flags=re.M)
    t = re.sub(r"^[\-\*_]{3,}\s*$", "\n", t, flags=re.M)    # horizontal rules
    t = re.sub(r"^#{1,4}\s+.*$", "", t, flags=re.M)          # drop headings
    t = re.sub(r"^\*\*[^*]+\*\*.*$", "", t, flags=re.M)     # drop **Label** lines
    t = re.sub(r"^[-*]\s+.*$", "", t, flags=re.M)             # drop list lines
    t = re.sub(r"(?m)^Source:.*$|^Local PDF:.*$|^Pages:.*$|^Images extracted:.*$|^Converted:.*$|^Metadata\s*$|^Author:.*$|^Subject:.*$|^Creator:.*$|^Producer:.*$", "", t)
    paras = []
    for blk in t.split("\n\n"):
        lines = [ln.strip() for ln in blk.splitlines() if ln.strip()]
        if lines:
            paras.append(" ".join(lines))
    return "\n\n".join(paras).strip()


def is_scanned_doc(doc):
    """True when a document has no meaningful extracted text (scanned PDF without
    OCR): cleaned text under 50 characters. md_to_html still emits page-marker
    HTML for such files, so callers must test this rather than full_html truthiness."""
    return len(clean_doc_text(doc).strip()) < 50


# Injected into every document page: lets #page-N links (ToC, citations, shared
# URLs) open the (collapsed) full-document section and scroll to the exact page.
# Works for text docs (.doc-page#page-N) and scanned docs (.scan-page#page-N).
DOC_ANCHOR_JS = """<script>
(function(){
  function expandAndScroll(){
    var h = location.hash;
    if (!h || h.indexOf('#page-') !== 0) return;
    var d = document.querySelector('.full-doc');
    if (d && !d.open) d.open = true;
    var el = document.getElementById(h.slice(1));
    if (el) setTimeout(function(){ el.scrollIntoView({block:'start'}); }, 60);
  }
  window.addEventListener('hashchange', expandAndScroll);
  expandAndScroll();
})();
</script>"""


# LLM narrative summaries (data/doc_summaries.json, from codes/doc_summaries.py) —
# preferred over the raw text excerpt, which for long documents is just cover/TOC text.
DOC_SUMMARIES = _load_json(os.path.join(DATA, "doc_summaries.json"), {})


def scanned_page_images(doc):
    """For scanned documents (no OCR text), return page-sorted list of image
    filenames covering the pages, so the full document can be read as images.
    Uses triage labels: prefer page_scan/photo per page; falls back to any image."""
    slug = slug_of(doc)
    files = [f for f in os.listdir(os.path.join(DATA, "images")) if f.startswith(slug + "_")]
    if not files:
        return []
    inv_imgs = IMAGE_INV.get("images", {}) if isinstance(IMAGE_INV.get("images", {}), dict) else {}
    # one representative image per page, page order
    by_page = {}
    for f in files:
        m = re.search(r"_p(\d+)_img(\d+)", f)
        if not m:
            continue
        pg, img = int(m.group(1)), int(m.group(2))
        label = (inv_imgs.get(f) or {}).get("label", "")
        score = {"page_scan": 3, "photo": 2, "diagram": 1, "blank": 0, "junk_tiny": 0}.get(label, 1)
        cur = by_page.get(pg)
        if cur is None or score > cur[0]:
            by_page[pg] = (score, f, img)
    return [by_page[p][1] for p in sorted(by_page)]


def doc_full_summary(doc):
    """Complete summary for a document: the LLM narrative summary when available,
    else a clean-text excerpt, else the index summary."""
    s = DOC_SUMMARIES.get(doc["title"], {}).get("summary")
    if s and s.strip():
        return s.strip()
    # clean-text excerpt for text documents
    txt = clean_doc_text(doc)
    words = re.split(r"\s+", txt)
    if len(words) >= 120:
        excerpt = " ".join(words[:350])
        return excerpt + (" …" if len(words) > 350 else "")
    # scanned document: fall back to the index summary (short but all we have)
    return (doc.get("summary") or "").strip()


def doc_cross_summary(doc):
    """(language_label, text) of the cross-language LLM summary, or None."""
    v = CROSS_LANG.get(doc["title"], {})
    if v.get("direction") == "zh":
        s = (v.get("summary_zh") or "").strip()
        return ("繁體中文", s) if s else None
    s = (v.get("summary_en") or "").strip()
    return ("English", s) if s else None


def img_keep_and_caption(fname, pg):
    """Return (keep, caption_html, importance) for a gallery image.
    Uses the vision description when available; falls back to the triage label.
    The keep decision is based on the vision importance rating (★3+ counts as
    meaningful, including ★3 evidence pages such as tender-comparison scans);
    the separate keep flag is not used as a hard filter."""
    desc = IMAGE_DESC.get(fname)
    if desc and desc.get("ok"):
        subj = (desc.get("subject") or "").strip()
        try:
            imp = int(desc.get("importance") or 0)
        except Exception:
            imp = 0
        if imp >= 3:
            stars = "<span class='img-imp'>" + "★" * imp + "</span>" + "☆" * (5 - imp)
            cap = f"Page {pg} · {stars}"
            if subj:
                cap += f"<span class='img-sub'>{esc(subj)}</span>"
            return True, cap, imp
        return False, "", imp
    inv = IMAGE_INV.get("images", {}).get(fname)
    if inv and inv.get("label") in _JUNK_LABELS:
        return False, "", 0
    return True, f"Page {pg}", 1


_IMG_EX_COPIED = set()


def _copy_img_example(src_name, dest_name):
    """Copy an image from data/images into site_out/assets/img-examples (once).
    Returns the web-relative path (assets/img-examples/<dest>) or None on failure."""
    src = os.path.join(DATA, "images", src_name)
    if not os.path.exists(src):
        return None
    ex_dir = os.path.join(OUT, "assets", "img-examples")
    os.makedirs(ex_dir, exist_ok=True)
    dst = os.path.join(ex_dir, dest_name)
    if (src_name, dest_name) not in _IMG_EX_COPIED or not os.path.exists(dst):
        try:
            with open(src, "rb") as f:
                data = f.read()
            with open(dst, "wb") as f:
                f.write(data)
        except Exception:
            return None
        _IMG_EX_COPIED.add((src_name, dest_name))
    return "assets/img-examples/" + dest_name


def _img_ex_card(src_name, dest_name, title, desc_text, tag):
    """One example card: thumbnail + caption. tag in {"kept", "filtered"}."""
    rel = _copy_img_example(src_name, dest_name)
    if not rel:
        return ""
    tag_html = ('<span class="ex-tag ex-kept">Counted</span>' if tag == "kept"
                else '<span class="ex-tag ex-filtered">Filtered out</span>')
    return f"""
    <figure class="img-ex">
      <img loading="lazy" src="{esc(rel)}" alt="{esc(desc_text)}">
      <figcaption>{tag_html} <strong>{esc(title)}</strong><br><span class="muted">{esc(desc_text)}</span></figcaption>
    </figure>"""


def image_examples_html():
    """Curated 'counted vs filtered out' image examples for the About page.
    Picks high-importance kept photos/diagrams and typical filtered items
    (tiny fragment, blank) that exist on disk."""
    desc = IMAGE_DESC.get("images", IMAGE_DESC) if isinstance(IMAGE_DESC.get("images", {}), dict) else IMAGE_DESC
    inv_imgs = IMAGE_INV.get("images", {}) if isinstance(IMAGE_INV.get("images", {}), dict) else {}

    def exists(fn):
        return os.path.exists(os.path.join(DATA, "images", fn))

    # best kept photo (★5)
    kept_photo = next((k for k, v in desc.items()
                       if v.get("keep") and v.get("type") == "photo" and (v.get("importance") or 0) >= 5
                       and exists(k)), None)
    # best kept diagram (★5)
    kept_diag = next((k for k, v in desc.items()
                      if v.get("keep") and v.get("type") == "diagram" and (v.get("importance") or 0) >= 5
                      and exists(k)), None)
    # a tiny junk fragment and a blank
    junk = next((k for k, l in inv_imgs.items() if l.get("label") == "junk_tiny" and exists(k)), None)
    blank = next((k for k, l in inv_imgs.items() if l.get("label") == "blank" and exists(k)), None)

    cards = []
    if kept_photo:
        subj = (desc[kept_photo].get("subject") or "Photograph from the inquiry documents").strip()
        cards.append(_img_ex_card(kept_photo, "example-kept-photo.jpg", "Photograph (★5)", subj, "kept"))
    if kept_diag:
        subj = (desc[kept_diag].get("subject") or "Diagram from the inquiry documents").strip()
        cards.append(_img_ex_card(kept_diag, "example-kept-diagram.jpg", "Diagram / plan (★5)", subj, "kept"))
    if junk:
        cards.append(_img_ex_card(junk, "example-filtered-junk.jpg", "Layout fragment",
                                  "Tiny non-image fragment produced by PDF extraction", "filtered"))
    if blank:
        cards.append(_img_ex_card(blank, "example-filtered-blank.jpg", "Blank page",
                                  "Blank page with no content", "filtered"))
    if not cards:
        return ""
    return ('<div class="img-examples"><h4>Examples — counted vs filtered out</h4>'
            '<div class="img-ex-grid">' + "".join(cards) + "</div></div>")


# consistent document numbering (stable: sorted by title)
_DOC_ORDER = sorted(INDEX, key=lambda x: x["title"].lower())
DOC_NUM = {d["title"]: i for i, d in enumerate(_DOC_ORDER, 1)}
BY_TITLE = {d["title"]: d for d in INDEX}


def find_doc_slug(fragment):
    """Resolve a title fragment to a doc slug (local_md stem) or None."""
    frag = (fragment or "").strip().lower()
    if not frag:
        return None
    # normalise both sides: drop file ext, spaces, hyphens, underscores
    frag_n = "".join(ch for ch in frag if ch.isalnum())
    for d in INDEX:
        s = slug_of(d)
        s_n = "".join(ch for ch in s.lower() if ch.isalnum())
        if frag_n and frag_n == s_n:
            return s
    best = None
    best_len = 0
    for d in INDEX:
        s = slug_of(d)
        s_n = "".join(ch for ch in s.lower() if ch.isalnum())
        t_n = "".join(ch for ch in d["title"].lower() if ch.isalnum())
        if frag_n and (frag_n in s_n or frag_n in t_n):
            if len(frag_n) > best_len:
                best, best_len = s, len(frag_n)
    return best


def tor_href(tag):
    """ToR tag -> page href (or None for unknown)."""
    if tag in TOR_TAGS_BY_ID:
        return "tor/" + tag + ".html"
    if tag == "General / Other" or tag == "General":
        return "tor/GeneralOther.html"
    return None


def md_to_html(text):
    """Minimal markdown -> HTML with --- Page N --- anchors (#page-N).
    Reflows single-line breaks into paragraphs (PDF text extraction wraps lines)."""
    out = []
    # split on page markers
    parts = re.split(r"^---\s*Page\s+(\d+)\s*---\s*$", text, flags=re.M)

    def para(chunk):
        html = []
        buf = []
        def flush():
            if buf:
                html.append("<p>" + "<br>".join(esc(l) for l in buf) + "</p>")
                buf.clear()
        # first reflow: join hard-wrapped lines within a paragraph block
        block = []
        for raw in chunk.split("\n\n"):
            lines = [ln.rstrip() for ln in raw.splitlines()]
            lines = [ln for ln in lines if ln.strip()]
            if not lines:
                continue
            if re.match(r"^(#{1,4})\s", lines[0]):
                # heading block (keep each heading line)
                block.append("\n\n".join(lines))
            elif all(re.match(r"^\s*[-*]\s", ln) for ln in lines):
                block.append("\n\n".join(lines))   # list block, keep lines
            else:
                # prose: join wrapped lines with a single space
                block.append(" ".join(ln.strip() for ln in lines))
        for raw in "\n\n".join(block).split("\n\n"):
            s = raw.strip()
            if not s:
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", s)
            if m:
                lvl = len(m.group(1)); html.append(f"<h{lvl+1} class=\"md-h\">{esc(m.group(2))}</h{lvl+1}>"); continue
            m = re.match(r"^\s*[-*]\s+(.*)$", s)
            if m:
                html.append(f"<li class=\"md-li\">{esc(m.group(1))}</li>"); continue
            buf.append(s)
        flush()
        return "".join(html)

    if parts and parts[0].strip():
        out.append(f"<div class=\"md-block\">{para(parts[0])}</div>")
    for i in range(1, len(parts), 2):
        n = parts[i]
        out.append(f"<section class=\"doc-page\" id=\"page-{n}\"><h4 class=\"page-marker\">Page {n}</h4><div class=\"md-block\">{para(parts[i+1])}</div></section>")
    return "".join(out)

TOR_TAGS = [
    ("ToR1", "ToR1: Causes & Circumstances of Fire", "How the fire started, spread and caused casualties and damage"),
    ("ToR2", "ToR2: Fire Service Installations & Equipment", "Whether fire-service installations existed and worked, and who supervised them"),
    ("ToR3", "ToR3: Building Maintenance & Renovation Works", "Safety requirements, materials, and verification in the renovation works"),
    ("ToR4", "ToR4: Supervision, Roles & Responsibilities", "Who was responsible — officers, professionals, contractors, the committee"),
    ("ToR5", "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)", "Connected interests, collusion and bid-rigging in maintenance and renovation"),
    ("ToR6", "ToR6: Adequacy of Laws & Penalties", "Whether existing laws and penalties are adequate"),
    ("ToR7", "ToR7: Recommendations & Improvement Measures", "What should change so this never happens again"),
]
TOR_TAGS_BY_ID = {tid: (tid, title, blurb) for tid, title, blurb in TOR_TAGS}

TOR_NARRATIVES = {
    "ToR1: Causes & Circumstances of Fire": (
        "Start with the Inter-departmental Fire Investigation Task Force (IFITF) Interim and Final "
        "Investigation Reports, which reconstruct the night chronologically and technically. Pair them with "
        "the fire-engineering expert reports (Prof Usmani & Prof Jiang for the Committee; Prof Yuen for the "
        "Government) and the expert presentation slides, which test alternative hypotheses about ignition, "
        "spread and collapse. Resident and worker witness statements add the human timeline; cross-check "
        "dates and floor-by-floor details against the hearing transcripts to spot discrepancies the inquiry "
        "is itself testing."
    ),
    "ToR2: Fire Service Installations & Equipment": (
        "Begin with Fire Services Department evidence (Ir Dr To Chi Wing's witness statement and presentation "
        "slides) describing the systems and their condition on the night. Follow the maintenance chain: "
        "Victory Fire Engineering (the FSI contractor) and Hop On Management (property management) show who "
        "serviced the systems. The Competition Commission and ICAC reports under ToR 2 expose how FSI "
        "procurement may have been rigged; the transcripts show how each party defended its role when systems "
        "failed."
    ),
    "ToR3: Building Maintenance & Renovation Works": (
        "Map the procurement-to-site chain: the 12th Management Committee's responses describe how the "
        "renovation was commissioned; contractors' replies (Hang Fung, Hoi Tak, Fred & Willie, Red Sun, Tin "
        "Hung, Wang Hua Tian, On Cheong, Lam Kee Construction Materials) show materials and supervision; the "
        "Police witness statement on irregularities and the Competition Tribunal cartel case reveal how "
        "tender and material supply were manipulated. Read the URA opening and closing addresses for the "
        "regulator's account of renovation governance."
    ),
    "ToR4: Supervision, Roles & Responsibilities": (
        "Build an organisational chart from the List of Involved Parties and the witness statements of "
        "management committee members (e.g. Ku Siu Ping, Tang Wing Wah, Keung Sai Ming, Wong Sze Lut, Tsui "
        "Moon Come), then trace each decision and sign-off through the hearing transcripts. The Government's "
        "opening and closing addresses set out the official positions; the Rules of Procedure and Committee "
        "directions define how evidence was taken. Ask of every document: who knew, who decided, who signed."
    ),
    "ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)": (
        "Start with the ICAC report and the Competition Commission's report, press release and originating "
        "notice on the building-maintenance cartel submitted to the Competition Tribunal. The Commission's "
        "opening and closing addresses summarise the cartel mechanics (cover bidding, market allocation, "
        "price fixing); the Police statement on irregularities connects criminal patterns to specific "
        "renovation works. Compare company replies and witness statements to detect repeated names, "
        "overlapping directorships and unusual tender patterns."
    ),
    "ToR6: Adequacy of Laws & Penalties": (
        "Collect every legal provision invoked across the documents — building-safety ordinances, fire-"
        "services regulations, the Competition Ordinance, corruption offences, maintenance standards. The "
        "Government's closing address states the official view of the framework; legal submissions by law "
        "firms (e.g. Wong & Lawyers for Hang Fung and Hoi Tak) argue the limits of liability. Contrast what "
        "the law requires on paper with what the evidence shows happened."
    ),
    "ToR7: Recommendations & Improvement Measures": (
        "Gather every recommendations document: the fire-engineering experts' recommendations, the "
        "Government's submission for ToR 1 and 2, the Competition Commission's recommendations for ToR 2, "
        "the nine residents' recommendations, and the closing addresses of counsel. Compare who recommends "
        "what and where recommendations converge — statutory reform of fire-safety inspections, FSI "
        "maintenance accountability, tender transparency and competition enforcement."
    ),
    "General / Other": (
        "Procedural and support materials: the Committee's Terms of Reference, Rules of Procedure, "
        "appointments of counsel and experts, hearing notices and timetables, direction-conference "
        "transcripts, and lists of involved parties. Use them to understand the process and as a reference "
        "spine for the other perspectives."
    ),
}

NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def esc(s):
    return htmlmod.escape(str(s or ""), quote=True)


def slug_of(doc):
    stem = os.path.splitext(os.path.basename(doc.get("local_md", doc["title"])))[0]
    return stem


# Full-text paragraph-level ToR tags (data/tor_full_tags.json, from
# codes/tor_full_scan.py + tor_aggregate.py). Preferred over summary-level
# analysis.json tor_tags; degrades gracefully when absent.
TOR_FULL = _load_json(os.path.join(DATA, "tor_full_tags.json"), {})


def doc_tor_tags(doc):
    """Document-level ToR tags: full-text scan first, then analysis summary
    tags, then the original index metadata. Returns list of full tag strings."""
    ft = TOR_FULL.get(doc["title"], {})
    tags = ft.get("tor_tags") if isinstance(ft, dict) else None
    if tags:
        return tags
    a = ANALYSIS.get(doc["title"], {})
    tags = a.get("tor_tags")
    if tags:
        return tags
    return doc.get("related_to_tor") or ["General / Other"]


def doc_tor_chunk_counts(doc):
    ft = TOR_FULL.get(doc["title"], {})
    if isinstance(ft, dict):
        return ft.get("tor_chunk_counts") or {}
    return {}


def old_tor_counts():
    """Summary-level (analysis.json) ToR counts — the 'before' numbers kept
    in brackets alongside full-text counts, to show the effect of deeper
    reading. Docs re-analysed after OCR keep their ORIGINAL first-pass tags in
    tor_tags_v1 so the historical contrast is preserved."""
    c = Counter()
    for v in ANALYSIS.values():
        for t in (v.get("tor_tags_v1") or v.get("tor_tags") or []):
            c[t] += 1
    return c


def tor_first(doc):
    tags = doc_tor_tags(doc)
    return tags[0] if tags else "General / Other"


def tor_all(doc):
    return doc_tor_tags(doc)


def ana(doc):
    return ANALYSIS.get(doc["title"], {})


# ----------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------
NAV = [
    ("index.html", "Home", "M0 0h24v24H0z", "M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10"),
    ("documents.html", "Map & Documents", "M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10", "M3 12l9-9 9 9M5 10v10h5v-6h4v6h5V10"),
    ("zh-docs.html", "Chinese Docs \u4e2d\u6587", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("search.html", "Search", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("tor.html", "ToR Perspectives", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("work.html", "Work & Effort", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("news.html", "News & Coverage", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("letter.html", "Our Letter", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("engagement/legcoDraft.html", "Engagement", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("images.html", "All Images", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
    ("about.html", "About & Credits", "M4 6h16M4 12h16M4 18h16", "M4 6h16M4 12h16M4 18h16"),
]


def page(title, active, body_html, desc=""):
    nav_items = []
    for href, label, _i1, _i2 in NAV:
        cls = "active" if href == active else ""
        nav_items.append(f'<a class="nav-item {cls}" href="{href}">{label}</a>')
    nav = "\n".join(nav_items)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)} · Wang Fuk Court Fire Inquiry</title>
<meta name="description" content="{esc(desc)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <a class="brand" href="index.html">
      <span class="brand-mark">WF</span>
      <span class="brand-text"><strong>Wang Fuk Court</strong><small>Fire Inquiry · Reorganized</small></span>
    </a>
    <nav class="nav">
      {nav}
    </nav>
    <div class="sidebar-foot">
      <a href="https://www.ic-wangfukcourtfire.gov.hk/eng/index.html" target="_blank" rel="noopener">Original Committee Site ↗</a>
      <a href="zh/index.html" class="lang-switch">繁體中文版 →</a>
      <small>Educational use · by Dr Simon Wang</small>
      <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">Open source on GitHub ↗</a>
    </div>
  </aside>
  <main class="main">
    {body_html}
    <footer class="page-foot">
      <span>Data from the Independent Committee on the Wang Fuk Court fire · reorganized for journalists &amp; the public</span>
      <span class="muted">Built {NOW} · educational, non-commercial · <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">open source ↗</a></span>
    </footer>
  </main>
</div>
<script>document.querySelectorAll('a[href^="doc/"]').forEach(a=>a.setAttribute("target","_blank"));</script>
</body>
</html>"""


def stat_card(value, label, sub=""):
    sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
    return f'<div class="stat-card"><div class="stat-value">{esc(value)}</div><div class="stat-label">{esc(label)}</div>{sub_html}</div>'


# ----------------------------------------------------------------------------
# Home
# ----------------------------------------------------------------------------
def build_home():
    tor_counts = Counter()
    for d in INDEX:
        tor_counts[tor_first(d)] += 1
    ana_tor = Counter()
    for d in INDEX:
        for t in doc_tor_tags(d):
            ana_tor[t] += 1
    # old (summary-level) counts — kept in brackets to show the effect of deeper reading
    old_tor = old_tor_counts()
    old_tor5 = old_tor.get("ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)", 0)

    themes = Counter()
    for v in ANALYSIS.values():
        for th in (v.get("themes") or []):
            themes[th.strip().lower()] += 1
    top_themes = themes.most_common(8)

    tor_cards = []
    for key, tag, blurb in TOR_TAGS:
        n = ana_tor.get(tag, 0)
        o = old_tor.get(tag, 0)
        old_note = f' <span class="tor-old" title="Earlier summary-level reading found {o} docs; full-text reading found {n}">(was {o})</span>' if o != n else ""
        tor_cards.append(f"""
        <a class="tor-card" href="documents.html?tor={esc(urlquote(tag, safe=''))}">
          <div class="tor-card-top"><span class="tor-chip">{esc(key)}</span><span class="tor-count">{n} docs{old_note}</span></div>
          <div class="tor-card-title">{esc(tag.split(":",1)[1] if ":" in tag else tag)}</div>
          <div class="tor-card-blurb">{esc(blurb)}</div>
        </a>""")
    tor_method_note = (
        '<p class="muted tor-method-note">Counts are from full-text paragraph-level reading of all documents. '
        'Bracketed figures are the earlier summary-level counts — the difference shows how much relevant '
        'material is invisible to keyword or summary reading (see '
        '<a href="about.html#tor-counts">methodology</a>).</p>'
        if any(old_tor.get(t, 0) != ana_tor.get(t, 0) for _, t, _ in TOR_TAGS) else ""
    )
    theme_html = "".join(
        f'<span class="theme-chip">{esc(t)} <b>{n}</b></span>' for t, n in top_themes
    )

    body = f"""
    <section class="hero">
      <div class="hero-badge">INDEPENDENT COMMITTEE MATERIALS · REORGANIZED FOR JOURNALISTS</div>
      <h1>Wang Fuk Court <br>Fire Inquiry</h1>
      <p class="hero-sub">1.9 million words of inquiry material, reorganized by the Committee's
      Terms of Reference so journalists and the public can find the evidence by question — not by filing order.</p>
      <div class="hero-actions">
        <a class="btn btn-dark" href="documents.html">Browse all {len(INDEX)} documents</a>
        <a class="btn btn-ghost" href="tor.html">Explore the ToR framework</a>
      </div>
    </section>

    <section class="stats">
      {stat_card(len(INDEX), "Documents", "243 PDFs processed")}
      {stat_card(f"{sum(d.get('pages') or 0 for d in INDEX):,}", "Pages", "of reports & transcripts")}
      {stat_card('≈ 1,800', "Images", 'meaningful, after filtering <a class="stat-link" href="about.html#images">8,785 extracted</a>')}
      {stat_card("1,875,666", "Words", "≈ 1.9 million total")}
      {stat_card(f"{WORK.get('total_hours', 0):,.0f}", "Est. work hours", "see the Work &amp; Effort ledger") if WORK.get('total_hours') else ''}
    </section>

    <section class="block narrow">
      <h2>The fire and the Committee</h2>
      <p>On 26 November 2025, a fire broke out at Wang Fuk Court in Tai Po — a Home Ownership Scheme estate of eight blocks, built in 1983. All eight blocks were undergoing external renovation, wrapped in bamboo scaffolding and protective netting. The fire burned for about 43 hours, killing 168 people (including one firefighter) and injuring 79. At its peak, the Fire Services Department deployed 174 fire engines, 47 ambulances and 989 firefighters — the largest operation in the department's history.</p>
      <p>The Chief Executive announced an Independent Committee on 2 December 2025, formally established it on 12 December, and tasked it with completing its work within nine months. The Committee is chaired by a High Court judge. Its <a href="tor.html">Terms of Reference</a> cover four areas: (1) the fire's causes, spread and casualties, including fire-service installations and renovation works; (2) systemic issues — connected interests, collusion and bid-rigging in the maintenance works; (3) the adequacy of existing laws and penalties; and (4) recommendations. The Committee held 27 days of public hearings, heard 73 factual witnesses and 7 expert witnesses, and received nearly one million documents totalling over 1&nbsp;TB of data.</p>
    </section>

    <section class="block narrow">
      <h2>The government's site — and its weaknesses</h2>
      <p>The Committee has published its material on <a href="https://www.ic-wangfukcourtfire.gov.hk/eng/documents.html" target="_blank" rel="noopener">its official website</a> — 243 documents comprising investigation reports, expert reports, hearing transcripts, witness statements, closing addresses, replies from contractors and legal submissions. This is a remarkable act of transparency. But the material is arranged by the sequence of the Committee's work, not by the questions it was asked to answer. The site does have a search bar — powered by the generic GovHK search engine — but it indexes PDF filenames and cached text only, returns results as a flat list of links, and cannot filter by topic, show which page a term appears on, or group results by Terms of Reference. A search for "collusion" returns 30 links to PDFs; the user must still open each one and search within it manually. The 243 documents total 6,377 pages and roughly 1.9 million words — far more than any journalist or member of the public can read in full.</p>
    </section>

    <section class="block narrow">
      <h2>The Committee's findings — in brief</h2>
      <p>The Committee's own closing submissions, drawing on the full evidential record, identify a chain of systemic failures: a main contractor (宏業) that deliberately purchased non-fire-retardant scaffolding netting and used flammable foam boards to cover windows, while providing suspected forged test certificates; a registered fire-service contractor (中華發展) that filed shutdown notices without ever visiting the site, acting as a "rubber stamp"; a supervision consultant (鴻毅) that performed no effective oversight; and a property management company (置邦) that allowed unlicensed personnel to operate fire installations. The fire-service shutdown regime — designed to let the Fire Services Department monitor safety — was systematically abused. The Competition Commission and ICAC evidence shows that bid-rigging and collusion in the building maintenance industry are systemic and long-standing. The Committee's full closing submissions run to 627 pages; the key findings are summarised on each document page and in the <a href="tor.html">ToR perspectives</a> on this site.</p>
    </section>

    <section class="block narrow">
      <h2>What this site can do that the original cannot</h2>
      <p>The Committee's final report, when published, will present its conclusions. The government's document site gives you 243 PDFs in filing order. Neither lets you ask a question and get every relevant passage across every document. This site does. Here are specific questions a journalist or resident can answer here that they cannot answer from the final report alone or by browsing the government site:</p>
      <ul>
        <li><strong>"Which documents contain evidence on bid-rigging?"</strong> — The government site lists documents by date; the final report cites selected ones. Here, <a href="documents.html?tor=ToR5">99 documents</a> are tagged and listed, each with a summary of its relevance to collusion — including documents that never use the word "collusion" but describe oral subcontracts, rubber-stamp approvals, and work allocation controlled by the main contractor.</li>
        <li><strong>"What did each contractor actually say?"</strong> — The final report summarises; the government site gives you a 7-page PDF. Here, each contractor's reply is on its own page with a summary, key points, and a direct link to the exact passage — e.g., On Cheong's admission of an <a href="doc/Reply-On-Cheong.html#page-7">oral subcontract with no written contract</a>, or Tin Hung's statement that <a href="doc/Reply-Tin-Hung.html#page-6">all work was directed by the main contractor</a>.</li>
        <li><strong>"Search across all 243 documents for a name, a company, or a phrase — and see which page it's on."</strong> — The government site's search returns a flat list of PDF links; you must open each PDF and search within it yourself. Here, <a href="search.html">full-text search</a> spans all 1.9 million words and returns every document with the matching term, with a snippet of the surrounding text — so you can see the context without opening a single PDF. A search for "collusion" returns 35 documents here, each with a snippet; on the government site it returns 30 PDF links with no context.</li>
        <li><strong>"How do the documents relate to each other?"</strong> — The government site offers no cross-referencing. Here, an <a href="documents.html">interactive map</a> shows which documents cite each other, which cover the same theme, and how evidence accumulates across witness statements, expert reports and closing addresses.</li>
        <li><strong>"Which documents are scanned images that cannot be searched?"</strong> — The government site publishes 46 documents (347 pages) as scanned images with no machine-readable text. Here, every page has been OCR'd and made searchable — and the <a href="about.html#ocr">About page</a> documents this gap and condemns the practice.</li>
        <li><strong>"Give me a one-page summary of each document before I decide whether to read it."</strong> — The government site gives you a filename. Here, every document has a summary, key points, themes, parties mentioned, and related documents — so you can assess relevance in 30 seconds instead of downloading and skimming a 100-page PDF.</li>
      </ul>
      <p>This site is an independent, non-commercial project. It is not a publication of the Committee and makes no findings of its own; the original documents remain authoritative. It is bilingual (English and Traditional Chinese).</p>
    </section>

    <section class="block">
      <div class="block-head"><h2>Terms of Reference</h2><a class="link" href="tor.html">View perspectives →</a></div>
      <p class="block-sub">Every document is tagged against the Committee's seven Terms of Reference.
      Figures show documents touching each category (deep AI analysis of all {len(INDEX)} documents).</p>
      <div class="tor-grid">{''.join(tor_cards)}</div>
      {tor_method_note}
    </section>

    <section class="block">
      <div class="block-head"><h2>What the analysis surfaced</h2></div>
      <div class="insights">
        <div class="insight-card">
          <div class="insight-kicker">THE KEY QUESTION, BURIED</div>
          <p><b>{ana_tor.get("ToR5: Systemic Issues (Collusion, Bid-rigging, Conflicts)", 0)} of {len(INDEX)}</b>
          documents relate to the bid-rigging and collusion residents most want explained. Reading only titles and
          summaries, that number looked like {old_tor5}; evidence surfaced in documents that never mention the
          keywords — identical bids, payments for uninspected work, approvals given without a visit — only after
          every document was read in full.</p>
        </div>
        <div class="insight-card">
          <div class="insight-kicker">LEADING THEMES ACROSS ALL DOCS</div>
          <div class="themes">{theme_html}</div>
          <p class="muted" style="margin-top:.75rem">Extracted by an LLM that read and tagged every document
          against the seven Terms of Reference.</p>
        </div>
      </div>
    </section>

    <section class="block narrow">
      <div class="block-head"><h2>In the press</h2><a class="link" href="letter.html">Read our letter →</a></div>
      <p>Our letter on the accessibility of the Wang Fuk Court fire inquiry documents was published in the
      <strong>South China Morning Post letters column on 19 August 2026</strong>
      (<a href="https://www.scmp.com/comment/letters" target="_blank" rel="noopener">SCMP Letters ↗</a>).
      It makes the case that the committee's 243 documents — 6,377 pages, 1.9 million words — are arranged by
      the sequence of the committee's work, not by the questions it was asked to answer, and that the evidence
      people most want (on collusion and bid-rigging) is buried in documents a keyword search never surfaces.
      This site is our working answer: <a href="documents.html">243 documents</a> tagged by
      <a href="tor.html">Terms of Reference</a>, <a href="search.html">full-text search</a>, and
      <a href="doc/Reply-On-Cheong.html#page-7">page-level citations</a>. The source code is
      <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">open source on GitHub ↗</a>
      (FireReport under <code>projects/FireReport</code>).</p>
    </section>
    """
    return page("Home", "index.html", body, "Reorganized Wang Fuk Court fire inquiry documents")


# ----------------------------------------------------------------------------
# Documents index
# ----------------------------------------------------------------------------
def build_documents():
    """Merged 'Map & Documents' page (map.html + documents.html per plan L82-93).
    Interactive ToR relationship map on top; below it a searchable document list
    that groups by theme when a ToR is selected and by ToR for 'All'.
    Selection is synced: map nodes, legend, filter buttons and the ?tor= URL.
    """
    groups = {tag: [] for _, tag, _ in TOR_TAGS}
    groups["General / Other"] = []
    all_docs = []
    for d in INDEX:
        slug = slug_of(d)
        a = ana(d)
        tags = doc_tor_tags(d)
        # rich search haystack: title + type + lang + summaries + text excerpt + deep terms
        cross = doc_cross_summary(d)
        cross_txt = cross[1] if cross else ""
        excerpt = clean_doc_text(d)[:900]
        base = " ".join([d["title"], doc_type_label(d), LANG_LABEL.get(doc_language(d), ""),
                         (d.get("summary") or ""), cross_txt, excerpt,
                         *a.get("themes", []), *a.get("key_points", [])]).lower()
        # deep-text terms NOT already covered by the base haystack
        extra = [t for t in doc_search_terms(d) if t not in base][:150]
        search = (base + " " + " ".join(extra)).lower()
        rec = {"slug": slug, "title": d["title"], "url": d.get("url", ""),
                "num": DOC_NUM.get(d["title"], ""),
                "pages": d.get("pages") or 0, "images": d.get("images") or 0,
                "themes": (a.get("themes") or [])[:2],
                "kp": (a.get("key_points") or [""])[0],
                "tor_tag": tags[0],
                "type": doc_type_label(d),
                "lang": LANG_LABEL.get(doc_language(d), "English"),
                "search": search}
        all_docs.append(rec)
        for t in tags:
            groups.setdefault(t, []).append(rec)
    data = []
    old_tor = old_tor_counts()
    for i, (key, tag, blurb) in enumerate(TOR_TAGS):
        data.append({"key": key, "tag": tag, "blurb": blurb,
                     "narrative": TOR_NARRATIVES.get(tag, ""),
                     "color": TOR_COLORS[i], "docs": groups.get(tag, []),
                     "old": old_tor.get(tag, 0)})
    data.append({"key": "Gen", "tag": "General / Other", "blurb": "Procedural and support materials",
                 "narrative": TOR_NARRATIVES.get("General / Other", ""), "color": TOR_COLORS[-1],
                 "docs": groups.get("General / Other", []),
                 "old": old_tor.get("General / Other", 0)})
    payload = json.dumps({"groups": data, "all": all_docs}, ensure_ascii=False)

    body = f"""
    <section class="page-head">
      <h1>Map &amp; Documents</h1>
      <p>How the {len(INDEX)} inquiry documents relate to the Committee's Terms of Reference.
      Click a ToR node (or a filter button) to see its documents grouped by theme, with a reading
      narrative; click any document to open its full page. Selection updates the URL for sharing.</p>
    </section>

    <section class="map-shell">
      <div class="map-canvas" id="map-canvas">
        <svg id="map-svg" viewBox="0 0 940 640" role="img" aria-label="ToR relationship map"></svg>
      </div>
      <div class="map-legend" id="map-legend"></div>
    </section>

    <section class="toolbar">
      <input id="map-search" type="search" placeholder="Filter documents…">
      <div id="tor-filters" class="filters">
        <button class="filter" data-tor="">All</button>
      </div>
      <span class="doc-count" id="doc-count"></span>
    </section>
    <section class="toolbar meta-filters">
      <span class="filter-label">Type</span>
      <div id="type-filters" class="filters">
        <button class="filter active" data-type="ALL">All</button>
      </div>
      <span class="filter-label">Language</span>
      <div id="lang-filters" class="filters">
        <button class="filter active" data-lang="ALL">All</button>
        <button class="filter" data-lang="English">English</button>
        <button class="filter" data-lang="中文">中文</button>
        <button class="filter" data-lang="Bilingual">Bilingual</button>
      </div>
    </section>

    <section id="map-narrative" class="map-narrative"></section>
    <section id="map-docs"></section>

    <script>
    const DATA = {payload};
    const svg = document.getElementById('map-svg');
    const CX = 470, CY = 300, R = 215, CENTER = 84;
    const FILTER_TAGS = {json.dumps([t[1] for t in TOR_TAGS] + ["General / Other"], ensure_ascii=False)};
    let active = null;   // short key: ToR1..ToR7 | Gen
    let curTag = '';     // full tag or '' for All
    let query = '';
    let curType = 'ALL', curLang = 'ALL';

    function el(name, attrs) {{ const e = document.createElementNS('http://www.w3.org/2000/svg', name); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; }}
    function esc(s) {{ return String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]); }}

    // center node
    svg.appendChild(el('circle', {{cx: CX, cy: CY, r: CENTER, fill: '#0f172a'}}));
    const ct = el('text', {{x: CX, y: CY - 8, 'text-anchor': 'middle', fill: '#fff', 'font-size': '15', 'font-weight': '700'}}); ct.textContent = 'Independent';
    const ct2 = el('text', {{x: CX, y: CY + 10, 'text-anchor': 'middle', fill: '#cbd5e1', 'font-size': '11'}}); ct2.textContent = 'Committee';
    svg.appendChild(ct); svg.appendChild(ct2);
    const cTip = el('title', {{}}); cTip.textContent = 'Independent Committee on the Wang Fuk Court fire — the hub of the inquiry. Every document is connected to one or more Terms of Reference; click a ToR node to see its documents below.';
    svg.appendChild(cTip);

    // ToR nodes on a ring
    const nodes = DATA.groups.map((g, i) => {{
        const a = (i / DATA.groups.length) * 2 * Math.PI - Math.PI / 2;
        const x = CX + R * Math.cos(a), y = CY + R * Math.sin(a);
        svg.appendChild(el('line', {{x1: CX, y1: CY, x2: x, y2: y, stroke: g.color, 'stroke-width': 2, opacity: .35}}));
        const g2 = el('g', {{class: 'map-tor', 'data-key': g.key, style: 'cursor:pointer'}});
        g2.appendChild(el('circle', {{cx: x, cy: y, r: 58, fill: g.color, stroke: '#fff', 'stroke-width': 3}}));
        const t1 = el('text', {{x: x, y: y - 4, 'text-anchor': 'middle', fill: '#fff', 'font-size': '12', 'font-weight': '700'}}); t1.textContent = g.key;
        const t2 = el('text', {{x: x, y: y + 12, 'text-anchor': 'middle', fill: 'rgba(255,255,255,.9)', 'font-size': '9'}}); t2.textContent = g.docs.length + ' docs';
        g2.appendChild(t1); g2.appendChild(t2);
        const tip = el('title', {{}});
        tip.textContent = g.key + ' — ' + g.tag + '. ' + g.docs.length + ' documents relate to this Term of Reference' + (g.old && g.old !== g.docs.length ? ' (was ' + g.old + ' in the earlier summary-level reading)' : '') + '. Click to filter the documents below, grouped by theme, with a reading narrative.';
        g2.appendChild(tip);
        svg.appendChild(g2);
        g2.addEventListener('click', () => select(g.key));
        return {{key: g.key, x, y}};
    }});

    // legend + filter buttons
    const legend = document.getElementById('map-legend');
    DATA.groups.forEach(g => {{
        const b = document.createElement('button');
        b.className = 'legend-item'; b.dataset.key = g.key;
        b.innerHTML = '<span class="legend-dot" style="background:' + g.color + '"></span>' + esc(g.tag);
        b.addEventListener('click', () => select(g.key));
        legend.appendChild(b);
    }});
    const bar = document.getElementById('tor-filters');
    FILTER_TAGS.forEach(t => {{
        const b = document.createElement('button');
        b.className = 'filter'; b.dataset.tor = t; b.textContent = t;
        bar.appendChild(b);
    }});
    // document-type filter buttons (unique types across the corpus)
    const typeBar = document.getElementById('type-filters');
    const TYPE_LIST = [...new Set(DATA.all.map(d => d.type))].sort();
    TYPE_LIST.forEach(t => {{
        const b = document.createElement('button');
        b.className = 'filter'; b.dataset.type = t; b.textContent = t;
        typeBar.appendChild(b);
    }});
    const langBar = document.getElementById('lang-filters');

    function groupOf(d) {{ return (active && d.themes && d.themes[0]) ? d.themes[0] : (d.tor_tag || 'General / Other'); }}

    function rowHtml(d) {{
        return '<li class="doc-row">' +
            '<span class="doc-num">#' + esc(d.num) + '</span>' +
            '<div class="row-main"><a class="row-title" href="doc/' + encodeURIComponent(d.slug) + '.html">' + esc(d.title) + '</a>' +
            '<div class="row-sub">' + esc(d.kp) + '</div></div>' +
            '<div class="row-meta"><span class="tor-badge">' + esc(d.tor_tag) + '</span>' +
            '<span class="type-badge">' + esc(d.type) + '</span>' +
            '<span class="lang-badge lang-' + esc(d.lang.toLowerCase()) + '">' + esc(d.lang) + '</span>' +
            '<span>' + d.pages + 'p · ' + d.images + ' img</span>' +
            '<a class="row-pdf" href="' + esc(d.url) + '" target="_blank" rel="noopener">PDF ↗</a></div>' +
            '</li>';
    }}

    const BOOST_TYPES = /investigation report|expert report|closing address|opening address|recommendation/i;
    function scoreDoc(d, q) {{
        let s = 0;
        if (d.title.toLowerCase().includes(q)) s += 100;
        if (BOOST_TYPES.test(d.type)) s += 40;
        if (d.search.includes(q)) s += 20;
        return s;
    }}

    function render() {{
        const src = active ? (DATA.groups.find(x => x.key === active)?.docs || []) : DATA.all;
        const q = query.trim().toLowerCase();
        let list = src.filter(d => {{
            const okQ = !q || d.search.includes(q);
            const okT = curType === 'ALL' || d.type === curType;
            const okL = curLang === 'ALL' || d.lang === curLang;
            return okQ && okT && okL;
        }});
        if (q) {{
            list = list.slice().sort((x, y) => scoreDoc(y, q) - scoreDoc(x, q));
        }}
        const box = document.getElementById('map-docs');
        box.innerHTML = '';
        if (!list.length) {{ box.innerHTML = '<p class="muted">No documents match.</p>'; setCount(0); return; }}
        const groups = {{}};
        list.forEach(d => {{ (groups[groupOf(d)] = groups[groupOf(d)] || []).push(d); }});
        Object.keys(groups).sort().forEach(k => {{
            const h = document.createElement('h3');
            h.className = 'map-group-head';
            h.textContent = k + ' (' + groups[k].length + ')';
            box.appendChild(h);
            const ul = document.createElement('ul');
            ul.className = 'doc-list';
            ul.innerHTML = groups[k].map(rowHtml).join('');
            box.appendChild(ul);
        }});
        setCount(list.length);
    }}

    function setCount(n) {{ document.getElementById('doc-count').textContent = n + ' of ' + DATA.all.length + ' documents'; }}

    function syncUrl() {{
        const u = new URL(location.href);
        // keep the short key (e.g. ?tor=ToR5) rather than the long full tag in the URL
        if (active) u.searchParams.set('tor', active); else u.searchParams.delete('tor');
        history.replaceState({{}}, '', u);
    }}

    function select(key) {{
        const g = DATA.groups.find(x => x.key === key);
        active = key; curTag = g.tag;
        document.querySelectorAll('.map-tor').forEach(n => n.style.opacity = (n.dataset.key === key) ? 1 : .45);
        legend.querySelectorAll('.legend-item').forEach(b => b.classList.toggle('active', b.dataset.key === key));
        bar.querySelectorAll('.filter').forEach(b => b.classList.toggle('active', b.dataset.tor === g.tag));
        document.getElementById('map-narrative').innerHTML =
            '<div class="map-narr-card"><div class="map-narr-head"><span class="tor-chip">' + esc(g.key) + '</span> <strong>' + esc(g.tag) + '</strong></div><p>' + esc(g.narrative) + '</p></div>';
        render();
        syncUrl();
    }}

    function showAll() {{
        active = null; curTag = '';
        document.querySelectorAll('.map-tor').forEach(n => n.style.opacity = 1);
        legend.querySelectorAll('.legend-item').forEach(b => b.classList.remove('active'));
        bar.querySelectorAll('.filter').forEach(b => b.classList.toggle('active', b.dataset.tor === ''));
        document.getElementById('map-narrative').innerHTML = '';
        render();
        syncUrl();
    }}

    bar.addEventListener('click', e => {{
        const b = e.target.closest('.filter');
        if (!b) return;
        const t = b.dataset.tor || '';
        if (!t) {{ showAll(); return; }}
        const g = DATA.groups.find(x => x.tag === t);
        if (g) select(g.key);
    }});
    typeBar.addEventListener('click', e => {{
        const b = e.target.closest('.filter');
        if (!b) return;
        curType = b.dataset.type || 'ALL';
        typeBar.querySelectorAll('.filter').forEach(x => x.classList.toggle('active', x === b));
        render();
    }});
    langBar.addEventListener('click', e => {{
        const b = e.target.closest('.filter');
        if (!b) return;
        curLang = b.dataset.lang || 'ALL';
        langBar.querySelectorAll('.filter').forEach(x => x.classList.toggle('active', x === b));
        render();
    }});
    document.getElementById('map-search').addEventListener('input', e => {{ query = e.target.value; render(); }});

    // deep link ?tor= on load (accept short key "ToR5" or full tag "ToR5: …")
    const param = new URLSearchParams(location.search).get('tor');
    if (param) {{
        const g = DATA.groups.find(x => x.tag === param)
              || DATA.groups.find(x => x.key === param)
              || DATA.groups.find(x => x.tag.startsWith(param));
        if (g) select(g.key); else showAll();
    }} else {{
        showAll();
    }}
    </script>
    """
    return page("Map & Documents", "documents.html", body, "Interactive map of inquiry documents by Terms of Reference, with searchable index")


# ----------------------------------------------------------------------------
# ToR index
# ----------------------------------------------------------------------------
def tor_filename(tag):
    return re.sub(r"[^A-Za-z0-9]+\s*", "", tag.split(":")[0]) + ".html"


def build_tor():
    ana_tor = Counter()
    for d in INDEX:
        for t in doc_tor_tags(d):
            ana_tor[t] += 1
    old_tor = old_tor_counts()
    cards = []
    for key, tag, blurb in TOR_TAGS:
        n = ana_tor.get(tag, 0)
        o = old_tor.get(tag, 0)
        old_note = f' <span class="tor-old" title="Earlier summary-level reading found {o} docs; full-text reading found {n}">(was {o})</span>' if o != n else ""
        narr = TOR_NARRATIVES.get(tag, "")
        cards.append(f"""
        <article class="tor-perspective">
          <div class="tor-card-top"><span class="tor-chip">{esc(key)}</span><span class="tor-count">{n} docs{old_note}</span></div>
          <h3><a href="tor/{tor_filename(tag)}">{esc(tag)}</a></h3>
          <p class="tor-narr">{esc(narr)}</p>
          <a class="link" href="tor/{tor_filename(tag)}">Open this perspective →</a>
        </article>""")
    tor_method_note = (
        '<p class="muted tor-method-note">Counts are from full-text paragraph-level reading of all documents. '
        'Bracketed figures are the earlier summary-level counts — the difference shows how much relevant '
        'material is invisible to keyword or summary reading (see '
        '<a href="about.html#tor-counts">methodology</a>).</p>'
        if any(old_tor.get(t, 0) != ana_tor.get(t, 0) for _, t, _ in TOR_TAGS) else ""
    )
    body = f"""
    <section class="page-head">
      <h1>Terms of Reference — Perspectives</h1>
      <p>How to read the inquiry's documents from each perspective of the Committee's mandate.
      Each perspective page explains the narrative and cites the supporting documents.</p>
    </section>
    <section class="tor-perspectives">{''.join(cards)}</section>
    {tor_method_note}
    """
    return page("ToR Perspectives", "tor.html", body, "ToR perspectives with narratives")


# ----------------------------------------------------------------------------
# About / News
# ----------------------------------------------------------------------------
def build_about():
    img_ex = image_examples_html()
    body = f"""
    <section class="page-head"><h1>About &amp; Credits</h1></section>
    <section class="block narrow">
      <div class="note-block">
        <h3>Acknowledgement of source</h3>
        <p>All documents presented on this site originate from the
        <a href="https://www.ic-wangfukcourtfire.gov.hk/eng/index.html" target="_blank" rel="noopener">Independent Committee
        in relation to the Fire at Wang Fuk Court in Tai Po</a> and are the work of the Committee, its counsel, experts,
        witnesses and the Government. Original PDFs are linked from every document page. This site reorganises, indexes
        and summarises those public materials; it claims no authorship of them.</p>
      </div>
      <div class="note-block">
        <h3>Compiler</h3>
        <p>Compiled and maintained by <strong>Dr Simon Wang</strong>
        (<a href="mailto:simonwanghkteacher@gmail.com">simonwanghkteacher@gmail.com</a>).</p>
      </div>
      <div class="note-block warn">
        <h3>Disclaimer</h3>
        <p>Dr Simon Wang compiles this site as a <strong>private individual</strong>, not as a scholar of Hong Kong
        Baptist University (HKBU). HKBU is not involved in, and bears no responsibility for, this site. The site is
        provided <strong>for educational purposes only</strong> and is <strong>not for commercial use</strong>. Readers
        should consult the original documents for authoritative content.</p>
      </div>
      <div class="note-block" id="images">
        <h3>Image count and filtering (8,785 extracted → ≈1,800 shown)</h3>
        <p>All <strong>8,785 images</strong> embedded in the 243 PDFs were extracted programmatically. Most are not
        meaningful standalone items: automatic inspection classifies them into <em>photographs</em> (1,772),
        <em>diagrams, charts and plans</em> (1,036), <em>full-page scans</em> (834), <em>blank</em> (304) and
        <em>tiny layout fragments</em> (4,837 — single dots, sprites and formatting debris produced by PDF
        extraction). A vision model then reviewed the photographs and diagrams, rated each for importance (★1–5)
        and relevance; the ≈1,800 that met the bar (importance ★3 or above, or clearly substantive non-photographic
        material) are shown on the document pages — 'N shown of M' — so readers see evidence rather than
        extraction noise. The full extracted set remains available in the original PDFs.</p>
        {img_ex}
      </div>
      <div class="note-block" id="tor-counts">
        <h3>How Terms-of-Reference counts are computed</h3>
        <p>Counts under each ToR reflect how many of the 243 documents contain substantive material related to that
        task, judged by a large language model that <strong>read the full text</strong> of every document (in
        ~2,000-character passages, semantic judgment rather than keyword matching). Documents may count under
        several ToR. Twenty-seven documents arrived as scans with no readable text; they have since been OCR'd
        and re-read by the model, so every document now has full-text tags. This full-text reading markedly
        raised the counts for ToR5 (collusion, bid-rigging) and ToR6 (laws) compared with the earlier
        summary-level classification: many documents that never use those keywords still contain directly relevant
        evidence — for example a registered fire-service contractor that never visited the estate, an oral
        subcontract with no written contract, and a contract attachment whose material-data folder was empty.</p>
      </div>
      <div class="note-block warn" id="ocr">
        <h3>Scanned pages: 347 pages of evidence published as images</h3>
        <p>Of the 243 documents (6,377 pages) published by the Committee, <strong>46 documents — 347 pages</strong> —
        carried their text only as scanned images with no machine-readable text layer: 27 documents (283 pages) were
        scans in full, and a further 19 documents contained 64 individual scanned pages mixed into otherwise
        text-based PDFs. None of these pages can be searched, quoted or read by a computer as-is; anyone who wishes
        to process the text — a journalist, a researcher, a member of the public, or the compiler of this site — must
        first run optical character recognition (OCR) page by page, then check and correct the output, because OCR of
        scanned pages is never perfectly accurate. This site performed that work for every affected page so the
        material could be searched and read. Publishing official evidence as images instead of text imposes a hidden,
        unnecessary burden on anyone who wants to work with the documents on a computer; this practice is to be
        <strong>strongly condemned</strong>.</p>
      </div>
      <div class="note-block" id="open-source">
        <h3>Open source &amp; press</h3>
        <p>This site is built from an <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">open-source
        repository on GitHub ↗</a> (project under <code>projects/FireReport</code>): the crawler, PDF processor,
        OCR, LLM analysis and site generator are all public, so journalists, researchers and developers can
        reproduce or adapt the methodology. Our letter on the accessibility of the inquiry documents was published
        in the <a href="https://www.scmp.com/comment/letters" target="_blank" rel="noopener">South China Morning Post
        letters column on 19 August 2026 ↗</a> — read it on the <a href="letter.html">Our Letter page</a>.</p>
      </div>
    </section>
    """
    return page("About & Credits", "about.html", body, "Credits and disclaimer")


def build_work():
    """Work ledger page: estimated person-hours behind the documents, by type of
    work and by Terms of Reference."""
    if not WORK.get("total_hours"):
        body = """
        <section class="page-head"><h1>Work &amp; Effort</h1>
        <p>The work ledger is being prepared — run <code>codes/work_ledger.py</code>.</p></section>
        """
        return page("Work & Effort", "work.html", body, "Estimated work behind the inquiry documents")

    th = WORK["total_hours"]
    days = WORK["total_person_days"]
    years = round(days / 250, 1)

    # --- by type table ---
    type_rows = []
    for typ, v in WORK.get("by_type", {}).items():
        pct = v["hours"] / th * 100 if th else 0
        type_rows.append(
            f'<tr><td>{esc(typ.replace("_", " ").title())}</td><td class="num">{v["count"]}</td>'
            f'<td class="num">{v["pages"]:,}</td><td class="num">{v["hours"]:,.0f}</td>'
            f'<td class="num">{pct:.0f}%</td></tr>'
        )
    type_rows_html = "".join(type_rows)

    # --- by ToR bars ---
    tor_rows = []
    tor_items = sorted(WORK.get("by_tor", {}).items(), key=lambda x: -x[1]["hours_split"])
    max_h = tor_items[0][1]["hours_split"] if tor_items else 1
    for tag, v in tor_items:
        href = tor_href(tag)
        name = tag.split(":")[0].strip() if ":" in tag else tag
        pct = v["hours_split"] / max_h * 100 if max_h else 0
        link = f'<a href="{href}">{esc(name)}</a>' if href else esc(name)
        tor_rows.append(
            f'<div class="work-tor-row"><div class="work-tor-label">{link} '
            f'<span class="muted">{v["docs"]} docs · {v["pages"]:,} pages</span></div>'
            f'<div class="work-bar"><div class="work-bar-fill" style="width:{pct:.1f}%"></div></div>'
            f'<div class="work-tor-hours">{v["hours_split"]:,.0f} h</div></div>'
        )
    tor_rows_html = "".join(tor_rows)

    # --- top docs ---
    top = []
    for title, v in WORK.get("top_docs", [])[:12]:
        slug = slug_of(BY_TITLE[title]) if title in BY_TITLE else ""
        link = f'<a href="/doc/{esc(slug)}.html">{esc(title)}</a>' if slug else esc(title)
        top.append(f'<li><span class="doc-num">#{DOC_NUM.get(title,"")}</span> {link} '
                   f'<span class="rel-tag">{v["hours"]:,.0f} h · {esc(v["type"].replace("_"," ").title())}</span></li>')
    top_html = "".join(top)

    stats = "".join([
        stat_card(f"{th:,.0f}", "Estimated person-hours", "across all 243 documents"),
        stat_card(f"{days:,.0f}", "Person-days", "≈ 8-hour working days"),
        stat_card(f"{years}", "Person-years", "at 250 working days/yr"),
        stat_card("120+", "Witness statements", "≈1,600 h of interviewing & drafting"),
    ])

    body = f"""
    <section class="page-head">
      <h1>Work &amp; Effort</h1>
      <p>An estimate of the person-hours behind the inquiry's published documents, and how that
      effort was distributed across the Terms of Reference. Figures are indicative, not audited.</p>
    </section>

    <section class="stats">{stats}</section>

    <section class="note-block">
      <h3>How the estimate is made (methodology)</h3>
      <p>Each document is assigned a <strong>base effort</strong> reflecting the characteristic work behind
      its type — interviewing and drafting a witness statement (≈12 h), preparing and running a hearing
      session (≈8 h), expert analysis (≈60 h), an inter-departmental investigation report (≈120 h),
      closing submissions (≈40 h), a routine notice (≈1.5 h) — plus a <strong>reading/checking allowance
      of 0.12 h per page</strong>. Document types come from the classification in <code>data/doc_meta.json</code>;
      the full table of base figures is in <code>data/work_ledger.json</code>. A document tagged with several
      Terms of Reference splits its hours equally among them, so the ToR figures sum to the total.</p>
    </section>

    <section class="block narrow">
      <h2>Effort by type of work</h2>
      <p class="block-sub">Witness statements and hearings — the human evidence-gathering core of the
      inquiry — account for nearly half of the estimated effort.</p>
      <div class="table-wrap">
        <table class="work-table">
          <thead><tr><th>Type of work</th><th class="num">Docs</th><th class="num">Pages</th><th class="num">Est. hours</th><th class="num">Share</th></tr></thead>
          <tbody>{type_rows_html}</tbody>
        </table>
      </div>
    </section>

    <section class="block narrow">
      <h2>Effort by Terms of Reference</h2>
      <p class="block-sub">How the estimated work hours are distributed across the questions the committee
      was asked to answer. Click a ToR name for its perspective page.</p>
      {tor_rows_html}
      <p class="muted" style="margin-top:.8rem">Note: the adequacy-of-laws question (ToR 6) received the
      smallest dedicated documentary effort (≈{WORK.get('by_tor',{}).get('ToR6: Adequacy of Laws &amp; Penalties',{}).get('hours_split',0):,.0f} h) — itself a finding worth weighing against
      the committee's recommendations.</p>
    </section>

    <section class="block narrow">
      <h2>The heaviest documents</h2>
      <p class="block-sub">The largest single items of work in the published record.</p>
      <ul class="rel-list">{top_html}</ul>
    </section>
    """
    return page("Work & Effort", "work.html", body, "Estimated work behind the inquiry documents, by type and by Terms of Reference")


def build_search():
    """Mini full-text search engine page (search.html). Index: /search/index.json."""
    # Suggested searches — clickable terms that demonstrate how the archive is
    # searchable by question/topic, with a semantic expansion shown next to each.
    suggestions = [
        ("sprinkler failure", ["sprinkler", "hydrant", "fire service installation", "水錶房", "消防系統"]),
        ("tender collusion", ["collusion", "bid-rigging", "cartel", "identical bids", "圍標"]),
        ("smoking / cigarette fire", ["smoking", "cigarette", "ignition", "light well", "煙頭"]),
        ("rubber-stamping approvals", ["rubber-stamping", "inspection", "approval", "不檢驗批核"]),
        ("uninspected payments", ["payment", "uninspected", "invoice", "付款"]),
        ("fire alarm switched off", ["alarm", "switched off", "disconnected", "警鐘"]),
        ("tender scoring manipulation", ["tender", "scoring", "litigation record", "評分"]),
    ]
    chips = "".join(
        f'<button class="chip" data-q="{esc(htmlmod.escape(q, quote=True))}">{esc(label)}</button>'
        for label, q in [(label, " ".join(q[:2])) for label, q in suggestions]
    )
    body = f"""
    <section class="page-head">
      <h1>Full-text Search</h1>
      <p>Search the full text of all 243 inquiry documents — English and 中文.
      You can also ask questions (e.g. "was the sprinkler system working?") — the engine
      finds the documents most likely to answer them. Results show a highlighted excerpt
      and link to each document's page.</p>
    </section>
    <section class="block narrow">
      <div class="block-sub">Try a suggested question — each expands to related terms automatically:</div>
      <div class="search-chips" id="search-chips">{chips}</div>
    </section>
    <section class="toolbar">
      <input id="search-q" type="search" placeholder="輸入關鍵詞 / Enter keywords…" autofocus>
    </section>
    <p class="muted" id="search-status"></p>
    <div id="search-results"></div>
    """
    js = '<script src="/assets/search.js"></script>'
    return page("Search", "search.html", body + js, "Full-text search across all inquiry documents")


def build_news():
    """News coverage analysis page (revamp item 8).
    Renders: methodology, key facts, timeline, themes mapped to ToR (with links
    to the tor pages and matching inquiry documents), coverage gaps, insights,
    and a filterable article index.
    """
    ff = NEWS.get("fire_facts", {})
    themes = NEWS.get("themes", [])
    timeline = NEWS.get("timeline", [])
    gaps = NEWS.get("coverage_gaps", [])
    insights = NEWS.get("insights", [])
    articles = NEWS.get("articles", [])

    # --- key facts stats ---
    stats = "".join([
        stat_card("168", "Lives lost", "26 Nov 2025 · incl. one firefighter"),
        stat_card("7 / 8", "Blocks ablaze", "Wang Cheong House first"),
        stat_card("HK$330M", "Renovation project", "2016 order → 2024 works"),
        stat_card("24", "Hearings held", "77 witnesses by round four"),
        stat_card("243", "Inquiry documents", "available on this site"),
        stat_card("7", "ToR categories", "news themes mapped below"),
    ])

    # --- latest developments (post-hearing) ---
    dev_items = []
    for ev in NEWS.get("latest_developments", []):
        src = ev.get("source", "")
        url = ev.get("url", "")
        src_html = (f'<span class="dev-src">· <a href="{esc(url)}" target="_blank" rel="noopener">{esc(src)} ↗</a></span>'
                    if url else f'<span class="dev-src">· {esc(src)}</span>')
        dev_items.append(
            f'<div class="dev-item"><div class="dev-date">{esc(ev.get("date", ""))}</div>'
            f'<div><p>{esc(ev.get("event", ""))} {src_html}</p></div></div>'
        )
    dev_html = "".join(dev_items)

    # --- timeline ---
    tl_items = []
    for ev in timeline:
        tor_chips = "".join(
            f'<a class="theme-chip" href="{tor_href(t)}'
            f'">{esc(t)}</a>' for t in ev.get("tor", []) if tor_href(t)
        )
        tl_items.append(
            f'<div class="tl-item"><div class="tl-date">{esc(ev.get("date", ""))}</div>'
            f'<div class="tl-body"><p>{esc(ev.get("event", ""))}</p>'
            f'<div class="themes">{tor_chips}</div></div></div>'
        )
    timeline_html = "".join(tl_items)

    # --- themes mapped to ToR ---
    theme_cards = []
    for th in themes:
        tor_links = "".join(
            f'<a class="theme-chip" href="{tor_href(t)}">{esc(t)}</a>'
            for t in th.get("tor", []) if tor_href(t)
        )
        media = "".join(f"<li>{esc(m)}</li>" for m in th.get("media", []))
        doc_links = []
        for frag in th.get("related_docs", []):
            slug = find_doc_slug(frag)
            if slug:
                doc_links.append(f'<a class="btn btn-ghost" href="doc/{slug}.html">View doc →</a>')
            else:
                doc_links.append(f'<span class="muted">({esc(frag)} — not matched)</span>')
        docs_html = "".join(doc_links)
        theme_cards.append(f"""
        <div class="card news-theme" id="theme-{esc(th.get("id", ""))}">
          <div class="block-head"><h3>{esc(th.get("title", ""))}</h3><div class="themes">{tor_links}</div></div>
          <p class="news-para">{esc(th.get("coverage", ""))}</p>
          <h4 class="news-sub">What the coverage said</h4>
          <ul class="news-list">{media}</ul>
          <h4 class="news-sub">What the record adds</h4>
          <p class="news-para">{esc(th.get("gaps", ""))}</p>
          <div class="acc-links">{docs_html}</div>
        </div>""")
    themes_html = "".join(theme_cards)

    # --- coverage gaps ---
    gaps_html = "".join(f"<li>{esc(g)}</li>" for g in gaps)

    # --- insights ---
    ins_cards = "".join(
        f'<div class="insight-card"><div class="insight-kicker">Insight {i+1}</div>'
        f'<p class="news-para">{esc(v)}</p></div>'
        for i, v in enumerate(insights)
    )

    # --- article index ---
    art_rows = []
    for i, a in enumerate(articles):
        lang = a.get("lang", "EN")
        tor_chips = "".join(
            f'<a class="theme-chip" href="{tor_href(t)}">{esc(t)}</a>'
            for t in a.get("tor", []) if tor_href(t)
        )
        art_rows.append(f"""
        <div class="news-art" data-lang="{esc(lang)}" data-tor="{esc(",".join(a.get("tor", [])))}">
          <span class="art-num">{i+1:02d}</span>
          <div class="art-main">
            <a class="art-title" href="{esc(a.get("url", "#"))}" target="_blank" rel="noopener">{esc(a.get("title", ""))}</a>
            <div class="art-meta">{esc(a.get("source", ""))} · {esc(a.get("date", ""))}</div>
            <div class="themes">{tor_chips}</div>
          </div>
          <span class="art-lang lang-{esc(lang.lower())}">{esc(lang)}</span>
        </div>""")
    articles_html = "".join(art_rows)

    body = f"""
    <section class="page-head">
      <h1>News &amp; Coverage</h1>
      <p>How the media reported the Wang Fuk Court fire and the inquiry — mapped to the
      Committee's Terms of Reference, with the coverage gaps and insights that the
      documentary record can fill.</p>
    </section>

    <section class="block narrow">
      <div class="block-head"><h2>Latest developments</h2><a class="link" href="letter.html">Our letter to SCMP →</a></div>
      <p class="block-sub">What has happened since the hearings closed on 17 July 2026 — including our own
      published letter and the inquiry's next steps. Each item links to the original report.</p>
      <div class="timeline">{dev_html}</div>
    </section>

    <section class="note-block">
      <h3>Methodology &amp; transparency</h3>
      <p>This analysis was prepared {esc(NEWS.get("generated", ""))} by searching international and
      Hong Kong media (EN + 繁體中文) and reading key reporting in full: HKFP's timeline
      (2025-12-17), HKFP's first-ten-days hearing findings (2026-04-12), HKFP's closing-address
      report (2026-07-17) and The Standard's reforms piece (2026-05-12). Themes are our
      interpretation, organised under the Committee's own ToR headings; every claim should be
      checked against the original inquiry documents, which are linked throughout this site.
      News items are for reference only and remain the copyright of their publishers.</p>
    </section>

    <section class="block narrow">
      <h2>The fire in numbers</h2>
      <div class="stats">{stats}</div>
      <p class="news-para">{esc(ff.get("estate", ""))}. The blaze began on
      {esc(ff.get("fire_date", ""))}. Per the Committee's closing address, the toll reached
      {esc(ff.get("death_toll", ""))}. The fire occurred during a
      {esc(ff.get("renovation", ""))}; committee counsel described the probable origin as
      {esc(ff.get("cause", ""))}.</p>
    </section>

    <section class="block narrow">
      <h2>Timeline</h2>
      <p class="block-sub">From the 2016 inspection order to the close of hearings. Each event is tagged
      to the ToR categories it illuminates.</p>
      <div class="timeline">{timeline_html}</div>
    </section>

    <section class="block">
      <h2>News themes mapped to the Terms of Reference</h2>
      <p class="block-sub">Seven themes dominate coverage. Each maps to the ToR framework and to the
      inquiry documents that contain the underlying evidence.</p>
      {themes_html}
    </section>

    <section class="block narrow">
      <h2>Coverage gaps</h2>
      <p class="block-sub">Questions the news coverage raises but does not fully answer — the documentary
      record on this site can help.</p>
      <ul class="news-list gaps">{gaps_html}</ul>
    </section>

    <section class="block">
      <h2>Insights from reading coverage against the record</h2>
      <p class="block-sub">What connecting the news themes to the Committee's own documents suggests.</p>
      <div class="insights">{ins_cards}</div>
    </section>

    <section class="block">
      <h2>Article index</h2>
      <p class="block-sub">Representative coverage; filter by language or ToR. External links open the
      original publisher's page.</p>
      <div class="toolbar">
        <div class="filters" id="art-lang-filters">
          <button class="filter active" data-lang="ALL">All</button>
          <button class="filter" data-lang="EN">English</button>
          <button class="filter" data-lang="TC">繁體中文</button>
        </div>
        <div class="filters" id="art-tor-filters">
          <button class="filter active" data-tor="ALL">All ToR</button>
          <button class="filter" data-tor="ToR1">ToR1</button>
          <button class="filter" data-tor="ToR2">ToR2</button>
          <button class="filter" data-tor="ToR3">ToR3</button>
          <button class="filter" data-tor="ToR4">ToR4</button>
          <button class="filter" data-tor="ToR5">ToR5</button>
          <button class="filter" data-tor="ToR6">ToR6</button>
          <button class="filter" data-tor="ToR7">ToR7</button>
        </div>
      </div>
      <div id="art-list">{articles_html}</div>
    </section>
    """

    js = """
    <script>
    (function(){
      var langBtn = document.getElementById('art-lang-filters');
      var torBtn = document.getElementById('art-tor-filters');
      var rows = Array.prototype.slice.call(document.querySelectorAll('.news-art'));
      var curLang = 'ALL', curTor = 'ALL';
      function apply(){
        rows.forEach(function(r){
          var langs = (r.getAttribute('data-lang')||'').split(',');
          var tors = (r.getAttribute('data-tor')||'').split(',');
          var okLang = curLang==='ALL' || langs.indexOf(curLang)>=0;
          var okTor = curTor==='ALL' || tors.indexOf(curTor)>=0;
          r.style.display = (okLang&&okTor) ? '' : 'none';
        });
      }
      function bind(container, attr, onPick){
        container.addEventListener('click', function(e){
          var b = e.target.closest('.filter');
          if(!b) return;
          container.querySelectorAll('.filter').forEach(function(x){x.classList.remove('active');});
          b.classList.add('active');
          onPick(b.getAttribute(attr));
        });
      }
      bind(langBtn, 'data-lang', function(v){curLang=v;apply();});
      bind(torBtn, 'data-tor', function(v){curTor=v;apply();});
    })();
    </script>
    """

    return page("News & Coverage", "news.html", body + js, "News coverage analysis mapped to the inquiry's Terms of Reference")


# ----------------------------------------------------------------------------
# Letter to the editor (published)
# ----------------------------------------------------------------------------
def build_letter():
    """Our letter to the SCMP editor, published 2026-08-19, plus context."""
    pub = PRESS.get("published", {})
    let = PRESS.get("letter", {})
    paras = "".join(f"<p>{esc(p)}</p>" for p in let.get("paragraphs", []))
    body = f"""
    <section class="page-head">
      <div class="hero-badge">PUBLISHED IN SCMP LETTERS · {esc(pub.get("date", ""))}</div>
      <h1>Our letter to the editor</h1>
      <p>The accessibility of the Wang Fuk Court fire inquiry documents — as published in the
      South China Morning Post.</p>
    </section>
    <section class="block narrow">
      <div class="note-block">
        <h3>Publication</h3>
        <p>Published in the <a href="{esc(pub.get("url", "#"))}" target="_blank" rel="noopener">South China Morning Post
        letters column ↗</a> on <strong>{esc(pub.get("date", ""))}</strong> under the heading
        <strong>“{esc(pub.get("letter_headline", ""))}”</strong>, in the edition
        “{esc(pub.get("edition", ""))}”. {esc(pub.get("note", ""))}</p>
        <p>The letter grew out of this site’s analysis: <a href="documents.html">243 documents</a>,
        <a href="search.html">full-text search</a> and the
        <a href="tor.html">Terms-of-Reference framework</a> are all referenced in the text below.</p>
      </div>
    </section>
    <section class="block narrow">
      <div class="letter-doc">
        <h2>{esc(let.get("subject", ""))}</h2>
        <p class="letter-salutation">{esc(let.get("salutation", ""))}</p>
        {paras}
        <p class="letter-signature">{esc(let.get("signature", ""))}</p>
      </div>
      <p class="letter-as-submitted">{esc(let.get("as_submitted_note", ""))}</p>
    </section>
    <section class="block narrow">
      <h2>About the site the letter describes</h2>
      <ul class="news-list">
        <li><strong><a href="documents.html">Map &amp; Documents</a></strong> — every document, tagged against the seven Terms of Reference.</li>
        <li><strong><a href="search.html">Full-text search</a></strong> — across all 243 documents, with page-level snippets.</li>
        <li><strong><a href="tor.html">ToR Perspectives</a></strong> — themed narratives that cite the documents behind each task.</li>
        <li><strong><a href="news.html">News &amp; Coverage</a></strong> — how the media covered the fire, mapped to the record.</li>
        <li><strong><a href="about.html">About &amp; Credits</a></strong> — methodology, image filtering and the OCR burden.</li>
        <li><strong><a href="engagement/legcoDraft.html">LegCo engagement</a></strong> — the draft report to the Panel on Security, and how AI prepared it.</li>
        <li><strong><a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">Source code ↗</a></strong> — open source, under <code>projects/FireReport</code>.</li>
      </ul>
    </section>
    """
    return page("Our Letter", "letter.html", body, "Our letter to SCMP on the accessibility of the inquiry documents")

# ----------------------------------------------------------------------------
# Engagement — LegCo draft
# ----------------------------------------------------------------------------
def build_legco_draft():
    """Engagement page for LegCo members: why the original record is hard to
    use, the alternative we built, what the deeper reading reveals, the draft
    report to the Panel on Security, and how AI prepared it."""
    body = """
    <section class="page-head lg-hero">
      <div class="hero-badge">FOR LEGCO MEMBERS · DRAFT REPORT READY · OCTOBER 2026</div>
      <h1>The record is public.<br>The answers are hard to find.</h1>
      <p>The Independent Committee has published everything online — 243 documents, 6,377 pages,
      1.9 million words. But the material is filed by the sequence of the committee's work, not by
      the seven questions in its Terms of Reference. We rebuilt the record around those questions —
      and drafted the report to the Panel on Security.</p>
      <div class="hero-actions">
        <a class="btn btn-dark" href="https://github.com/tesolchina/wangfukcourtfirereport/blob/main/docs/legco_panel_security_report.md" target="_blank" rel="noopener">Read the draft report ↗</a>
        <a class="btn btn-ghost" href="documents.html">Explore the reorganized record →</a>
        <a class="btn btn-ghost" href="https://www.ic-wangfukcourtfire.gov.hk/eng/index.html" target="_blank" rel="noopener">Original committee site ↗</a>
      </div>
    </section>
    <section class="stats">
      <div class="stat-card"><div class="stat-value">243</div><div class="stat-label">documents published by the Committee</div></div>
      <div class="stat-card"><div class="stat-value">6,377</div><div class="stat-label">pages of evidence</div></div>
      <div class="stat-card"><div class="stat-value">1.9M</div><div class="stat-label">words — statements, transcripts, expert reports</div></div>
      <div class="stat-card"><div class="stat-value">~1,800</div><div class="stat-label">photographs and diagrams</div></div>
      <div class="stat-card"><div class="stat-value">7</div><div class="stat-label">Terms-of-Reference tasks tagged on every document</div></div>
    </section>

    <section class="block narrow" id="problem">
      <div class="block-head"><h2>Why the original site is hard to use</h2></div>
      <div class="note-block warn" style="margin-top:1rem">
        <p>The committee's own menu — About the Committee, Timetable for Hearings, Key Documents,
        Transcripts — mirrors how it worked, not what the public needs to know. Anyone chasing
        evidence on sprinkler failure or tender collusion must wade through page after page, with no
        overview of how the documents relate to the seven Terms of Reference. And a keyword search
        cannot bridge the gap: the strongest evidence on tender irregularities sits in documents
        that never use those words.</p>
      </div>
      <div class="lg-compare">
        <div class="col">
          <h4>How the record is filed</h4>
          <ul>
            <li>About the Committee</li>
            <li>Timetable for Hearings</li>
            <li>Key Documents</li>
            <li>Transcripts — by hearing date</li>
            <li>Documents — by filing sequence</li>
          </ul>
        </div>
        <div class="col">
          <h4>What people actually ask</h4>
          <ul>
            <li>Why did the fire alarms fail?</li>
            <li>Who verified the netting and the boards?</li>
            <li>Was the renovation tender rigged?</li>
            <li>Who was supposed to supervise — and didn't?</li>
            <li>Are the existing laws and penalties adequate?</li>
          </ul>
        </div>
      </div>
      <div class="lg-quote">Every document is public — but the questions people ask are the ones
      the archive makes hardest to answer.
      <small>— our letter to the editor, South China Morning Post, 19 August 2026 (<a href="letter.html">read it here</a>)</small></div>
    </section>

    <section class="block narrow" id="alternative">
      <div class="block-head"><h2>An alternative is feasible — and already built</h2></div>
      <p class="block-sub">A web crawler collected every document; PDFs were converted to text with
      all 8,785 embedded images extracted; the 27 documents that arrived only as scans were read by
      OCR; and large language models read, summarised and tagged every document against the seven
      Terms-of-Reference tasks. The result is a free, bilingual, open-source companion to the
      committee's site.</p>
      <div class="insights">
        <a class="insight-card lg-card-link" href="documents.html">
          <div class="insight-kicker">MAP &amp; DOCUMENTS</div>
          <p>Every one of the 243 documents on a page of its own — summary, key points, table of
          contents, link to the original PDF — and an interactive map of how they relate to each task.</p>
        </a>
        <a class="insight-card lg-card-link" href="search.html">
          <div class="insight-kicker">FULL-TEXT SEARCH</div>
          <p>Search across all 1.9 million words, with page-level snippets that jump straight to the
          passage in the original document.</p>
        </a>
        <a class="insight-card lg-card-link" href="tor.html">
          <div class="insight-kicker">ToR PERSPECTIVES</div>
          <p>Seven themed narratives — one per Terms-of-Reference task — citing the documents behind
          every point.</p>
        </a>
        <a class="insight-card lg-card-link" href="news.html">
          <div class="insight-kicker">NEWS &amp; COVERAGE</div>
          <p>How the media covered the fire, mapped against the documentary record — including what
          the coverage missed.</p>
        </a>
      </div>
    </section>

    <section class="block narrow" id="insights">
      <div class="block-head"><h2>What the deeper reading reveals</h2></div>
      <p class="block-sub">Findings from reading all 243 documents in full — most of them invisible
      to a keyword search of the committee's own site.</p>
      <div class="insights">
        <div class="insight-card">
          <div class="insight-kicker">UNEVEN DISTRIBUTION</div>
          <p>Supervision responsibilities appear in <b>195 documents</b>; the adequacy of laws in
          <b>77</b>. Bid-rigging and collusion — what residents most want explained — appear in
          <b>99 documents</b> in the full text, against 8 and 11 in a summary-level first pass.</p>
        </div>
        <div class="insight-card">
          <div class="insight-kicker">EVIDENCE WITHOUT THE WORDS</div>
          <p>A fire-service contractor filed <b>85 shutdown-renewal notices without ever visiting
          the estate</b>; a renovation subcontract was agreed <b>orally, with no written contract</b>;
          a contract attachment's material-data folder was <b>empty</b>. None of these documents says
          "bid-rigging" — a keyword search would never surface them.</p>
        </div>
        <div class="insight-card">
          <div class="insight-kicker">THE HONOUR-SYSTEM THREAD</div>
          <p>The independent checking unit gave advance notice of inspections; an FSD inspection five
          weeks before the fire missed the deactivated alarms; a registered inspector was described
          in evidence as a rubber stamp. The same pattern recurs across regulators.</p>
        </div>
        <div class="insight-card">
          <div class="insight-kicker">TWO FAILURE CHAINS, ONE OUTCOME</div>
          <p>Renovation-contractor fraud and fire-safety-contractor behaviour are two distinct
          failure chains. They meet in the fire systems that were switched off — alarms deactivated
          in <b>seven of the eight blocks</b>, fire-service water tanks emptied.</p>
        </div>
      </div>
    </section>

    <section class="block narrow" id="report">
      <div class="block-head"><h2>The draft report to the Panel on Security</h2></div>
      <p class="block-sub">Modelled on the 2021 minibus-safety letter to the Panel on Transport
      (LC Paper No. CB(4)1353/20-21(01)): a short letter, our published SCMP letter as the appendix,
      and a sources table linking every factual claim. Addressed to
      <code>panel_s@legco.gov.hk</code>.</p>
      <div class="lg-asks">
        <div class="lg-ask"><div class="lg-ask-num">a</div><p><b>Brief the Panel.</b> Invite the Security Bureau and the Fire Services Department to present the Committee's findings and recommendations as soon as the report is published — and table the report to the Panel.</p></div>
        <div class="lg-ask"><div class="lg-ask-num">b</div><p><b>Fix the shutdown regime.</b> A contractor filed 85 shutdown-renewal notices without any site visit. Ask how shutdowns and restorations of fire service installations will in future be verified by physical inspection.</p></div>
        <div class="lg-ask"><div class="lg-ask-num">c</div><p><b>Contractor accountability.</b> Ask what mechanisms can suspend or debar contractors implicated in the inquiry pending prosecutions — two fire-service contractors linked to the tragedy were still taking new contracts in August 2026.</p></div>
        <div class="lg-ask"><div class="lg-ask-num">d</div><p><b>A public implementation timetable.</b> For the Committee's recommendations, including legislative amendments under its third term of reference on the adequacy of existing laws and penalties — with progress reported back to the Panel.</p></div>
        <div class="lg-ask"><div class="lg-ask-num">e</div><p><b>Present the record by ToR.</b> So that members and the public can trace each recommendation to the underlying evidence — the accessibility concern in our published letter.</p></div>
      </div>
      <div class="note-block" style="margin-top:1rem">
        <h3>Timing</h3>
        <p>The Committee's report is due by the <strong>end of October 2026</strong> (extension
        granted on 18 August 2026). The letter is timed to land in the week the report is published,
        so the Panel can put the briefing on its next agenda.</p>
      </div>
      <p style="margin-top:1rem"><a class="link" href="https://github.com/tesolchina/wangfukcourtfirereport/blob/main/docs/legco_panel_security_report.md" target="_blank" rel="noopener">Read the full draft with the sources table ↗</a> ·
      <a class="link" href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">Source code on GitHub ↗</a> ·
      <a class="link" href="letter.html">Our published SCMP letter →</a></p>
    </section>

    <section class="block narrow" id="how">
      <div class="block-head"><h2>How AI prepared this report</h2></div>
      <p class="block-sub">The draft was prepared by an AI agent in a single working session under
      Dr Simon Wang's direction, instructed through the public GitHub issue. The full session log is
      attached to the issue; the steps below summarise it.</p>
      <div class="timeline lg-steps">
        <div class="tl-item"><div class="tl-date">1 · Task intake</div><div class="tl-body"><p>Read the GitHub issue and the instruction; identified the sample paper to follow — the 2021 minibus-safety letter to the Panel on Transport.</p></div></div>
        <div class="tl-item"><div class="tl-date">2 · Template study</div><div class="tl-body"><p>Downloaded the sample paper PDF, extracted its text and learned its structure — letter, appendix, sign-off.</p></div></div>
        <div class="tl-item"><div class="tl-date">3 · Project memory</div><div class="tl-body"><p>Read the repository README, the published SCMP letter and its sixteen draft versions, and the press record.</p></div></div>
        <div class="tl-item"><div class="tl-date">4 · Evidence mining</div><div class="tl-body"><p>Queried the project's own analysis data — fire facts, themes, ToR coverage counts, latest developments — rather than re-reading 6,377 pages.</p></div></div>
        <div class="tl-item"><div class="tl-date">5 · Primary-source verification</div><div class="tl-body"><p>Checked every key fact against the committee's site and news sources; rendered the JavaScript-only LegCo panel page in a headless browser to verify the panel's email address and the CB(2) paper series.</p></div></div>
        <div class="tl-item"><div class="tl-date">6 · Citation discipline</div><div class="tl-body"><p>Built a twelve-row sources table linking every factual claim in the letter to its authoritative source.</p></div></div>
        <div class="tl-item"><div class="tl-date">7 · Drafting with guardrails</div><div class="tl-body"><p>Modelled the letter on the sample; kept legal liabilities outside the asks, per the Committee's own scope note; left co-signatories as a placeholder for the editors' list.</p></div></div>
        <div class="tl-item"><div class="tl-date">8 · Publication</div><div class="tl-body"><p>Posted the full text to GitHub issue #1 and committed the file to both repositories — public by design, as the issue itself notes.</p></div></div>
      </div>
      <div class="lg-duo">
        <div class="col">
          <h4>What the human decided</h4>
          <ul>
            <li>The task, the audience and the sample to follow</li>
            <li>The editor contacts for co-signatories</li>
            <li>Review, signature and the decision to submit</li>
          </ul>
        </div>
        <div class="col">
          <h4>What the AI did</h4>
          <ul>
            <li>Gathered and verified the evidence, source by source</li>
            <li>Drafted the letter, the five asks and the appendix</li>
            <li>Built the sources table and the submission notes</li>
            <li>Published to the issue and committed to both repos</li>
          </ul>
        </div>
      </div>
    </section>

    <section class="lg-cta">
      <h2>For LegCo members: the briefing this record deserves</h2>
      <p>168 people died at Wang Fuk Court. The evidence of what failed — and what must change — is
      already public. We ask the Panel on Security to follow up the Committee's findings with the
      Security Bureau, and to make the implementation of its recommendations public and trackable.</p>
      <div class="hero-actions">
        <a class="btn btn-dark lg-btn-light" href="https://github.com/tesolchina/wangfukcourtfirereport/blob/main/docs/legco_panel_security_report.md" target="_blank" rel="noopener">Read the draft report ↗</a>
        <a class="btn btn-ghost" href="documents.html">Explore the record →</a>
        <a class="btn btn-ghost" href="mailto:simonwanghkteacher@gmail.com">Contact Dr Simon Wang</a>
      </div>
    </section>
    """
    return page("Engagement — LegCo Draft", "engagement/legcoDraft.html", body,
                "For LegCo members: the inquiry record is public but hard to navigate — an alternative is feasible, and the draft report to the Panel on Security is ready")


# ----------------------------------------------------------------------------
# Document pages
# ----------------------------------------------------------------------------
def build_doc_pages():
    out_dir = os.path.join(OUT, "doc")
    os.makedirs(out_dir, exist_ok=True)
    by_title = BY_TITLE
    FULL_FALLBACK = ('<p class="muted">Text extraction produced no content (scanned document) — '
                     'see the extracted images above or the original PDF.</p>')
    n = 0
    for d in INDEX:
        a = ana(d)
        slug = slug_of(d)
        num = DOC_NUM.get(d["title"], 0)
        tags = "".join(f'<span class="tor-badge">{esc(t)}</span>' for t in doc_tor_tags(d))
        kp = a.get("key_points", [])
        themes = a.get("themes", [])
        parties = a.get("parties", [])[:6]
        toc = d.get("toc") or []
        pages_n = d.get("pages") or 0

        # full text from markdown
        md_path = os.path.join(DATA, "markdown", f"{slug}.md")
        full_html = ""
        if os.path.exists(md_path):
            full_html = md_to_html(open(md_path, encoding="utf-8", errors="ignore").read())
        # scanned PDFs (no OCR text) yield only page-marker HTML; treat as no text
        # so the scan-page images render as the readable full document below
        if is_scanned_doc(d):
            full_html = ""
        # ToC -> page anchors (fallback to plain list)
        toc_html = "".join(
            f'<li><a href="#page-{x}">{esc(x)}</a></li>' if full_html and re.match(r"^Page \d+$", x) else f"<li>{esc(x)}</li>"
            for x in toc[:20]
        )
        toc_more = f"<li class='muted'>… {len(toc) - 20} more</li>" if len(toc) > 20 else ""

        # images
        imgs = sorted(glob.glob(os.path.join(DATA, "images", f"{slug}_*.jpeg")) +
                      glob.glob(os.path.join(DATA, "images", f"{slug}_*.png")))
        imgs = [os.path.basename(x) for x in imgs]
        imgs.sort(key=lambda x: (int(re.search(r"p(\d+)", x).group(1)) if re.search(r"p(\d+)", x) else 0,
                                 int(re.search(r"img(\d+)", x).group(1)) if re.search(r"img(\d+)", x) else 0))
        gal = ""
        if imgs:
            kept = []
            for fname in imgs:
                pm = re.search(r"p(\d+)", fname)
                pg = pm.group(1) if pm else "?"
                keep, cap, imp = img_keep_and_caption(fname, pg)
                if keep:
                    kept.append((fname, cap, imp, pg))
            # most important first, then page order
            kept.sort(key=lambda x: (-x[2], x[3]))
            if kept:
                thumbs = []
                for fname, cap, imp, pg in kept:
                    # first 24 images load eagerly (visible on open); the rest stay lazy
                    eager = len(thumbs) < 24
                    lazy_attr = '' if eager else 'loading="lazy"'
                    thumbs.append(
                        f'<figure class="img-item"><a href="/images/{esc(fname)}" target="_blank" rel="noopener">'
                        f'<img {lazy_attr} src="/images/{esc(fname)}" alt="Page {esc(pg)} image" title="Page {pg}"></a>'
                        f'<figcaption>{cap}</figcaption></figure>'
                    )
                hidden = "".join(thumbs[24:])
                shown = "".join(thumbs[:24])
                more_div = f'<div class="img-more" hidden>{hidden}</div>' if hidden else ""
                more_btn = (
                    f'<button class="btn btn-ghost" id="img-more-btn" '
                    f'onclick="document.getElementById(\'img-more-btn\').hidden=true;'
                    f'document.querySelector(\'.img-more\').hidden=false">Show all {len(kept)} images</button>'
                ) if hidden else ""
                filtered_note = ""
                if len(kept) < len(imgs):
                    filtered_note = (
                        f'<p class="img-note">{len(imgs) - len(kept)} of {len(imgs)} extracted images were '
                        f'automatically filtered as non-informative (blank, tiny fragments, logos or text-only '
                        f'pages). Captions and importance ratings are AI-generated; the full set remains in the '
                        f'original PDF.</p>'
                    )
                gal = f"""
                <details class="img-gallery" open>
                  <summary>Images ({len(kept)} shown of {len(imgs)} extracted) — click to expand/collapse</summary>
                  <div class="img-grid">{shown}{more_div}</div>
                  {more_btn}
                  {filtered_note}
                </details>"""
            else:
                gal = f"""
                <details class="img-gallery">
                  <summary>Images ({len(imgs)} extracted) — click for detail</summary>
                  <p class="img-note">All {len(imgs)} extracted images were automatically filtered as
                  non-informative (text pages, blanks, logos or tiny fragments). The complete set is in the
                  <a href="{esc(d.get('url','#'))}" target="_blank" rel="noopener">original PDF</a>.</p>
                </details>"""

        # related docs: LLM fragments (resolved) + shared parties + shared ToR
        meta = DOC_META.get(d["title"], {})
        rel_items = []          # (title, relation_label)
        seen_rel = set()
        for fr in meta.get("related_fragments") or []:
            frag = (fr or {}).get("title", "") if isinstance(fr, dict) else ""
            t = resolve_doc_fragment(frag)
            if t and t != d["title"] and t not in seen_rel:
                rel_items.append((t, (fr.get("relation") if isinstance(fr, dict) else "") or "related"))
                seen_rel.add(t)
        # shared parties (same witness/company/entity speaks in both)
        my_parties = set(parties)
        for other in _DOC_ORDER:
            if other["title"] == d["title"] or other["title"] in seen_rel:
                continue
            shared = my_parties & set(ana(other).get("parties", []))
            if shared and len(rel_items) < 8:
                rel_items.append((other["title"], "same party: " + next(iter(shared))))
                seen_rel.add(other["title"])
        # shared ToR fallback to round out the list
        if len(rel_items) < 3:
            my_tags = set(doc_tor_tags(d))
            for other in _DOC_ORDER:
                if other["title"] == d["title"] or other["title"] in seen_rel:
                    continue
                if set(doc_tor_tags(other)) & my_tags:
                    rel_items.append((other["title"], "same Terms of Reference"))
                    seen_rel.add(other["title"])
                    if len(rel_items) >= 6:
                        break
        rel_html = "".join(
            f'<li><span class="doc-num">#{DOC_NUM.get(t,"")}</span> '
            f'<a href="/doc/{esc(slug_of(by_title[t]))}.html">{esc(t)}</a>'
            f'<span class="rel-tag">{esc(r)}</span></li>'
            for t, r in rel_items
        ) or "<li class='muted'>none found yet</li>"

        # how the ToR themes appear in THIS document
        tor_themes = meta.get("tor_themes") or []
        tor_themes_html = ""
        if tor_themes:
            rows = []
            for item in tor_themes:
                tor = item.get("tor", "") if isinstance(item, dict) else ""
                theme = item.get("theme", "") if isinstance(item, dict) else ""
                evidence = item.get("evidence", "") if isinstance(item, dict) else ""
                href = tor_href(tor)
                tor_link = f'<a class="theme-chip" href="{href}">{esc(tor)}</a>' if href else f'<span class="theme-chip">{esc(tor)}</span>'
                rows.append(
                    f'<div class="tor-theme"><div class="tor-theme-head">{tor_link} <strong>{esc(theme)}</strong></div>'
                    f'<p>{esc(evidence)}</p></div>'
                )
            tor_themes_html = (
                '<div class="card"><h2>How the Terms of Reference appear in this document</h2>'
                + "".join(rows) + "</div>"
            )

        # news coverage links
        news_matches = doc_news_matches(d, ANALYSIS)
        news_html = ""
        if news_matches:
            links = "".join(
                f'<a class="theme-chip" href="news.html#theme-{esc(tid)}">{esc(title)}</a>'
                for tid, title in news_matches[:4]
            )
            news_html = (
                '<div class="card"><h2>In the news</h2>'
                '<p class="news-para muted">This document connects to these themes in the news coverage analysis '
                '(<a href="/news.html">News &amp; Coverage</a>).</p>'
                f'<div class="themes">{links}</div></div>'
            )

        # metadata badges
        lang_label = LANG_LABEL.get(doc_language(d), "English")
        type_label = doc_type_label(d)
        type_detail = doc_type_detail(d)
        fmt = "PDF" + (" · scanned" if not full_html else " · text")
        wl = WORK_BY_TITLE.get(d["title"], {})
        work_row = (
            f'<li><span>Est. work</span><b>{wl.get("hours", 0):,.0f} h</b></li>'
            if wl.get("hours") else ""
        )

        # complete summary + cross-language summary
        full_sum = doc_full_summary(d)
        cross = doc_cross_summary(d)
        cross_html = ""
        if cross:
            cl_label, cl_text = cross
            cross_html = (
                f'<div class="card cross-sum"><h2>Summary in {esc(cl_label)}</h2>'
                f'<div class="summary">{esc(cl_text)}</div></div>'
            )
        full_html_text = esc(full_sum) if full_sum else esc(d.get("summary", ""))
        # for scanned documents (no OCR text), render the page images as the
        # readable full document; otherwise show the extracted text
        if full_html:
            full_body = full_html
            scanned_note = ""
        else:
            pg_imgs = scanned_page_images(d)
            if pg_imgs:
                def _pgno(f):
                    m = re.search(r"_p(\d+)_", f)
                    return int(m.group(1)) if m else 0
                pages_html = "".join(
                    f'<figure class="scan-page" id="page-{_pgno(f)}"><a href="/images/{esc(f)}" target="_blank" rel="noopener">'
                    f'<img loading="lazy" src="/images/{esc(f)}" alt="Page {_pgno(f)}"></a>'
                    f'<figcaption>Page {_pgno(f)}</figcaption></figure>'
                    for f in pg_imgs
                )
                full_body = (f'<div class="scan-pages">{pages_html}</div>'
                             '<p class="muted">This is a scanned document — no searchable text could be '
                             'extracted; the page images above and the original PDF contain the content. '
                             'It is therefore not covered by the full-text search.</p>')
            else:
                full_body = FULL_FALLBACK
            scanned_note = ""

        body = f"""
        <section class="page-head">
          <p class="crumbs"><a href="/documents.html">Documents</a> → <span class="doc-num">#{num}</span></p>
          <h1>{esc(d['title'])}</h1>
          <p class="doc-sub">Document {num} of {len(INDEX)} · {pages_n} pages · {d.get('images') or 0} images</p>
          <div class="doc-tags">
            <span class="type-badge">{esc(type_label)}</span>
            <span class="lang-badge lang-{esc(lang_label.lower())}">{esc(lang_label)}</span>
            <span class="tor-badge">{esc(fmt)}</span>
            {tags}
          </div>
          {f'<p class="muted">{esc(type_detail)}</p>' if type_detail else ''}
        </section>
        <section class="doc-layout">
          <div class="doc-main">
            <div class="card">
              <h2>Summary</h2>
              <div class="summary">{full_html_text}</div>
              {scanned_note}
            </div>
            {cross_html}
            <div class="card">
              <h2>Key points</h2>
              <ul class="doc-points">{''.join(f'<li>{esc(p)}</li>' for p in kp)}</ul>
            </div>
            {tor_themes_html}
            {news_html}
            {gal}
            <details class="full-doc"{' open' if not full_html else ''}>
              <summary>Full document ({pages_n} pages) — click to expand</summary>
              {full_body}
            </details>
          </div>
          <aside class="doc-side">
            <div class="card">
              <h2>Document facts</h2>
              <ul class="facts">
                <li><span>Number</span><b>#{num} / {len(INDEX)}</b></li>
                <li><span>Type</span><b>{esc(type_label)}</b></li>
                <li><span>Language</span><b>{esc(lang_label)}</b></li>
                <li><span>Format</span><b>{esc(fmt)}</b></li>
                <li><span>Pages</span><b>{pages_n}</b></li>
                <li><span>Images</span><b>{d.get('images') or 0}</b></li>
                {work_row}
              </ul>
              <a class="btn btn-dark btn-block" href="{esc(d['url'])}" target="_blank" rel="noopener">Open original PDF ↗</a>
            </div>
            <div class="card">
              <h2>Table of contents</h2>
              <ul class="toc-list">{toc_html}{toc_more}</ul>
            </div>
            <div class="card">
              <h2>Themes</h2>
              <div class="themes">{''.join(f'<span class="theme-chip">{esc(t)}</span>' for t in themes)}</div>
            </div>
            <div class="card">
              <h2>Parties mentioned</h2>
              <ul class="facts">{''.join(f'<li><span>{esc(p)}</span></li>' for p in parties)}</ul>
            </div>
          </aside>
        </section>
        <section class="block">
          <h2>Related documents</h2>
          <ul class="rel-list">{rel_html}</ul>
        </section>
        {DOC_ANCHOR_JS}
        """
        open(os.path.join(out_dir, f"{slug}.html"), "w").write(
            fix_abs_links(page(d["title"], "documents.html", body, d["title"]))
        )
        n += 1
    return n


def load_reports():
    p = os.path.join(DATA, "tor_reports.json")
    if os.path.exists(p):
        return json.load(open(p))
    return {}


METHODOLOGY = (
    "Methodology: every document was read and tagged by a large language model (gpt-4.1-mini "
    "via the HKBU GenAI gateway) against the Committee's seven Terms of Reference; key points, "
    "themes and parties were extracted per document. For each ToR, the relevant documents were "
    "grouped into themes and the narratives below were drafted from the documents' own summaries "
    "and key points. Inline citations [n] link to this site's HTML rendering of each document "
    "(which links to the original PDF on the government site). This page is an editorial aid for "
    "journalists and the public; it is not a finding or publication of the Committee, and the "
    "original documents remain authoritative."
)


def build_tor_pages():
    """One page per ToR: full themed report (overview + theme sections with citations) + expandable doc list."""
    out_dir = os.path.join(OUT, "tor")
    os.makedirs(out_dir, exist_ok=True)
    reports = load_reports()
    by_title = {d["title"]: d for d in INDEX}

    groups = {tag: [] for _, tag, _ in TOR_TAGS}
    groups["General / Other"] = []
    for d in INDEX:
        tags = doc_tor_tags(d)
        rec = {"slug": slug_of(d), "title": d["title"], "url": d.get("url"), "a": ana(d)}
        for t in tags:
            groups.setdefault(t, []).append(rec)

    entries = [(*x, "General / Other") for x in TOR_TAGS] + [("General", "General / Other", "Procedural and support materials", "General / Other")]
    filenames = {t: re.sub(r"[^A-Za-z0-9]+\s*", "", t.split(":")[0]) + ".html" for _, t, _, _ in entries}
    built = 0
    for key, tag, blurb, _g in entries:
        docs = sorted(groups.get(tag, []), key=lambda r: r["title"].lower())
        fname = filenames[tag]
        report = reports.get(key)
        wl_tor = WORK.get("by_tor", {}).get(tag, {})
        if wl_tor:
            work_line = (
                f'<p class="doc-sub">Estimated work: <strong>{wl_tor.get("hours_split", 0):,.0f} hours</strong> '
                f'across {wl_tor.get("docs", len(docs))} documents · {wl_tor.get("pages", 0):,} pages · '
                f'see the <a href="/work.html">Work &amp; Effort</a> ledger</p>'
            )
        else:
            work_line = ""
        old_n = old_tor_counts().get(tag, 0)
        old_note = (f' <span class="tor-old" title="Earlier summary-level reading found {old_n} docs; '
                    f'full-text reading found {len(docs)}">(was {old_n})</span>') if old_n != len(docs) else ""

        if report and report.get("sections"):
            # numbered list exactly as the LLM saw it (sorted by title)
            numbered = sorted(groups.get(tag, []), key=lambda r: r["title"].lower())
            num_slug = {i + 1: r for i, r in enumerate(numbered)}

            def cite(text):
                def repl(m):
                    n = int(m.group(1))
                    r = num_slug.get(n)
                    if not r:
                        return m.group(0)
                    return f'<sup><a class="cite-ref" href="/doc/{esc(r["slug"])}.html" title="{esc(r["title"])}">[{n}]</a></sup>'
                return re.sub(r"\[(\d+)\]", repl, text)

            sections = []
            for s in report["sections"]:
                paras = "".join(f"<p>{cite(esc(p))}</p>" for p in re.split(r"\n{2,}", s.get("narrative", "")) if p.strip())
                cited = []
                for t in s.get("doc_titles", []):
                    r = by_title.get(t)
                    if r:
                        cited.append(
                            f'<li><a href="/doc/{esc(slug_of(r))}.html">{esc(t)}</a> · '
                            f'<a class="pdf" href="{esc(r["url"])}" target="_blank" rel="noopener">original PDF ↗</a></li>'
                        )
                sections.append(f"""
                <section class="report-section">
                  <h2>{esc(s.get("theme", ""))}</h2>
                  {paras}
                  <details class="sources"><summary>Cited documents ({len(cited)})</summary><ul>{''.join(cited)}</ul></details>
                </section>""")

            # expandable document list (accordion)
            acc = []
            for r in docs:
                a = r["a"]
                kps = "".join(f"<li>{esc(p)}</li>" for p in (a.get("key_points") or [])[:4])
                th = "".join(f'<span class="theme-chip">{esc(t)}</span>' for t in (a.get("themes") or [])[:4])
                toc = "".join(f"<li>{esc(x)}</li>" for x in (by_title[r["title"]].get("toc") or [])[:8])
                acc.append(f"""
                <details class="doc-acc">
                  <summary><span class="acc-title"><span class="doc-num">#{DOC_NUM.get(r['title'], '')}</span> {esc(r['title'])}</span><span class="acc-meta">{by_title[r['title']].get('pages') or '?'}p · {by_title[r['title']].get('images') or '?'} img</span></summary>
                  <div class="acc-body">
                    <div class="themes">{th}</div>
                    <ul class="doc-points">{kps}</ul>
                    <div class="acc-links">
                      <a class="btn btn-ghost" href="/doc/{esc(r['slug'])}.html">Full page + ToC</a>
                      <a class="btn btn-dark" href="{esc(r['url'])}" target="_blank" rel="noopener">Original PDF ↗</a>
                    </div>
                  </div>
                </details>""")

            body = f"""
            <section class="page-head">
              <p class="crumbs"><a href="/tor.html">ToR Perspectives</a> → {esc(key)}</p>
              <h1>{esc(tag)}</h1>
              <p class="block-sub">{esc(blurb)}</p>
              {work_line}
            </section>
            <section class="block">
              <div class="methodology"><strong>How this report was made.</strong> {esc(METHODOLOGY)}</div>
            </section>
            <section class="block">
              <div class="card">
                <h2>Overview</h2>
                <p class="tor-narr">{esc(report.get('overview', ''))}</p>
              </div>
            </section>
            <section class="block">
              <div class="block-head"><h2>Report sections by theme</h2></div>
              <p class="block-sub">Each section synthesises the relevant documents; inline citations link to each document's page.</p>
              {''.join(sections)}
            </section>
            <section class="block">
              <div class="block-head"><h2>All documents in this ToR ({len(docs)}{old_note})</h2></div>
              <p class="block-sub">Expand each document for its summary, key points and links.</p>
              {''.join(acc)}
            </section>
            """
        else:
            # fallback: simpler list
            acc = []
            for r in docs:
                a = r["a"]
                kps = "".join(f"<li>{esc(p)}</li>" for p in (a.get("key_points") or [])[:3])
                acc.append(f"""
                <details class="doc-acc">
                  <summary><span class="acc-title">{esc(r['title'])}</span></summary>
                  <div class="acc-body">
                    <ul class="doc-points">{kps}</ul>
                    <div class="acc-links">
                      <a class="btn btn-ghost" href="/doc/{esc(r['slug'])}.html">Full page</a>
                      <a class="btn btn-dark" href="{esc(r['url'])}" target="_blank" rel="noopener">Original PDF ↗</a>
                    </div>
                  </div>
                </details>""")
            body = f"""
            <section class="page-head">
              <p class="crumbs"><a href="/tor.html">ToR Perspectives</a> → {esc(key)}</p>
              <h1>{esc(tag)}</h1>
              <p class="block-sub">{esc(blurb)}</p>
              {work_line}
            </section>
            <section class="block">
              <div class="methodology"><strong>How this report was made.</strong> {esc(METHODOLOGY)}</div>
            </section>
            <section class="block">
              <div class="block-head"><h2>Documents in this ToR ({len(docs)}{old_note})</h2></div>
              {''.join(acc)}
            </section>
            """
        open(os.path.join(out_dir, fname), "w").write(
            fix_abs_links(page(tag, "tor.html", body, tag))
        )
        built += 1
    return built


# ----------------------------------------------------------------------------
# Interactive relationship map
# ----------------------------------------------------------------------------
TOR_COLORS = ["#0f172a", "#e11d48", "#0e7490", "#7c3aed", "#b45309", "#15803d", "#be185d", "#475569"]


# ----------------------------------------------------------------------------
# CSS
# ----------------------------------------------------------------------------
CSS = """/* Wang Fuk Court Fire Inquiry — revamped site */
:root{--ink:#0f172a;--mut:#64748b;--bg:#f8fafc;--card:#fff;--line:#e2e8f0;--acc:#0f172a;--acc2:#e11d48}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--ink);line-height:1.6}
h1,h2,h3,.brand-text strong{font-family:'Space Grotesk','Inter',sans-serif}
a{color:var(--acc)}
.layout{display:flex;min-height:100vh}
/* sidebar */
.sidebar{width:264px;flex-shrink:0;background:var(--ink);color:#e2e8f0;display:flex;flex-direction:column;padding:1.5rem 1rem;position:sticky;top:0;height:100vh}
.brand{display:flex;gap:.75rem;align-items:center;text-decoration:none;color:#fff;padding:.25rem .5rem 1.25rem;border-bottom:1px solid #334155}
.brand-mark{width:40px;height:40px;background:#fff;color:var(--ink);border-radius:12px;display:grid;place-items:center;font-weight:700;font-size:1.05rem}
.brand-text{display:flex;flex-direction:column;line-height:1.2}
.brand-text small{color:#94a3b8;font-size:.66rem}
.nav{display:flex;flex-direction:column;gap:.25rem;margin-top:1.25rem}
.nav-item{color:#cbd5e1;text-decoration:none;padding:.6rem .75rem;border-radius:10px;font-size:.9rem;font-weight:500}
.nav-item:hover{background:#1e293b;color:#fff}
.nav-item.active{background:#fff;color:var(--ink);font-weight:600}
.sidebar-foot{margin-top:auto;display:flex;flex-direction:column;gap:.4rem;font-size:.72rem;color:#94a3b8;padding:.75rem .5rem 0;border-top:1px solid #334155}
.sidebar-foot a{color:#e2e8f0}
.lang-switch{display:inline-block;margin-top:.1rem;font-weight:600;color:#fbbf24!important}
/* main */
.main{flex:1;min-width:0;padding:2.5rem clamp(1.25rem,4vw,3.5rem) 1rem;max-width:1200px}
.page-foot{display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--line);font-size:.75rem;color:var(--mut)}
/* hero */
.hero{padding:1rem 0 2rem}
.hero-badge{display:inline-flex;align-items:center;gap:.5rem;background:#fff;border:1px solid var(--line);border-radius:999px;padding:.4rem .9rem;font-size:.68rem;font-weight:600;letter-spacing:.08em;color:var(--mut);margin-bottom:1.25rem}
.hero-badge::before{content:'';width:8px;height:8px;border-radius:50%;background:#10b981;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.hero h1{font-size:clamp(2.6rem,6vw,4.2rem);line-height:1.02;letter-spacing:-.03em;font-weight:700}
.hero-sub{max-width:560px;margin-top:1rem;font-size:1.08rem;color:#475569}
.hero-actions{display:flex;gap:.75rem;margin-top:1.75rem;flex-wrap:wrap}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;padding:.75rem 1.4rem;border-radius:14px;font-weight:600;font-size:.92rem;text-decoration:none;border:1px solid transparent;cursor:pointer}
.btn-dark{background:var(--ink);color:#fff}
.btn-dark:hover{background:#1e293b}
.btn-ghost{background:#fff;border-color:var(--line);color:var(--ink)}
.btn-ghost:hover{border-color:#94a3b8}
.btn-block{width:100%;margin-top:.75rem}
/* stats */
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin:1.5rem 0 2.5rem}
.stat-card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.25rem}
.stat-value{font-family:'Space Grotesk',sans-serif;font-size:1.9rem;font-weight:700;letter-spacing:-.02em}
.stat-label{color:var(--mut);font-size:.82rem;font-weight:500;margin-top:.15rem}
.stat-sub{color:#94a3b8;font-size:.72rem}
/* blocks */
.block{margin:2.5rem 0}
.block.narrow{max-width:820px}
.block-head{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.block h2{font-size:1.5rem;letter-spacing:-.02em}
.block-sub{color:var(--mut);font-size:.9rem;margin:.35rem 0 1.1rem}
.link{color:var(--acc);font-size:.88rem;font-weight:600;text-decoration:none}
.link:hover{text-decoration:underline}
/* ToR cards */
.tor-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:1rem}
.tor-card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.1rem;text-decoration:none;color:inherit;transition:transform .15s,box-shadow .15s}
.tor-card:hover{transform:translateY(-3px);box-shadow:0 14px 28px -12px rgb(15 23 42/.18)}
.tor-card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem}
.tor-chip{font-size:.62rem;font-weight:700;letter-spacing:.05em;background:var(--ink);color:#fff;padding:.15rem .6rem;border-radius:999px}
.tor-count{font-size:.72rem;color:var(--mut);font-weight:600}
.tor-old{font-size:.66rem;color:#94a3b8;font-weight:500;margin-left:.3rem}
.tor-method-note{margin-top:1rem;max-width:62rem}
.img-examples{margin-top:1rem}
.img-examples h4{font-size:.9rem;margin:.9rem 0 .5rem}
.img-ex-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:.8rem}
.img-ex{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
.img-ex img{width:100%;height:110px;object-fit:cover;display:block;background:#f8fafc}
.img-ex figcaption{font-size:.72rem;padding:.45rem .6rem;color:#475569;line-height:1.4}
.ex-tag{display:inline-block;font-size:.6rem;font-weight:700;letter-spacing:.04em;padding:.12rem .45rem;border-radius:999px;margin-right:.3rem;vertical-align:middle}
.ex-kept{background:#dcfce7;color:#166534}
.ex-filtered{background:#fee2e2;color:#991b1b}
.lk-toolbar{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:.75rem}
.lk-toolbar input[type=search]{flex:1 1 240px}
.lk-toolbar select{padding:.45rem .6rem;border:1px solid var(--line);border-radius:8px;font-size:.85rem;background:#fff}
.lk-count{font-size:.85rem;color:var(--mut);margin:.25rem 0 .75rem}
.lk-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:.7rem}
.lk-item{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
.lk-item img{width:100%;height:120px;object-fit:cover;display:block;background:#f1f5f9}
.lk-item figcaption{font-size:.68rem;padding:.45rem .55rem;color:#475569;line-height:1.45}
.lk-tag{display:inline-block;font-size:.58rem;font-weight:700;letter-spacing:.03em;padding:.1rem .4rem;border-radius:999px;margin-right:.25rem}
.lk-kept{background:#dcfce7;color:#166534}.lk-filtered{background:#fee2e2;color:#991b1b}.lk-unknown{background:#e2e8f0;color:#334155}
.lk-imp{color:#d97706;font-weight:700;margin-right:.3rem}
.lk-lbl{color:#64748b}
.lk-doc{display:block;margin-top:.15rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.lk-doc a{color:var(--acc);text-decoration:none}
.lk-meta{color:#94a3b8;display:block}
.lk-sub{display:block;color:#64748b;margin-top:.15rem}
.lk-pager{display:flex;gap:1rem;align-items:center;justify-content:center;margin-top:1.25rem}
.lk-pager span{font-size:.85rem;color:var(--mut)}
.search-chips{display:flex;flex-wrap:wrap;gap:.45rem;margin:.5rem 0 1rem}
.chip{background:#f1f5f9;border:1px solid var(--line);color:#334155;border-radius:999px;padding:.4rem .85rem;font-size:.8rem;cursor:pointer;transition:all .15s}
.chip:hover{background:var(--ink);color:#fff;border-color:var(--ink)}
.search-expand-note{margin-top:.6rem;font-size:.78rem;color:#64748b}
.search-group-head{margin:1.1rem 0 .45rem;font-size:1rem}
.search-group-head.search-semantic{color:var(--acc)}
.search-group-note{margin:0 0 .6rem;font-size:.78rem;color:#64748b}
.row-link{background:none;border:none;cursor:pointer;font-size:.9rem;padding:.1rem .25rem;opacity:.55;transition:opacity .15s}
.row-link:hover{opacity:1}
.search-share-row{margin-top:1rem;text-align:right}
.search-mode{display:flex;flex-wrap:wrap;gap:.45rem;margin:.5rem 0 .75rem}
.mode-btn{border:1px solid var(--line);background:#fff;border-radius:999px;padding:.35rem .85rem;font-size:.78rem;font-weight:500;cursor:pointer;color:#475569}
.mode-btn.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.mode-count{font-size:.72rem;opacity:.8;margin-left:.2rem}
.doc-row.search-hit{padding:.55rem .85rem}
.search-hit .row-top{display:flex;align-items:center;gap:.6rem}
.search-hit .row-title{flex:1 1 auto;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.82rem}
.search-hit .row-meta-inline{display:flex;align-items:center;gap:.4rem;font-size:.7rem;color:var(--mut);white-space:nowrap}
.search-hit .row-sub{font-size:.75rem;margin-top:.15rem}
.scan-pages{display:flex;flex-direction:column;gap:.9rem;margin-top:.4rem}
.scan-page{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
.scan-page img{width:100%;height:auto;display:block}
.scan-page figcaption{font-size:.72rem;color:#64748b;padding:.4rem .6rem;border-top:1px solid var(--line)}
.tor-card-title{font-weight:600;font-size:.98rem}
.tor-card-blurb{color:var(--mut);font-size:.8rem;margin-top:.35rem}
/* insights */
.insights{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:1rem}
.insight-card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.25rem}
.insight-kicker{font-size:.66rem;font-weight:700;letter-spacing:.1em;color:var(--acc2);margin-bottom:.5rem}
.themes{display:flex;flex-wrap:wrap;gap:.45rem}
.theme-chip{background:#f1f5f9;border:1px solid var(--line);border-radius:999px;padding:.22rem .7rem;font-size:.74rem;color:#334155}
.theme-chip b{color:var(--ink)}
/* pages */
.page-head{padding:0 0 1.5rem}
.page-head h1{font-size:2.2rem;letter-spacing:-.02em;line-height:1.1}
.page-head p{color:var(--mut);max-width:640px;margin-top:.4rem;font-size:.95rem}
.crumbs{font-size:.78rem;color:var(--mut);margin-bottom:.5rem}
/* documents index */
.toolbar{display:flex;gap:1rem;flex-wrap:wrap;align-items:center;margin-bottom:1.25rem}
#search{flex:1;min-width:220px;padding:.7rem 1rem;border:1px solid var(--line);border-radius:12px;font-size:.9rem;background:#fff}
.filters{display:flex;flex-wrap:wrap;gap:.45rem}
.filter{border:1px solid var(--line);background:#fff;border-radius:999px;padding:.35rem .85rem;font-size:.76rem;font-weight:500;cursor:pointer;color:#475569}
.filter.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.doc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
/* document list rows (documents.html) */
.doc-list{list-style:none;display:flex;flex-direction:column;gap:.5rem}
.doc-row{display:flex;align-items:center;gap:1rem;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:.7rem 1rem}
.row-main{flex:1;min-width:0}
.row-title{font-weight:600;font-size:.88rem;text-decoration:none;color:inherit;display:block;line-height:1.35}
.row-title:hover{text-decoration:underline}
.row-sub{color:var(--mut);font-size:.76rem;margin-top:.2rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row-meta{display:flex;align-items:center;gap:.6rem;font-size:.74rem;color:var(--mut);white-space:nowrap}
.row-pdf{font-weight:600;color:var(--acc2);text-decoration:none}
.doc-count{margin-left:auto;font-size:.74rem;color:var(--mut);align-self:center}
/* map docs grouping */
.map-group-head{font-size:.95rem;margin:1.1rem 0 .5rem;padding-bottom:.25rem;border-bottom:1px solid var(--line);letter-spacing:-.01em}
.map-doc-row{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.6rem}
.chip-sum{font-size:.72rem;color:#64748b;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.map-tor circle{transition:filter .12s}
.map-tor:hover circle{filter:brightness(1.15)}
.doc-card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1.1rem;display:flex;flex-direction:column;gap:.6rem}
.doc-card-head h3{font-size:.95rem;line-height:1.35}
.doc-card-head h3 a{text-decoration:none;color:inherit}
.doc-card-head h3 a:hover{text-decoration:underline}
.tor-badge{font-size:.62rem;font-weight:600;background:#f1f5f9;border:1px solid var(--line);color:#475569;border-radius:999px;padding:.12rem .55rem;white-space:nowrap}
.type-badge{font-size:.62rem;font-weight:600;background:#eef2ff;border:1px solid #c7d2fe;color:#4338ca;border-radius:999px;padding:.12rem .55rem;white-space:nowrap}
.lang-badge{font-size:.62rem;font-weight:600;background:#f0fdf4;border:1px solid #bbf7d0;color:#15803d;border-radius:999px;padding:.12rem .55rem;white-space:nowrap}
.lang-badge.lang-中文{background:#fef2f2;border-color:#fecaca;color:#b91c1c}
.lang-badge.lang-bilingual{background:#fffbeb;border-color:#fde68a;color:#b45309}
.filter-label{font-size:.7rem;font-weight:700;letter-spacing:.06em;color:var(--mut);text-transform:uppercase;align-self:center}
.meta-filters{row-gap:.5rem}
/* work ledger page */
.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px}
.work-table{width:100%;border-collapse:collapse;font-size:.85rem}
.work-table th,.work-table td{padding:.55rem .9rem;text-align:left;border-bottom:1px solid var(--line)}
.work-table th{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--mut);background:#f8fafc}
.work-table td.num{text-align:right;font-variant-numeric:tabular-nums}
.work-table tbody tr:last-child td{border-bottom:none}
.work-tor-row{display:grid;grid-template-columns:minmax(0,1fr) 180px 70px;gap:.8rem;align-items:center;padding:.5rem 0;border-bottom:1px dashed var(--line)}
.work-tor-row:last-child{border-bottom:none}
.work-tor-label{font-size:.85rem;font-weight:600}
.work-tor-label .muted{font-weight:400;margin-left:.4rem}
.work-bar{background:#f1f5f9;border-radius:999px;height:10px;overflow:hidden}
.work-bar-fill{background:linear-gradient(90deg,var(--acc2),var(--acc));height:100%;border-radius:999px}
.work-tor-hours{font-size:.85rem;font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
.doc-points{margin:.35rem 0 .15rem;padding-left:1.1rem;color:#475569;font-size:.82rem}
.doc-points li{margin-bottom:.25rem}
.doc-meta{display:flex;gap:1rem;align-items:center;font-size:.74rem;color:var(--mut);margin-top:auto}
.doc-meta a{margin-left:auto;font-weight:600;text-decoration:none}
/* tor perspectives */
.tor-perspectives{display:flex;flex-direction:column;gap:1rem}
.tor-perspective{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.4rem}
.tor-perspective h3{margin:.5rem 0 .5rem;font-size:1.1rem}
.tor-perspective h3 a{text-decoration:none}
.tor-narr{color:#475569;font-size:.9rem}
.cite-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:1rem}
.cite-card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem;display:flex;flex-direction:column;gap:.5rem}
.cite-card h4{font-size:.88rem;line-height:1.35}
.cite-card h4 a{text-decoration:none;color:inherit}
.cite-card h4 a:hover{text-decoration:underline}
.cite-foot{display:flex;justify-content:space-between;align-items:center;gap:.5rem;margin-top:auto;font-size:.72rem}
.cite-foot a{font-weight:600;text-decoration:none}
.tor-pills{display:flex;flex-wrap:wrap;gap:.5rem}
.tor-pill{background:#fff;border:1px solid var(--line);border-radius:999px;padding:.4rem .9rem;font-size:.8rem;font-weight:500;text-decoration:none;color:#334155}
.tor-pill:hover{border-color:var(--ink);color:var(--ink)}
/* themed report pages */
.methodology{background:#f8fafc;border:1px solid var(--line);border-left:4px solid #94a3b8;border-radius:12px;padding:1rem 1.25rem;font-size:.82rem;color:#475569;line-height:1.7}
.report-section{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.4rem;margin-bottom:1.25rem}
.report-section h2{font-size:1.2rem;margin-bottom:.6rem}
.report-section p{color:#334155;font-size:.92rem;line-height:1.75;margin-bottom:.6rem}
.cite-ref{color:var(--acc2);text-decoration:none;font-size:.72em;font-weight:700}
.cite-ref:hover{text-decoration:underline}
sources{margin-top:.5rem;font-size:.82rem}
sources summary{cursor:pointer;color:var(--acc);font-weight:600}
sources ul{margin:.6rem 0 0 1.1rem;color:#475569}
sources li{margin-bottom:.35rem}
sources .pdf{color:var(--acc2)}
.doc-acc{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:.6rem;overflow:hidden}
.doc-acc summary{display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:.8rem 1rem;cursor:pointer;font-size:.86rem;list-style:none}
.doc-acc summary::-webkit-details-marker{display:none}
.doc-acc summary::before{content:'▸';margin-right:.5rem;color:var(--mut);transition:transform .15s}
.doc-acc[open] summary::before{transform:rotate(90deg)}
.acc-title{font-weight:600;flex:1}
.acc-meta{font-size:.72rem;color:var(--mut);white-space:nowrap}
.acc-body{padding:0 1rem 1rem 2.1rem;border-top:1px dashed var(--line)}
.acc-body .themes{margin:.8rem 0}
.acc-links{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:.8rem}
.acc-links .btn{padding:.5rem 1rem;font-size:.8rem}
/* doc pages: full text + images */
.doc-sub{color:var(--mut);font-size:.85rem;margin-top:.4rem}
.doc-num{font-weight:700;color:var(--acc2);font-size:.82em}
.full-doc{margin-top:1rem;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem 1.25rem}
.full-doc summary{cursor:pointer;font-weight:600;font-size:.95rem}
.doc-page{margin-top:1rem;padding-top:.75rem;border-top:1px dashed var(--line)}
/* highlighted target when a link arrives at #page-N */
.doc-page:target,.scan-page:target{background:#fffbeb;border-left:4px solid #f59e0b;border-radius:10px;padding:.75rem 1rem .75rem .85rem;animation:target-flash 1.6s ease-out}
.doc-page:target .page-marker,.scan-page:target figcaption{color:#b45309;font-weight:700}
@keyframes target-flash{0%{background:#fde68a}100%{background:#fffbeb}}
.page-marker{font-size:.72rem;letter-spacing:.08em;color:var(--acc2);margin-bottom:.5rem}
.md-block{font-size:.88rem;color:#334155;line-height:1.75}
.md-block p{margin:.35rem 0}
.md-h{margin:.9rem 0 .4rem;font-size:1rem}
.md-li{margin-left:1.2rem}
.img-gallery{margin-top:1rem;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:1rem 1.25rem}
.img-gallery summary{cursor:pointer;font-weight:600;font-size:.95rem;margin-bottom:.6rem}
.img-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.6rem}
.img-item{margin:0;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#fff}
.img-item img{width:100%;height:130px;object-fit:cover;display:block;background:#f1f5f9}
.img-item figcaption{font-size:.68rem;color:var(--mut);padding:.3rem .5rem;text-align:center}
.img-imp{color:#d97706;font-weight:700}
.img-sub{display:block;font-size:.62rem;color:#64748b;margin-top:.15rem;line-height:1.35}
.img-note{font-size:.72rem;color:var(--mut);margin-top:.6rem;line-height:1.5}
.img-more{display:contents}
#img-more-btn{margin-top:.75rem}
/* doc page */
.doc-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:1.25rem;align-items:start}
.doc-tags{display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.75rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:1.25rem;margin-bottom:1.25rem}
.card h2{font-size:1.05rem;margin-bottom:.6rem}
.summary{white-space:pre-wrap;font-size:.86rem;color:#475569}
.cross-sum{border-left:4px solid var(--acc2)}
.cross-sum h2{font-size:.95rem}
.toc-list{list-style:none;font-size:.84rem;color:#475569;columns:2;column-gap:2rem}
.toc-list li{padding:.22rem 0;border-bottom:1px dashed var(--line)}
.facts{list-style:none;font-size:.85rem}
.facts li{display:flex;justify-content:space-between;gap:1rem;padding:.35rem 0;border-bottom:1px dashed var(--line)}
.rel-list{list-style:none;font-size:.88rem}
.rel-list li{padding:.35rem 0;border-bottom:1px dashed var(--line)}
.rel-tag{font-size:.66rem;color:var(--mut);margin-left:.5rem;background:#f1f5f9;border-radius:999px;padding:.1rem .5rem}
.tor-theme{padding:.55rem 0;border-bottom:1px dashed var(--line)}
.tor-theme:last-child{border-bottom:none}
.tor-theme-head{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.25rem}
.tor-theme-head strong{font-size:.88rem}
.tor-theme p{font-size:.83rem;color:#475569;line-height:1.6}
/* notes */
.map-shell{{display:flex;gap:1rem;flex-wrap:wrap;align-items:flex-start;margin-bottom:1rem}}
.map-canvas{{flex:1;min-width:280px;background:linear-gradient(180deg,#fff,#f1f5f9);border:1px solid var(--line);border-radius:18px;padding:.5rem}}
#map-svg{{width:100%;height:auto}}
.map-legend{{display:flex;flex-direction:column;gap:.4rem;min-width:230px}}
.legend-item{{display:flex;align-items:center;gap:.5rem;text-align:left;border:1px solid var(--line);background:#fff;border-radius:10px;padding:.45rem .7rem;font-size:.78rem;cursor:pointer;color:#334155}}
.legend-item.active{{border-color:var(--ink);background:var(--ink);color:#fff}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.map-narrative{{margin-bottom:1rem}}
.map-narr-card{{background:#fff;border:1px solid var(--line);border-left:4px solid var(--ink);border-radius:14px;padding:1.1rem 1.25rem}}
.map-narr-head{{display:flex;align-items:center;gap:.6rem;margin-bottom:.4rem}}
.map-narr-card p{{font-size:.88rem;color:#475569}}
.map-docs{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:.7rem}}
.map-doc-chip{{display:flex;flex-direction:column;gap:.25rem;background:#fff;border:1px solid var(--line);border-radius:12px;padding:.7rem .9rem;text-decoration:none;color:inherit;transition:border-color .12s,transform .12s}}
.map-doc-chip:hover{{border-color:var(--ink);transform:translateY(-1px)}}
.chip-title{{font-size:.8rem;font-weight:600;line-height:1.35}}
.chip-meta{{font-size:.68rem;color:var(--mut)}}
/* notes */
.note-block{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--ink);border-radius:12px;padding:1.1rem 1.25rem;margin-bottom:1rem}
.note-block h3{font-size:1rem;margin-bottom:.4rem}
.note-block p{font-size:.9rem;color:#475569}
.note-block.warn{border-left-color:#f59e0b;background:#fffbeb}
.muted{color:var(--mut);font-size:.8rem}
code{background:#f1f5f9;padding:.1rem .35rem;border-radius:6px;font-size:.8em}
.zh-notice{background:#fffbeb;border:1px solid #fde68a;border-left:4px solid #f59e0b;border-radius:10px;padding:.6rem .9rem;font-size:.78rem;color:#92400e;line-height:1.55;margin-bottom:1.25rem}
.zh-notice a{color:#b45309;font-weight:600}
/* news page */
.news-para{font-size:.9rem;color:#475569;line-height:1.7}
.news-list{list-style:none;font-size:.85rem;color:#475569;margin:.4rem 0 .9rem}
.news-list li{padding:.3rem 0 .3rem 1rem;position:relative}
.news-list li::before{content:'—';position:absolute;left:0;color:var(--acc2)}
.news-list.gaps li::before{content:'▸'}
.news-sub{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--acc2);margin:1rem 0 .35rem}
.timeline{position:relative;padding-left:1.6rem;border-left:2px solid var(--line)}
.tl-item{margin-bottom:1.1rem;position:relative}
.tl-item::before{content:'';position:absolute;left:-1.68rem;top:.32rem;width:10px;height:10px;border-radius:50%;background:var(--acc2);border:2px solid #fff;box-shadow:0 0 0 2px var(--acc2)}
.tl-date{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:.8rem;color:var(--ink);letter-spacing:.02em}
.tl-body p{font-size:.85rem;color:#475569;line-height:1.65;margin:.15rem 0 .35rem}
.tl-body .themes{margin-top:.1rem}
.news-theme h3{font-size:1.05rem;margin-bottom:.5rem}
.news-art{display:flex;align-items:flex-start;gap:.9rem;background:#fff;border:1px solid var(--line);border-radius:12px;padding:.8rem 1rem;margin-bottom:.55rem}
.art-num{font-family:'Space Grotesk',sans-serif;font-weight:700;color:var(--acc2);font-size:.78rem;padding-top:.15rem;flex-shrink:0}
.art-main{flex:1;min-width:0}
.art-title{font-size:.9rem;font-weight:600;color:var(--ink);text-decoration:none;line-height:1.45}
.art-title:hover{text-decoration:underline}
.art-meta{font-size:.72rem;color:var(--mut);margin:.15rem 0 .3rem}
.art-lang{flex-shrink:0;font-size:.62rem;font-weight:700;letter-spacing:.06em;padding:.15rem .5rem;border-radius:999px;border:1px solid var(--line);color:var(--mut)}
.art-lang.lang-en{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe}
.art-lang.lang-tc{background:#fef2f2;color:#b91c1c;border-color:#fecaca}
/* responsive */
@media(max-width:900px){
  .layout{flex-direction:column}
  .sidebar{width:100%;height:auto;position:static;padding:1rem}
  .nav{flex-direction:row;flex-wrap:wrap;margin-top:.75rem}
  .nav-item{padding:.45rem .7rem}
  .sidebar-foot{display:none}
  .doc-layout{grid-template-columns:1fr}
}
@media(max-width:560px){
  .main{padding:1.25rem 1rem}
  .stats{grid-template-columns:1fr 1fr}
}
/* letter page */
.letter-doc{background:#fff;border:1px solid var(--line);border-radius:16px;padding:2rem 2.2rem;box-shadow:0 1px 2px rgb(0 0 0 / .04)}
.letter-doc h2{font-size:1.25rem;line-height:1.4;margin-bottom:1.1rem;letter-spacing:-.01em}
.letter-doc .letter-salutation{font-size:.95rem;margin-bottom:1rem}
.letter-doc p{font-size:.95rem;color:#334155;line-height:1.85;margin-bottom:1.1rem}
.letter-doc .letter-signature{color:var(--ink);font-weight:600;margin-top:1.4rem}
.letter-as-submitted{font-size:.78rem;color:var(--mut);margin-top:.6rem}
.dev-item{display:flex;gap:.6rem;align-items:baseline;padding:.45rem 0;border-bottom:1px dashed var(--line)}
.dev-item:last-child{border-bottom:none}
.dev-item .dev-date{flex-shrink:0;font-family:'Space Grotesk',monospace;font-size:.78rem;font-weight:600;color:var(--acc2)}
.dev-item p{font-size:.88rem;color:#334155;line-height:1.6}
.dev-item .dev-src{font-size:.72rem;color:var(--mut)}
/* engagement (LegCo draft) page */
.lg-hero h1{font-size:clamp(2.2rem,5vw,3.4rem);line-height:1.05}
.lg-hero p{font-size:1.05rem;max-width:680px}
.lg-card-link{display:block;text-decoration:none;color:inherit;transition:transform .15s,box-shadow .15s}
.lg-card-link:hover{transform:translateY(-3px);box-shadow:0 14px 28px -12px rgb(15 23 42/.18)}
.lg-card-link p{font-size:.9rem;color:#475569;line-height:1.65}
.lg-compare{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin:1.1rem 0}
.lg-compare .col{background:#fff;border:1px solid var(--line);border-radius:14px;padding:1.1rem 1.25rem}
.lg-compare h4{font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin-bottom:.6rem}
.lg-compare ul{list-style:none;font-size:.88rem;color:#334155}
.lg-compare li{padding:.3rem 0 .3rem 1rem;position:relative;border-bottom:1px dashed var(--line)}
.lg-compare li:last-child{border-bottom:none}
.lg-compare .col h4+ul li::before{content:'—';position:absolute;left:0;color:var(--acc2)}
.lg-quote{border-left:4px solid var(--acc2);background:#fff;border-radius:0 14px 14px 0;padding:1rem 1.4rem;font-size:1.05rem;line-height:1.65;color:var(--ink);margin:1.25rem 0}
.lg-quote small{display:block;margin-top:.5rem;color:var(--mut);font-size:.78rem}
.lg-asks{display:flex;flex-direction:column;gap:.7rem;margin-top:1rem}
.lg-ask{display:flex;gap:.9rem;background:#fff;border:1px solid var(--line);border-radius:14px;padding:.95rem 1.1rem;align-items:flex-start}
.lg-ask-num{flex-shrink:0;width:30px;height:30px;border-radius:10px;background:var(--ink);color:#fff;display:grid;place-items:center;font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:.85rem;text-transform:uppercase}
.lg-ask p{font-size:.9rem;color:#334155;line-height:1.6}
.lg-ask b{color:var(--ink)}
.lg-steps{margin-top:1rem}
.lg-duo{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1.25rem}
.lg-duo .col{background:#fff;border:1px solid var(--line);border-radius:14px;padding:1.1rem 1.25rem}
.lg-duo h4{font-size:.95rem;margin-bottom:.5rem}
.lg-duo ul{list-style:none;font-size:.85rem;color:#475569}
.lg-duo li{padding:.3rem 0 .3rem 1rem;position:relative}
.lg-duo li::before{content:'—';position:absolute;left:0;color:var(--acc2)}
.lg-cta{background:var(--ink);color:#e2e8f0;border-radius:18px;padding:1.6rem 1.8rem;margin-top:2.5rem}
.lg-cta h2{color:#fff;font-size:1.4rem;letter-spacing:-.02em}
.lg-cta p{color:#cbd5e1;font-size:.92rem;max-width:640px;margin:.5rem 0 1.1rem}
.lg-cta .btn-ghost{background:transparent;color:#fff;border-color:#334155}
.lg-cta .btn-ghost:hover{border-color:#94a3b8}
.lg-btn-light{background:#fff;color:var(--ink)!important}
.lg-btn-light:hover{background:#e2e8f0}
@media(max-width:760px){.lg-compare,.lg-duo{grid-template-columns:1fr}}

/* --- Chinese corpus page (zh-docs.html) --- */
.lede{color:var(--mut);max-width:680px;font-size:.98rem}
.section-block{margin:2rem 0}
.section-block h2{font-size:1.3rem;letter-spacing:-.01em;margin-bottom:.9rem}
.zh-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:.9rem}
.zh-meta{display:flex;flex-wrap:wrap;gap:.35rem}
.zh-links{display:flex;flex-wrap:wrap;gap:.35rem 1rem;font-size:.85rem;margin-top:auto}
.zh-links a{color:var(--accent,#2563eb);text-decoration:none}
.zh-links a:hover{text-decoration:underline}
.zh-en-link{font-weight:600}
.note-box{background:var(--card);border:1px solid var(--line);border-left:4px solid #f59e0b;border-radius:12px;padding:.9rem 1.1rem;font-size:.9rem;margin:1.25rem 0}
.tag{display:inline-block;font-size:.68rem;font-weight:600;padding:.15rem .5rem;border-radius:999px;background:rgba(37,99,235,.1);color:#1e40af}
@media(max-width:760px){.zh-grid{grid-template-columns:1fr}}
"""


def fix_abs_links(html):
    """Convert site-relative links to root-absolute so pages in subfolders work."""
    for prefix in ["index.html", "map.html", "documents.html", "zh-docs.html", "tor.html", "news.html", "about.html", "work.html", "search.html", "assets/", "doc/", "tor/", "zh/", "engagement/", "letter.html", "images.html"]:
        html = html.replace(f'href="{prefix}', f'href="/{prefix}')
    return html


def build_zh_docs():
    """Chinese-language corpus page (parallel to the 243-doc EN corpus).

    The committee's /chi/ site links 80 PDFs the EN pages never link. Presented
    here as a parallel corpus so the established '243 documents' counts stay
    valid; each card cross-links the English counterpart where one exists.
    """
    n = len(ZH_INDEX)
    n_counter = sum(1 for d in ZH_INDEX if d.get("en_counterpart"))
    cats = {}
    for d in ZH_INDEX:
        cats.setdefault(d.get("category", "Other (Chinese)"), []).append(d)
    order = sorted(cats.items(), key=lambda kv: -len(kv[1]))

    def card(d):
        tags = "".join(f'<span class="tag">{esc(t.split(":")[0])}</span>' for t in d.get("related_to_tor", [])[:3])
        counter = ""
        if d.get("en_counterpart"):
            counter = (f'<a class="zh-en-link" href="{esc(d["en_counterpart"])}" target="_blank" rel="noopener">'
                       'English version ↗</a>')
        return f"""<div class="doc-card">
  <div class="doc-card-head"><h3>{esc(d['title'])}</h3></div>
  <div class="zh-meta"><span class="tag">{esc(d['category'])}</span><span class="tag">{d.get('pages', 0)} pp</span>{tags}</div>
  <div class="zh-links">
    <a href="{esc(d['url'])}" target="_blank" rel="noopener">原文 PDF ↗</a>
    {counter}
  </div>
</div>"""

    sections = []
    for cat, docs in order:
        cards = "\n".join(card(d) for d in docs)
        sections.append(f"""<section class="section-block">
  <h2>{esc(cat)} <span class="muted">({len(docs)})</span></h2>
  <div class="zh-grid">{cards}</div>
</section>""")
    sections_html = "\n".join(sections)

    body = f"""<header class="page-head">
  <h1>Chinese-language documents <span class="muted">\u4e2d\u6587\u6587\u4ef6</span></h1>
  <p class="lede">A parallel corpus of {n} documents the Committee publishes only on its
  <a href="https://www.ic-wangfukcourtfire.gov.hk/chi/index.html" target="_blank" rel="noopener">Chinese site</a>
  \u2014 the English pages never link them, so keyword tools built on the English record miss them entirely.</p>
</header>
<div class="stats">
  {stat_card(n, 'Chinese documents', 'linked only from /chi/')}
  {stat_card(31, 'Hearing transcripts', 'Chinese versions of the hearings')}
  {stat_card(f'{n_counter}/{n}', 'with English counterpart', 'cross-linked below')}
</div>
<div class="note-box">
  <strong>Parallel corpus \u2014 counts unchanged.</strong> The main site's figures (243 documents,
  6,377 pages, 1.9M words) describe the English record and are unchanged. ToR tags below are
  provisional keyword matches; LLM semantic tagging is pending.
</div>
{sections_html}"""

    return page("Chinese Docs", "zh-docs.html", body,
                "The 80 Chinese-language inquiry documents linked only from the committee's Chinese site, cross-linked to their English counterparts.")


def main():
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    open(os.path.join(OUT, "assets", "site.css"), "w").write(CSS)
    pages = {
        "index.html": build_home(),
        "documents.html": build_documents(),
        "search.html": build_search(),
        "tor.html": build_tor(),
        "work.html": build_work(),
        "about.html": build_about(),
        "news.html": build_news(),
        "letter.html": build_letter(),
        "zh-docs.html": build_zh_docs(),
        "engagement/legcoDraft.html": build_legco_draft(),
    }
    os.makedirs(os.path.join(OUT, "engagement"), exist_ok=True)
    for name, content in pages.items():
        open(os.path.join(OUT, name), "w").write(fix_abs_links(content))
    # full-text search assets: shared JS + prebuilt inverted index
    import shutil
    os.makedirs(os.path.join(OUT, "search"), exist_ok=True)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "search.js"),
                os.path.join(OUT, "assets", "search.js"))
    shutil.copy(os.path.join(DATA, "search_index.json"), os.path.join(OUT, "search", "index.json"))
    # map.html was merged into documents.html; keep a redirect for old links
    open(os.path.join(OUT, "map.html"), "w").write(
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=/documents.html">'
        '<title>Redirecting…</title></head><body>'
        '<p>The visual map and document index are now one page: '
        '<a href="/documents.html">Map &amp; Documents</a>.</p></body></html>')
    nd = build_doc_pages()
    nt = build_tor_pages()
    print(f"Built site into {OUT}")
    print(f"  pages: {', '.join(pages)} + map.html redirect + {nd} document pages + {nt} ToR pages")
    print(f"  docs analysed: {len(ANALYSIS)}/243")


if __name__ == "__main__":
    main()
