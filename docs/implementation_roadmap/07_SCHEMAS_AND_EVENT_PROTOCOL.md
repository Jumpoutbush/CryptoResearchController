# 七、四个版本必须保持兼容的核心数据契约

> **R01 本地落地说明（2026-10-16）：**事件规范字段以本页的 `trigger_type/state/focus`
> 为准，不接受个别示例中的别名。稳定 Python Schema 接口在 `supervision_contracts.py`；
> 快照接口在 `supervision_snapshot.py`。`next_obligation_id` 在非聚焦建议且确实没有已登记
> 义务编号时可为 `null`；聚焦建议仍必须绑定真实义务。R01 的事件状态转换是纯数据契约，
> 持久化与消费由后续 R02 实现。该适配不表示本页其余版本已经完成。

此文档只定义**预期实现接口**。现有 `67618536` 源码并无这些新增监督/知识/候选/评价对象；实施过程中若修订字段，必须做版本迁移与向后兼容测试，更新全部相关轮次文档。

## 7.1 监督事件（v3.3）

```json
{
  "schema_version": 1,
  "event_id": "sha256(canonical trigger payload)",
  "project_id": "example-project",
  "route_epoch": 1,
  "trigger_type": "PERIODIC",
  "trigger_run_id": "real accepted run id",
  "focus": {"goal_sha256": "...", "anchor_id": "...", "selected_idea": null},
  "source_manifest_sha256": "...",
  "state": "QUEUED",
  "review_precedence": "ROUTE_REVIEW_NOT_PENDING",
  "created_utc": "real timestamp"
}
```

枚举：`trigger_type ∈ {PERIODIC, POST_ROUTE_REVIEW, MANUAL}`；`state ∈ {QUEUED, RUNNING, PROPOSED, APPLIED, REJECTED, FAILED, CONFLICT}`。规范化 JSON 后计算事件哈希，但**不要把 `event_id` 自身放进计算输入**，避免循环定义。`created_utc` 不应影响重复事件键；稳定去重键来自项目、纪元、run ID、触发原因及 GOAL 锚点。

## 7.2 监督提案（v3.3）

```json
{
  "schema_version": 1,
  "event_id": "exact event id",
  "project_id": "exact project id",
  "goal_anchor_id": "exact goal anchor",
  "input_snapshot_sha256": "exact input snapshot digest",
  "action": "REFOCUS_RECOMMENDED",
  "evidence_refs": [{"path": "research/proofs/example.md", "sha256": "...", "scope": "DIRECT_DEPENDENCY"}],
  "reason": "具体且可复核的当前障碍",
  "next_obligation_id": "O-001",
  "next_task": "一个有可证伪标准的下一轮任务",
  "success_criterion": "可检验成功证据",
  "falsification_criterion": "决定性反例或直接覆盖证据",
  "requires_operator_approval": false,
  "guide_notes": ["可核查的补充限制，最多三项"]
}
```

允许动作：`KEEP_GUIDE / REFOCUS_RECOMMENDED / PAUSE_RECOMMENDED / ESCALATE`；不能包含 `STOP`, `APPROVE_THEOREM`, `RESET_BUDGET` 作为自动行动。`KEEP_GUIDE` 可以不生成新指南，但也要保存监督报告。受控指南自动应用仅限候选任务指引、证据筛选和审查提示，不能越权改变路线裁决。

## 7.3 指南应用回执（v3.3）

```json
{
  "event_id": "...",
  "project_id": "...",
  "target_path": "supervision/ACTIVE_GUIDE.md",
  "precondition": {"goal_sha256": "...", "last_run": "...", "old_guide_sha256": "..."},
  "result": {"new_guide_sha256": "...", "receipt_status": "APPLIED"},
  "history_path": "state/supervision/<project>/guides/<event_id>.md"
}
```

应用器只接受 `target_path` 的固定常量，不能由模型自由指定。跨项目路径、`../`、Windows 绝对路径、符号链接、扩展名伪装均拒绝。历史中应保留**新旧内容**及摘要，以便非 Git 管理的个人项目回滚。

## 7.4 知识证据边（v3.4）

```json
{
  "edge_id": "stable digest",
  "origin_project_id": "...",
  "source_node_id": "claim version id",
  "target_node_id": "obligation or source version id",
  "kind": "SUPPORTS",
  "evidence": {"relative_path": "...", "sha256": "...", "paper_location": null},
  "trust": "MODEL_CANDIDATE",
  "source_validity": "PENDING",
  "derived_from_authoritative_status": true
}
```

此结构用于**可重建索引**。任何科学审查状态都必须读取权威 `claim_graph.status`，派生节点不能写回其证明等级。

## 7.5 候选节点（v3.5）

```json
{
  "candidate_id": "C-0001",
  "candidate_revision": 1,
  "project_id": "...",
  "anchor_id": "...",
  "parent_candidate_id": null,
  "problem_version_binding": null,
  "status": "SCREENING",
  "hypothesis": "...",
  "falsification_criterion": "...",
  "novelty_coverage": "UNVERIFIED",
  "evidence_refs": []
}
```

候选权威字段包括冻结锚点与假设。候选历史追加保存；候选状态与正式命题/主张是不同对象，不能互相自动提升。

## 7.6 基准任务和评价报告（v4.0）

```json
{
  "case_id": "BENCH-COUNTEREXAMPLE-001",
  "case_version": 1,
  "type": "COUNTEREXAMPLE",
  "public_input_sha256": "...",
  "oracle_sha256": "...",
  "isolation_audited": false,
  "scoring_rule_version": 1,
  "oracle_status": "PENDING_CURATION"
}
```

只有 `isolation_audited=true` 且 `oracle_status=CURATED` 的任务进入正式指标。金标准不在代理运行的可访问工作目录里；必须使用经过验证的文件隔离或进程权限策略，不能仅在提示词中要求“不要读取答案”。

## 7.7 可信 Python 伪代码：监督事件后的安全应用

```python
# 伪代码：函数为设计意图，非基准仓库已有可调用 API。
def process_supervision(event_id):
    event = trusted_store.get(event_id)
    if event.state == "APPLIED":
        return existing_receipt(event_id)
    with claim_once(event_id):
        snapshot = load_and_revalidate_snapshot(event)
        reserve_call_once(event)  # 先记费用/调用预算
        proposal = read_only_executor(snapshot)
        validate_schema_and_evidence(proposal, snapshot)
        if proposal.requires_operator_approval:
            persist_proposal_only(event, proposal)
            return
        with project_lock(event.project_id):
            verify_no_live_research_transaction()
            check_goal_anchor_and_latest_run(event)
            check_guide_compare_and_swap(event)
            receipt = atomic_replace_guide_and_store_history(proposal)
            commit_supervision_receipt(event, receipt)
```

科研轮次提交与监督事务要分离；不能在 `runner.py` 的 `ProjectTransaction` 中等待外部监督模型返回。若模型调用失败，已验收科研结果应保留。
