# R09 local evidence retrieval and bounded context

The new context is opt-in and independent of the original claim authority. It never
calls a model, embedding service, network fetch, scientific refresh, or budget writer.
The original R08 prompt function is preserved as a regression fixture; with retrieval
disabled, the complete generated prompt remains byte-for-byte identical.

```text
research.cmd knowledge context <project> --problem P-1 --problem-version 1 --obligation O-1 --task "Resolve the original obligation" --dry-run
research.cmd knowledge context <project> --claim C-1 --max-bytes 8192 --dry-run
```

Context commands are always read-only, including without --dry-run. They create no
cache, event, lock, research receipt, or budget record. IDs are exact and namespace
qualified in results; ambiguous problem/obligation versions produce missing-required
diagnostics. A problem version requires its explicit problem ID. Free text assists
recall only; each hit expands through its exact dependency, support, review and
counterexample edges. Equal titles never merge different theorem/source versions.

Priority is relevant registered counterexamples and necessary dependencies, current
independently reviewed claims, original located theorem evidence, candidates, then
background. A counterexample retains the original machine predicate, assumptions,
witness and scope. Ordinary failed branches do not gain refutation authority. Scores
only order reading; proof/novelty/formal status remain the original modules' values.
Unreviewed, historical or invalidated claims are not positive theorem evidence.

Each item carries stable node/source identity, source_file/SHA-256, claim revision
(null for a non-claim), verification_status, original provenance file/hash, role,
and explicit positive_basis. A theorem span distinguishes its original PDF hash and
location from its technical-review hash and preserves MATH_RENDER_UNCERTAIN.
Small local text sources may include a bounded excerpt (up to 1024 source bytes,
only for files up to 256 KiB), with excerpt hash and explicit truncation. Binary PDF
content is never transmitted to an external service. Other files remain exact local
references requiring original inspection; excerpts are never complete proofs.

Every query derives from current authority and verifies input manifests; disk cache
approvals are never trusted. This deliberately uses deterministic live lookup instead
of adding another cache or external index. Frozen route focus is fully recomputed and
checked. The active attempt's exact problem/version/hash, binding, status and original
budget/call summary are retained and checked; an explicit conflicting query cannot
hide it. Retrieval never runs the scheduler's check or changes an attempt.

The entire rendered UTF-8 data section, including delimiters and missing/omitted
metadata, is limited to 2048..32768 bytes. Frozen GOAL and problem/attempt conditions
are reserved first. Long task display and long missing lists are compressed before
discarding mandatory content. Full counts and SHA-256 of unlisted diagnostics/IDs
are retained, with listed_count; selected source items are omitted atomically rather
than cutting mathematical statements or conditions. If mandatory conditions alone
cannot fit, REQUIRED_CONTEXT_EXCEEDS_BUDGET and complete=false explicitly report it;
there is no fabricated complete goal or proof. The original main prompt still keeps
its full GOAL, STATE and safety/output instructions.

All source text remains escaped JSON inside BEGIN_UNTRUSTED_EVIDENCE_CONTEXT and
END_UNTRUSTED_EVIDENCE_CONTEXT. Newlines and Unicode line separators cannot introduce
controller heading lines. A fixed instruction says these are untrusted source data.
No source fragment changes permissions, tasks, goals or tool authority.

Enable explicitly in a project's existing controller config (operator action):

```json
{"knowledge_policy":{"enabled":true,"max_context_bytes":32768}}
```

The path is config/projects/<id>.json; merge this field with existing settings rather
than replacing them. Set enabled=false/remove the override to disable it. Global
defaults are in config/knowledge_policy.json and default to false. Development does
not enable or modify any real project's config. The root knowledge_policy adapter
keeps older offline fixtures portable when the optional package is disabled.

The shared read-only build API can also serve supervision previews. R01 frozen
snapshot/contracts remain unchanged: an old event never receives live, unbound
retrieval results. No new executor or real Codex enablement is introduced here.

OpenSource design reference: [PaperQA2 fixed commit](https://github.com/Future-House/paper-qa/tree/57e89f7223b0960d5ee5ea048c69e3c47e088572), Apache-2.0.
LICENSE SHA-256 a10f591e3522fbfe867cfde0b35e0594f6f43a51b013540208a1469c9e0b0f62.
docs.py retrieve_texts/aget_evidence/aquery and agents/main.py's search/evidence stages
informed separation of recall, ranking and provenance. No upstream code, MD5 identity,
automatic query rewriting, LLM summaries, embeddings or upstream run_fake_agent were
adopted; the latter still invokes models. This implementation uses standard-library
matching and original controller trust rules. Pin/license/file hashes and local test
mapping are recorded in the acceptance reference manifest.

Validation: test_knowledge_retrieval.py, scripts/verify_r09_offline.py, and the full
controller regression suite. Native acceptance uses only disposable toy projects and
compares actual original/opt-in prompt bytes, readonly query fingerprints, original
PDF loss and cache/history recovery. There are no paid provider requests.
