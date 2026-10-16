# v3.3 · 开发轮次 R01：监督事件契约与只读快照

> **本地适配记录（2026-10-16）：**本轮实际采用 `supervision_contracts.py` 与
> `supervision_snapshot.py`，避免与已有 `supervision.py` 同名冲突。
> wire 字段统一采用公共 07 的 `trigger_type/state/focus`，本页示例别名不作为另一个协议。
> GOAL 用完整内容哈希标识版本，不虚构编号。事件持久化与调度在 R02 接入。
> 快照限额额外覆盖完整规范 JSON；实际接口和验证证据见
> [R01 实现说明](../../../SUPERVISION_R01_CONTRACTS.md) 与追踪表。

> **本地执行状态：DONE**。实现与离线验收完成，本地提交
> `4b406f92f39b0851101da7b318df4ada01e5f814`。仅表示 R01 通过，
> 不宣称整个 v3.3 已按本路线图发布。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

定义所有项目共用的监督事件、安全快照和配置格式。只实现确定性的本地逻辑，不调用模型，也不改变当前 `run/watch` 流程。

**现有基础：** `route_budget.load_ledger()` 已提供 `epoch`、`effective_rounds`、`last_processed_run`；`research_focus.make_focus()` 给出目标锚点；`runner_core.PROTECTED` 已保护项目指令。

**进入条件：** 基准回归测试通过；当前开发分支没有科研代理正在同时写入目标项目。

## 2. 设计裁决与数据流

### 1.1 快照只提取真正需要的证据

从单一项目的真实路径抽取：GOAL、已有 AGENTS、continue、STATE、`CLAIM_GRAPH.json` 的验证状态、最近 3 份已接受报告、路线账本摘要、选中想法、相关定理与近邻论文技术审查。每个源文件记录原相对路径、大小、SHA-256、是否摘要截断及验证等级。单次总文本大小先限定为 256 KiB；超限必须显式报告省略策略和遗漏文件，不能制造完整阅读的假象。

### 1.2 事件状态机

`QUEUED → RUNNING → PROPOSED → APPLIED`；失败分支 `FAILED/REJECTED/CONFLICT`。状态均持久化；任何状态转换必须保留来源触发轮次与目标绑定。事件不能直接要求某条主张从 `CANDIDATE` 变为 `INDEPENDENTLY_REVIEWED`。

### 1.3 来源级别

`USER_FROZEN`、`INDEPENDENTLY_REVIEWED`、`TOOL_CHECKED_AUDIT_PENDING`、`MODEL_CANDIDATE`、`UNVERIFIED`。无对应证明或审核回执时不能自称更高级别。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `supervision/contracts.py`：事件和监督输出的 Python 类型/验证器。
- 新建 `supervision/snapshot.py`：只读信息提取器与摘要 manifest。
- 新建 `config/supervision_defaults.json`：`enabled=false`、`periodic_accepted_rounds=3`、`calls_per_event=1`、`max_snapshot_bytes=262144`、`max_guide_bytes=12288`、`model_tier=critical`。
- 新建 `tests/test_supervision_contract.py` 与模拟项目夹具；必要时在 `docs/` 增加模式说明。

## 4. Codex 必须完成的实现步骤

1. 对照 `configuration.settings_for` 和 `route_budget.load_ledger` 提取**只读**项目绑定；不得在预览过程中触发路由账本创建或写入。
2. 定义 `SupervisionEvent` 校验：稳定项目 ID、真实 run ID、真实 epoch、触发类型、目标哈希及版本、创建时间、输入 manifest。
3. 设计受限 JSON Schema，使用 `additionalProperties=false`；监督建议必须包含引用过的证据路径和判定依据。
4. 实现文件枚举白名单；拒绝符号链接、路径穿越、跨项目文件、过大的文献全文和包含密钥的运行环境文件。
5. 快照按确定顺序排序并哈希；相同输入再次提取，清单摘要相同。
6. 在自定义临时项目上运行读取器，验证不会新增/改变任何文件。

## 5. 输入、输出与接口约定

建议 `supervision/snapshot.py` 提供 `build_snapshot(project, *, last_n=3) -> Snapshot`，`contracts.py` 提供 `validate_event`、`validate_proposal`。名称如调整必须保留等价的稳定测试接口。

```json
{
  "schema_version": 1,
  "event_id": "通过规范序列化计算的真实 SHA-256",
  "project_id": "example-project",
  "trigger": "PERIODIC",
  "trigger_run_id": "已接受的真实 run ID",
  "route_epoch": 1,
  "goal_anchor_id": "冻结主线锚点",
  "status": "QUEUED",
  "source_manifest": [
    {"path": "GOAL.md", "sha256": "真实文件摘要", "trust": "USER_FROZEN"}
  ]
}
```

数据中的说明文字为字段示例，不得伪装成实际生产记录。

## 6. 必做的离线自动测试

- 同一项目同一轮次重复采样，得到相同的规范 manifest 摘要。
- 路径为 `../other-project/GOAL.md`、符号链接或绝对路径时拒绝。
- 缺少 `reports/LATEST.md` 时降级记录缺失，不能伪造最新报告。
- 旧 `CLAIM_GRAPH.json` 不存在时标记空索引、保持状态，不创建虚假主张。
- 文件超限明确显示 `truncated=true` 与省略字节数；GOAL 不能被截断后当作完整目标使用。
- 运行前后比较 fixture 全目录 SHA 集合，确认只读。

## 7. 本轮验收标准

- JSON Schema 和 Python 验证器拒绝非法输入。
- 快照中可逐条追溯所有来源文件哈希和验证级别。
- 不调用 Codex、不更改个人科研项目、不建立新的路线预算。
- 全量既有测试通过。

## 8. 停止、回滚及禁止事项

若冻结目标无法完整读取、项目 ID 与 manifest 不一致或路径验证失败，应直接拒绝构造快照；不得自动回退到未绑定的自由文本监督。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
