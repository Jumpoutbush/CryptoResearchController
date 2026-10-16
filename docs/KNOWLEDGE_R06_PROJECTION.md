# R06 只读证据图与可重建缓存

R05 已在 1695bdd / 5e498f2 完成离线验收后才开始本轮。新增 knowledge 包读取现有
claim_graph.status、problem_compiler.pool、knowledge_graph.status 和原路线/attempt
回执。没有替换权威主张图，没有调用 refresh/save，不建立第二份预算或证明等级。

## 使用

```powershell
.\research.cmd knowledge status <project>
.\research.cmd knowledge build <project> --dry-run
.\research.cmd knowledge build <project>
.\research.cmd knowledge explain <project> --claim <claim-id>
.\research.cmd knowledge explain <project> --claim <claim-id> --revision 1
```

status 保留旧 knowledge 视图，并附加 projection 摘要。status/explain/dry-run 不创建
缓存、锁或账本。build 仅原子写 `state/knowledge/<project>/index.json`，沿用原
route/core/queue 锁序及单独 knowledge 锁；相同字节不重复写。支持项目目录调用。
旧 search/show/trace/impact/import/refresh/invalidate 与 claim show/status 均保留。
旧 refresh 仍是显式维护旧 memory 的接口，不能与本轮只读来源 build 混用。

缓存可直接删除后重新 build；原始来源、主张和预算保持原样。构建失败保留旧缓存。
Python接口为 `knowledge.build.build(controller, project, dry_run=False)` 及
`knowledge.build.explain_claim(controller, project, claim_id, revision=None)`；显式传控制器
路径以对齐既有助手接口。调用者须使用与原 configuration.ROOT 一致的控制器根目录，CLI已保证。
读取始终从当前权威资料派生，不信任缓存里的科学状态；缓存显示 ABSENT、CURRENT、
STALE 或 CORRUPT。合法 JSON 但类型错误同样是 CORRUPT，读取不会自动修复。
源码回退只涉及本轮控制器提交；无需回滚、清理任何个人项目。

## 身份与来源

节点ID为 `project_id:kind:source-id:revision`，各段独立URL编码。同标题/同ID的跨项目
主张不合并；义务同时绑定问题ID、问题版本、原义务ID。SOURCE_VERSION 按来源SHA
区分版本，EVIDENCE_FILE 保留文件身份；GOAL 历史版本保持原SHA，不重绑新目标。
schema_version=1、builder_version=R06.1，输入清单逐项保存scope/path/SHA/source schema。
来源schema为null表示未声明版本或不是结构化JSON；缺失路径的SHA为null，不推断其内容。
节点和边稳定排序，无构建时间戳；相同输入产生相同摘要。输入最多10,000项，缓存16MB。

节点覆盖 PROJECT、GOAL、PROBLEM_VERSION、OBLIGATION、CLAIM_REVISION、EVIDENCE_FILE、
SOURCE_VERSION、RESEARCH_RUN，并增加 EXPLORATION_NODE、FAILED_BRANCH。paper/theorem
沿用旧 memory 的 record_kind，不自动变成已审查主张。每条边携带 provenance_kind、
source_path、source_sha256、scope、verified_status；证据pin另存原哈希及来源定位。

当前主张的 proof_status、novelty_status、invalidation_reasons 完整继承原权威接口。
历史主张标记 HISTORICAL_NOT_REVALIDATED；精确 claim/memory 依赖按原版本与spec SHA
解析，多层历史链不跳转最新版本。缺失或不匹配的pin保存coverage gap，不能假装已解析。
来源变化后保留旧pin、显示当前SHA并标记PENDING_REVALIDATION；不向权威图写失效事件。
源文件构建前后两次清单不一致则拒绝提交缓存。这里只是R06投影，不实现后续失效事件协议。

正式研究run来自原路线回执，首次记录的纪元/锚点不会因路线重访复制 counted_run_ids
而被重新归属；缺失字段为null，不猜预算。attempt→call父关系直接来自原结构。
只有明确失败的call才成为结构化失败分支，保留失败理由。Markdown失败章节只标
UNVERIFIED_TEXT_REFERENCE；文件包含关系使用DERIVED_FROM，不猜REFUTES或逻辑依赖。
工具记录不证明定理；仅原canonical状态已确认机器反例时生成相应REFUTES边。

## 离线验证

```powershell
python -B -m unittest discover -s tests -p test_knowledge_projection.py -v
python -B scripts/verify_r06_offline.py --output <outside-project-evidence-dir>
python -B -m unittest discover -s tests -v
.\research.cmd check all
.\research.cmd doctor --offline
```

入口脚本复制公开控制器到临时目录，用官方 problem/claim/attempt CLI 创建两个
不同前提的合成项目。原生research.cmd验证 CLAIM→OBLIGATION→PROBLEM_VERSION→GOAL、
跨项目ID、删缓存重建、项目目录调用、证据变化及损坏缓存恢复。未调用模型或研究轮次。
真实项目仅只读核验摘要，不创建个人缓存，不更改其状态、预算、历史或证明结论。

## OpenSource附录参考

已读取并纳入本轮 `implementation_roadmap/UPGRADE_20261016/round_addenda/R06_open_source_addendum.md`。
只读参考 [ARA固定提交](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/commit/e52a925e9d03b4ada3008653e72f99b04116fca2)，
SHA `e52a925e9d03b4ada3008653e72f99b04116fca2`。
[MIT许可证](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/LICENSE)，
Copyright 2026 Orchestra Research。没有复制、安装或执行上游系统/技能，没有新增运行依赖。

| 参考文件 | 内容与本地适配 | 验证 |
| --- | --- | --- |
| [logic/claims.md](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/examples/the-ara-of-ara/logic/claims.md) 3—11 | 独立ID、状态、出处、证据与依赖；本地以原canonical状态为准 | 跨项目身份、未审查不提升、claim show/status不变 |
| [trace/exploration_tree.yaml](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/examples/the-ara-of-ara/trace/exploration_tree.yaml) 329—344 | 保留失败原因/教训及显式父子结构；不导入其样例科研结论 | attempt/call精确父节点、Markdown只unverified、重复日志去重 |
| [research-manager](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/skills/research-manager/SKILL.md) 384—436、650—655 | 探索/主张模式、来源不等于验证；仅作为外部设计资料 | 历史pin、来源变更、缓存删除重建、权威文件字节不变 |

SHA-256：LICENSE `25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`；
claims.md `f1bf1bca131e5b02d92c6cee785f2693444f019cc22be0e5dedb01d922c93d3d`；
exploration_tree.yaml `c5bc957e1bd4feb7fb908b5ca6ab4cce9e8e223a5ef2094610d4e3df5e97c016`；
research-manager/SKILL.md `fc8fb52d57cbae4c754fd7bf9e6023dbf54fd4e796152d87786749e1f30d2c37`。
