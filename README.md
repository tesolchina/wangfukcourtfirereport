# Wang Fuk Court Fire Report — inquiry documents reorganized for journalists

Open-source project that crawls, converts, describes and reorganizes the public
materials of the **Independent Committee in relation to the Fire at Wang Fuk Court
in Tai Po** (Hong Kong, November 2025), so journalists and the public can find the
evidence by question — not by filing order.

- **Live bilingual site**: https://wangfukcourtfirereport.simonsays.hk/ (EN + 繁體中文)
- **Source materials**: https://www.ic-wangfukcourtfire.gov.hk/eng/
- **Our letter to the editor** (published in SCMP Letters, 2026-08-19): https://wangfukcourtfirereport.simonsays.hk/letter.html

## What this is

The Committee published 243 documents — 6,377 pages, ~1.9 million words — on a
site arranged by the sequence of its work, not by the questions it was asked to
answer. This project:

1. crawls the entire committee site and downloads every PDF (243, audited 0 missed);
2. converts PDFs to Markdown and extracts every embedded image (8,785) with page numbers;
3. OCRs the 347 pages (46 documents) published only as scanned images;
4. has LLMs read every document in full, tagging each against the Committee's
   seven **Terms of Reference** (semantic judgment, not keyword matching);
5. builds a bilingual static site with per-document pages (summary, ToC, key points,
   page-level citations, original PDF links), an interactive document map, a
   full-text search engine across all 1.9 million words, per-ToR narrative
   perspectives, a news-coverage analysis, and a work-effort ledger.

The point of the analysis: material people most want — evidence of collusion and
bid-rigging — is buried in documents that never use those words, and a keyword
search of the committee's own site cannot surface them (99 documents relate to
ToR5 vs 11 under a summary-level first pass).

## Repository layout

```
├── codes/                  # all scripts (Python + shell)
│   ├── fire_crawler.py     # discover pages & PDFs, download everything
│   ├── crawler_auditor.py  # static + live audit: verify nothing was missed
│   ├── audit_updates.py    # re-crawl check: new pages + revised/removed PDFs vs manifest
│   ├── audit_coverage2.py  # coverage check: Chinese-site PDFs, non-PDF assets, new dated content
│   ├── pdf_processor.py    # PDF -> Markdown + extract images (PyMuPDF)
│   ├── ocr_gaps.py / ocr_scanned.py / ocr_gaps_tess.py  # OCR of scanned pages
│   ├── image_triage.py / image_vision.py  # classify + describe images (vision LLM)
│   ├── relationship_mapper.py / tor_full_scan.py / tor_aggregate.py  # ToR tagging
│   ├── tor_deep_analysis.py / doc_meta.py / doc_summaries.py  # LLM analysis
│   ├── search_build.py     # full-text search index
│   ├── build_site.py       # EN site generator -> site_out/
│   ├── tc_site.py          # Traditional Chinese mirror -> site_out/zh/
│   ├── deploy_site.py      # upload site_out/ to Aliyun OSS (creds from local file)
│   └── qa_site.py / qa_live.py / qa_journalist.py  # Playwright QA
├── data/
│   ├── index.json          # 243 docs: summary, ToC, ToR tags
│   ├── analysis.json       # deep LLM analysis output (key points, themes, parties)
│   ├── tor_full_tags.json  # full-text paragraph-level ToR tags
│   ├── news_analysis.json  # news coverage analysis + latest developments
│   ├── press.json          # the published letter (EN/TC) -> /letter.html
│   ├── search_index.json   # prebuilt search index (regenerate via search_build.py)
│   └── …                   # other curated JSON (doc_meta, summaries, work ledger…)
├── docs/
│   ├── plan16Aug26.md      # original plan + real-time progress log
│   ├── revampSite.log      # detailed change log
│   └── letterSCMP.md       # the letter to SCMP, v1–v16 (v16 = published)
└── README.md
```

**Not included in this repo (by design):** the raw PDFs, converted Markdown and
extracted images (`data/pdfs`, `data/markdown`, `data/images`) — download them from
the Committee's site with `codes/fire_crawler.py` + `codes/pdf_processor.py`
(≈1.8 GB total), or read them directly on the live site.

## Coverage & update audits

Run these after the Committee updates its site (e.g. when the final report is
published) to find what changed and what our corpus is missing. Both are
read-only: they fetch the live site and compare against `data/manifest.json`,
and download nothing.

```bash
python3 codes/crawler_auditor.py   # live PDF URLs vs manifest (missing / extra)
python3 codes/audit_updates.py     # new pages (BFS) + revised/removed PDFs (size diff)
python3 codes/audit_coverage2.py   # Chinese-site PDFs, non-PDF assets, post-crawl dated content
```

What each check covers:

| Script | Checks |
|---|---|
| `crawler_auditor.py` | PDF URLs linked from the five key EN pages vs the manifest |
| `audit_updates.py` | discovers all internal pages from the 8 start pages (flags new sections); GETs every manifest PDF and flags size changes (revisions) or removals |
| `audit_coverage2.py` | PDFs linked only from the Chinese `/chi/` pages (the EN pages never link them); non-PDF file assets; dated content newer than the crawl |

Reference result (audit of 2026-10-08 vs the 2026-08-16 crawl): EN site
unchanged — 0 new pages, 0 new/changed/removed PDFs; one gap found: **80
Chinese-language PDFs** (26 hearing transcripts, 24 witness timetables, 8
notices, 6 lists of involved parties, plus appointments/addresses/Rules of
Procedure) are linked only from `/chi/` and are not yet in our corpus. They are
text-based PDFs (no OCR needed). See issue #4 for the full breakdown.

## Rebuild the site locally

```bash
cd wangfukcourtfirereport
python3 codes/build_site.py     # EN site -> site_out/
python3 codes/search_build.py   # search index -> data/search_index.json
python3 codes/tc_site.py        # TC mirror -> site_out/zh/
# optional: serve site_out/ with any static server
```

## API keys

The scripts call LLM APIs (HKBU GenAI gateway / OpenRouter / Brave Search). **Keys
have been redacted from this public repo** — replace the `REPLACE_WITH_*` placeholders
in `codes/` with your own keys (or set them via environment variables / a local
credentials file). The Aliyun OSS deploy scripts read credentials from a local file
(`~/Documents/FITE/GoogleAccess.md` on the author's machine) — never commit credentials.

## Media & press

- **Letter to the editor** (v16) was published in the **SCMP letters column on
  2026-08-19** and is reproduced on the site at `/letter.html` (EN + TC) — see
  `docs/letterSCMP.md` and `data/press.json`.
- A media-contact list (print + TV + radio, HK + international) is maintained in a
  private shared Google Doc, not in this repo.

## Credits & disclaimer

All documents originate from the **Independent Committee in relation to the Fire at
Wang Fuk Court in Tai Po** and are the work of the Committee, its counsel, experts,
witnesses and the Government. This site reorganises, indexes and summarises those
public materials; it claims no authorship of them, makes no findings of its own, and
the original documents remain authoritative.

Compiled and maintained by **Dr Simon Wang** (simonwanghkteacher@gmail.com) as a
**private individual** — not as a scholar of Hong Kong Baptist University, which is
not involved in and bears no responsibility for this project. The site is provided
**for educational purposes only** and is **not for commercial use**.

## License

MIT — see [LICENSE](LICENSE).
