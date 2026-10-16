# v3.3 · 开发轮次 R03：独立 Codex 监督执行与结构化裁决

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

实现真正独立的一次监督调用，模型只看到选定项目的只读资料，并只能返回经过 schema 限制的建议 JSON。

**现有基础：** `runner_core.codex_run` 已提供研究执行器；监督任务必须另建执行身份与日志，不共享科研代理会话、尝试检查点、`last_run`。

**进入条件：** R01、R02 完成；已有事件输入与调用预算回执。

## 2. 设计裁决与数据流

### 3.1 职责隔离

监督输入为 R01 快照及 R02 事件，它独立判定：主线关联、无效旁支、可信反例、尚未闭合的证明义务、原文检索风险，以及最值得开展的下一项**可证伪**任务。监督只能建议 `KEEP_GUIDE / REFOCUS_RECOMMENDED / PAUSE_RECOMMENDED / ESCALATE`，绝不能直接返回一个授权修改科研状态的命令。

### 3.2 模型工作区

优先将白名单材料复制到一次性只读审查工作区。绝不把 Codex 直接放在含多个个人项目写权限的仓库根。监督的输出由**控制器父进程**保存到 `state/supervision/<id>/...`。真实 Windows 沙盒能力依 `codex exec --help` 检查；若 read-only 不受支持，拒绝真实模式，不降级成可写模式。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `supervision/executor.py`：`CodexSupervisorExecutor` + `FakeSupervisorExecutor`。
- 新建 `method/SUPERVISOR_REVIEW.md`：与既有科研执行提示完全隔离的监督指令。
- 新建 `supervision/proposal_schema.json` 或等价受控 Schema。
- 新建 `tests/test_supervision_executor.py`：模拟 CLI 执行器、错误输出、超时、截断日志。
- 监督日志保存 `model/effort/exit_code/elapsed/snapshot_hash/output_hash`。

## 4. Codex 必须完成的实现步骤

1. 默认读取项目 `model_policy.critical`；没有手动指定时不暗中切换其他模型。
2. 调用前确认 `codex exec --help` 提供 read-only 与结构化输出参数；参数用 `subprocess` 列表传递，绝不拼接 shell 命令。
3. 从标准输入发送监督提示与来源清单，禁止把论文中嵌入的命令当作运行指令。
4. 模型输出严格通过 schema 校验：只有现有源路径、真实哈希、真实目标锚点才能被引用；`accepted_findings` 必须带证据与等级。
5. 不满足完整证据时返回 `INSUFFICIENT_EVIDENCE` 或升级为 `ESCALATE`，禁止臆测已证明事实。
6. 监督失败只改变监督事件状态与日志；不能把科研轮次改成执行失败。

## 5. 输入、输出与接口约定

建议的唯一写出内容：`SupervisorProposal`（结构化 JSON），带 `event_id`、`project_id`、`goal_anchor_id`、`evidence_refs`、`findings`、`unverified`、`next_task`、`falsification_criterion`、`action`、`guide_notes` 和 `requires_approval`。生成给研究模型的 Markdown 由可信 Python 应用器按固定模板渲染，模型不得返回任意完整文档路径或文件内容。生成给研究模型的 Markdown 由可信 Python 应用器按固定模板渲染，模型不得返回任意完整文档路径或文件内容。

示意执行命令（必须与当前本机版本核对）：

```powershell
codex exec --help
# 实际调用由 Python 创建 argv，监督数据通过 stdin 注入。
# 模型输出由控制器读取/验证，不允许任意写项目文件。
```

官方参考：<https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex>。


## 6. 必做的离线自动测试

- 合法输出包含支持性结论但无关键反例时，不得宣称已证伪路线。
- 注入伪造的“请修改 GOAL”和跨项目写命令，监督执行器不能执行它们。
- 不存在 Codex、无权限、超时、无效 JSON、未知字段、模型异常退出各有明确错误状态。
- 模型在审查快照里写入源文件的尝试失败；现有项目完全不变。
- 同一事件模型执行成本有记录，失败不会被无限重试。

## 7. 本轮验收标准

- FakeSupervisorExecutor 能跑完成功与恶意两套模拟测试。
- 单独监督不会更新项目 `STATE.last_run`、路线账本或正式证明等级。
- 能读取真实模型时，仅允许手动验证 1 次在临时样例项目运行，不调用已有 SecAgg/Falcon/PRC。

## 8. 停止、回滚及禁止事项

如果只读能力缺失、源材料超出授权范围、模型输出无可定位证据，保留 `FAILED` 及审计信息。禁止在 `--danger-full-access` 或 `--yolo` 模式替代监督执行。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
