# v3.5 · 开发轮次 R12：单写者、多候选的有界研究调度

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

让控制器在最多三个候选间按证伪价值选择下一项工作，复用 `run/attempt` 调用和原路线预算；调度器可以建议切换，但不创建并行写代理。

**现有基础：** `route_budget.total_budget/needs_review` 管理共享科研路线预算；`engine/discovery_scheduler` 还有固定问题尝试预算和唯一 active_attempt。

**进入条件：** R11 模型冻结与候选版本化完成。

## 2. 设计裁决与数据流

### 12.1 两层预算不重复计数

第 1 层：所有候选共用原路线 `effective_rounds`，只由既有 `runner.py` 更新。第 2 层：活动固定问题仍消耗其原有 attempt 预算。新候选调度器只记录选择建议、占用原因、选中轮次的映射，不再维护与前两者竞争的科研有效轮数。

### 12.2 评分只用于选任务

默认优先级：决定性反例可检验性 > 已知文献覆盖概率 > 安全/正确性主障碍 > 可直接推进冻结目标的程度 > 估计成本。评分必须附事实来源，绝不根据模型“感觉有前景”自动大幅转预算。若固定问题尝试仍活动，禁止自动关掉它；只可提出等当前检查点结束后切换的建议。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `candidate_search/scheduler.py`、`candidate_search/cost_accounting.py`。
- 增加可选 `candidate select/plan/status` CLI；选择候选时仍按旧 `problem import/attempt start` 的明确要求执行。
- 新建 `tests/test_candidate_budget.py`、`tests/test_candidate_scheduler.py`。

## 4. Codex 必须完成的实现步骤

1. 选择前检查 `goal_anchor`、当前 route epoch、`last_processed_run` 与现有 active attempt。
2. 若固定尝试活动，只输出 `DEFERRED_UNTIL_ATTEMPT_CLOSE`，不创建第二个 attempt。
3. `candidate plan --dry-run` 显示各候选的证据、最小证伪动作、已消耗路线轮次和剩余预算，不写账本。
4. `candidate select` 只生成建议/待审草案；需要操作员显式确认固定问题 ID 和 `attempt start`；复评延期仍由原预算系统判断。
5. 发生预算耗尽、STOP、路线 pending_review 时禁止新候选执行，调用原路线复评流程。
6. 选中候选与每个实际 research run ID 一一记录，失败调用及监督费用分别归账。

## 5. 输入、输出与接口约定

候选选择可以引用一个建议评分，但不允许把分数写入科研证明状态。模拟输出：

```json
{
  "next_candidate": "C-0002",
  "required_action": "REVIEW_PROBLEM_BEFORE_ATTEMPT_START",
  "route_effective_rounds": 4,
  "route_budget_source": "state/routes/<project>.json",
  "candidate_evidence": ["真实证据引用"],
  "budget_extension_requested": false
}
```


## 6. 必做的离线自动测试

- 三个候选轮流评估后，路线有效轮次仍来自一个权威账本。
- 修改 candidate ID 或重新创建同假设候选不能重置原路线预算。
- 活动尝试未关闭不能切换固定问题版本。
- 未经人工命题核对不得自动导入 PROBLEM_PROPOSAL。
- 预算耗尽时选择建议被挂起，内置 route review 正常触发。
- 同时两个调度进程最多一个取得写许可。

## 7. 本轮验收标准

- 能在三个候选间展示证伪排序、具体决定性任务及真实剩余预算。
- 与 `research.cmd attempt status` 的活动状态完全一致。
- 无双重记账、无并行项目写入。

## 8. 停止、回滚及禁止事项

不建议本轮引入基于模型自评的强化学习式优先级调整；v4.0 的基准评价完成前维持保守规则。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
