# 二、目标架构、事件协议与唯一真相源

## 2.1 四个升级模块的职责

```text
现有科研执行：research.py → runner.py → runner_core.py → 项目科研证据
                                       │ 已验收结果和路线裁决
                                       ▼
v3.3 监督：event queue → snapshot → independent Codex → schema check → guide apply
                                       │ 结构化监督事件／生成指南
                                       ▼
v3.4 记忆：claim_graph + sources + receipts → derived provenance index
                                       │ 可引用、可失效的证据子图
                                       ▼
v3.5 候选：candidate catalog → bounded selector → existing discovery attempt
                                       │ 证明或反例的独立状态
                                       ▼
v4.0 评价：benchmark cases → offline replay → metrics → shadow policy
```

升级期间保留所有现有 CLI 入口。新增模块可作为 `supervision/`、`knowledge/`、`candidate_search/`、`evaluation/` 顶层 Python 包，以标准库为优先。

## 2.2 必须只有一个权威的数据来源

| 信息 | 权威位置 | 新模块能否写 |
| --- | --- | --- |
| 冻结目标 | `projects/<id>/GOAL.md` | 不可写 |
| 用户安全约束 | `inputs/` + GOAL + 固定问题版本 | 不可写 |
| 当前研究阶段 | `research/STATE.json` | 仅沿用原 `research.py/runner.py` 合法流程 |
| 路线预算/停滞 | `state/routes/<id>.json` | 只允许原预算控制器更新 |
| 固定问题与尝试 | `research/discovery/`、`state/discovery/` | 原发现引擎更新 |
| 主张与证明等级 | `research/discovery/CLAIM_GRAPH.json` | 原 `engine/claim_graph.py` 更新 |
| 原始来源 | `literature/pdfs/` 和登记哈希 | 禁止静默替换 |
| 监督计划及执行 | `state/supervision/` | 仅监督控制器更新 |
| 下轮生成指南 | `supervision/ACTIVE_GUIDE.md` | 仅可信监督应用器写 |
| 图谱索引 | `state/knowledge/` | 可重建的派生缓存 |
| 基准答案 | `state/evaluation/private_oracles/`（受限） | 评价器读取，代理无权访问 |

## 2.3 跨模块关键字段

统一使用以下主键，避免用文件名充当永久身份：

```json
{
  "project_id": "secagg-research",
  "goal_sha256": "真实 GOAL.md 的 SHA-256",
  "anchor_id": "研究主线锚点（沿用 research_focus.make_focus）",
  "route_epoch": 1,
  "accepted_run_id": "真实已验收科研轮次",
  "problem_id": "P-001",
  "problem_version": 1,
  "claim_id": "CLAIM-001",
  "claim_revision": 1,
  "source_sha256": "原始材料 SHA-256"
}
```

此为字段契约示意，`"..."` 只是占位符，不能写入真实状态。跨轮/跨项目索引必须显式标注字段实际存在与否，未知值存 `null` 并说明原因，不能凭标题推断同一研究结论。

## 2.4 模块间 API 约束

- `supervision.queue_after_accept(project, run_id, route_epoch, trigger_type)` 只能产生待处理事件，不调用模型。
- `supervision.consume(event_id)` 读取已落盘事件，调用独立模型或离线模拟器，提出结构化建议；科研成功/失败的写事务已结束。
- `supervision.apply_guide(event_id, expected_hash)` 只允许更新受保护的生成指南，保留历史；不修改预算或定理等级。
- `knowledge.build(project)` 从已有源构建派生知识索引；索引文件可删除重建，不得反向修改 `CLAIM_GRAPH.json`。
- `candidate_search.choose(project, proposal_id)` 选择一个待审候选；冻结问题仍通过旧 `problem import / attempt start` 接口。
- `evaluation.replay(fixture_id, policy_variant)` 默认使用模拟模型和固定输入，不能静默进行真实付费调用。

这些函数名为建议的 Python API，开发时若调整，需同步所有后续实现文档、测试和用户手册。

## 2.5 状态恢复原则

先落盘不可变触发快照，再请求模型；先验 schema 与哈希，再原子应用；只有在应用完成并写入回执后，将事件状态置 `APPLIED`。异常重启后，扫描 `QUEUED/RUNNING/PROPOSED` 并按输出哈希去重恢复。绝不为了修复监督失败而回滚一个已经完成的科研轮次。
