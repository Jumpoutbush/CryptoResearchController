# v3.3：独立科研监督与安全指南修订

监督由统一控制器调度，各项目使用同一套实现。科研代理负责研究和提交证据；独立监督进程读取当前项目证据、冻结合同及控制器源码，提出方法修正和下一轮任务。控制器先保存结构化裁决、证据映射、指南补丁与版本化短期指南，验证通过后才应用 `AGENTS.md` 和 `prompts/continue.md` 中的监督管理区，并登记审计记录。下一轮同时核验并加载已应用版本的 `guidance.md`。

监督不能修改 `GOAL.md`、安全模型、证明义务、研究结论、`research/STATE.json` 或路线预算。`PAUSE` 和 `RECOMMEND_STOP` 会阻止控制器启动下一科研轮，但不会自行将科研状态改成 STOP、切换路线或重置预算。现有控制器仍负责路线复评与状态管理。自动校验能够确认修改范围、冻结文件摘要、主线锚点、已存在的目标义务、证据文件及版本一致性；数学正确性、新颖性和自然语言建议是否真正推进目标，仍需审查原始论证。

## 开启与使用

在 PowerShell 中进入实际控制器目录：

```powershell
Set-Location D:\CryptoResearchController
python research.py supervision status all
python research.py supervision configure all --enabled on
```

开启只登记监督起点、冻结目标摘要和独立监督配置，不调用模型，不修改现有项目指南或科研状态。登记前已经完成的历史轮次作为基线保留，不会补算成新监督触发。对单个项目配置时，将 `all` 换成项目 ID。

原有入口保持不变：

```powershell
.\research.cmd watch secagg-research --max-rounds 8
.\research.cmd watch falcon-dkg --max-rounds 8
.\research.cmd watch prc-malicious-integrity --max-rounds 8
```

默认每 3 轮控制器计入科研预算的已验收工作触发一次监督；失败、未验收、路线复评以及预览不计入这一计数。路线预算耗尽后的复评节点也触发监督。相同证据快照的触发具有幂等记录；重启 `watch` 不会因同一个已完成触发而重复消耗监督预算。下一轮提示词重新读取最新指南及监督上下文。

v3.4 在已验收科研轮完成尝试登记后，先持锁刷新长期知识索引，再判断监督触发。科研提示词和监督请求都包含有长度上限的只读知识上下文；监督仍须核验原始证据。索引失败时保留该轮已验收结果和预算，在运行状态 `knowledge_index` 记录原因，返回 `KNOWLEDGE_INDEX_FAILED` 并停止本次后续监督。来源、历史追溯和恢复边界见 [长期科研知识图谱](RESEARCH_KNOWLEDGE_V3.4.md)。

监督仅在真实 `run`/`watch` 或明确执行监督时调用独立 `codex exec`；查看状态和预览不会调用模型。机器需要有可用的 Codex 命令行和登录环境，桌面窗口无需一直打开。项目原有停止请求、人工审查门禁和研究预算仍然有效。

以下命令手动查看、触发及关闭监督：

```powershell
python research.py supervision run secagg-research --dry-run
python research.py supervision history all
python research.py supervision show secagg-research
python research.py supervision show secagg-research --id REVIEW_ID
python research.py supervision run secagg-research --force
python research.py supervision configure secagg-research --enabled off
```

`history` 只读列出成功、失败及回滚记录、执行次数与时长；`show` 默认查看当前有效版本，没有有效版本时查看最近记录，也可以用 `--id` 指定历史审查。输出包含结构化裁决、证据映射和本地审计文件路径，便于在桌面版直接打开。没有历史时返回空列表或 `no_reviews`，不会创建运行目录。

`--force` 表示明确审查当前快照，仍然遵守冻结合同、独立预算和幂等约束。`run`、`show` 和 `rollback` 必须指定一个项目，`all` 只支持 `status`、`history` 和 `configure`。

## 结构化裁决与提案校验

v3.3 新监督执行请求 schema 2；已有 schema 1 审计与离线接口保持兼容。裁决分为 `CONTINUE`、`REFOCUS`、`PAUSE`、`RECOMMEND_STOP`，并保留以下可核对字段：

| 字段 | 控制器校验 |
| --- | --- |
| `core_goal_changed` | 必须为 `false`，目标由用户冻结 |
| `main_obligation` | 绑定本轮输入中的现有目标或证明义务 |
| `evidence_verified` | 必须为 `false`，调度审查不能升级证明等级 |
| `reason` | 对照已保存的证据说明路线判断 |
| `next_action` | 必须与提案中的下一任务目标一致 |
| `requires_human_approval` | 为 `true` 时必须暂停或建议终止，阻止下一轮自动执行 |

控制器核对来源文件摘要、冻结目标、主线绑定、提案输入版本和允许的修改范围。证据引用有效不等于所述定理正确；文件摘要与接口校验也不能识别所有自然语言误判。短期任务、步骤、证伪要求和预期证据保存到版本化 `guidance.md`。只有确需长期方法调整时才填写 `agents_guidance`，同时给出 `method_change_reason`；普通短期调度将两个字段均留空，原 `AGENTS.md` 字节保持不变。

## 独立监督预算与模型

