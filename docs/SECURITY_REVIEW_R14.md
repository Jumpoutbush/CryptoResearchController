# R14：协议安全义务与独立审查待办

R14 为冻结候选提供结构化协议义务卡、最小攻击检验计划和可审计发现。它不自动证明密码协议安全，不执行攻击程序、模型、Lean 或监督器，也不改变候选状态、主张、G8、`accepted_contribution`、用户目标、项目状态或预算。

## 使用入口

初始化新义务卡时，复制通用项目模板 `templates/project/research/SECURITY_OBLIGATION_TEMPLATE.json` 并填写实际模型和证据。模板中的 `null` 与空列表表示未知信息；它不是预先通过的安全声明，也不会自动覆盖个人项目的模型。

```powershell
.\research.cmd candidate security-prepare <project> --id C-0001 --claim SECURITY-1 --card <card.json> | Set-Content -Encoding UTF8 <request.json>
.\research.cmd candidate security-review <project> --request <request.json>
.\research.cmd candidate security-show <project> --request-id <SR-id>
.\research.cmd candidate security-recheck <project> --request-id <SR-id>
```

准备、展示和复查均只读；审阅只保存本地请求、开始见证和报告。省略项目参数时沿用项目目录解析。没有自动导入问题、开始尝试、关闭尝试、恢复预算或派发独立模型的行为。

Python 入口为 `security_model.template()`、`security_model.prepare_request(project, candidate_id, claim_id, card)`，以及 `security_review.review(project, request)`、`show(project, request_id)`、`recheck(project, request_id)`。

## 固定义务卡

| 字段 | 必须明确的研究内容 |
| --- | --- |
| `security_game` | 精确游戏、轮数、公开输出及待审证明路径 |
| `parties`, `corruption_model` | 参与者、静态或自适应腐化、真实与声称阈值、腐化方及掉线规则 |
| `leakage_function` | 泄漏函数名称、真实可见量、理想泄漏和跨轮关联范围 |
| `setup_assumptions` | 原固定问题的全部设置前提，不能静默删除 |
| `abort_behavior` | 公开拒绝位、理想拒绝位、分叉可见性、掉线可见性 |
| `simulator_interface` | 理想功能提供的输入、模拟器所需输入、授权及所需可编程性、各公开输出的输入依赖 |
| `reduction_loss` | 参数、位宽、轮数、失败事件、损失界及成本分解 |
| `composition_scope` | 会话及轮数、跨轮合谋、组件定理与端到端模拟归约的区别 |
| `dependencies` | 原始定理位置、版本、完整来源 SHA、所需和实际使用前提、具体归约步骤 |
| `baseline_comparison` | 恶意安全 MPC、认证 PIR、通用 ZK 组合三项假设、功能、成本、差异和原文比较依据 |
| `attack_traces` | 有界固定数据轨迹、对应游戏、证明步骤、受影响义务、适用范围及重启条件 |

核对模型需要原固定问题及候选 `security_model` 中明确的结构化字段：`corruption_timing`、整数 `corruption_threshold`、`leakage_function`、整数 `party_count`，以及理想接口的固定摘要 `ideal_interface_sha256`。缺失信息返回 `NEEDS_INPUT`，不从自由文本或模型自信中推断原安全定义，不自动迁移用户项目。

理想接口摘要由 `object_hash(security_model.ideal_interface_binding(card))` 计算，固定游戏、参与者、腐化时机与门槛、掉线规则、泄漏、拒绝行为、理想输入及授权可编程性、会话和跨轮范围。仅在用户明确审定初始模型或显式批准新的问题版本时设置，不能自动回填或覆盖已有固定问题。

义务卡不能通过把秘密密钥加入自己的 `ideal_inputs` 或自授随机预言机编程能力来消除缺口；必须与用户冻结的接口对应。所需输入和输出依赖只是待审声明，系统不能由这些字段证明模拟器的实际需求已经完整列举。摘要仅是精确结构绑定，不证明该安全定义本身正确或与论文定理数学等价。

