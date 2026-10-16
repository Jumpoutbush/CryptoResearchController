# R02：监督触发器与独立调用预留

## 2026-10-16 兼容补充

本次按 [R02 崩溃恢复附录](implementation_roadmap/UPGRADE_20261016/02_R02_CRASH_RECOVERY_ADDENDUM.md)
增量核查，R01 的 schema、事件 ID、快照和主状态机保持原字节。
原已正确的去重、ACK 补记、路线计数和验收后唯一入口继续复用。

`RESERVATION_INTENT` 在唯一成本账本提交前保存基线摘要、领取令牌、PID/实例身份、
世代 1、输入/事件版本和模型路由。它不累计余额。预留前中断且原账本完整不变时复用
相同意图；有意图却缺账本或账本不相容时停止，不能重新登记为零。
租约依赖原生排他锁和不可重复领取的令牌，不根据超时、PID 重用或删锁文件自动重派。

`supervision_calls.py` 仅提供本地兼容恢复接口，没有子进程、模型或指南执行器：

- `mark_dispatched`：先保存派发 fence，再确认日志，成功返回一次许可。
  参数向量按规范化摘要冻结，明文只保留已冻结模型/effort，不保存可能含凭据的原始参数。
  全局或项目开关已关闭时不能获许可；日志与账本派发见证不符则停止。
- `save_completion`：原始输出、日志、状态和耗时以有界不可变回执先落盘，始终标记
  `UNVERIFIED_EXTERNAL_OUTPUT`。此状态不是证明、新颖性或指南应用的批准。
- `recover_completion`：严格校验原回执后，复用 `finish_claim` 幂等结算和补确认。
  没有原回执不能将派发风险按零耗时退款，恢复过程不调用模型。

派发后无完成回执时，R01 上层仍可为 RUNNING；内部显示 `UNKNOWN_EXTERNAL_OUTCOME`，
`operator_audit_required=true` 且禁止自动重试。尚未派发显示 RESERVED_NOT_DISPATCHED；
旧版没有派发元数据的未完成预留显示 LEGACY_DISPATCH_UNRECORDED，需要人工审计。
已有回执但未结算显示 CALL_COMPLETED/COMPLETION_REPLAY_REQUIRED，只允许重放。
不能凭“租约过期”或“本地文件缺失”推断提供方未收到请求。

冻结包缺失、损坏、必要正文截断或非法链接时，领取/恢复写入
BLOCKED_MISSING_FROZEN_INPUT 诊断，只记录相对路径、期望摘要与原因，不打印全文。
R02 要求 GOAL、PROJECT、STATE 和已选想法完整，其他来源仍遵循原 R01 可选截断规则。
查询不落盘诊断；操作者应恢复原快照字节，不能把现场新 GOAL 绑定为旧事件。

这里分别保证事件去重、本地不重复预留/结算和派发许可至多一次；没有可验证的提供方
幂等键，不能承诺远端实际账单恰好一次。未知结果只接受操作者审计和可靠原回执恢复，
本轮不提供清零、强制重派或释放派发预留的命令。

R02 故障矩阵的第 7/8 项在本轮验证 PROPOSED 恢复不再调用且不写任何指南；
既有旧指南原子替换失败测试继续回归。新 ACTIVE_GUIDE 的应用、CAS 和半写恢复须在
R04 实际接入后另外验收，不能用旧流程测试冒充新流程完成。
进入 R03 前须保留本轮故障注入、真实 runner＋模拟 Codex 的回执、全套回归、
Windows 占用文件验证和私人数据哈希对比，并登记真实提交；R03 本轮不启动。

按 `implementation_roadmap/00_INDEX.md` 完成 R01 后，本轮只实现事件、复评优先级及
调用预留，不启动监督模型、不应用指南。R03—R05 和 v3.3 发布门禁仍须分别验收。

## 复用与兼容

科研轮数只读取原路线账本当前 epoch 的 `effective_rounds/counted_run_ids`，
预算及停滞复评由原 `route_budget.needs_review` 决定。
wrapper 传入当次已解析策略，保留 `--route-budget/--stagnation-rounds` 的临时覆盖；
独立入口和领取使用持久策略，不把当次覆盖静默保存为新预算。
监督成本继续写原 `state/supervision/<id>/ledger.json` 的 `attempts_used/seconds_used`，
在同一账本增加 `event_reservations`，不创建第二份成本余额。
原项目监督策略决定开启状态及 `max_reviews/max_seconds/max_total_seconds`。

