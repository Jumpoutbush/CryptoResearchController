# 可选只读证据图

本项目复用控制器 knowledge build/status/explain，不需要项目专用代理。
索引只存于控制器 state/knowledge，可删除重建。构建不修改本项目原始资料、
CLAIM_GRAPH、状态、预算或证明等级；默认不创建缓存。
原始论文页码核验和失效事件的能力按实施追踪表分别验收。

# Original-paper references

The optional `literature/source_spans.json` operator registry binds exact original
PDF pages, extraction and technical-review hashes. See `docs/KNOWLEDGE_R07_SOURCES.md`
in the controller. Old free-form locations remain unverified; no automatic download
or scientific proof promotion occurs when building this index.

Graph builds also retain an append-only observation history beside the disposable
index. `knowledge diff --from-index <sha> --to-index <sha>` compares recorded versions;
`knowledge explain` shows original invalidation causes and exact old dependency pins.
Preserve `history.json` when deleting an index. See `docs/KNOWLEDGE_R08_LINEAGE.md`.
