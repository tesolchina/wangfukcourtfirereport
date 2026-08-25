#!/usr/bin/env python3
"""IMAGES_LOOKUP — build an inspectable index of ALL extracted images (8,785),
including the ones we filtered out, so every image can be reviewed one by one.

Writes:
  data/images_lookup.json  — per-image record {file, doc, doc_slug, title, page,
                             label, keep, importance, type, subject, size, w, h}
  site_out/images.html     — filterable, paginated review page (EN)
  site_out/zh/images.html  — same in Traditional Chinese

Filters (client-side JS): label (photo/diagram/page_scan/blank/junk_tiny/low_value/
unlabeled), keep state (kept/filtered/unknown), importance ★1–5, document, and a
free-text search. Shows thumbnails + metadata; click opens the full image.
"""
import json, os, re, sys, html as htmlmod

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as bs
import tc_i18n as i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "site_out")

LABEL_LABEL = {
    "photo": "Photograph", "diagram": "Diagram / plan", "page_scan": "Page scan",
    "blank": "Blank", "junk_tiny": "Fragment (junk)", "low_value": "Low value",
    "unlabeled": "No label",
}
LABEL_LABEL_TC = {
    "photo": "照片", "diagram": "圖表／圖則", "page_scan": "整頁掃描",
    "blank": "空白", "junk_tiny": "微小碎片", "low_value": "低價值",
    "unlabeled": "無標籤",
}


def esc(s):
    return htmlmod.escape(str(s or ""), quote=True)


