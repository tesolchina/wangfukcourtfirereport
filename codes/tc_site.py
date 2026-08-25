# -*- coding: utf-8 -*-
"""Generate the Traditional Chinese (繁體中文) mirror of the site into site_out/zh/.

Reuses build_site's data + helpers. Pages use RELATIVE links so the /zh/ tree
resolves internally (zh/doc/*.html -> /zh/doc/...). A language switcher links
EN <-> 中文. Usage: python3 codes/tc_site.py
"""
import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_site as bs
import tc_i18n as i18n
from build_site import (esc, slug_of, DOC_NUM, BY_TITLE, INDEX, ANALYSIS,
                        doc_language, LANG_LABEL, doc_cross_summary,
                        doc_full_summary, clean_doc_text, md_to_html,
                        WORK, WORK_BY_TITLE, DOC_META, doc_type_label,
                        IMAGE_DESC, IMAGE_INV, _JUNK_LABELS, img_keep_and_caption,
                        TOR_TAGS, TOR_NARRATIVES, METHODOLOGY, doc_tor_tags,
                        old_tor_counts)

ROOT = bs.ROOT
DATA = bs.DATA
ZH = os.path.join(ROOT, "site_out", "zh")

CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def tor_tc(tag):
    key = tag.split(":")[0].strip()
    return i18n.TOR_TITLES.get(tag, i18n.TOR_TITLES.get(key, tag))


def tor_blurb_tc(tag):
    key = tag.split(":")[0].strip()
    return i18n.TOR_BLURBS.get(tag, i18n.TOR_BLURBS.get(key, ""))


def tor_narr_tc(tag):
    key = tag.split(":")[0].strip()
    return i18n.TOR_NARRATIVES.get(tag, i18n.TOR_NARRATIVES.get(key, TOR_NARRATIVES.get(tag, "")))


def tc_summary_for(doc):
    """Best TC summary: cross_lang summary_zh (en docs) or the Chinese index summary
    (zh docs), else empty."""
    t = doc["title"]
    cross = bs.CROSS_LANG.get(t, {})
    if cross.get("direction") == "zh":
        s = (cross.get("summary_zh") or "").strip()
        if s:
            return s
    s = (doc.get("summary") or "").strip()
    if CJK_RE.search(s):
        return s
    return ""


def fix_tc_links(html):
    """Convert TC-page links to root-absolute so /zh/doc/ and /zh/tor/ pages work."""
    for p in ["index.html", "documents.html", "tor.html", "work.html", "news.html", "about.html"]:
        html = html.replace(f'href="{p}"', f'href="/zh/{p}"')
    html = html.replace('href="../assets/', 'href="/assets/')
    html = html.replace('href="../images/', 'href="/images/')
    html = html.replace('src="../images/', 'src="/images/')
    html = html.replace('href="../doc/', 'href="/zh/doc/')
    html = html.replace('href="../tor/', 'href="/zh/tor/')
    html = html.replace('href="doc/', 'href="/zh/doc/')
    html = html.replace('href="tor/', 'href="/zh/tor/')
    html = html.replace('href="../index.html"', 'href="/index.html"')
    return html


def page_tc(title, active, body, desc=""):
    nav = []
    for label, href in i18n.NAV:
        cls = ' class="nav-item active"' if href == active else ' class="nav-item"'
        nav.append(f'<a{cls} href="/zh/{href}">{label}</a>')
    nav_html = "\n".join(nav)
    brand_a, brand_b = i18n.BRAND
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)} · 大埔宏福苑火災調查</title>
<meta name="description" content="{esc(desc)}">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <a class="brand" href="/zh/index.html">
      <span class="brand-mark">富</span>
      <span class="brand-text"><strong>{esc(brand_a)}</strong><small>{esc(brand_b)}</small></span>
    </a>
    <nav class="nav">{nav_html}</nav>
    <div class="sidebar-foot">
      <a href="/index.html" class="lang-switch">English version →</a>
      <a href="https://www.ic-wangfukcourtfire.gov.hk/chi/index.html" target="_blank" rel="noopener">委員會官方網站 ↗</a>
      <small>教育用途 · Dr Simon Wang 編纂</small>
      <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">GitHub 開源 ↗</a>
    </div>
  </aside>
  <main class="main">
    <div class="zh-notice">部分中文翻譯或有不準確之處，本網站正持續檢視及修正中。如發現錯誤，歡迎電郵
      <a href="mailto:simonwanghkteacher@gmail.com">simonwanghkteacher@gmail.com</a> 告知。
      所有內容請以<a href="https://www.ic-wangfukcourtfire.gov.hk/chi/index.html" target="_blank" rel="noopener">官方網站</a>的原始文件為準。</div>
    {body}
    <footer class="page-foot">
      <span>資料源自就大埔宏福苑火災成立的獨立委員會 · 供記者及公眾參考</span>
      <span class="muted">教育用途 · 非商業性質 · <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">GitHub 開源 ↗</a></span>
    </footer>
  </main>