文件使用 `supervision_scheduler.py`、`supervision_ledger.py`，避免与原 `supervision.py`
冲突。事件放在 `state/supervision/<id>/event_queue/`，避免混入旧日志。这些是规划路径
的兼容适配，没有复制科研计数、重置预算或迁移个人历史。

## 开关与只读查询

新协议需同时将 `config/supervision_defaults.json.enabled` 设为 `true`，并开启原项目
监督策略，例如 `research.cmd supervise configure <项目> --enabled on`。
本次保持实际配置，全局新开关默认 `false`；**已启用的旧监督仍可能在真实科研时调用
原监督模型**。两级开关同时开启后进入 R02 排队模式并绕过旧执行器。本轮没有事件消费
CLI，待办不会自动调用模型或修改指南。`supervise` 是 `supervision` 的完整别名。

```powershell
.\research.cmd supervise status all
.\research.cmd supervise pending --dry-run
.\research.cmd supervision pending <项目> --dry-run
```

查询不创建锁、事件、配置或账本。`status` 保留原字段，增加 `event_queue`；`pending`
展示事件、延期原因、恢复标记、原成本及逐事件领取限制。
`supervise run <项目> --force` 在新模式下只提出 MANUAL 请求。

## 唯一触发点

`run/watch/runner.py` 共用 `runner.advance_one`，在事务 `accept()` 和发现引擎
`finalize_wrapper()` 后、知识索引刷新前记录事件。队列失败返回 `SUPERVISION_QUEUE_FAILED`，
保留已接受科研、预算扣账及成功回执；重启在下一轮前按相同收据恢复。缺失匹配的
ROUND_REVIEW 或未提交的 epoch 均拒绝。

默认周期为三轮，当前 epoch 有效轮数到达 3、6、9……才产生 PERIODIC；失败、dry-run、
复评和重复 run 不额外计数。中途开启不回填更早区间；当前 last_run 恰在周期边界时，
启动恢复会补登记该边界。原登记基线保持不变。
同时需要预算/停滞复评时先持久保存 DEFERRED_TO_ROUTE_REVIEW，原控制器合法
ROUTE_VERDICT_RECORDED 后合并为一个 POST_ROUTE_REVIEW。事件绑定原科学 run，
context 另存复评 run、全部来源和触发原因。无效裁决、原生停止、目标绑定变化不解除延期。

STOP、NEEDS_INPUT、旧监督暂停和不完整事务阻止领取；活动 attempt 仅允许只读建议。
本轮不改指南、不关闭 attempt、不换题、不恢复科研、不追加预算。旧事件在目标锚点或
纪元失效、当前仍需复评时保留待办，不能领取。

## 持久化与故障恢复

`events/<event_id>.json` 保存带摘要的不可变 R01 事件、快照及 context；
`deferrals/<id>.json` 保存冻结延期身份。事件键不因采样时间或新证据改变。
`events.jsonl` 带序号和摘要链，每次原子替换保留完整追加前缀；残行、确认后丢失输入、
不同摘要的重建和消失的调用预留均停止处理。

锁顺序为路线锁、执行锁（领取时）、队列锁。Windows 双进程仅一方领取，冲突另存
`lock-conflicts/` 恢复原因，不扣费、不启动第二科研进程。
排队免费；`claim_event` 在外部执行前向原监督账本预留一次调用和最大秒数。
同事件重试不再领取；进程死亡保留全部预留。`finish_claim` 凭相同令牌结算实际耗时，
重复完成只补确认，不重复退款。

输入先落盘、日志确认中断时重放补确认；成本先落盘、确认中断时从原成本账本恢复。
查询只标记恢复需求，不自行修复。输入丢失或日志损坏应恢复原备份，不能删除预留获得新调用。
回退只关闭新协议或回退本轮源码；保留事件、成本及原项目历史，没有自动批量迁移。

## 离线验证

专项：`python -m unittest discover -s tests -p test_supervision_triggers.py -v` 和
`python -m unittest discover -s tests -p test_supervision_trigger_runner.py -v`。
随后运行全套 unittest、`research.cmd check all`、`research.cmd doctor --offline`。
正常证据：`test_budget_boundary_defers_then_valid_review_coalesces_without_science_recount`；
故障证据：`test_queue_failure_preserves_acceptance_and_recovers_before_next_round`、
`test_reservation_ack_failure_cannot_hide_removed_cost_receipt`、
`test_finish_ack_interruption_is_visible_and_repaired_without_refund_twice`。
测试使用临时项目和模拟科研子进程，运行原控制器的真实验收逻辑，不调用付费模型。