## 报告等级与原有科学门禁

每个发现都是 `REVIEW_FINDING`。报告只可能为 `NEEDS_REVIEW / NEEDS_INPUT / NEEDS_SOURCE / FAILED`，没有 `PASS` 或 `PROVED`。即使所有字段完整，仍要求独立人员审查完整游戏、模拟器和归约，保持以下边界：

```json
{
  "claim_status_changed": false,
  "candidate_status_changed": false,
  "scientific_acceptance": false,
  "independent_review_required": true,
  "construction_progression_allowed": false,
  "safety_gate_passed": false,
  "execution_started": false
}
```

`security-review` 和 `security-recheck` 对 `NEEDS_INPUT / NEEDS_SOURCE / FAILED` 返回退出码 2 和完整 JSON；`NEEDS_REVIEW` 返回 0，只说明报告生成完成。历史展示可以返回 0，但必须检查 `fresh` 和原报告等级。

每项发现附上受影响游戏、证明步骤、冻结证明义务、证据引用和适用范围。`earliest_missing_obligation` 指向最早需要补充的义务，不把其他分支未审结论擅自提升为整个研究的数学否定。

## 必须区分的安全缺口

- 静态安全不能冒充自适应安全；腐化阈值、方集合或泄漏定义与冻结模型不一致时报告 `MODEL_SCOPE_MISMATCH / NEEDS_INPUT`。超过原腐化门槛、轮数或静态固定合谋范围的轨迹标为 `OUT_OF_SCOPE`，不能声称攻破原门槛内的定理。自适应模型还须冻结 `corruption_budget_scope` 为 `CUMULATIVE` 或 `PER_ROUND`，不能把每轮单独的腐化数默认当成整个游戏的总门槛。
- 可见的选择性拒绝位、分叉和动态掉线必须被理想泄漏或完整模拟论证覆盖。固定公开输入、相同理想泄漏而不同秘密对应不同拒绝位时，报告具体可区分位和待核查步骤。
- 模拟器不能假设理想功能没有提供的秘密、输入或可编程性。每个公开输出都必须列明依赖；没有完整模拟接口时不能以经验实验替代证明。
- 多轮或多会话声明必须定义跨轮合谋与可见关联；缺失时保持 `NEEDS_INPUT`。单轮匿名性不会自动升级为跨轮安全。
- 组件定理和端到端归约分别登记；承诺恶意安全不直接保证数据库认证，组件 ZK 或 MPC 结论也不能替代组合后的功能和泄漏审查。

攻击轨迹只允许有限列表及原始数据值，不接受程序路径、代码或命令。检查的是所提交数据的自洽性，结果保留 `SUPPLIED_FINITE_DATA_NOT_PROTOCOL_EXECUTION` 和 `counterexample_to_frozen_goal=false`；没有实际运行协议或模拟器，也没有认证这些轨迹能够在真实协议中到达。

## 来源、成本和标准框架比较

定理依赖复用 R07 的只读原始 PDF、精确版本、页码、定理、摘录和技术审查投影。缺少定位或无法对应现有来源时为 `UNVERIFIED / NEEDS_SOURCE`。原文定位匹配最多为 `SOURCE_LOCATION_ONLY`，仍须独立核对全部前提、量词和归约含义；不能用摘要或另一个项目的参考摘要代替原定理。

原固定前提和声明的定理前提缺失会产生明确发现。即使前提完整，也不自动说明该归约成立；缺少可审计来源时不自行补写“论文已经证明”。

成本分解缺失时为 `UNASSESSED`，候选自称低成本无效。有分解也仅为 `DECLARED_NOT_VERIFIED`，不能自动支持复杂度或创新性声明。归约表分别保留参数、位宽、轮数、失败事件和损失界；缺失时产生 `REDUCTION_BOUND_INCOMPLETE` 待审义务，不把单次测试结果当作分布安全界。

