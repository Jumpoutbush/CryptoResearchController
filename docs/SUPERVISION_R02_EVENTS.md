# R02：监督触发器与独立调用预留

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
