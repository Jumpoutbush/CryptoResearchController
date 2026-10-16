# R08 graph history and invalidation lineage

The original claim graph remains the sole authority for proof, novelty and formal
review. `knowledge build` reads it and records observations; it never calls scientific
`refresh`, `review`, `import` or `invalidate`. Tests use those original operator APIs
only inside temporary projects.

```text
research.cmd knowledge build <project>
research.cmd knowledge explain <project> --claim <claim-id>
research.cmd knowledge diff <project> --from-index <sha256> --to-index <sha256>
research.cmd knowledge build <project> --dry-run
```

Graph schema is now 2, builder R08.1. Existing R06/R07 caches may be rebuilt; no
project migration or budget reset occurs. The deterministic `index.json` remains
disposable. `state/knowledge/<project>/history.json` separately contains logically
append-only events and exact graph snapshots. Each event binds sequence, previous
event SHA-256, UTC observation time, operation, before/after index digests, source
manifest differences, exact claim revisions/spec hashes and original status reasons.
Proof, novelty, formal review and accepted-contribution losses are distinguished.
Original-paper and memory binding losses retain their separate scope. These are
recorded observations, not assertions that the first observation time is when a
mathematical fact changed.

Every stored snapshot must be referenced by a valid event. Lost/pruned snapshots
yield `HISTORY_UNAVAILABLE`; the system never invents an earlier version. A repeated
build and a file mtime change append nothing. A repeated source rename with equal
bytes is shown as `PATH_RELOCATED`, never a scientific discovery. An enclosing
CLAIM_GRAPH file change alone does not invalidate every already-pending claim.

Explain follows C→B→A through canonical current observations while also showing
the exact older dependency pin; it never redirects that pin to the latest revision.
It includes memory dependencies, original/review file hashes, proof and novelty
status separately, and the original counterexample assumptions, witness and machine
statement scope. Bounded search failure and ordinary failed branches do not imply
theorem refutation or a whole-route rejection. Historical snapshots are audit data;
live explain always derives current scientific status from the original modules.

Recovery is ordered: commit the event and its snapshot atomically, then atomically
replace the disposable index, under existing route/core/queue and knowledge locks.
After interruption between those writes, rerunning build reuses the committed event
and repairs the index without another event. A corrupt index can be rebuilt normally.
Malformed/duplicated/reordered/deeply nested history, broken hash chains and orphan
snapshots are reported as `HISTORY_INTEGRITY`; reads never repair them. Bounds are
checked before writes (10,000 events and 64 MiB per history transaction); reaching
them requires explicit preservation/archival, not automatic deletion.

To rebuild only the current disposable index while preserving a damaged history:

```text
research.cmd knowledge build <project> --cache-only
```

This explicit operation still reports history corruption and never rewrites or
discards the damaged log. Save it for review/recovery. Hash chains detect inconsistent
local history, but cannot prevent a filesystem owner deleting or rewriting all of it;
there is no claimed external timestamp or remote append-only anchor.

The user confirmed the original R08 revalidation rule on 2026-10-16. Explicit
`claim refresh <project>` persists observed losses in canonical per-scope revocation
latches and operation events. Restoring exact old bytes after that observation does
not restore approval. Each affected scope requires a new independent review;
upstream dependencies must become valid before downstream approval can recover.
Formal revision/withdrawal still requires the existing explicit rebind/review path.

Read-only status/context/explain and projection derive never persist observations.
Ordinary build/cache-only also never writes scientific authority: an unrecorded loss
of a positive receipt stops the build before index/history writes and requests
explicit claim refresh. Empty graphs and unreviewed candidates remain buildable.
A transient read without a durable observation cannot remember a past filesystem
change; it is not a recorded revocation. The canonical latch is authority, never
the disposable cache or a reconstruction from missing review history.

OpenSource design reference: [ARA fixed commit](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/tree/e52a925e9d03b4ada3008653e72f99b04116fca2),
MIT, Copyright 2026 Orchestra Research. LICENSE SHA-256
`25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`.
`logic/related_work.md` 3–6 distinguishes imports/bounds/baseline;
`skills/research-manager/SKILL.md` 32–49 and its event-taxonomy reference distinguish
current views from append-only trace. The explicit failure N16 is retained in
`trace/exploration_tree.yaml` 329–344. We adopt typed references and retained failure
history, not autonomous scientific status changes, chronology-implied dependencies
or external framework execution. No upstream source code was copied. OpenAI Math
and Science One references remain evidence-organization examples as recorded for R07;
they confer no independent scientific approval.

Validation: `python -B -m unittest discover -s tests -p test_knowledge_invalidation.py -v`
and `python -B scripts/verify_r08_offline.py --output <external-evidence-directory>`.
The native fixture checks original PDF loss through A→B→C, formal revision, readonly
diff/project-directory invocation, unavailable history, cache deletion, a real process
terminated after history commit, and preserved corrupt-history recovery. No model calls.

Rollback only the scoped code change; preserve all historical evidence/logs and
original scientific files. Remove only the disposable index if a rebuild is desired.