全局默认值位于 `config/supervision_policy.json`，默认关闭。项目覆盖写入 `config/projects/<项目 ID>.json` 的 `supervision_policy` 字段，其他模型配置和路线预算保持原样。

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `enabled` | `false` | 是否启用监督 |
| `interval` | `3` | 两次周期监督之间的已验收科研轮数 |
| `max_reviews` | `20` | 独立监督调用次数上限，失败尝试也计入 |
| `max_attempts_per_review` | `2` | 同一个审查触发的尝试上限 |
| `max_seconds` | `600` | 单次监督执行时限（秒） |
| `max_total_seconds` | `12000` | 项目监督累计执行时长上限（秒） |
| `model` / `effort` | 空字符串 | 沿用该项目 `critical` 模型和推理强度 |

例如：

```powershell
python research.py supervision configure secagg-research --interval 3 --max-reviews 20 --max-seconds 600 --max-total-seconds 12000
python research.py supervision configure secagg-research --model your-review-model --effort high
python research.py supervision configure secagg-research --model inherit --effort inherit
```

监督账本位于 `state/supervision/<项目 ID>/ledger.json`。调整配置不会清零已经使用的次数、时长或科研路线预算。关闭后再开启也会保留监督历史。监督预算不足或审查失败时，控制器保留原指南并停止继续研究，修复原因后再显式恢复执行。

## 在 Codex 桌面版查看审查与指南

打开本地 `D:\CryptoResearchController`。每次监督的项目内审计位于：

```text
projects/<项目>/research/SUPERVISION_REPORT.md
projects/<项目>/research/supervision/<review_id>/
    REPORT.md
    proposal.json
    verdict.json
    evidence_map.json
    guide.patch
    guidance.md
    manifest.json
    changes.diff
    before.json
    after.json
```

`SUPERVISION_REPORT.md` 是最近一次审查报告；各 `review_id` 目录保留历史报告、提案、实际差异和前后版本。`verdict.json` 记录调度裁决，`evidence_map.json` 保留引用依据，`guide.patch` 记录允许管理区的变更，`manifest.json` 绑定输入与文件版本，`guidance.md` 保存下一轮实际读取的任务。`before.json` / `after.json` 保存文件的字节内容映射；`changes.diff` 继续保留作为兼容的实际差异视图。

模型输入、schema、输出和进程日志保存在 `state/supervision/<项目 ID>/reviews/<review_id>/attempt-N/`，用于诊断无效提案、超时和失败隔离。待应用产物先保存到该目录下的 `proposal/`；校验失败或写入失败时仍能审查具体建议，项目原指南保持原样或按事务恢复。输入也记录监督读取的控制器源码与方法文件摘要。日志可能包含本地研究材料，遵循仓库原有本地文件管理规则。

此仓库将 `/projects/`、`/config/projects/`、`/state/` 和 `/logs/` 设为 Git 忽略目录。因此，根仓库的 Git 差异视图一般只显示控制器代码和模板变更；查看个人项目指南变化时，先运行 `supervision history` / `show` 获取路径，再在桌面版打开对应 `guide.patch`、`changes.diff`、`verdict.json` 和指南文件。无需为了查看审计而将私有科研材料加入 Git。

## 修改边界与回滚

控制器使用以下唯一标记定位管理区：

```markdown
<!-- SUPERVISION:BEGIN -->
控制器校验后应用的长期方法或下一轮任务。
<!-- SUPERVISION:END -->
```

已有项目无需迁移：首次成功应用时，控制器在原有文件后追加管理区，保留原始指南全文。新项目从 `templates/project` 自动继承管理区及同一监督接口；创建后使用 `supervision configure <项目> --enabled on` 开启。

监督进程以控制器根目录为工作区，在只读 Codex 会话中提出结构化提案，可读取控制器代码与当前项目证据；它不能直接写项目，实际指南由控制器持锁更新。冻结目标、证据或指南版本在审查期间变化时，提案不能直接应用。文件应用失败时恢复原字节，审查记录和失败原因保留；研究状态与路线预算不由监督修改。重复或损坏的管理区也会被拒绝。

查看 `supervision status <项目>` 获取最近记录及 `review_id`，然后回滚最新已应用版本：

```powershell
python research.py supervision rollback secagg-research --id REVIEW_ID
```

回滚保留审计历史，不删除研究证据、不恢复旧科研状态，也不返还已消耗的预算。连续回滚会恢复上一版本的监督上下文。若指南已经被人工修改，或归档的原版本遭到篡改，版本校验会阻止覆盖，需要先查看差异并处理冲突。关闭监督也必须先恢复未完成的写入事务，不能让下一轮读取半应用的指南。

实现使用 `codex exec --sandbox read-only`、结构化输出 schema 和独立临时会话；具体 CLI 选项参见 [OpenAI 官方非交互执行文档](https://developers.openai.com/codex/noninteractive/) 和 [CLI 参考](https://developers.openai.com/codex/cli/reference/)。

## 本地验证

```powershell
python -m unittest discover -s tests -v
python research.py check all
python research.py supervision status all
python -m unittest discover -s tests -p test_supervision_quality.py -v
```

这些命令不运行付费科研轮次。回归测试使用临时项目和模拟监督输出，覆盖周期触发、预算节点、幂等、范围限制、失败恢复、预算记账、配置、锁、模板及回滚。

已知偏移和正常对照保存于 `tests/research_benchmark/supervision_cases.json`。生产模块 `supervision_quality.py` 对照已验收收据提取连续辅助研究、没有主线推进和内容重复等调度信号，独立监督可据此优先检查可疑分支。它不认证自然语言相关性或数学结论，固定样本测试也不等于真实模型质量评价。