def main():
    inv = json.load(open(os.path.join(DATA, "image_inventory.json")))
    inv_imgs = inv.get("images", {}) if isinstance(inv.get("images", {}), dict) else {}
    desc = json.load(open(os.path.join(DATA, "image_descriptions.json")))
    desc_imgs = desc.get("images", desc) if isinstance(desc.get("images", {}), dict) else desc
    idx = json.load(open(os.path.join(DATA, "index.json")))["docs"]
    # slug -> (title, doc page slug) for attribution
    slug_meta = {}
    for d in idx:
        s = os.path.splitext(os.path.basename(d.get("local_md", "")))[0]
        slug_meta[s] = {"title": d["title"], "doc_slug": s}

    files = sorted(os.listdir(os.path.join(DATA, "images")))
    records = []
    for fn in files:
        inv_r = inv_imgs.get(fn) or {}
        desc_r = desc_imgs.get(fn) or {}
        label = inv_r.get("label") or "unlabeled"
        # doc slug = filename before _pNNN_imgNNN.ext
        m = re.match(r"^(.*?)_p\d+_img\d+\.(?:jpe?g|png|gif|tiff?)$", fn, re.I)
        slug = m.group(1) if m else ""
        meta = slug_meta.get(slug, {})
        keep = desc_r.get("keep")
        try:
            imp = int(desc_r.get("importance") or 0)
        except Exception:
            imp = 0
        # The review page's 'kept' status follows the same ★3+ criterion used
        # everywhere on the site (≈1,800 meaningful images), so the counts match.
        if desc_r.get("ok"):
            review_keep = (True if imp >= 3 else False)
        else:
            review_keep = None  # unrated / not yet described
        pg_m = re.search(r"_p(\d+)_img(\d+)", fn)
        records.append({
            "file": fn,
            "slug": slug,
            "doc": meta.get("title", ""),
            "doc_slug": meta.get("doc_slug", ""),
            "page": int(pg_m.group(1)) if pg_m else 0,
            "img": int(pg_m.group(2)) if pg_m else 0,
            "label": label,
            "keep": review_keep,
            "importance": imp,
            "type": desc_r.get("type") or "",
            "subject": (desc_r.get("subject") or "").strip(),
            "size": inv_r.get("size") or os.path.getsize(os.path.join(DATA, "images", fn)),
            "w": inv_r.get("w") or 0,
            "h": inv_r.get("h") or 0,
        })

    # stats for the header
    from collections import Counter
    label_c = Counter(r["label"] for r in records)
    keep_c = Counter({True: 0, False: 0, None: 0})
    for r in records:
        keep_c[r["keep"]] += 1

    with open(os.path.join(DATA, "images_lookup.json"), "w", encoding="utf-8") as f:
        json.dump({"total": len(records), "records": records}, f, ensure_ascii=False)

    # ---------- shared JS + page ----------
    labels_json = json.dumps({k: LABEL_LABEL[k] for k in LABEL_LABEL}, ensure_ascii=False)
    tc_labels_json = json.dumps({k: LABEL_LABEL_TC[k] for k in LABEL_LABEL_TC}, ensure_ascii=False)

    def build_page(lang, title, labels_map, ui, prefix):
        js = f"""
        <script>
        const DATA = {json.dumps(records, ensure_ascii=False)};
        const LABELS = {json.dumps(labels_map, ensure_ascii=False)};
        const UI = {json.dumps(ui, ensure_ascii=False)};
        const PREFIX = {json.dumps(prefix)};
        const PAGE = 200;
        let label = 'all', keep = 'all', impMin = 0, doc = 'all', q = '', page = 0;
        function fmt(r) {{
            const k = r.keep === true ? UI.kept : (r.keep === false ? UI.filtered : UI.unknown);
            const im = r.importance ? '★'.repeat(r.importance) : '—';
            const subj = r.subject ? '<span class="lk-sub">' + esc(r.subject.slice(0, 120)) + '</span>' : '';
            const docL = r.doc ? '<span class="lk-doc"><a href="' + PREFIX + 'doc/' + esc(r.doc_slug) + '.html" target="_blank">' + esc(r.doc) + '</a></span>' : '';
            const pageL = r.page ? ' · p.' + r.page : '';
            return '<figure class="lk-item">'
              + '<a href="' + PREFIX + 'images/' + esc(r.file) + '" target="_blank" rel="noopener">'
              + '<img loading="lazy" src="' + PREFIX + 'images/' + esc(r.file) + '" alt="' + esc(r.file) + '"></a>'
              + '<figcaption><span class="lk-tag lk-' + k.cls + '">' + k.t + '</span>'
              + '<span class="lk-imp">' + im + '</span>'
              + '<span class="lk-lbl">' + LABELS[r.label] + '</span>'
              + docL + '<span class="lk-meta">' + (r.w||'?') + '×' + (r.h||'?') + pageL + '</span>'
              + subj + '</figcaption></figure>';
        }}
        function esc(s) {{ return String(s).replace(/[&<>"]/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}})[c]); }}
        function apply() {{
            let list = DATA.filter(r => {{
                if (label !== 'all' && r.label !== label) return false;
                if (keep !== 'all' && (r.keep === null ? 'unknown' : (r.keep ? 'kept' : 'filtered')) !== keep) return false;
                if (impMin && (r.importance || 0) < impMin) return false;
                if (doc !== 'all' && r.slug !== doc) return false;
                if (q) {{
                    const h = (r.file + ' ' + r.doc + ' ' + (r.subject||'') + ' ' + r.label).toLowerCase();
                    if (!h.includes(q.toLowerCase())) return false;
                }}
                return true;
            }});
            const total = list.length, pages = Math.max(1, Math.ceil(total / PAGE));
            page = Math.min(page, pages - 1);
            const slice = list.slice(page * PAGE, (page + 1) * PAGE);
            document.getElementById('lk-count').textContent = UI.count.replace('{{n}}', total).replace('{{m}}', DATA.length);
            document.getElementById('lk-grid').innerHTML = slice.map(fmt).join('') || '<p class="muted">' + UI.none + '</p>';
            document.getElementById('lk-page').textContent = UI.pg.replace('{{p}}', page + 1).replace('{{n}}', pages);
            document.getElementById('lk-prev').disabled = page <= 0;
            document.getElementById('lk-next').disabled = page >= pages - 1;
        }}
        function bind(id, fn) {{ document.getElementById(id).addEventListener('change', fn); }}
        bind('lk-label', e => {{ label = e.target.value; page = 0; apply(); }});
        bind('lk-keep', e => {{ keep = e.target.value; page = 0; apply(); }});
        bind('lk-imp', e => {{ impMin = +e.target.value; page = 0; apply(); }});
        bind('lk-doc', e => {{ doc = e.target.value; page = 0; apply(); }});
        document.getElementById('lk-q').addEventListener('input', e => {{ q = e.target.value; page = 0; apply(); }});
        document.getElementById('lk-prev').addEventListener('click', () => {{ page--; apply(); }});
        document.getElementById('lk-next').addEventListener('click', () => {{ page++; apply(); }});
        // populate doc select
        const docs = {{}};
        DATA.forEach(r => {{ if (r.slug && !docs[r.slug]) docs[r.slug] = r.doc; }});
        const sel = document.getElementById('lk-doc');
        Object.keys(docs).sort().forEach(s => {{
            const o = document.createElement('option'); o.value = s; o.textContent = docs[s].slice(0, 60); sel.appendChild(o);
        }});
        apply();
        </script>
        """
        sel_options = "".join(
            f'<option value="{esc(v)}">{esc(k)}</option>'
            for k, v in [("—", "all")] + [(labels_map[l], l) for l in labels_map]
        )
        body = f"""
        <section class="page-head">
          <h1>{esc(title)}</h1>
          <p>{esc(ui["intro"])}</p>
        </section>
        <section class="block">
          <div class="toolbar lk-toolbar">
            <input id="lk-q" type="search" placeholder="{esc(ui['qph'])}">
            <select id="lk-label">{sel_options}</select>
            <select id="lk-keep">
              <option value="all">{esc(ui['keep_all'])}</option>
              <option value="kept">{esc(ui['kept'])}</option>
              <option value="filtered">{esc(ui['filtered'])}</option>
              <option value="unknown">{esc(ui['unknown'])}</option>
            </select>
            <select id="lk-imp">
              <option value="0">{esc(ui['imp_all'])}</option>
              <option value="3">★3+</option><option value="4">★4+</option><option value="5">★5</option>
            </select>
            <select id="lk-doc"><option value="all">{esc(ui['doc_all'])}</option></select>
          </div>
          <p class="lk-count" id="lk-count"></p>
          <div class="lk-grid" id="lk-grid"></div>
          <div class="lk-pager">
            <button class="btn btn-ghost" id="lk-prev">← {esc(ui['prev'])}</button>
            <span id="lk-page"></span>
            <button class="btn btn-ghost" id="lk-next">{esc(ui['next'])} →</button>
          </div>
        </section>
        """
        return page_html(lang, title, body + js, ui)

    def page_html(lang, title, body, ui):
        # EN: reuse build_site's page() template (sidebar nav, shared CSS).
        if lang == "en":
            return bs.page(title, "images.html", body, ui.get("desc", ""))
        # TC: minimal mirror of page_tc (sidebar nav from i18n.NAV).
        nav = []
        for label, href in i18n.NAV:
            cls = ' class="nav-item active"' if href == "images.html" else ' class="nav-item"'
            nav.append(f'<a{cls} href="/zh/{href}">{esc(label)}</a>')
        nav_html = "\n".join(nav)
        brand_a, brand_b = i18n.BRAND
        return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <a class="brand" href="/zh/index.html">
      <span class="brand-mark">WF</span>
      <span class="brand-text"><strong>{esc(brand_a)}</strong><small>{esc(brand_b)}</small></span>
    </a>
    <nav class="nav">{nav_html}</nav>
    <div class="sidebar-foot">
      <a href="/images.html" class="lang-switch">English version →</a>
    </div>
  </aside>
  <main class="main"><div class="container">
{body}
  </div></main>
