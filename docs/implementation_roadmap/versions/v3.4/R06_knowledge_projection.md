# v3.4 · 开发轮次 R06：基于现有主张图建立统一证据投影

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

统一引用论文、证明义务、主张、反例、候选和研究轮次的实体身份；先做**派生只读图索引**，不替换现有 `engine/claim_graph.py`。

**现有基础：** `claim_graph.load/status/refresh` 是已存在的主张版本与审查接口；`research/PROOF_OBLIGATIONS.json`、`reports`、`literature` 属于不同资料层。

**进入条件：** v3.3 发布门禁通过，监督报告已有真实引用路径。

## 2. 设计裁决与数据流

### 6.1 最小图模式

节点 `PROJECT, GOAL, PROBLEM_VERSION, OBLIGATION, CLAIM_REVISION, EVIDENCE_FILE, SOURCE_VERSION, RESEARCH_RUN`；边 `REQUIRES, SUPPORTS, REFUTES, DERIVED_FROM, REVIEWED_BY, USES_SOURCE`。每条边存 `provenance_kind`、`source_path`、`source_sha256`、`scope`、`verified_status`。同名主张在两个项目中拥有不同稳定 ID。

### 6.2 权威与派生分离

从旧主张图读取结果时，只能保留其现有 `proof_status`、`novelty_status` 和失效原因；禁止在索引中把模型候选升级成独立审查。历史 Markdown 无结构字段时，最多生成 `UNVERIFIED_TEXT_REFERENCE`，不能构造确定性逻辑依赖边。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `knowledge/schema.py`、`knowledge/build.py`、`knowledge/adapters/claims.py`。
- 新建 `state/knowledge/<project_id>/index.sqlite` 或内容寻址 JSON 索引，明确其为可删重建缓存。
- 新建 `tests/test_knowledge_projection.py`。
- 在 `research.py` 增加只读 `knowledge status <项目>` 和 `knowledge build <项目>`（实现并验证后开放）。

## 4. Codex 必须完成的实现步骤

1. 明确图节点 ID 规则：`project_id:kind:source-id:revision`，绝不只按标题或自然语言字符串合并。
2. 从 `engine/claim_graph.status()` 建主张与其精确问题、义务、依赖边；每条继承权威状态。
3. 从旧路线账本抽取科研轮次和目标锚点，不在索引建立新预算。
4. 使用版本化的 `schema_version=1`；索引内容需包含来源 schema 版本与构建器版本。
5. 构建顺序稳定，重复构建无变化时最终摘要一致，避免过度重建。
6. 将索引写在 `state/knowledge`，不写入用户的 `research/discovery/CLAIM_GRAPH.json`。

## 5. 输入、输出与接口约定

建议公共接口：

```python
build(project) -> BuildReceipt  # 返回输入清单、索引摘要、节点数、边数
explain_claim(project, claim_id, revision=None) -> EvidenceSubgraph
```

输出需携带 `claim_revision`、`proof_status`、`invalidation_reasons` 等来自权威模块的字段。


## 6. 必做的离线自动测试

- 两条同标题却不同前提/项目的主张生成不同节点。
- 没有 claim 图或文献时可构建空图并显示覆盖缺口。
- `claim_graph` 中已有上游依赖失效时，索引展示同样原因。
- 删除 `index.sqlite` 后重建结构和摘要一致。
- 模型未审查主张无法通过索引导出“已证”状态。
- 对一份人工修改的证据文件重新构建，来源哈希改变且影响边被标记待刷新。

## 7. 本轮验收标准

- 有一个在虚拟项目中展示 CLAIM→OBLIGATION→PROBLEM→GOAL 的真实查询。
- 索引完全可重建，项目原始证据哈希在构建前后不变。
- 既有 `claim show/status` 结果不变。

## 8. 停止、回滚及禁止事项

禁止首次升级就引入复杂远端图数据库、Neo4j 服务或自动向量嵌入付费接口。所有图结论必须追溯权威来源。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
