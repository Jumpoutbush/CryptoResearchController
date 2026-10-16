# v3.3 · 开发轮次 R02：监督触发器、独立预算与去重

> 2026-10-16 增量补充：另按 `UPGRADE_20261016/02_R02_CRASH_RECOVERY_ADDENDUM.md`
> 核查本地调用恢复和未知外部结果，不更改已提交 R01 契约。原 R02 验收历史保留，
> 本次补充以追踪表追加回执为准；不进入 R03。

> **本地执行状态：DONE**（2026-10-16）。实现与离线验收完成，本地提交
> `7257e070c20af2b563197c9b748463797a6c40d1`。仅表示 R02 通过，未启动 R03。
> 兼容已有 `supervision.py`，实际新增 `supervision_scheduler.py/supervision_ledger.py`；
> 不可变输入与追加日志在原监督目录的 `event_queue/`，成本仍在原 `ledger.json`。
> 新全局开关默认关闭，并保留原项目策略和预算；开启新协议时仅排队，不调用旧执行器。
> wrapper 传入本次已解析路线策略，保留临时 CLI 覆盖；其他入口复用原持久策略。
> 接口、恢复规则与离线证据见 [R02 实现说明](../../../SUPERVISION_R02_EVENTS.md)。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

在已验收研究轮次之后产生持久化监督事件，实现每三轮触发、路线复评优先、独立调用账本，不调用真实监督模型。

**现有基础：** `runner.py.advance_one` 已区分 `COUNTED_RESEARCH_ROUND` 与 `ROUTE_REVIEW`；`needs_review` 决定原预算复评；`research.py.watch` 遵循 `last_run`。

**进入条件：** R01 契约和快照生成测试通过。

## 2. 设计裁决与数据流

### 2.1 触发优先级（固定）

- 已验收研究轮次且 `effective_rounds` 到达 3 的整数倍：周期监督。
- 该轮同时触发 `review_pending`：只记录 `DEFERRED_TO_ROUTE_REVIEW`，等内置 `--route-review` 验收后，将两项原因合并为**一次** `POST_ROUTE_REVIEW` 事件。
- 若人工主动请求监督，事件类型为 `MANUAL`；不得突破 STOP、活动尝试或不完整事务的限制。
- 失败轮、缺失 `ROUND_REVIEW`、独立监督自己的一轮、dry-run 均不计入 `effective_rounds`。

### 2.2 可靠队列

主键：项目 ID + route epoch + 触发源 run ID + 已规范化触发原因。事件写入原子文件，`event_id` 为哈希；按事件 ID 去重。`QUEUED` 不是已付费，执行前先预留 `CALL_RESERVED`，中断也保留预算消费记录。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `supervision/scheduler.py`：`record_postaccept`, `pending`, `deduplicate`, `claim_event`。
- 新建 `supervision/ledger.py`：`state/supervision/<id>/events.jsonl`、不可变事件文件和调用记账。
- 在 `runner.py` **研究提交成功并事务结束** 的安全边界接入事件写入；避免监督崩溃使已接受科研回滚。
- 在 `research.py` 添加只读 `supervise status <项目>` 与 `supervise pending [项目] --dry-run`（若解析器已有同名接口，先合并）。
- 新建 `tests/test_supervision_triggers.py`。

## 4. Codex 必须完成的实现步骤

1. 用最少代码复用 `epoch['effective_rounds']`，不要新增 second_effective_rounds 字段。
2. 记录触发时冻结 `goal_sha256`、`anchor_id`、`selected_idea`、`route_epoch` 和源 run ID。
3. 原内置路线复评未完成时不允许监督修改指南；仅落盘“复评后再审”的持久事件。
4. 事件采用追加式操作日志；预留监督调用次数独立于研究预算和固定问题预算。
5. 确定性的离线调度支持模拟当前状态和时钟；重启后从队列恢复。
6. 测试 `run`、`watch` 与直接 `runner.py` 在同一个接入点产生相同事件，不另写一套 watch 计数。

## 5. 输入、输出与接口约定

新增 CLI 仅为计划，实施并通过解析测试后才对外发布：

```powershell
.\research.cmd supervise status secagg-research
.\research.cmd supervise pending --dry-run
```

`--dry-run` 读取结果但不得落盘新的事件、账本或临时配置。


## 6. 必做的离线自动测试

- 计数序列 `1,2,3,4,5,6` 只在第 3、6 个已接受轮产生周期事件。
- 相同 run ID 重放三次仍只有一个事件，且模型调用预算未消耗。
- 第 3 轮恰逢预算复评时，复评前无自动应用，复评后最多一个合并事件。
- 有活动 `attempt`、显式 `STOP_REQUESTED`、`NEEDS_INPUT` 的场景正确区分“允许只读建议”和“不允许改路线”。
- 并发模拟两个进程领取相同事件，只允许一方获得领取权。
- 模拟 Windows 锁占用与重启，待办队列不丢失。

## 7. 本轮验收标准

- 三轮触发、去重、复评优先三个性质均由测试证明。
- 成功的旧研究回执与路线使用量不变。
- 新旧 `research.cmd run/watch` 调用契约完全兼容。

## 8. 停止、回滚及禁止事项

任何情况下不得为了完成监督触发而自动运行 `refocus` 或增补研究预算。发生锁冲突只保留事件待办，并记录恢复原因，不启动第二个科研进程。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