</div>
</body></html>"""

    ui_en = {
        "intro": ("All {m} images extracted from the 243 PDFs, including those automatically filtered "
                  "out, listed for review. Use the filters to inspect the photographs, diagrams, page "
                  "scans, blanks and fragments one by one; click any thumbnail for the full image."),
        "qph": "Search file name, document, subject…",
        "keep_all": "Any status", "kept": "Kept", "filtered": "Filtered out", "unknown": "Unrated",
        "imp_all": "Any importance", "doc_all": "All documents",
        "prev": "Prev", "next": "Next",
        "count": "{n} of {m} images",
        "pg": "Page {p} of {n}", "none": "No images match the filters.",
        "desc": "All 8,785 extracted images with filters for review",
    }
    ui_en["intro"] = ui_en["intro"].replace("{m}", str(len(records)))
    ui_tc = {
        "intro": (f"以下為從 243 份 PDF 抽取的全部 {len(records)} 張圖片（包括被自動篩走的），供逐張覆核。"
                  "可用篩選器逐一檢視照片、圖表、整頁掃描、空白及碎片；點擊縮圖查看原圖。"),
        "qph": "搜尋檔名、文件、內容…",
        "keep_all": "任何狀態", "kept": "已保留", "filtered": "已篩走", "unknown": "未評級",
        "imp_all": "任何重要性", "doc_all": "所有文件",
        "prev": "上一頁", "next": "下一頁",
        "count": "共 {n} / {m} 張圖片",
        "pg": "第 {p} / {n} 頁", "none": "沒有符合篩選條件的圖片。",
        "desc": "全部 8,785 張抽取圖片（含篩走者），附篩選器供覆核",
    }

    en_html = build_page("en", "All Images — Review", LABEL_LABEL, ui_en, "")
    zh_html = build_page("zh-Hant", "全部圖片 — 覆核", LABEL_LABEL_TC, ui_tc, "../")

    os.makedirs(os.path.join(OUT, "zh"), exist_ok=True)
    open(os.path.join(OUT, "images.html"), "w", encoding="utf-8").write(en_html)
    open(os.path.join(OUT, "zh", "images.html"), "w", encoding="utf-8").write(zh_html)

    print(f"images_lookup.json: {len(records)} records")
    print("label counts:", dict(label_c))
    print("keep counts:", dict(keep_c))
    print("wrote site_out/images.html + site_out/zh/images.html")


if __name__ == "__main__":
    main()