</div>
</body>
</html>"""


def doc_link_tc(slug):
    return f"doc/{esc(slug)}.html"


def build_home_tc():
    tor_cards = []
    ana_tor = {}
    for d in INDEX:
        for t in doc_tor_tags(d):
            ana_tor[t] = ana_tor.get(t, 0) + 1
    old_tor = bs.old_tor_counts()
    for key, tag, blurb in TOR_TAGS:
        n = ana_tor.get(tag, 0)
        o = old_tor.get(tag, 0)
        old_note = f' <span class="tor-old" title="早前摘要級閱讀找到 {o} 份文件；通讀全文後為 {n} 份">(原 {o})</span>' if o != n else ""
        fname = re.sub(r"[^A-Za-z0-9]+\s*", "", tag.split(":")[0]) + ".html"
        tor_cards.append(f"""
        <a class="tor-card" href="tor/{fname}">
          <div class="tor-card-top"><span class="tor-chip">{esc(key)}</span><span class="tor-count">{n} 份文件{old_note}</span></div>
          <div class="tor-card-title">{esc(tor_tc(tag))}</div>
          <div class="tor-card-blurb">{esc(tor_blurb_tc(tag))}</div>
        </a>""")
    stats = "".join([
        f'<div class="stat-card"><div class="stat-value">{len(INDEX)}</div><div class="stat-label">文件</div><div class="stat-sub">243 份 PDF 已處理</div></div>',
        f'<div class="stat-card"><div class="stat-value">{sum(d.get("pages") or 0 for d in INDEX):,}</div><div class="stat-label">頁數</div><div class="stat-sub">報告與謄本</div></div>',
        f'<div class="stat-card"><div class="stat-value">約 1,800</div><div class="stat-label">圖片</div><div class="stat-sub">篩選後有價值之照片及圖表（原本抽取 <a class="stat-link" href="about.html#images">8,785</a> 張）</div></div>',
        '<div class="stat-card"><div class="stat-value">1,875,666</div><div class="stat-label">字數</div><div class="stat-sub">約 190 萬字</div></div>',
        f'<div class="stat-card"><div class="stat-value">{WORK.get("total_hours", 0):,.0f}</div><div class="stat-label">估算工時</div><div class="stat-sub">見工作量頁</div></div>' if WORK.get("total_hours") else "",
    ])
    body = f"""
    <section class="page-head">
      <h1>大埔宏福苑火災調查文件庫</h1>
      <p>本網站重新整理獨立委員會公開的 {len(INDEX)} 份文件，按委員會的七項職權範圍編排，方便記者及公眾以「問題」而非「檔案順序」搜尋證據。</p>
    </section>
    <section class="stats">{stats}</section>
    <section class="block narrow">
      <h2>火災與委員會</h2>
      <p>2025 年 11 月 26 日，大埔宏福苑發生嚴重火災。宏福苑為居者有其屋計劃屋苑，由八幢於 1983 年落成的高層住宅大廈組成。事發時，所有八幢大廈正同時進行外牆維修及翻新工程，整幢大廈由地面至天台均被竹棚及保護網包圍。大火持續焚燒約 43 小時，奪去 168 條人命（包括一名消防人員），79 人受傷。在行動高峰期，共出動 174 輛消防車、47 輛救護車及 989 名消防人員，為消防處歷來最大規模的部署。</p>
      <p>行政長官於 2025 年 12 月 2 日宣布成立獨立委員會，12 月 12 日正式成立，目標於九個月內完成工作。委員會由現任高等法院法官出任主席。其<a href="tor.html">職權範圍</a>涵蓋四個方面：（一）火災成因、火勢蔓延及傷亡，包括消防裝置及維修工程；（二）系統性問題——相連利益、合謀串連及圍標；（三）現行法律及罰則是否足夠；（四）提出建議。委員會舉行了 27 個聆訊日的公開聽證，聽取了 73 名事實證人及 7 名專家證人的供詞，接獲近百萬份文件，數據總量超過 1&nbsp;TB。</p>
    </section>
    <section class="block narrow">
      <h2>政府網站——及其不足</h2>
      <p>委員會已將其材料上載至<a href="https://www.ic-wangfukcourtfire.gov.hk/eng/documents.html" target="_blank" rel="noopener">官方網站</a>——共 243 份文件，包括調查報告、專家報告、聆訊謄本、證人陳述書、結案陳詞、承建商回覆及法律陳詞。這是高度的透明度。然而，材料按委員會的工作順序編排，而非按其被要求回答的問題編排。網站設有搜尋列——由政府通用搜尋引擎驅動——但只索引 PDF 檔案名稱及快取文字，結果以扁平連結列表形式返回，無法按主題篩選、顯示詞彙出現的頁碼，或按職權範圍分組。搜尋「collusion」返回 30 個 PDF 連結；用戶仍需逐一打開 PDF 並手動搜尋。243 份文件共 6,377 頁、約 190 萬字——遠超任何記者或公眾人士所能通讀。</p>
    </section>
    <section class="block narrow">
      <h2>委員會的發現——摘要</h2>
      <p>委員會的結案陳詞，根據完整的證據紀錄，指出一連串系統性失誤：主承建商（宏業）蓄意購買非阻燃棚網及使用可燃發泡膠板封蓋窗戶，並提供疑為偽造的測試證書；註冊消防裝置承辦商（中華發展）從未到訪現場便提交關閉通知書，僅作「橡皮圖章」；監督顧問（鴻毅）完全沒有履行監督職責；物業管理公司（置邦）允許非持牌人員操作消防裝置。消防裝置關閉通知書制度——原意是讓消防處監察安全——被系統性地濫用。競爭事務委員會及廉政公署的證據顯示，樓宇維修行業的圍標及合謀問題屬系統性且積弊已久。委員會的完整結案陳詞長達 627 頁；主要發現已摘要於本網站各文件頁及<a href="tor.html">職權範圍視角</a>中。</p>
    </section>
    <section class="block narrow">
      <h2>本網站能做什麼是原始網站做不到的</h2>
      <p>委員會的最終報告將提出結論。政府的文件網站給你 243 份按日期排列的 PDF。兩者都不能讓你提出一個問題，然後跨所有文件找到每一段相關段落。本網站可以。以下是記者或居民可以在本網站回答、但無法僅靠最終報告或瀏覽政府網站回答的具體問題：</p>
      <ul>
        <li><strong>「哪些文件含有圍標證據？」</strong>——政府網站按日期列出文件；最終報告引用部分文件。在本網站，<a href="documents.html?tor=ToR5">99 份文件</a>被標籤並列出，每份均附有與合謀相關的摘要——包括從未使用「合謀」一詞、但描述口頭分判、橡皮圖章批核、以及由大判控制工作分配的文件。</li>
        <li><strong>「每個承建商實際上說了什麼？」</strong>——最終報告作摘要；政府網站給你一份 7 頁的 PDF。在本網站，每個承建商的回覆都在獨立頁面上，附有摘要、要點及直達相關段落的連結——例如安創工程承認<a href="doc/Reply-On-Cheong.html#page-7">口頭分判、沒有簽訂合約</a>，或天雄工程表示<a href="doc/Reply-Tin-Hung.html#page-6">所有工作由大判安排</a>。</li>
        <li><strong>「跨所有 243 份文件搜尋一個名字、一間公司或一個詞——並看到出現在哪一頁。」</strong>——政府網站的搜尋返回扁平的 PDF 連結列表；你必須打開每個 PDF 自行搜尋。在本網站，<a href="search.html">全文搜尋</a>涵蓋全部 190 萬字，返回每份含有該詞的文件及周邊文字摘要——讓你無需打開任何 PDF 即可看到上下文。搜尋「collusion」在本網站返回 35 份文件及摘要；在政府網站返回 30 個 PDF 連結，沒有上下文。</li>
        <li><strong>「文件之間有什麼關係？」</strong>——政府網站沒有交叉引用。在本網站，<a href="documents.html">互動地圖</a>展示哪些文件互相引用、哪些涵蓋同一主題、以及證據如何在證人陳述書、專家報告及結案陳詞之間累積。</li>
        <li><strong>「哪些文件是無法搜尋的掃描圖片？」</strong>——政府網站發布了 46 份文件（347 頁）為掃描圖片，沒有機器可讀文字。在本網站，每一頁均已 OCR 並可搜尋——<a href="about.html#ocr">關於頁面</a>記錄了這一缺口並予以譴責。</li>
        <li><strong>「在決定是否閱讀之前，給我每份文件的一頁摘要。」</strong>——政府網站只給你一個檔案名。在本網站，每份文件都有摘要、要點、主題、提及的各方及相關文件——讓你在 30 秒內評估相關性，而非下載並翻閱一份 100 頁的 PDF。</li>
      </ul>
      <p>本網站為獨立、非商業項目。本網站並非委員會的出版物，亦不作任何事實裁斷；原始文件仍為權威來源。本網站為雙語（英文及繁體中文）。</p>
    </section>
    <section class="block narrow">
      <h2>職權範圍</h2>
      <p class="block-sub">按問題瀏覽——每項職權範圍均有敘述、引用及相關文件清單。</p>
      <div class="tor-grid">{''.join(tor_cards)}</div>
    </section>
    <section class="block narrow">
      <div class="block-head"><h2>見諸報章</h2><a class="link" href="letter.html">閱讀我們的信函 →</a></div>
      <p>我們就「宏福苑火災調查文件的可及性」致《南華早報》的信函，已於 <strong>2026 年 8 月 19 日</strong>在
      <a href="https://www.scmp.com/comment/letters" target="_blank" rel="noopener">南華早報 Letters 版刊出 ↗</a>。
      信函指出委員會的 243 份文件（6,377 頁、190 萬字）按委員會工作次序而非其所須回答的問題編排；
      居民最想了解的圍標及合謀證據，埋藏在關鍵詞搜尋永遠找不到的文件之中。本網站正是我們的答案：
      <a href="documents.html">243 份文件</a>按<a href="tor.html">職權範圍</a>標籤、
      <a href="search.html">全文搜尋</a>、以及<a href="doc/Reply-On-Cheong.html#page-7">頁碼級引述</a>。
      程式碼於 <a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">GitHub 開源 ↗</a>
      （<code>projects/FireReport</code>）。</p>
    </section>
    """
    return page_tc("首頁", "index.html", body, "大埔宏福苑火災調查文件庫")


def build_documents_tc():
    """Merged map + documents, TC chrome. Reuses the EN payload structure."""
    groups = {tag: [] for _, tag, _ in TOR_TAGS}
    groups["General / Other"] = []
    all_docs = []
    for d in INDEX:
        a = bs.ana(d)
        tags = bs.doc_tor_tags(d)
        cross = doc_cross_summary(d)
        cross_txt = cross[1] if cross else ""
        excerpt = clean_doc_text(d)[:900]
        base = " ".join([d["title"], doc_type_label(d), LANG_LABEL.get(doc_language(d), ""),
                         (d.get("summary") or ""), cross_txt, excerpt,
                         *a.get("themes", []), *a.get("key_points", [])]).lower()
        extra = [t for t in bs.doc_search_terms(d) if t not in base][:150]
        search = (base + " " + " ".join(extra)).lower()
        rec = {"slug": slug_of(d), "title": d["title"], "url": d.get("url", ""),
               "num": DOC_NUM.get(d["title"], ""),
               "pages": d.get("pages") or 0, "images": d.get("images") or 0,
               "themes": (a.get("themes") or [])[:2],
               "kp": (a.get("key_points") or [""])[0],
               "tor_tag": tags[0],
               "type": doc_type_label(d),
               "lang": LANG_LABEL.get(doc_language(d), "English"),
               "zh_sum": tc_summary_for(d)[:160],
               "search": search}
        all_docs.append(rec)
        for t in tags:
            groups.setdefault(t, []).append(rec)
    data = []
    for i, (key, tag, blurb) in enumerate(TOR_TAGS):
        data.append({"key": key, "tag": tag, "tc": tor_tc(tag), "narrative": tor_narr_tc(tag),
                     "color": bs.TOR_COLORS[i], "docs": groups.get(tag, [])})
    data.append({"key": "Gen", "tag": "General / Other", "tc": tor_tc("General / Other"),
                 "narrative": tor_narr_tc("General / Other"), "color": bs.TOR_COLORS[-1],
                 "docs": groups.get("General / Other", [])})
    payload = json.dumps({"groups": data, "all": all_docs}, ensure_ascii=False)

    body = f"""
    <section class="page-head">
      <h1>地圖與文件</h1>
      <p>{len(INDEX)} 份文件如何對應委員會的職權範圍。點擊圖中節點（或篩選按鈕）查看文件；點擊任何文件開啟其完整頁面。</p>
    </section>
    <section class="map-shell">
      <div class="map-canvas"><svg id="map-svg" viewBox="0 0 940 640" role="img" aria-label="職權範圍關係圖"></svg></div>
      <div class="map-legend" id="map-legend"></div>
    </section>
    <section class="toolbar">
      <input id="map-search" type="search" placeholder="搜尋文件…">
      <div id="tor-filters" class="filters"><button class="filter" data-tor="">全部</button></div>
      <span class="doc-count" id="doc-count"></span>
    </section>
    <section id="map-narrative" class="map-narrative"></section>
    <section id="map-docs"></section>
    <script>
    const DATA = {payload};
    const svg = document.getElementById('map-svg');
    const CX = 470, CY = 300, R = 215, CENTER = 84;
    let active = null, curTag = '', query = '';
    function el(n,a){{const e=document.createElementNS('http://www.w3.org/2000/svg',n);for(const k in a)e.setAttribute(k,a[k]);return e;}}
    function esc(s){{return String(s).replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}})[c]);}}
    svg.appendChild(el('circle',{{cx:CX,cy:CY,r:CENTER,fill:'#0f172a'}}));
    const ct=el('text',{{x:CX,y:CY-8,'text-anchor':'middle',fill:'#fff','font-size':'15','font-weight':'700'}});ct.textContent='獨立委員會';svg.appendChild(ct);
    const ct2=el('text',{{x:CX,y:CY+10,'text-anchor':'middle',fill:'#cbd5e1','font-size':'11'}});ct2.textContent='大埔宏福苑火災';svg.appendChild(ct2);
    const nodes=DATA.groups.map((g,i)=>{{
      const a=(i/DATA.groups.length)*2*Math.PI-Math.PI/2;
      const x=CX+R*Math.cos(a),y=CY+R*Math.sin(a);
      svg.appendChild(el('line',{{x1:CX,y1:CY,x2:x,y2:y,stroke:g.color,'stroke-width':2,opacity:.35}}));
      const g2=el('g',{{'data-key':g.key,style:'cursor:pointer'}});
      g2.appendChild(el('circle',{{cx:x,cy:y,r:58,fill:g.color,stroke:'#fff','stroke-width':3}}));
      const t1=el('text',{{x:x,y:y-4,'text-anchor':'middle',fill:'#fff','font-size':'12','font-weight':'700'}});t1.textContent=g.key;
      const t2=el('text',{{x:x,y:y+12,'text-anchor':'middle',fill:'rgba(255,255,255,.9)','font-size':'9'}});t2.textContent=g.docs.length+' 份文件';
      g2.appendChild(t1);g2.appendChild(t2);
      const tip=el('title',{{}});tip.textContent=g.tc+' — '+g.docs.length+' 份文件。';g2.appendChild(tip);
      svg.appendChild(g2);
      g2.addEventListener('click',()=>select(g.key));
      return {{key:g.key,x,y}};
    }});
    const legend=document.getElementById('map-legend');
    DATA.groups.forEach(g=>{{
      const b=document.createElement('button');b.className='legend-item';b.dataset.key=g.key;
      b.innerHTML='<span class="legend-dot" style="background:'+g.color+'"></span>'+esc(g.tc);
      b.addEventListener('click',()=>select(g.key));legend.appendChild(b);
    }});
    const bar=document.getElementById('tor-filters');
    DATA.groups.forEach(g=>{{
      const b=document.createElement('button');b.className='filter';b.dataset.tor=g.tag;b.textContent=g.tc;bar.appendChild(b);
    }});
    function groupOf(d){{return (active&&d.themes&&d.themes[0])?d.themes[0]:(d.tor_tag||'General / Other');}}
    function rowHtml(d){{
      const zh=d.zh_sum?'<div class="row-sub zh-sum">'+esc(d.zh_sum)+'</div>':'';
      return '<li class="doc-row"><span class="doc-num">#'+esc(d.num)+'</span>'+
        '<div class="row-main"><a class="row-title" href="'+esc(docPage(d.slug))+'">'+esc(d.title)+'</a>'+zh+'</div>'+
        '<div class="row-meta"><span class="tor-badge">'+esc(d.tor_tag)+'</span>'+
        '<span class="type-badge">'+esc(d.type)+'</span>'+
        '<span>'+d.pages+'p · '+d.images+' img</span>'+
        '<a class="row-pdf" href="'+esc(d.url)+'" target="_blank" rel="noopener">PDF ↗</a></div></li>';
    }}
    function docPage(slug){{return 'doc/'+encodeURIComponent(slug)+'.html';}}
    function render(){{
      const src=active?(DATA.groups.find(x=>x.key===active)?.docs||[]):DATA.all;
      const q=query.trim().toLowerCase();
      const list=src.filter(d=>!q||d.search.includes(q));
      const box=document.getElementById('map-docs');box.innerHTML='';
      if(!list.length){{box.innerHTML='<p class="muted">沒有相符文件。</p>';setCount(0);return;}}
      const groups={{}};list.forEach(d=>{{(groups[groupOf(d)]=groups[groupOf(d)]||[]).push(d);}});
      Object.keys(groups).sort().forEach(k=>{{
        const h=document.createElement('h3');h.className='map-group-head';h.textContent=k+' ('+groups[k].length+')';box.appendChild(h);
        const ul=document.createElement('ul');ul.className='doc-list';ul.innerHTML=groups[k].map(rowHtml).join('');box.appendChild(ul);
      }});setCount(list.length);
    }}
    function setCount(n){{document.getElementById('doc-count').textContent=n+' / '+DATA.all.length+' 份文件';}}
    function select(key){{
      const g=DATA.groups.find(x=>x.key===key);active=key;curTag=g.tag;
      document.querySelectorAll('[data-key]').forEach(n=>{{if(n.tagName==='G')n.style.opacity=(n.dataset.key===key)?1:.45;}});
      legend.querySelectorAll('.legend-item').forEach(b=>b.classList.toggle('active',b.dataset.key===key));
      bar.querySelectorAll('.filter').forEach(b=>b.classList.toggle('active',b.dataset.tor===g.tag));
      document.getElementById('map-narrative').innerHTML='<div class="map-narr-card"><div class="map-narr-head"><span class="tor-chip">'+esc(g.key)+'</span> <strong>'+esc(g.tc)+'</strong></div><p>'+esc(g.narrative)+'</p></div>';
      render();
    }}
    function showAll(){{active=null;curTag='';
      document.querySelectorAll('svg g').forEach(n=>n.style.opacity=1);
      legend.querySelectorAll('.legend-item').forEach(b=>b.classList.remove('active'));
      bar.querySelectorAll('.filter').forEach(b=>b.classList.toggle('active',b.dataset.tor===''));
      document.getElementById('map-narrative').innerHTML='';render();}}
    bar.addEventListener('click',e=>{{const b=e.target.closest('.filter');if(!b)return;const t=b.dataset.tor||'';if(!t){{showAll();return;}}const g=DATA.groups.find(x=>x.tag===t);if(g)select(g.key);}});
    document.getElementById('map-search').addEventListener('input',e=>{{query=e.target.value;render();}});
    showAll();
    </script>
    """
    return page_tc("地圖與文件", "documents.html", body, "大埔宏福苑火災調查文件")


def build_tor_index_tc():
    cards = []
    old_tor = bs.old_tor_counts()
    for key, tag, blurb in TOR_TAGS:
        n = sum(1 for d in INDEX if tag in bs.doc_tor_tags(d))
        o = old_tor.get(tag, 0)
        old_note = f' <span class="tor-old" title="早前摘要級閱讀找到 {o} 份文件；通讀全文後為 {n} 份">(原 {o})</span>' if o != n else ""
        fname = re.sub(r"[^A-Za-z0-9]+\s*", "", key) + ".html"
        cards.append(f"""
        <article class="tor-perspective">
          <div class="tor-card-top"><span class="tor-chip">{esc(key)}</span><span class="tor-count">{n} 份文件{old_note}</span></div>
          <h3><a href="tor/{fname}">{esc(tor_tc(tag))}</a></h3>
          <p class="tor-narr">{esc(tor_narr_tc(tag))}</p>
          <a class="link" href="tor/{fname}">開啟此視角 →</a>
        </article>""")
    tor_method_note = (
        '<p class="muted tor-method-note">數字基於通讀全部文件的段落級分析。括號內為早前摘要級閱讀的舊數字——兩者差異顯示有多少相關材料在關鍵詞或摘要閱讀下不可見（見<a href="about.html#tor-counts">方法學</a>）。</p>'
        if any(old_tor.get(t, 0) != sum(1 for d in INDEX if t in bs.doc_tor_tags(d)) for _, t, _ in TOR_TAGS) else ""
    )
    body = f"""
    <section class="page-head">
      <h1>職權範圍視角</h1>
      <p>從委員會授權範圍的每個角度閱讀調查文件。每個視角頁面解釋敘述脈絡，並引用相關文件。</p>
    </section>
    <section class="tor-perspectives">{''.join(cards)}</section>
    {tor_method_note}
    """
    return page_tc("職權範圍視角", "tor.html", body, "按職權範圍整理的敘述與引用")


def build_tor_page_tc(key, tag):
    fname = re.sub(r"[^A-Za-z0-9]+\s*", "", key) + ".html"
    docs = []
    for d in sorted(INDEX, key=lambda x: x["title"].lower()):
        if tag in bs.doc_tor_tags(d):
            docs.append(d)
    acc = []
    for d in docs:
        a = bs.ana(d)
        kps = "".join(f"<li>{esc(p)}</li>" for p in (a.get("key_points") or [])[:3])
        zh = tc_summary_for(d)
        zh_html = f'<div class="row-sub zh-sum">{esc(zh[:300])}</div>' if zh else ""
        acc.append(f"""
        <details class="doc-acc">
          <summary><span class="acc-title">#{DOC_NUM.get(d['title'],'')} {esc(d['title'])}</span></summary>
          <div class="acc-body">
            {zh_html}
            <ul class="doc-points">{kps}</ul>
            <div class="acc-links">
              <a class="btn btn-ghost" href="../{doc_link_tc(slug_of(d))}">完整頁面</a>
              <a class="btn btn-dark" href="{esc(d.get('url',''))}" target="_blank" rel="noopener">原始 PDF ↗</a>
            </div>
          </div>
        </details>""")
    wl = WORK.get("by_tor", {}).get(tag, {})
    work_line = ""
    if wl:
        work_line = (f'<p class="doc-sub">估算工時：<strong>{wl.get("hours_split",0):,.0f} 小時</strong> · '
                     f'{wl.get("docs",len(docs))} 份文件 · {wl.get("pages",0):,} 頁</p>')
    o = bs.old_tor_counts().get(tag, 0)
    old_note = f' <span class="tor-old" title="早前摘要級閱讀找到 {o} 份文件；通讀全文後為 {len(docs)} 份">(原 {o})</span>' if o != len(docs) else ""
    body = f"""
    <section class="page-head">
      <p class="crumbs"><a href="tor.html">職權範圍視角</a> → {esc(key)}</p>
      <h1>{esc(tor_tc(tag))}</h1>
      <p class="block-sub">{esc(tor_blurb_tc(tag))}</p>
      {work_line}
    </section>
    <section class="block">
      <div class="methodology"><strong>本報告的製作方法。</strong> {esc(METHODOLOGY)}</div>
    </section>
    <section class="block">
      <div class="card"><h2>閱讀指引</h2><p class="tor-narr">{esc(tor_narr_tc(tag))}</p></div>
    </section>
    <section class="block">
      <div class="block-head"><h2>此職權範圍內的所有文件（{len(docs)}{old_note}）</h2></div>
      <p class="block-sub">展開每份文件以查看其摘要、要點及連結。</p>
      {''.join(acc)}
    </section>
    """
    return page_tc(tor_tc(tag), "tor.html", body, tor_tc(tag))


def build_work_tc():
    th = WORK.get("total_hours", 0)
    days = WORK.get("total_person_days", 0)
    years = round(days / 250, 1)
    rows = []
    for typ, v in sorted(WORK.get("by_type", {}).items(), key=lambda x: -x[1]["hours"]):
        rows.append(f'<tr><td>{esc(typ.replace("_"," ").title())}</td><td class="num">{v["count"]}</td><td class="num">{v["pages"]:,}</td><td class="num">{v["hours"]:,.0f}</td></tr>')
    bars = []
    tor_items = sorted(WORK.get("by_tor", {}).items(), key=lambda x: -x[1]["hours_split"])
    mx = tor_items[0][1]["hours_split"] if tor_items else 1
    for tag, v in tor_items:
        pct = v["hours_split"] / mx * 100
        bars.append(f'<div class="work-tor-row"><div class="work-tor-label">{esc(tor_tc(tag))} <span class="muted">{v["docs"]} 份文件 · {v["pages"]:,} 頁</span></div><div class="work-bar"><div class="work-bar-fill" style="width:{pct:.1f}%"></div></div><div class="work-tor-hours">{v["hours_split"]:,.0f} h</div></div>')
    body = f"""
    <section class="page-head">
      <h1>{esc(i18n.WORK_LABELS["title"])}</h1>
      <p>{esc(i18n.WORK_LABELS["intro"])}</p>
    </section>
    <section class="stats">
      <div class="stat-card"><div class="stat-value">{th:,.0f}</div><div class="stat-label">{esc(i18n.WORK_LABELS["stats"][0])}</div></div>
      <div class="stat-card"><div class="stat-value">{days:,.0f}</div><div class="stat-label">{esc(i18n.WORK_LABELS["stats"][1])}</div></div>
      <div class="stat-card"><div class="stat-value">{years}</div><div class="stat-label">{esc(i18n.WORK_LABELS["stats"][2])}</div></div>
    </section>
    <section class="note-block">
      <h3>{esc(i18n.WORK_LABELS["methodology_title"])}</h3>
      <p>每份文件按其類型賦予「基礎工時」（證人供詞約 12 小時、聆訊一節約 8 小時、專家分析約 60 小時、跨部門調查報告約 120 小時、結案陳詞約 40 小時、例行通告約 1.5 小時），另加每頁 0.12 小時的閱讀／覆核時間。文件若標註多項職權範圍，其工時會平均分配至各範圍，因此各範圍數字之和等於總數。詳細基礎數字見 data/work_ledger.json。</p>
    </section>
    <section class="block narrow">
      <h2>{esc(i18n.WORK_LABELS["by_type"])}</h2>
      <div class="table-wrap"><table class="work-table"><thead><tr><th>工種</th><th class="num">文件</th><th class="num">頁數</th><th class="num">估算工時</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    </section>
    <section class="block narrow">
      <h2>{esc(i18n.WORK_LABELS["by_tor"])}</h2>
      {''.join(bars)}
    </section>
    """
    return page_tc(i18n.WORK_LABELS["title"], "work.html", body, i18n.WORK_LABELS["title"])


def news_label():
    for lbl, href in i18n.NAV:
        if href == "news.html":
            return lbl
    return "新聞與報導"


def build_news_tc():
    nl = news_label()
    themes = bs.NEWS.get("themes", [])
    cards = []
    for th in themes:
        tid = th.get("id", "")
        title = i18n.NEWS_THEME_TITLES.get(tid, th.get("title", ""))
        coverage = th.get("coverage", "")
        gaps = th.get("gaps", "")
        cards.append(f"""
        <div class="card" id="theme-{esc(tid)}">
          <h3>{esc(title)}</h3>
          <p class="news-para">{esc(coverage)}</p>
          <h4 class="news-sub">新聞報道未完全解答</h4>
          <p class="news-para">{esc(gaps)}</p>
        </div>""")
    arts = []
    for i, a in enumerate(bs.NEWS.get("articles", [])):
        arts.append(f'<div class="news-art"><span class="art-num">{i+1:02d}</span><div class="art-main"><a class="art-title" href="{esc(a.get("url","#"))}" target="_blank" rel="noopener">{esc(a.get("title",""))}</a><div class="art-meta">{esc(a.get("source",""))} · {esc(a.get("date",""))}</div></div><span class="art-lang">{esc(a.get("lang","EN"))}</span></div>')
    devs = []
    for ev in bs.NEWS.get("latest_developments", []):
        src = ev.get("source", "")
        url = ev.get("url", "")
        src_html = (f'<span class="dev-src">· <a href="{esc(url)}" target="_blank" rel="noopener">{esc(src)} ↗</a></span>'
                    if url else f'<span class="dev-src">· {esc(src)}</span>')
        devs.append(f'<div class="dev-item"><div class="dev-date">{esc(ev.get("date",""))}</div><div><p>{esc(ev.get("event",""))} {src_html}</p></div></div>')
    body = f"""
    <section class="page-head">
      <h1>{esc(nl)}</h1>
      <p>{esc(i18n.NEWS_COVERAGE_LEAD)}</p>
    </section>
    <section class="block narrow">
      <div class="block-head"><h2>最新發展</h2><a class="link" href="letter.html">我們的信函 →</a></div>
      <p class="block-sub">2026 年 7 月 17 日聆訊結束後的進展——包括我們已刊出的信函及調查的下一步。</p>
      <div class="timeline">{''.join(devs)}</div>
    </section>
    <section class="block">
      <h2>新聞主題與職權範圍的對應</h2>
      {''.join(cards)}
    </section>
    <section class="block">
      <h2>新聞文章索引</h2>
      <div id="art-list">{''.join(arts)}</div>
    </section>
    """
    return page_tc(nl, "news.html", body, nl)


def build_search_tc():
    suggestions = [
        ("消防花灑系統故障", "sprinkler failure"),
        ("圍標串通", "tender collusion"),
        ("吸煙／煙蒂起火", "smoking cigarette fire"),
        ("橡皮圖章式批核", "rubber-stamping approvals"),
        ("未經檢查付款", "uninspected payments"),
        ("消防警鐘被關掉", "fire alarm switched off"),
        ("評分操控", "tender scoring manipulation"),
    ]
    chips = "".join(
        f'<button class="chip" data-q="{esc(q)}">{esc(label)}</button>'
        for label, q in suggestions
    )
    body = f"""
    <section class="page-head">
      <h1>全文搜尋</h1>
      <p>搜尋全部 243 份調查文件的全文（中英文）。你也可以輸入問題（例如「消防花灑系統當時是否正常運作？」），
      搜尋引擎會找出最有可能解答問題的文件。結果會顯示含高亮的摘錄，並連結至每份文件的完整頁面。</p>
    </section>
    <section class="block narrow">
      <div class="block-sub">試試下列建議問題——引擎會自動擴展至相關詞彙：</div>
      <div class="search-chips" id="search-chips">{chips}</div>
    </section>
    <section class="toolbar">
      <input id="search-q" type="search" placeholder="輸入關鍵詞…" autofocus>
    </section>
    <p class="muted" id="search-status"></p>
    <div id="search-results"></div>
    <script>
    window.SEARCH_LABELS = {{
      searching: '正在載入索引…', results: '項結果',
      noresults: '沒有相符文件。請嘗試減少或放寬關鍵詞。', seconds: '秒',
      expanded: '已擴展至相關詞彙：', includesExpanded: '（已包含語義相關詞彙）',
      keywordGroup: '關鍵詞直接命中', semanticGroup: '語義相關',
      semanticNote: '這些文件並不包含您輸入的關鍵詞，而是透過上述相關詞彙找到（檔案中的證據往往用不同措辭表達）。',
      allResults: '全部結果', keywordOnly: '關鍵詞命中', semanticOnly: '語義相關',
      share: '複製搜尋連結', copied: '已複製 ✓', sharePrompt: '複製此搜尋連結：'
    }};
    </script>
    <script src="/assets/search.js"></script>
    """
    return page_tc("全文搜尋", "search.html", body, "全文搜尋")


def build_about_tc():
    img_ex = bs.image_examples_html()
    body = f"""
    <section class="page-head"><h1>{esc(i18n.ABOUT["title"])}</h1></section>
    <section class="block narrow">
      <div class="note-block"><h3>{esc(i18n.ABOUT["ack_title"])}</h3><p>{esc(i18n.ABOUT["ack"])}</p></div>
      <div class="note-block"><h3>{esc(i18n.ABOUT["compiler_title"])}</h3><p>{esc(i18n.ABOUT["compiler"])}</p></div>
      <div class="note-block warn"><h3>{esc(i18n.ABOUT["disclaimer_title"])}</h3><p>{esc(i18n.ABOUT["disclaimer"])}</p></div>
      <div class="note-block" id="images">
        <h3>圖片數量及篩選（抽取 8,785 張 → 展示約 1,800 張）</h3>
        <p>243 份 PDF 內嵌的 <strong>8,785 張圖片</strong>均已程式化抽取，但大部分並非有意義的獨立圖像：自動檢查將它們分類為<em>照片</em>（1,772）、<em>圖表／圖則</em>（1,036）、<em>整頁掃描</em>（834）、<em>空白</em>（304）及<em>微小版面殘片</em>（4,837，即 PDF 抽取產生的點、元件及排版碎屑）。視覺模型再對照片與圖表逐一檢視、按重要性評級（★1–5）；其中約 1,800 張達到納入標準（★3 或以上，或屬明顯具實質內容的非照片材料）者，均展示於各文件頁（「N shown of M」），讀者看到的是證據而非抽取噪音；完整抽取集仍見於原始 PDF。</p>
        {img_ex}
      </div>
      <div class="note-block" id="tor-counts">
        <h3>職權範圍數字的計算方法</h3>
        <p>各職權範圍下的數字，反映 243 份文件中有多少份含與該任務相關的實質內容，由大型語言模型<strong>通讀全文</strong>（約 2,000 字一段，屬語義判斷而非關鍵詞比對）後評定。一份文件可計入多個職權範圍。另有 76 份掃描或極短文件無法完整機器閱讀，採用早前摘要級分析的標籤並加以標示。與摘要級分類相比，通讀全文大幅提高了 ToR5（圍標、串通）及 ToR6（法例）的數字——不少文件從未使用這些關鍵詞，卻含有直接相關的證據，例如相同標價、未經檢查即付款、沒有到場便批核。</p>
      </div>
      <div class="note-block warn" id="ocr">
        <h3>掃描頁面：以圖片形式發表的 347 頁證據</h3>
        <p>委員會發表的 243 份文件（共 6,377 頁）中，有 <strong>46 份文件——共 347 頁</strong>——只以掃描圖片形式承載文字，沒有機器可讀的文字圖層：27 份文件（283 頁）整份為掃描件，另有 19 份文件夾雜了 64 頁掃描頁。這些頁面無法直接搜尋、引用或由電腦閱讀；任何人若要以電腦處理文字——記者、研究人員、公眾，或本網站編者——都必須先逐頁進行光學字符識別（OCR），再檢查及更正結果，因為掃描頁的 OCR 從不完美。本網站已為所有受影響頁面完成此工序，令材料可供搜尋及閱讀。以圖片而非文字形式發表官方證據，為任何想以電腦處理文件的人強加隱藏而多餘的工作；此做法應予以<strong>強烈譴責</strong>。</p>
      </div>
      <div class="note-block" id="open-source">
        <h3>開源與傳媒</h3>
        <p>本網站由<a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">GitHub 開源儲存庫 ↗</a>
        建構（項目位於 <code>projects/FireReport</code>）：爬蟲、PDF 處理、OCR、LLM 分析及網站生成程式全部公開，
        記者、研究人員及開發者均可重現或改進此方法。我們就調查文件可及性致《南華早報》的信函已於
        <a href="https://www.scmp.com/comment/letters" target="_blank" rel="noopener">2026 年 8 月 19 日刊出 ↗</a>——
        詳見<a href="letter.html">我們的信函</a>。</p>
      </div>
    </section>
    """
    return page_tc(i18n.ABOUT["title"], "about.html", body, i18n.ABOUT["title"])


def build_letter_tc():
    """Our letter to the SCMP editor (published 2026-08-19) — TC version."""
    pub = bs.PRESS.get("published", {})
    let = bs.PRESS.get("letter_tc", {})
    paras = "".join(f"<p>{esc(p)}</p>" for p in let.get("paragraphs", []))
    body = f"""
    <section class="page-head">
      <div class="hero-badge">已於《南華早報》Letters 版刊出 · {esc(pub.get("date", ""))}</div>
      <h1>我們的信函</h1>
      <p>就宏福苑火災調查文件的可及性致《南華早報》編輯的信函——已刊出版本。</p>
    </section>
    <section class="block narrow">
      <div class="note-block">
        <h3>刊出資料</h3>
        <p>已於 <strong>{esc(pub.get("date", ""))}</strong> 在 <a href="{esc(pub.get("url", "#"))}" target="_blank" rel="noopener">南華早報
        Letters 版刊出 ↗</a>，見當日版《{esc(pub.get("edition", ""))}》。{esc(pub.get("note", ""))}</p>
        <p>信函源自本網站的整理工作：<a href="documents.html">243 份文件</a>、<a href="search.html">全文搜尋</a>及
        <a href="tor.html">職權範圍框架</a>均見於下文。</p>
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
      <h2>信函所述網站的相關頁面</h2>
      <ul class="news-list">
        <li><strong><a href="documents.html">地圖與文件</a></strong>——每份文件均按七項職權範圍標籤。</li>
        <li><strong><a href="search.html">全文搜尋</a></strong>——涵蓋全部 243 份文件，附頁碼摘錄。</li>
        <li><strong><a href="tor.html">職權範圍視角</a></strong>——引用文件的主題敘述。</li>
        <li><strong><a href="news.html">新聞與報導</a></strong>——傳媒報道如何對應調查紀錄。</li>
        <li><strong><a href="about.html">關於與鳴謝</a></strong>——方法、圖片篩選及 OCR 負擔。</li>
        <li><strong><a href="https://github.com/tesolchina/wangfukcourtfirereport" target="_blank" rel="noopener">程式碼 ↗</a></strong>——開源，位於 <code>projects/FireReport</code>。</li>
      </ul>
    </section>
    """
    return page_tc("我們的信函", "letter.html", body, "我們的信函——宏福苑火災調查文件的可及性")


def build_doc_page_tc(d):
    slug = slug_of(d)
    a = bs.ana(d)
    num = DOC_NUM.get(d["title"], 0)
    md_path = os.path.join(DATA, "markdown", f"{slug}.md")
    full_html = ""
    if os.path.exists(md_path):
        full_html = md_to_html(open(md_path, encoding="utf-8", errors="ignore").read())
    # scanned PDFs (no OCR text): page-marker HTML only — render page images instead
    if bs.is_scanned_doc(d):
        full_html = ""
    zh = tc_summary_for(d)
    en_sum = doc_full_summary(d)
    kp = "".join(f"<li>{esc(p)}</li>" for p in (a.get("key_points") or [])[:6])
    themes = "".join(f'<span class="theme-chip">{esc(t)}</span>' for t in (a.get("themes") or []))
    parties = "".join(f"<li><span>{esc(p)}</span></li>" for p in (a.get("parties") or [])[:8])
    toc = d.get("toc") or []
    toc_html = "".join(f'<li><a href="#page-{esc(x)}">{esc(x)}</a></li>' if re.match(r"^Page \d+$", x) else f"<li>{esc(x)}</li>" for x in toc[:20])
    scanned_note = '<p class="muted">此為掃描文件，未能抽取可搜尋文字；頁面圖像及下方原始 PDF 載有內容。</p>' if not full_html else ""
    gal = ""
    imgs = sorted([os.path.basename(x) for x in (glob_join(slug))])
    if imgs:
        kept = []
        for fname in imgs:
            pm = re.search(r"p(\d+)", fname)
            pg = pm.group(1) if pm else "?"
            keep, cap, imp = img_keep_and_caption(fname, pg)
            if keep:
                kept.append((fname, cap, imp))
        kept.sort(key=lambda x: -x[2])
        if kept:
            thumbs = []
            for i, (f, c, _) in enumerate(kept[:24]):
                lazy = '' if i < 24 else 'loading="lazy"'
                thumbs.append(
                    f'<figure class="img-item"><a href="../images/{esc(f)}" target="_blank" rel="noopener">'
                    f'<img {lazy} src="../images/{esc(f)}" alt="Page {esc(pg)}"></a><figcaption>{c}</figcaption></figure>'
                )
            hidden = "".join(
                f'<figure class="img-item"><a href="../images/{esc(f)}" target="_blank" rel="noopener">'
                f'<img loading="lazy" src="../images/{esc(f)}" alt="Page {esc(pg)}"></a><figcaption>{c}</figcaption></figure>'
                for f, c, _ in kept[24:])
            more_div = f'<div class="img-more" hidden>{hidden}</div>' if hidden else ""
            more_btn = (
                f'<button class="btn btn-ghost" id="img-more-btn" '
                f'onclick="document.getElementById(\'img-more-btn\').hidden=true;'
                f'document.querySelector(\'.img-more\').hidden=false">顯示全部 {len(kept)} 張圖片</button>'
            ) if hidden else ""
            gal = (f'<details class="img-gallery" open><summary>圖片（{len(kept)} 張）</summary>'
                   f'<div class="img-grid">{"".join(thumbs)}{more_div}</div>{more_btn}</details>')
    lang_label = LANG_LABEL.get(doc_language(d), "English")
    type_label = doc_type_label(d)
    wl = WORK_BY_TITLE.get(d["title"], {})
    work_row = f'<li><span>估算工時</span><b>{wl.get("hours",0):,.0f} h</b></li>' if wl.get("hours") else ""
    cross = doc_cross_summary(d)
    cross_html = ""
    if cross:
        cl, ct = cross
        cross_html = f'<div class="card"><h2>{esc(i18n.DOC_PAGE["cross_summary"])}（{esc(cl)}）</h2><div class="summary">{esc(ct)}</div></div>'
    # scanned docs: render page images as the readable full document
    if full_html:
        full_body = full_html
    else:
        pg_imgs = bs.scanned_page_images(d)
        if pg_imgs:
            def _pgno(f):
                m = re.search(r"_p(\d+)_", f)
                return int(m.group(1)) if m else 0
            pages_html = "".join(
                f'<figure class="scan-page" id="page-{_pgno(f)}"><a href="../images/{esc(f)}" target="_blank" rel="noopener">'
                f'<img loading="lazy" src="../images/{esc(f)}" alt="第 {_pgno(f)} 頁"></a>'
                f'<figcaption>第 {_pgno(f)} 頁</figcaption></figure>'
                for f in pg_imgs
            )
            full_body = (f'<div class="scan-pages">{pages_html}</div>'
                         '<p class="muted">此為掃描文件，未能抽取可搜尋文字；上方頁面圖像及原始 PDF 載有內容，'
                         '因此不包含在全文搜尋內。</p>')
        else:
            full_body = '<p class="muted">掃描文件——請參閱原始 PDF。</p>'
    body = f"""
    <section class="page-head">
      <p class="crumbs"><a href="documents.html">地圖與文件</a> → <span class="doc-num">#{num}</span></p>
      <h1>{esc(d['title'])}</h1>
      <p class="doc-sub">文件 {num} / {len(INDEX)} · {d.get('pages') or '?'} 頁 · {d.get('images') or 0} 張圖片 · <a href="../{doc_link_tc(slug)}">English version</a></p>
      <div class="doc-tags"><span class="type-badge">{esc(type_label)}</span><span class="lang-badge">{esc(lang_label)}</span></div>
    </section>
    <section class="doc-layout">
      <div class="doc-main">
        <div class="card"><h2>{esc(i18n.DOC_PAGE["cross_summary"])}</h2><div class="summary">{esc(zh) if zh else esc(en_sum)}</div>{scanned_note}</div>
        {cross_html}
        <div class="card"><h2>{esc(i18n.DOC_PAGE["summary"])}（English）</h2><div class="summary">{esc(en_sum)}</div></div>
        <div class="card"><h2>{esc(i18n.DOC_PAGE["key_points"])}</h2><ul class="doc-points">{kp}</ul></div>
        {gal}
        <details class="full-doc"{' open' if not full_html else ''}><summary>{esc(i18n.DOC_PAGE["full_doc"])}（{d.get('pages') or '?'} 頁）</summary>{full_body}</details>
      </div>
      <aside class="doc-side">
        <div class="card">
          <h2>{esc(i18n.DOC_PAGE["facts"])}</h2>
          <ul class="facts">
            <li><span>編號</span><b>#{num} / {len(INDEX)}</b></li>
            <li><span>類型</span><b>{esc(type_label)}</b></li>
            <li><span>語言</span><b>{esc(lang_label)}</b></li>
            <li><span>頁數</span><b>{d.get('pages') or '?'}</b></li>
            <li><span>圖片</span><b>{d.get('images') or 0}</b></li>
            {work_row}
          </ul>
          <a class="btn btn-dark btn-block" href="{esc(d.get('url','#'))}" target="_blank" rel="noopener">開啟原始 PDF ↗</a>
        </div>
        <div class="card"><h2>{esc(i18n.DOC_PAGE["toc"])}</h2><ul class="toc-list">{toc_html}</ul></div>
        <div class="card"><h2>{esc(i18n.DOC_PAGE["themes"])}</h2><div class="themes">{themes}</div></div>
        <div class="card"><h2>{esc(i18n.DOC_PAGE["parties"])}</h2><ul class="facts">{parties}</ul></div>
      </aside>
    </section>
    {bs.DOC_ANCHOR_JS}
    """
    return page_tc(d["title"], "documents.html", body, d["title"])


def glob_join(slug):
    import glob
    return glob.glob(os.path.join(DATA, "images", f"{slug}_*.jpeg")) + \
           glob.glob(os.path.join(DATA, "images", f"{slug}_*.png"))


def main():
    import shutil
    os.makedirs(os.path.join(ZH, "tor"), exist_ok=True)
    os.makedirs(os.path.join(ZH, "doc"), exist_ok=True)
    pages = {
        "index.html": build_home_tc(),
        "documents.html": build_documents_tc(),
        "search.html": build_search_tc(),
        "tor.html": build_tor_index_tc(),
        "work.html": build_work_tc(),
        "news.html": build_news_tc(),
        "about.html": build_about_tc(),
        "letter.html": build_letter_tc(),
    }
    for name, content in pages.items():
        open(os.path.join(ZH, name), "w").write(fix_tc_links(content))
    for key, tag, blurb in TOR_TAGS:
        fname = re.sub(r"[^A-Za-z0-9]+\s*", "", key) + ".html"
        open(os.path.join(ZH, "tor", fname), "w").write(fix_tc_links(build_tor_page_tc(key, tag)))
    open(os.path.join(ZH, "tor", "GeneralOther.html"), "w").write(fix_tc_links(build_tor_page_tc("General", "General / Other")))
    n = 0
    for d in INDEX:
        open(os.path.join(ZH, "doc", f"{slug_of(d)}.html"), "w").write(fix_tc_links(build_doc_page_tc(d)))
        n += 1
    print(f"TC site built into {ZH}: {len(pages)} pages + 8 ToR pages + {n} doc pages")


if __name__ == "__main__":
    main()