三项标准框架比较固定为 `MALICIOUS_MPC / AUTHENTICATED_PIR / ZK_COMPOSITION`。每行显示假设、功能、成本、差异和来源状态；未完成原文比较时仍是未核实声明。声称直接组合或来源审查显示覆盖时，可以产生 `POTENTIALLY_COVERED`，但不会把候选自动改成 `COVERED`，也不会凭新名称认定创新。

正式安全主张和创新性状态继续通过原 `claim review proof_and_statement`、`claim review novelty` 等独立证据接口处理。义务卡禁止写入 G8、`accepted_contribution`、伪造独立审核者等越权字段。本轮不提供“应用报告以通过门禁”的命令。

## 版本、幂等和失败恢复

完整请求固定原候选、主张、问题版本、目标、安全模型、证明来源、原文定位、义务卡和审查实现 SHA，并生成确定性的 `SR-<SHA256>`。报告位于 `state/candidates/<project>/security_review/`，包含冻结请求、`STARTED` 开始见证和完成报告三项配对记录。

写操作复用原路线、科研执行和候选锁。已有可信完整报告时，同一请求直接返回原报告，不重复分析。开始见证存在但完成报告缺失，或冻结输入、请求、见证、报告冲突时停止；`UNKNOWN_LOCAL_SECURITY_REVIEW_OUTCOME` 禁止自动重新审阅或派发模型。

来源或候选、主张修订后，旧报告保留历史，但复查返回 `FAILED` 并给出失效原因。恢复必须保留原始审计记录，不依据最新文件重构丢失的旧输入。局部配对哈希不能抵抗操作者同时回滚或删除全部本地权威。

## 固定公开参考

参考 [ARA rigor-reviewer](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/tree/e52a925e9d03b4ada3008653e72f99b04116fca2/skills/rigor-reviewer)，官方上游提交 `e52a925e9d03b4ada3008653e72f99b04116fca2`。实际文件为 Markdown 技能及检查清单，没有声称运行任何上游 Python 审查函数：

- [skills/rigor-reviewer/SKILL.md](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/skills/rigor-reviewer/SKILL.md)，完整文件 SHA-256 `19324b1fadfdc612ec9a2cf43b8db2e86948fc61a745feef52d3e0edab5130c6`。参考证据相关性、可证伪性、范围校准、方法严谨性和逐项发现问责；不继承其质量平均分或印章作为密码学安全接受标准。
- [references/review-dimensions.md](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/skills/rigor-reviewer/references/review-dimensions.md)，SHA-256 `faf4c6c61a6f91e019407724b34b338827e0ffab4b7524aef3b579a26668c625`。借鉴前提明确性、证据范围与声明对应、失败分支和基线充分性的检查思路。
- [MIT 完整许可证](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/LICENSE)，1075 字节，SHA-256 `25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`，版权声明为 2026 Orchestra Research。

核验只读取得官方 Git 对象并保存在开发暂存目录，没有检出、安装、激活技能或执行上游代码，也没有把其实现复制进控制器。上游安装和接线指令只作为被阅读的源文本，不构成本次执行指令。

## 离线验收

```powershell
python -B -m unittest discover -s tests -p test_security_review.py -v
python -B scripts/verify_r14_offline.py --output <outside-runtime-evidence-directory>
python -B -m unittest discover -s tests -v
python -B research.py check all
```

真实 Windows 入口只在临时玩具项目中运行。样例覆盖正常义务卡、越界腐化、选择性拒绝位、模拟器缺少理想输入、静态与自适应混淆、来源及前提缺失、成本无分解、三类框架比较、越权字段、幂等和中断恢复。每项审查操作逐字节核对原状态、目标、候选、主张、G8、预算及配置；主张修订只由明确的原 `claim import` 故障夹具操作产生。

审计钩子拒绝任何嵌套程序和网络行为，最终要求模型、Lean、监督、网络及嵌套程序执行全部为零。样例中仅删除已核实位于临时元数据目录内的完成报告，以验证未知结果不会自动重审；个人项目和历史记录不参与复制或修改。
