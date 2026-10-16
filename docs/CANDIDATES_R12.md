# R12：证伪优先、共用原预算的候选调度

本轮在 R11 的冻结候选之间提供确定性的下一任务建议。调度器不调用模型，不自动导入问题，不启动或关闭科研尝试，不修改 `STATE.next_task`，也不创建第二套科研有效轮数。真实监督和 Lean 的既有执行阻断保持不变。

## 先预览，再明确选择

```powershell
.\research.cmd candidate plan <project> --dry-run
.\research.cmd candidate schedule-status <project>
.\research.cmd candidate plan <project> --dry-run | Set-Content -Encoding UTF8 <plan.json>
.\research.cmd candidate select <project> --id C-0002 --expected-revision 1 --plan-file <plan.json> --reason "先检查这一精确反例入口"
```

`plan` 和 `schedule-status` 始终只读；即使没有 `--dry-run`，也不会执行研究。已有 `candidate status --id --status --expected-revision --reason` 仍是 R11 状态变更接口，未改变含义。省略项目参数时沿用项目目录自动解析。

计划输出包括：

- `snapshot` 及 `snapshot_sha256`：当前目标锚点、路线 epoch、`last_processed_run`、候选、路线、注册见证、固定尝试、恢复状态及证据的精确输入快照。
- `rankings`：每个非终局候选的证伪动作、逐项事实来源、内容 SHA、定位符、适用范围和优先级向量。
- `route_budget`：原 `state/routes/<project>.json` 的已用有效轮数、总额度、剩余轮数、延期次数和复评原因。
- `attempt_budget` 与 `supervision_budget`：只读展示原固定问题尝试和独立监督账本；不把缺失账本解释为新额度。
- `required_action`、`blocking_reasons`：下一步的明确人工操作或恢复原因。
- `execution_allowed=false`、`automatic_retry_allowed=false`、`budget_extension_requested=false`：选择建议不授予执行或预算权限。

`select` 要求完整计划文件和当前候选版本，通过快照比较后只追加待人工核对的建议。同一快照和同一候选的重复选择返回同一个 `selection_id` 和 `idempotent=true`。过期输入拒绝选择，不能把空值或省略字段当作忽略版本校验的方式。可以显式选择当前调度窗口内的其他非终局候选，但不会因此获得执行许可；窗口外候选不能绕过计划直接选择。

每份计划最多比较 3 个候选。先保留已有 `SCREENING / READY_FOR_ATTEMPT / ACTIVE` 候选，再按证据优先级补充剩余空位；其他候选保留原记录，并在 `deferred_candidates` 中说明延期原因。调度窗口没有给候选增加状态、创建新尝试或重置预算，也不改变 R11 对活跃状态的独立上限。

## 排序依据及边界

默认比较顺序为决定性证伪入口、文献覆盖、安全或正确性障碍、冻结目标关联、可核对成本，最后按候选 ID 和版本稳定打破平局。不使用随机数、Elo、模型自评收益或候选自报的低成本直接分配预算。

当前证伪事实来自已钉住的现有主张：证据必须新鲜，版本、内容 SHA、依赖和审查历史有效，且 `machine_statement` 能由既有精确整数验证器解析。输出 `COMPUTABLE_PREDICATE_PENDING` 只表示存在可检查的命题；调度器没有执行验证，也没有证明它能够否决整个候选。下一任务仍要求独立核查该命题对候选的含义。

未独立审查的必要依赖可以生成待核对任务，但不能成为已证安全性或已证障碍。文献直接覆盖、无法从现有独立证据推出的结论等维度保持 `UNKNOWN`，不由模型凭感觉填入概率。已有 `REFUTED / COVERED / RETIRED` 分支保留在 R11 历史中，并从新的推荐列表排除。

成本展示区分候选自报上下文估计与当前输入字节数。实际测量也只是契约和证据文件大小，不是模型调用耗时、密码协议复杂度或完整上下文成本。R11 的 READY 和独立引理审查都不能证明整个候选安全；本轮尚无候选整体安全回执，因此所有成本仅作展示，`used_for_ranking=false`，优先级向量末位为零。便宜候选不会仅靠自报低成本排在可核验的证伪任务前。

所有排序维度都保持 `positive_basis=false`；计划和选择不修改主张、定理、证明或创新性等级。

## 固定问题和运行归属

活动尝试存在时，计划返回 `DEFERRED_UNTIL_ATTEMPT_CLOSE`，保留该尝试及其检查点，不自动切换问题或关闭尝试。未知或待结算调用、包装器接受事务未完成、STOP、路线待复评及预算耗尽都会阻断新候选的执行准备。预算问题交回原路线复评流程；本轮不会自动发起付费复评或重置预算。

人工确认固定命题后，仍须使用原入口显式导入问题、开始尝试，然后在任何调用之前绑定候选归属：

```powershell
.\research.cmd attempt start <project> --problem P-1 --version 1
.\research.cmd candidate bind-attempt <project> --selection-id <S-id> --attempt-id <attempt-id> --reason "人工确认同一冻结命题并在调用前绑定"
```

