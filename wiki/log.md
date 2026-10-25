# Log

Append-only. `grep "^## \[" log.md | tail -5` gives the last entries.

## [2026-10-25] init | wiki created
Schema, index and synthesis stubs created. Pattern: Karpathy LLM Wiki (gist 442a6bf5).

## [2026-10-25] ingest | Group 1 — closing submissions (10 docs, 1,217 pp)
Read the Committee's 627-page closing submissions (structure, Ch7, Ch8, Ch10, citation trail)
and logged the other nine. Key finding: Ch7 mentions "Bureau" zero times and assigns
responsibility to ICU/BD, FSD and LD (para 1187); Ch8/Ch10 recommend policy reform.
See [sources/group-1-closing-submissions.md](sources/group-1-closing-submissions.md).

## [2026-10-25] ingest | Group 2 — hearing transcripts (30 sessions + direction conference, 952 pp)
Per-session policy vocabulary measured. Peak policy discussion on department days (T20 BD/ICU 130,
T10 FSD 108, T17 FSD 107, T24 HAD 98, T16 Labour 95, T22 ICU 71); residents' days nearly none
(T4 = 1). No bureau session exists. See [sources/group-2-hearing-transcripts.md](sources/group-2-hearing-transcripts.md);
synthesis updated (two new rows, one correction).

## [2026-10-25] ingest | Groups 3–7 — witness statements, experts, openings, agency reports, procedural (all 243 docs screened)
Systematic pass over the 243 document summaries for formulation vs implementation vocabulary.
66/118 witness statements and 28/30 transcripts are policy-heavy; heaviest are argument documents
(Committee closing f=13, Government closing f=14, Usmani/Jiang recommendations f=15).
Conclusion: policy is discussed everywhere — but always with implementers, contractors, counsel or
experts; no policy-branch witness appears. See [sources/group-3-7-remaining-documents.md](sources/group-3-7-remaining-documents.md).

## [2026-10-25] ingest | Group 2 addendum — Chinese-language transcripts (31 files)
Chinese originals scanned with Chinese formulation terms. Pattern matches the English translations:
department days 97–204 policy terms (30 Apr URA 204; 10 Apr FSD 180; 27 Apr BD/ICU 173; 21 Apr Labour 172),
residents' days 2–8. Coverage note added: the record was read at summary level for all 243 docs, full text
for the 31+31 transcripts and the 10 closing submissions.

## [2026-10-25] ingest | Full-text scan of all 323 manifest entries
Downloaded the 212 PDFs that were missing locally; extracted text for 322 documents (300 with text).
Highest formulation scores are the argument documents: Government closing 523, Committee closing 522,
Competition Commission recommendations 397 / report 283, URA opening 311 — evidence documents far lower.
See the addendum in [sources/group-3-7-remaining-documents.md](sources/group-3-7-remaining-documents.md).

## [2026-10-25] ingest | Full-text conversion of the entire record (323 documents)
All 323 manifest PDFs now downloaded and converted to markdown with page markers
(`data/markdown_all/`, gitignored): 323 files, ~20 MB text. Includes the **IFITF Final
Investigation Report (Redacted, with appendices) — 1,142 pages, 1.16 M characters** recovered
after fixing a control-character URL. Its profile: cause 92 · standard 57 · bureau 10 · policy 5 —
a technical document about causation and standards, not about policy choices.

## [2026-10-25] ingest | Groups 8–9 — Government closing (408 pp) and IFITF report (1,142 pp)
Government closing: Parts I–V, ToR1 (A–F incl. "systemic issues") and ToR2; describes 27 factual witnesses
as officers "from different Bureaux and Departments" — but the timetable shows no bureau secretary/perm sec.
IFITF report: 11 chapters + appendices, scientific causation (incl. full-scale tests in Sichuan), **no
recommendations**, policy vocabulary 5 hits in 1.16 M characters. Counter-evidence section added to synthesis.
