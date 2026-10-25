# Wiki schema (LLM-maintained)

Pattern: Karpathy's "LLM Wiki" (gist 442a6bf5) — raw sources are immutable; this wiki is the
compiled layer between the sources and our writing (letters, articles, submissions).

## Layers
- **Raw sources** — `data/pdfs/`, `/tmp/closings_pdf/`, `data/markdown/`, `data/manifest.json`.
  Never edited.
- **Wiki** (this directory) — LLM-written markdown: entity pages, topic pages, source notes,
  `synthesis.md`. Cross-referenced with relative links.
- **Schema** — this file. Conventions for ingest / query / lint.

## Conventions
- One page per entity (body, office, contractor, witness group) or topic (a question the
  inquiry was asked). File names kebab-case.
- Every factual claim carries a citation in the form `[T<day>/page]`, `[WS<n>/page]`,
  `[Ch<n> §<para>]` or `[doc: <filename>]`.
- Distinguish **evidence** (what a witness said) from **argument** (what counsel submitted).
- When a new source contradicts an existing page, do not overwrite silently: add a
  "Contradiction" note with both citations and flag it in `log.md`.
- `index.md` is updated on every ingest. `log.md` is append-only, entries start `## [YYYY-MM-DD] ingest | <group>`.

## Operations
- **Ingest** — read a document group, write/update source note + entity/topic pages + synthesis.
- **Query** — answer from wiki pages with citations; file good answers back as pages.
- **Lint** — check contradictions, stale claims, orphan pages, missing cross-references.
