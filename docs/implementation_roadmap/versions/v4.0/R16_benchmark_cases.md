# v4.0 · 开发轮次 R16：密码学科研基准题库与隐藏标准答案

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

先建立一个覆盖查新、反例、安全漏洞、数学障碍、研究偏移、状态恢复的可独立评分任务集，避免“代理自评自己进步”。

**现有基础：** 目前控制器已有 research benchmark 协议与部分离线检查（见 `docs/MATHEMATICAL_DISCOVERY_V3.2.md`）；扩展时先核对现有 `tests/research_benchmark`，不要复制另一份重复基准。

**进入条件：** v3.5 发布验收完成；原始的科研执行、候选和监督都能在模拟环境重放。

## 2. 设计裁决与数据流

### 16.1 30 题起始建议

六类、每类 5 题，逐步补齐**独立金标准**：已知论文定理覆盖、隐藏算术或协议反例、模拟安全漏洞、未闭合数学障碍、跨轮目标跑偏、历史状态恢复。初期应先纳入已有答案的可验证题；真正开放难题只能评分界定能力，不能以“没有解决”作为自动错误。

### 16.2 双层题目文件

代理可见 `task.json`：冻结目标、允许输入、预算、可用工具和预期产物。评价器私有 `oracle.json`：真实答案、攻击见证、判定规则、专家审核与来源；私有目录在代理工作区之外。测试题中的学术引用必须有真实来源或明确标注为合成教学夹具。

## 3. 修改范围（新增文件均为规划路径）

- 新建/扩展 `evaluation/benchmarks/manifest.json`、`evaluation/benchmarks/public/`。
- 隐藏金标准建议存 `state/evaluation/private_oracles/`，不包含在 Codex 监督快照中。
- 新建 `evaluation/validate_cases.py`，与现有 `tests/research_benchmark` 对接。
- 添加 `tests/test_benchmark_dataset.py` 和各类至少一份端到端有效示例。

## 4. Codex 必须完成的实现步骤

1. 先审计当前 benchmark 目录和验证工具，列明可复用、不可重复的样本。
2. 为每题固定 `case_id/version/type/input_sha256/oracle_sha256/evaluator_version`。
3. 设定强制来源：真实既知结果要精确引文；合成反例必须给出可执行谓词与见证；开放问题须标记 `OPEN`。
4. 将 agent-visible 与 oracle-visible 数据分离在权限和路径层，测试代理拿不到金标准文件。必须有真实的操作系统权限隔离/独立沙盒验证；只靠提示词或更换工作目录不能保证隔离。隔离未经验证时标为 `NOT_ISOLATED`，不得计入基准。必须有真实的操作系统权限隔离/独立沙盒验证；只靠提示词或更换工作目录不能保证隔离。隔离未经验证时标为 `NOT_ISOLATED`，不得计入基准。
5. 为论文覆盖、新颖性和安全错误分别设计客观证据检查，而非仅用模型打分。
6. 题目变更需要新版本及审查记录；不能静默改写历史金标准以提高得分。

## 5. 输入、输出与接口约定

参考 schema：

```json
{
  "case_id": "BENCH-LIT-001",
  "version": 1,
  "category": "THEOREM_COVERAGE",
  "public_input_path": "evaluation/benchmarks/public/BENCH-LIT-001/task.json",
  "oracle_path": "state/evaluation/private_oracles/BENCH-LIT-001/oracle.json",
  "source_review_status": "CURATED_OR_SYNTHETIC_EXPLICIT",
  "scoring_rule_version": 1
}
```

真实答案和来源哈希不能使用上述示意值替代。


## 6. 必做的离线自动测试

- 金标准字段不出现在给科研代理的输入快照与提示词中。
- 每类至少一个正例、一个假阳性/假阴性防范测试。
- 已知定理覆盖任务必须具备原文定位或事先经审查的书面推导。
- 开放问题禁止按“是否找出新证明”自动评分。
- 题库修改后能查询完整版本差异与责任人。

## 7. 本轮验收标准

- 首先完成 6 类各至少 1 个真实可评分夹具，再扩展到目标 30 题。
- 至少一项评价器能凭明确反例见证输出确定性判断。
- 隐藏答案隔离测试通过。

## 8. 停止、回滚及禁止事项

若金标准不能独立验证，该题只能设为 `PENDING_CURATION`，不能进入正式质量统计。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
