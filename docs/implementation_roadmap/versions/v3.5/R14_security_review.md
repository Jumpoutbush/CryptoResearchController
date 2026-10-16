# v3.5 · 开发轮次 R14：密码协议安全模型与模拟归约独立审查

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

建立专门的协议级审查清单和强制人工独立审查接口，核对敌手腐化、泄漏、掉线、中止、模拟器与混合实验，而不宣称系统能自动证明任意密码协议安全性。

**现有基础：** `research/THREAT_MODEL.md`、`PROOF_OBLIGATIONS`、`research_quality` 的安全归约/证据回执、`claim review` 和 G0—G8 已提供理论门禁。

**进入条件：** R13 的验证回执等级及审查边界已经稳定。

## 2. 设计裁决与数据流

### 14.1 协议义务卡

每条安全声明保留 `security_game, parties, corruption_model, leakage_function, setup_assumptions, abort_behavior, simulator_interface, reduction_loss, composition_scope, dependencies`。如果本文原论文没有确切模型或界，必须标 `NEEDS_SOURCE`。

### 14.2 独立对抗性审查

审查代理尝试提出**固定假设下可验证的攻击执行**或识别归约缺失步骤。例如：恶意安全承诺不能自动保证查询结果来自认证数据库；选择性中止泄露需要明确定义；跨轮关联性不能由单轮匿名性直接推出。审查意见必须附上受影响的游戏与证明步骤；模型输出仅为 `REVIEW_FINDING`。

### 14.3 标准框架对比

必须与通用恶意安全多方计算、认证私有信息检索、通用零知识证明组合形成明确的假设/功能/成本差异表；只有有真实新增性质或非平凡复杂度界时，才进入构造推进。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `candidate_search/security_model.py`、`candidate_search/security_review.py`。
- 新建 `tests/test_security_review.py`，恶意腐化、选择性中止、模拟器缺少输入等失败夹具。
- 添加 `templates/project/research/SECURITY_OBLIGATION_TEMPLATE.json`（模板仅供初始化使用）。
- 兼容原 `claim review proof_and_statement`、`claim review novelty` 接口。

## 4. Codex 必须完成的实现步骤

1. 设计字段校验，避免未列举泄漏函数就使用“完全隐私”等含混结论。
2. 每次审查报告绑定固定问题版本、真实候选版本、原论文位置与待审查证明路径。
3. 若模型检测到已知直接组合，标记 `POTENTIALLY_COVERED` 并要求原文定理级比较，不自动把候选设为已覆盖。
4. 通过三类最小反例：腐化阈值超出、选择性拒绝位泄露、模拟器无法重现公开输出。
5. 为安全归约损失的参数、位宽、轮数与失败事件建立显式表格（数学变量如需出现应在正式报告使用块级公式）。
6. 将独立审核证据写入候选审查报告，真正的 claim 状态只经原审核接口变动。

## 5. 输入、输出与接口约定

拟定 `security_review.json` 主要字段：

```json
{
  "candidate_id": "C-0001",
  "problem_binding": "真实固定问题摘要",
  "threat_model_complete": false,
  "attack_or_gap": "可单独核查的模型漏洞或最小反例",
  "affected_obligations": ["O-001"],
  "evidence_refs": [],
  "decision": "NEEDS_REVIEW",
  "claim_status_changed": false
}
```


## 6. 必做的离线自动测试

- 缺失敌手模型的构造无法宣称安全门禁通过。
- 对选择性中止泄露的测试，审查报告指向明确的可见位或交互差异。
- 对不真实的低成本声称，如果缺少成本分解则返回 `UNASSESSED`。
- 审查代理无权更新 `G8`、`accepted_contribution` 或用户固定安全阈值。
- 引用另一论文的定理必须具备版本和定理位置，否则留 `UNVERIFIED`。

## 7. 本轮验收标准

- 可输出协议级、可逐项执行的审查义务卡和攻击检验计划。
- 人工独立审查仍为正式安全主张通过的必要条件。
- 无需为不同密码协议复制独立监督器代码。

## 8. 停止、回滚及禁止事项

如果无法给出完整模拟器接口，不能用经验性实验通过替代证明。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
