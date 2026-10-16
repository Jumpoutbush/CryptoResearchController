# R07 original-paper provenance

`knowledge build <project> [--dry-run]` and `knowledge explain <project> --claim <id>`
now include original-paper versions and structured theorem spans. This remains a
derived index. The canonical claim graph and original six-axis technical reviews
remain authoritative; no source query writes them or changes route decisions.

The controller reads the existing `literature/uploads.json` schema-1 `files` list,
the existing `pdf_index.json.files` dictionary keyed by PDF basename, and technical
reviews under `literature/technical_reviews/`. Explicitly cited legacy review paths
elsewhere under `literature/` are supported. Missing authors, venue, URL or source
version remain null; upload filenames and equal titles never establish identity.

An optional operator-authored `literature/source_spans.json` has `schema_version:1`
and `spans:[]`. Each entry requires:

- unique `id`, `source_file`, PDF `sha256`, explicit `version`;
- `review_file`, `review_sha256`, exact `claim_revision`, `claim_spec_sha256`;
- `extraction` with `source_file`, `sha256`, `parser:PyMuPDF`, actual parser `version`;
- `location` null, or `page_start`, `page_end` (one-based PDF pages), `theorem` and
  exact `excerpt`; `section` is retained as unverified metadata;
- optional `authors`, `venue`, `url`, and `supersedes` containing the old
  `source_file`, `sha256`, `version`. Supersession preserves the old node.

See `scripts/r07_fixture.py` for three valid synthetic PDF versions and a complete
example. It is an offline acceptance helper and must only run on disposable projects.
Import real papers through the existing explicit `paper ingest` interface and use
the existing local extraction workflow. Graph construction never fetches or extracts
files to disk. PyMuPDF is optional at runtime: missing/broken parser produces
`EXTRACTION_UNAVAILABLE`, without installing anything or inventing locations.

Each verified location checks PDF and extraction hashes, original PDF pages,
strictly ordered unique extraction page markers, exact excerpt/theorem marker,
extractor version, and existing index binding. A free-form old review location or
citation ID is insufficient: it remains `LOCATION_UNVERIFIED`. A changed PDF/extract
retains the old pin and reports a mismatch plus recovery action. Malformed paths,
invented locations, conflicting source metadata, mismatched review/claim pins and
invalid nested records reject construction and preserve the previous cache.
Extraction versions are pinned on the span that points to the original paper
version: multiple extraction generations do not overwrite a PDF version's identity.

The original coverage label is retained separately from the usable projection
label. `COVERS`/`CONTRADICTS` mapping requires the existing decisive validator,
checked fulltext, located original page and explicit existing layout attestation.
Otherwise effective status stays `UNVERIFIED`; uncertain mathematical layout is
`MATH_RENDER_UNCERTAIN`, requiring original-page inspection. Layout attestation and
source location are never independent theorem certification. No new REFUTES edge
or scientific proof status is inferred from a literature judgment.

OpenSource reference: [PaperQA2](https://github.com/Future-House/paper-qa/tree/57e89f7223b0960d5ee5ea048c69e3c47e088572), Apache-2.0, fixed upstream
`57e89f7223b0960d5ee5ea048c69e3c47e088572`. `src/paperqa/agents/main.py` 207–244,
`readers.py` 92–141 and `types.py` 75–87/155–174 informed separation of retrieval,
source chunks and contextual summaries. LICENSE SHA-256:
`a10f591e3522fbfe867cfde0b35e0594f6f43a51b013540208a1469c9e0b0f62`.
No upstream code, MD5 identity, network ingestion, embeddings or model execution
was copied. The public-evidence addendum is used only for versioned artifact/source
separation: [OpenAI Math](https://github.com/openai/math/tree/1581d4cbdd69a0faf34b2089614fe2a814316a6a) (Apache-2.0),
not its unreviewed mathematical status; [Science One official article](https://research.google/blog/science-one-framework-a-verifiable-autonomous-research-framework-via-chain-of-evidence/) is a design
reference only, with no imported code or claimed code license.

Acceptance: `python -B -m unittest discover -s tests -p test_source_provenance.py -v`
and `python -B scripts/verify_r07_offline.py --output <external-evidence-directory>`.
The latter uses native `research.cmd` problem/claim/paper ingestion and graph commands
on two temporary projects, preserves source/canonical bytes, and saves a normal
original-page subgraph and a replaced-PDF fault subgraph. No provider calls.

Rollback: revert the scoped implementation and remove only rebuildable graph caches
if desired. Do not revert original papers, reviews, claims, budgets or research history.