`bind-attempt` 不会代替 `attempt start`。候选必须已经是 `READY_FOR_ATTEMPT`，其独立门禁和原问题精确版本仍有效；条件变化、过期选择、预算复评或恢复待办会拒绝绑定。原尝试只要已经出现任何调用，就不能事后推断候选身份。绑定记录表示操作员赋予的调度归属，`candidate_injection_proven=false`；它不能证明科研代理实际读取了某份候选卡。

原科研入口完成运行后，才可以登记对应关系：

```powershell
.\research.cmd candidate map-run <project> --selection-id <S-id> --attempt-id <attempt-id> --run-id <run-id> --reason "登记原控制器完成回执的归属"
```

映射必须已有调用前的唯一绑定，并核验原固定尝试中的终局调用、结算开始见证和完整完成回执。成功科研调用还必须在原路线账本中存在唯一已验收事件及计数记录，并有原包装器的可信 `COMPLETE` 接受事务回执；孤立的旧计数字符串不能补造验收。失败调用保持原失败状态；`RESERVED / PENDING_WRAPPER / SETTLING / SETTLEMENT_READY` 等未知或待恢复结果不得映射、补造成功或自动重试。重复映射只读返回同一对应关系，`new_budget_charge=false`，不会重复本地记账。

## 写入与恢复

选择、绑定和映射历史位于 `state/candidates/<project>/selections.json`，每项事件包含前序哈希、请求和原因。它是归属审计记录，预算仍只来自原路线和尝试账本。注册见证位于 `state/candidate_selection_registry/<project>.json`，保存已提交哈希和待完成的原始事务后像。

写操作复用原项目路线锁和科研执行锁，并使用候选和选择记录锁；同一项目只有一个写者。事务先冻结待写后像，再原子更新历史并完成见证。中断后只接受完全相同的原始操作重放；其他请求、输入不匹配、缺失历史或损坏见证停止并要求审计。不会重新派发外部调用。文件哈希及本地见证不宣称能抵抗同时删除或回滚全部本地权威的操作者。

## 固定的 OpenSource 参考

仅参考“选择与执行分离”和可追踪的候选选择记录；未复制代码、安装、检出工作副本或执行上游框架。核验在离线验收前完成，只读从 GitHub 官方源获取固定 Git 对象，完整文件字节哈希如下。

- [AIDE `Agent.search_policy`](https://github.com/WecoAI/aideml/blob/1d8ec4026c67729443294c8b5c0907242d0de38c/aide/agent.py)，提交 `1d8ec4026c67729443294c8b5c0907242d0de38c`，源文件 SHA-256 `2748e393b4fa1bd9291a50d03dcaf0d62aaea908b4576c9131e9fb7d2b04607a`；[MIT 完整许可证](https://github.com/WecoAI/aideml/blob/1d8ec4026c67729443294c8b5c0907242d0de38c/LICENSE) SHA-256 `723b16d1701dfb2d280d229ff84f3056df65b6b00ad8419ec6cb7da2fdd8f616`。本地用确定性证据任务替代其随机调试选择和经验指标贪心选择，不继承指标作为科研成功标准。
- [OpenEvolve `openevolve/database.py`](https://github.com/algorithmicsuperintelligence/openevolve/blob/a1e9d91eecde612f0efc8e8e31f59b36998248c0/openevolve/database.py)，提交 `a1e9d91eecde612f0efc8e8e31f59b36998248c0`，源文件 SHA-256 `5fe668f274099ab820634f0154a9a0cc64c4ee3dc032b9d0a31e283bf9b51c6b`；[Apache-2.0 完整许可证](https://github.com/algorithmicsuperintelligence/openevolve/blob/a1e9d91eecde612f0efc8e8e31f59b36998248c0/LICENSE) SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。参考 `Program`、`ProgramDatabase.sample`、`sample_from_island`、`save` 和 `load` 的身份、来源和选择记录；不引入岛群并行执行、随机适应度采样或独立迭代预算。

## 离线验证

```powershell
python -B -m unittest discover -s tests -p test_candidate_scheduler.py -v
python -B -m unittest discover -s tests -p test_candidate_budget.py -v
python -B scripts/verify_r12_offline.py --output <outside-runtime-evidence-directory>
python -B -m unittest discover -s tests -v
python -B research.py check all
```

真实 Windows 入口验收仅在临时项目中运行。原 `runner.record_round` 和 `save_ledger` 模拟两次 `NO_PROGRESS` 验收，确认有效轮数从 0 到 1 到 2，三个候选共同读取剩余 4 轮；候选模块不手动增加该计数。临时样例的支持工作阈值设为 3，使这两次模拟不提前阻断正常计划，个人配置保持不变。

两个真实控制器进程竞争同一选择，最多形成一项唯一选择记录；后续测试覆盖 READY 的显式绑定、活动尝试延期、事后绑定拒绝、未知结果拒绝和原结算 API 生成的可信失败回执映射。该失败运行是纯本地故障样例，不存在模型请求。每项候选操作都逐字节比较项目、主张、原路线和尝试账本、监督账本及配置；只有明确调用的原控制器接口能改变相应临时权威。审计钩子拒绝并记录任何网络访问或嵌套进程执行，最终要求拒绝记录为空。
