# R10 explicit public references

Sharing is disabled in `config/sharing_policy.json`. No project is enumerated or
traversed for sharing. Existing `run/watch/refocus/attempt` and R09 prompts do not
automatically inject foreign references. The new commands are always read-only;
`--dry-run` documents intent and is not required to prevent writes.

```text
research.cmd knowledge shared beta --query NTRU --dry-run
research.cmd knowledge share-preview alpha --claim NTRU-1 --reference-id NTRU-EQ --revision 1 --summary knowledge/shared/drafts/summary.txt --public-source knowledge/shared/sources/paper.txt --license CC0-1.0 --approved-by operator --reason "Approve public toy fixture" --dry-run
```

The second command is an explicit **source-owner** preview. It uses the source's
existing canonical claim/projection, requires a current independently reviewed
claim, and keeps the union of the problem's and claim's assumptions. It writes
nothing. Its `knowledge` JSON object is an unsigned draft; it is not authorization.
An operator reviews/de-identifies the selected summary and freezes that object as
`knowledge/shared/references/NTRU-EQ.json`. No private proof/report or PDF is copied
into the draft. Sharing license, operator and reason are explicit metadata.

Both source and destination use `knowledge/shared/MODEL.json` with these fields:

```json
{
  "schema_version": 1,
  "goal_sha256": "SHA256 of this project's actual GOAL.md",
  "problem_id": "P-1",
  "problem_version": 1,
  "problem_sha256": "existing problem spec_sha256",
  "model": {
    "model": "operator-declared model name",
    "domain": "exact compiled problem domain",
    "quantifiers": "exact compiled problem quantifiers",
    "assumptions": ["all compiled assumptions; source also includes claim assumptions"],
    "parameters": "exact parameters and bounds",
    "adversary": "static/adaptive capabilities and corruption model",
    "leakage": "exact declared leakage function and exclusions"
  }
}
```

GOAL and problem hashes, original problem-goal binding and local problem source
bindings must remain current. Model/parameters/adversary/leakage are explicit human
declarations, not facts inferred by the controller. The destination model's complete
file SHA is fixed by its controller policy, outside model-writable project material.
Changing it requires an explicit operator repin; repinning does not rebind an old
problem to a changed goal.

An operator merges a bilateral whitelist into the controller's sharing policy:

For a project without a reviewed claim, the template's
`knowledge/shared/REFERENCE_TEMPLATE.json` is an intentionally incomplete
`PAPER_IDENTITY` draft. It has no claim, problem or proof authority. Fill its source
identity and actual public source SHA before approving it. `FAILED_ROUTE_TAG` uses
the same public-only envelope with a FAILED_BRANCH identity and remains a failure
tag, not a registered mathematical counterexample. The CLI source preview is for
reviewed theorem summaries; it does not manufacture these missing claims.

```json
{
  "schema_version": 1,
  "enabled": true,
  "projects": {
    "alpha": {
      "enabled": true,
      "imports": [],
      "exports": [{"id":"NTRU-EQ","path":"knowledge/shared/references/NTRU-EQ.json","sha256":"actual approved file SHA256","destinations":["beta"]}]
    },
    "beta": {
      "enabled": true,
      "model_sha256": "actual beta MODEL.json SHA256",
      "imports": [{"origin_project":"alpha","id":"NTRU-EQ","sha256":"same approved file SHA256"}],
      "exports": []
    }
  }
}
```

Placeholder strings above must be replaced with actual lowercase 64-digit SHA-256.
`Get-FileHash -Algorithm SHA256` supplies file hashes. Both sides must allow the same
capsule bytes before its body is opened. The default Git exclusion of `projects/`
does not authorize sharing: only explicit `references/` JSON and the capsule's exact
`sources/` text paths become exceptions. `.txt/.md/.json` public sources are bounded
to 1 MiB, capsules to 64 KiB; credentials, PDFs, code, logs, traversal and links are
rejected. There is no recursive source loading.

The **consumer** reads only the source PROJECT identity, approved capsule, and its
explicit public text source hashes. It never calls foreign `derive`, `goal_binding`,
claim status, or source/claim loaders. Private upstream PDF/claim freshness is thus
`NOT_READ_OR_REVALIDATED`; the checked scope is `EXPLICIT_PUBLIC_SOURCES_ONLY`.
Changing an authorized public text source immediately expires the reference and
reports its exact old/current SHA. Private original changes must be reviewed by the
source owner and followed by a new approved capsule or revocation. An unchanged
public capsule cannot reveal a private PDF changed in place; the implementation
does not claim otherwise.

Every result is `REFERENCE_ONLY`, `positive_basis=false`, and explicitly says
“参考用，尚未在目标项目重新审查”. It preserves origin/destination, problem/claim
versions, source hashes, permission and seven mapping dimensions. Equal text earns
only `EXACT_TEXT_MAPPING_REVIEW_PENDING`; different parameters or static/adaptive
adversaries remain mismatches. Same names retain separate namespaced IDs and conflict
markers. No mapping, source review, score or search result imports a target claim,
discharges an obligation, or counts as proof/novelty. Formal adoption uses the existing
claim import, theorem-level source review and independent review mechanisms.

Every request checks live policy, both pins, source hashes and all consumed metadata
again before returning. There is no sharing summary cache. Revocation prevents future
queries from using old index/cache content; it cannot erase a report already saved
by its recipient. Disable global/source/target `enabled` or remove a whitelist entry
to stop future sharing. No migration, project creation or budget reset is performed.

R06-R09 retain their current-authority/cache contracts. The review fixes add canonical
ordinary-pin validation and complete append-only receipts for new review/tool operations.
Missing old operations remain unavailable. Explicit claim refresh persists scope
revocations; restoring bytes after that observation cannot reapprove old receipts.
Sharing never repairs those pins or imports approval. Consumers do not revalidate
private canonical authority. Details are in `REVIEW_A0E23E3_FOLLOWUP.md`.

OpenSource reference: [ARA pinned e52a925](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/tree/e52a925e9d03b4ada3008653e72f99b04116fca2), MIT,
LICENSE SHA-256 `25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`.
README lines 102-138, research-manager Conditions/Sources/Proof/Dependencies and its
typed example claims informed separation of public artifacts, sources and claims.
ARA does not supply this privacy/authorization mechanism: bilateral pins, read
whitelists, revocation and model mapping are local R10 code. No upstream code or
skill was copied, installed or executed. File hashes and adaptation tests are in
the acceptance reference manifest.

Offline checks: `test_cross_project_isolation.py`, `test_knowledge_e2e.py`, and
`scripts/verify_r10_offline.py`. The last uses actual Windows `research.cmd` in two
temporary NTRU toy projects, including a guarded consumer read, source expiration,
revocation, model pin rejection, cache reconstruction and local revision invalidation.
T07-T09 are offline development checks. The user-confirmed R08 revalidation policy
is explicit; this is not approval for live paid deployment.
