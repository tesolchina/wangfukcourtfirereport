/* Mini full-text search engine for the Wang Fuk Court inquiry archive.
 * Loads the prebuilt inverted index (search/index.json), tokenises the query
 * (same rules as codes/search_build.py: latin words + CJK chars), scores
 * documents with BM25-ish ranking, renders results with highlights.
 * Shared by the EN and 中文 search pages. */
(function () {
  var INDEX_URL = '/search/index.json';
  var L = window.SEARCH_LABELS || { searching: 'Loading index…', results: 'results', noresults: 'No documents match. Try fewer or broader keywords.', seconds: 's', expanded: 'Expanded to related terms:', includesExpanded: 'includes semantically related terms', expandedTC: '已擴展至相關詞彙：', includesExpandedTC: '已包含語義相關詞彙', keywordGroup: 'Keyword matches', semanticGroup: 'Semantically related', semanticNote: "These documents do not contain your exact keywords — they were found through the related terms shown above (the archive evidence is often phrased differently).", keywordGroupTC: '關鍵詞直接命中', semanticGroupTC: '語義相關', semanticNoteTC: '這些文件並不包含您輸入的關鍵詞，而是透過上述相關詞彙找到（檔案中的證據往往用不同措辭表達）。', allResults: 'All results', keywordOnly: 'Keyword matches', semanticOnly: 'Semantic matches', share: 'Copy search link', copied: 'Link copied ✓', sharePrompt: 'Copy this search link:', shareTC: '複製搜尋連結', copiedTC: '已複製 ✓', sharePromptTC: '複製此搜尋連結：' };
  window.SEARCH_LABELS = window.SEARCH_LABELS || L;

  var idx = null, input = null, box = null, statusEl = null;

  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }

  var STOP = new Set(("a an and are as at be by for from has have in is it its of on or that the this to was were with would will can could should may might not no nor so than then there these they those their he she his her we you your our mr mrs ms dr page pages appendix annex part section paragraph figure table per cent committee independent court fire wang fuk court fire services department government inquiry investigation report statement evidence witness information document documents hong kong tai po november december january february march april may june july august september october 2025 2026 said say says according including also per via within among between under over around after before during while where when why what which who whom whose however therefore moreover into onto upon again further since until unless because although though yet still only just about above below across against along among around behind beside beyond down from inside into near off onto outside over through throughout up within without plus minus total number exhibit exhibits annex annexes item items clause clauses schedule schedules").split(' '));

  /* Semantic expansion: when a query contains a head term, also search its
   * related terms (drawn from the LLM analysis of the corpus). This makes the
   * engine behave more like a topic search than pure keyword matching. */
  var EXPAND = {
    'sprinkler': ['sprinkler', 'hydrant', 'hose', 'water tank', 'pump', 'fire service installation'],
    'collusion': ['collusion', 'bid-rig', 'bidrig', 'cartel', 'tender', 'identical bids', 'connected interest', 'competition', '圍標'],
    'bid': ['bid', 'tender', 'quote', 'quotation', 'bidding', '報價'],
    'tender': ['tender', 'bid', 'quotation', 'procurement', 'award', 'contractor selection', '招標'],
    'smoking': ['smoking', 'cigarette', 'ignition', 'light well', '煙頭', '煙蒂'],
    'alarm': ['alarm', 'fire alarm', '警鐘', '警報'],
    'inspection': ['inspection', 'inspect', 'rubber-stamp', 'rubber stamp', 'verification', '巡查', '檢查'],
    'payment': ['payment', 'paid', 'invoice', 'uninspected', '付款'],
    'supervision': ['supervision', 'supervise', 'oversight', 'responsibility', '監管', '監督'],
    'scaffold': ['scaffold', 'scaffolding', 'netting', '棚架', '棚網'],
    'netting': ['netting', 'scaffold', '棚網'],
    'foam': ['foam', 'styrofoam', 'polystyrene', '發泡', '發泡膠'],
    'law': ['law', 'ordinance', 'penalty', 'legislation', 'regulation', '法例'],
    'fire': ['fire', 'blaze', 'ignition', 'burn', '火警'],
  };
  function expandTerms(q) {
    var extra = [], seen = new Set();
    var lower = q.toLowerCase();
    Object.keys(EXPAND).forEach(function (head) {
      if (lower.indexOf(head) >= 0) {
        EXPAND[head].forEach(function (t) { if (!seen.has(t)) { seen.add(t); extra.push(t); } });
      }
    });
    return extra;
  }
  function tokenize(text) {
    var toks = [], re = /[a-z0-9]+|[\u4e00-\u9fff]+/g, m;
    var lower = text.toLowerCase();
    while ((m = re.exec(lower)) !== null) {
      var w = m[0];
      if (/^[a-z0-9]+$/.test(w)) { if (w.length >= 2 && !STOP.has(w)) toks.push(w); }
      else {
        // CJK: singles + overlapping bigrams (matches the Python index)
        if (w.length === 1) toks.push(w);
        else {
          for (var i = 0; i < w.length; i++) toks.push(w[i]);
          for (var i = 0; i < w.length - 1; i++) toks.push(w.slice(i, i + 2));
        }
      }
    }
    return toks;
  }

  function loadIndex() {
    statusEl.textContent = L.searching;
    return fetch(INDEX_URL).then(function (r) { return r.json(); }).then(function (data) {
      idx = data;
      statusEl.textContent = '';
    }).catch(function (e) { statusEl.textContent = 'Error loading index: ' + e; });
  }

  function search(origTerms, extraToks) {
    if (!idx) return { keyword: [], semantic: [], matched: new Map(), kTotal: 0, sTotal: 0 };
    var N = idx.num_docs, scores = new Map(), matched = new Map(), kHit = new Set(), sHit = new Set();
    function addTerm(t, isExtra) {
      var tid = idx.terms.indexOf(t);
      if (tid === -1) return;
      var pl = idx.postings[tid], df = idx.df[tid];
      var idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
      for (var i = 0; i < pl.length; i += 2) {
        var docId = pl[i], tf = pl[i + 1];
        var s = idf * (tf / (tf + 1.2));
        scores.set(docId, (scores.get(docId) || 0) + s);
        if (!matched.has(docId)) matched.set(docId, new Set());
        matched.get(docId).add(t);
        if (isExtra) sHit.add(docId); else kHit.add(docId);
      }
    }
    origTerms.forEach(function (t) { addTerm(t, false); });
    (extraToks || []).forEach(function (t) { addTerm(t, true); });
    var ranked = Array.from(scores.entries()).sort(function (a, b) { return b[1] - a[1]; });
    // keyword group: doc matched at least one ORIGINAL query token
    var keyword = ranked.filter(function (e) { return kHit.has(e[0]); });
    // semantic group: doc matched ONLY expanded tokens (no original keyword)
    var semantic = ranked.filter(function (e) { return !kHit.has(e[0]) && sHit.has(e[0]); });
    return { keyword: keyword, semantic: semantic, matched: matched, kTotal: keyword.length, sTotal: semantic.length };
  }

  function highlight(text, matchedTerms) {
    if (!matchedTerms || !matchedTerms.size) return esc(text);
    var re = new RegExp('(' + Array.from(matchedTerms).map(function (t) { return t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|') + ')', 'gi');
    return esc(text).replace(re, '<mark>$1</mark>');
  }

  function resultRows(list, res, max, offset) {
    var html = [];
    list.slice(0, max).forEach(function (e, i) {
      var d = idx.docs[e[0]];
      var mterms = res.matched.get(e[0]);
      var snip = highlight(d.snippet || d.title, mterms);
      var tor = (d.tor || []).map(function (t) { return '<span class="tor-badge">' + esc(t) + '</span>'; }).join('');
      var n = offset + i + 1;
      html.push('<li class="doc-row search-hit" id="r-' + n + '">' +
        '<span class="doc-num">#' + d.num + '</span>' +
        '<div class="row-main">' +
        '<div class="row-top">' +
        '<a class="row-title" href="/doc/' + encodeURIComponent(d.slug) + '.html" title="' + esc(d.title) + '">' + esc(d.title) + '</a>' +
        '<div class="row-meta-inline">' +
        '<span class="type-badge">' + esc(d.type) + '</span>' +
        '<span class="lang-badge">' + esc(d.lang) + '</span>' + tor +
        '<span class="row-pages">' + d.pages + 'p</span>' +
        '<a class="row-pdf" href="' + esc(d.url) + '" target="_blank" rel="noopener">PDF</a>' +
        '<button class="row-link" data-n="' + n + '" title="' + L.share + '">🔗</button>' +
        '</div></div>' +
        '<div class="row-sub search-snip">' + snip + '</div></div>' +
        '</li>');
    });
    return html.join('');
  }

  function copyResultLink(n) {
    var u = new URL(location.href);
    u.searchParams.set('q', input.value.trim());
    u.searchParams.set('doc', n);
    var link = u.toString();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link);
    } else {
      prompt(L.sharePrompt, link);
    }
  }

  function copyLink() {
    var u = new URL(location.href);
    u.searchParams.set('q', input.value.trim());
    var link = u.toString();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(link).then(function () {
        var b = document.getElementById('search-share');
        if (b) { b.textContent = L.copied; setTimeout(function () { b.textContent = L.share; }, 2000); }
      });
    } else {
      prompt(L.sharePrompt, link);
    }
  }

  var mode = 'all';

  function modeBar(kTotal, sTotal) {
    var mk = function (m, label, count) {
      var active = mode === m ? ' active' : '';
      return '<button class="mode-btn' + active + '" data-mode="' + m + '">' + esc(label) + ' <span class="mode-count">' + count + '</span></button>';
    };
    return '<div class="search-mode">' +
      mk('all', L.allResults, kTotal + sTotal) +
      mk('keyword', L.keywordOnly, kTotal) +
      mk('semantic', L.semanticOnly, sTotal) +
      '</div>';
  }

  function render() {
    var q = input.value.trim();
    // keep the URL shareable: ?q= reflects the current query
    var u = new URL(location.href);
    if (q) u.searchParams.set('q', q); else u.searchParams.delete('q');
    history.replaceState({}, '', u.toString());
    if (!q) { box.innerHTML = ''; statusEl.textContent = ''; return; }
    var t0 = Date.now();
    var origTerms = tokenize(q);
    var extra = expandTerms(q);
    var extraToks = [];
    if (extra.length) {
      extra.forEach(function (t) { extraToks = extraToks.concat(tokenize(t)); });
    }
    if (!origTerms.length && !extraToks.length) { box.innerHTML = ''; statusEl.textContent = L.noresults; return; }
    var res = search(origTerms, extraToks);
    var note = '';
    if (extra.length) {
      note = '<p class="muted search-expand-note">' + L.expanded + ' ' + extra.slice(0, 8).map(esc).join(', ') + '</p>';
    }
    var sec = '';
    var dt = ((Date.now() - t0) / 1000).toFixed(2);
    var showKeyword = (mode === 'all' || mode === 'keyword');
    var showSemantic = (mode === 'all' || mode === 'semantic');
    if (showKeyword && res.kTotal) {
      sec += '<h3 class="search-group-head">' + L.keywordGroup + ' (' + res.kTotal + ')</h3>' +
             '<ul class="doc-list">' + resultRows(res.keyword, res, 50, 0) + '</ul>';
    }
    if (showSemantic && res.sTotal) {
      sec += '<h3 class="search-group-head search-semantic">' + L.semanticGroup + ' (' + res.sTotal + ')</h3>' +
             '<p class="muted search-group-note">' + L.semanticNote + '</p>' +
             '<ul class="doc-list">' + resultRows(res.semantic, res, 30, showKeyword ? res.kTotal : 0) + '</ul>';
    }
    if (!sec) { box.innerHTML = '<p class="muted">' + L.noresults + '</p>' + note; statusEl.textContent = '0 ' + L.results + ' (' + dt + L.seconds + ')'; return; }
    var shareBtn = '<button class="btn btn-ghost" id="search-share">' + L.share + '</button>';
    box.innerHTML = modeBar(res.kTotal, res.sTotal) + sec + note + '<div class="search-share-row">' + shareBtn + '</div>';
    document.getElementById('search-share').addEventListener('click', copyLink);
    box.querySelectorAll('.mode-btn').forEach(function (b) {
      b.addEventListener('click', function () { mode = b.getAttribute('data-mode'); render(); });
    });
    box.addEventListener('click', function (e) {
      var b = e.target.closest('.row-link');
      if (b) copyResultLink(b.getAttribute('data-n'));
    });
    var total = res.kTotal + res.sTotal;
    var statusText = '';
    if (mode === 'all') statusText = total + ' ' + L.results + ' (' + dt + L.seconds + ') — ' + res.kTotal + ' ' + L.keywordGroup.toLowerCase() + ' + ' + res.sTotal + ' ' + L.semanticGroup.toLowerCase();
    else if (mode === 'keyword') statusText = res.kTotal + ' ' + L.keywordGroup.toLowerCase() + ' (' + dt + L.seconds + ')';
    else statusText = res.sTotal + ' ' + L.semanticGroup.toLowerCase() + ' (' + dt + L.seconds + ')';
    statusEl.textContent = statusText;
    var target = new URLSearchParams(location.search).get('doc');
    if (target) {
      var el = document.getElementById('r-' + target);
      if (el) { el.scrollIntoView({ block: 'center' }); el.style.outline = '2px solid var(--acc)'; }
    }
  }

  function run() { render(); }

  function init() {
    input = document.getElementById('search-q');
    box = document.getElementById('search-results');
    statusEl = document.getElementById('search-status');
    if (!input || !box) return;
    var debounce;
    input.addEventListener('input', function () { clearTimeout(debounce); debounce = setTimeout(render, 250); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { clearTimeout(debounce); render(); } });
    // suggested-search chips: fill the box and search immediately (also updates URL)
    var chips = document.getElementById('search-chips');
    if (chips) {
      chips.addEventListener('click', function (e) {
        var b = e.target.closest('.chip');
        if (!b) return;
        e.preventDefault();
        input.value = b.getAttribute('data-q');
        render();
        input.focus();
      });
    }
    loadIndex().then(function () {
      // deep link ?q= runs the search on load
      var qp = new URLSearchParams(location.search).get('q');
      if (qp) { input.value = qp; render(); }
      else { run(); }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
