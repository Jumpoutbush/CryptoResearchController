# R15：候选分支收束、证据归档与显式切换

R15 在 R11—R14 的候选、计划、精确验证和安全审查之上增加分支裁决。裁决适用于精确候选版本和所声明的局部义务；否决一个构造不会自动否决父问题、整个协议族或冻结目标。模型建议、旧手工状态标签和有限范围内没有发现反例，都不能代替独立证据。

## 证据与结论的边界

`REFUTED` 必须同时具有当前 R13 精确反例证书和独立的语义对应记录。对应记录说明该具体候选为何必需被反例否定的命题、受影响的原证明义务以及结论范围。它通过既有 `claim review --kind statement` 接口，由与 proposer 不同的操作者逐字节绑定；单独放置一个写着“已审查”的文件不构成独立审查。该记录审查反例对候选的含义，不给已被反例否定的主张登记正面证明。

`COVERED` 需要原始论文、具体定理位置、实际前提和经过独立核对的包含关系。只有题名、摘要、相似文本或来源缺失时保持条件性。`RETIRED` 是操作员停止投入的决定，不宣称数学错误或全族不可能。`CONDITIONAL` 保存待补材料与范围限制，不升级科学认可。

归档保留候选版本、原目标锚点、问题版本和 SHA、假设、失败原因、反例或原文绑定、重启条件、未闭合义务及原路线已用轮数。可复用引理仅登记 `DIRECT_DEPENDENCY` 或 `SUPPORT` 的引用；归档不会给未审引理授予正确性，也不删除历史反例。

## 切换与预算

关闭旧尝试与启动新尝试是两个明确操作。关闭阶段使用原固定问题尝试的检查和账本；启动阶段再次核对目标、问题版本、候选版本和独立门禁，然后使用原 `attempt start`。R15 不自动进入下一阶段、不调用 `run`、不自动导入新问题，也不更改 `STATE.selected_idea` 来切换目标。

切换保留原 route epoch、累计有效轮数、延期次数及原输入哈希；候选没有第二份科研额度。STOP、路线待复评、未完成验收、未知外部结果、未核验或过期检查点会阻断切换。监督推荐与可执行切换请求分别保存；监督报告不会授予越过这些门禁的权限。

关闭失败保留旧活动尝试，不会启动 B。恢复只能重放已经冻结的同一局部事务后像；不能因结果未知而重跑研究、重新结算或自动进入下一阶段。历史丢失、见证损坏、冻结输入变化时停止并要求审计。已经否决的方向若要重启，必须登记新的候选版本，实际改变构造假设或允许修改的前提，并提交新的独立范围审查，仍继承原目标的消耗历史。仅重写标题、证伪说明或成本估计不能重启，冻结目标和问题前提的保护仍由原契约决定。

## 操作入口

先通过 R13 的 `verify-prepare / verify / verification-recheck` 保存精确反例，再生成独立范围审查模板：

```powershell
.\research.cmd candidate resolution-review-template <project> --id C-A --claim CLAIM-A --status REFUTED --scope "只否定这个候选版本所必需的精确等式" --verification-request-id <V-id>
.\research.cmd claim review <project> --id CLAIM-A --kind statement --evidence research/branch_reviews/A.json --reviewer <independent-operator> --reason "核对原命题与候选必要性的精确对应"
.\research.cmd candidate resolve-prepare <project> --id C-A --claim CLAIM-A --card <resolution-card.json>
.\research.cmd candidate resolve <project> --request <frozen-resolution.json>
.\research.cmd candidate compare <project> --id C-A --id C-B
.\research.cmd candidate history <project> --id C-A
```

模板是待人工填写的结构，不是自动通过的审查。最小裁决卡包含 `schema_version: 1`、`requested_status`、`scope`、`restart_conditions`、`reason`、`verification_request_id`、`semantic_review_file`、`source_dependencies` 和 `reusable_lemmas`；无对应材料的字段使用 `null` 或空列表，不捏造证据。`retire --id --expected-revision --reason --scope --restart-conditions` 用于明确停止投入。

准备与应用分别调用，完整 JSON 应写到文件后传入下一命令。关闭不会连带启动：

```powershell
.\research.cmd candidate switch-prepare <project> --id C-A --expected-revision 1 --phase CLOSE --from-attempt-id <attempt-A> --reason "明确关闭已审查的局部分支"
.\research.cmd candidate switch-apply <project> --request <frozen-close.json>
.\research.cmd candidate switch-prepare <project> --id C-B --expected-revision 1 --phase START --reason "明确启动原目标下的另一构造"
.\research.cmd candidate switch-apply <project> --request <frozen-start.json>
.\research.cmd candidate switch-status <project> --request-id <switch-id>
.\research.cmd candidate switch-recover <project> --request-id <switch-id>
```

`switch-status` 只读展示本地阶段；`switch-recover` 只能完成同一冻结事务允许的局部恢复。开始 B 后仍须由操作员决定是否通过原研究入口执行，R15 命令不会派发模型。

重新考虑已经否决的同一分支时，先显式 `candidate revise`，再用 `candidate restart-review-template <project> --id <candidate> --claim <claim>` 生成待审模板。模板钉住旧裁决、旧版本和新版本的精确 SHA、构造假设及原前提的前后值、当前主张版本；独立操作者填写 `reviewer` 和具体的 `why_old_evidence_not_applicable`，解释为何旧反例不否定新的局部构造，再通过原 `claim review --kind statement` 登记该文件。重启审查从 canonical statement receipt 的精确证据中读取，避免把审查文件先塞进候选自身证据造成版本与哈希的循环依赖。该范围审查允许重新考虑方向，不授予证明、新颖性或预算。

项目运行记录位于控制器的 `state/candidates/<project>/`：`resolutions/BR-<sha>.json` 保存裁决输入与结果；`switches/SW-<sha>.json` 保存某一次 CLOSE 或 START 的冻结原控制器后像及阶段；`history.json` 和 `history.registry.json` 保存追加历史与独立高水位见证。在 Codex 的文件视图中可直接对照这些 JSON、原 `state/discovery/<project>.json`、原 `state/routes/<project>.json` 和 `candidate history` 输出。知识投影把已归档分支呈现为带精确来源的节点，不把它升级为全局不可能性定理。

每项裁决和切换还保存 `operation_witnesses/<BR-or-SW-id>.json`，独立绑定请求 SHA、操作类型和 intent 文件位置。intent 与见证就绪后才能修改候选或原尝试；任一侧丢失、未知阶段或输入不符都停止，不能把缺失文件当成从未派发。待完成的切换也会阻断原 `run / attempt start` 等执行入口；只能审计并显式恢复原操作，不能通过绕回旧入口另开尝试。

知识归档始终是非正面依据：`positive_basis=false`、`scientific_acceptance=false`、`family_refuted=false`。原 R13 机器回执或独立起始见证丢失、被改，原文和范围审查证据变化，或 canonical 主张审查发生持久撤销，均使对应归档显示为待重新核验。恢复原文件不能绕过原审查的持久撤销锁；须经原主张流程重新审查。历史裁决及反例保留用于追溯，不把旧标签当作当前仍有效的科学结论。

## OpenSource 参考与适配

仅参考失败节点保留、父子来源和决策理由的组织方式。没有复制、安装或运行任何上游代码。参考核验在离线验收之外完成，使用 GitHub 官方只读 Git 对象；完整回执在 `outputs/R15/opensource-reference.json`。

- [AIDE `aide/journal.py`](https://github.com/WecoAI/aideml/blob/1d8ec4026c67729443294c8b5c0907242d0de38c/aide/journal.py)，固定提交 `1d8ec4026c67729443294c8b5c0907242d0de38c`，文件 SHA-256 `6539cac937ef65af1ee6f05c6434ec66c2d3c268460c74f13eba4fa7bf9b6020`。实际符号为 `Node.parent/children`、`Node.__post_init__`、`Node.stage_name`、`Node.debug_depth`、`Journal.append` 与 good/buggy 节点访问。其可执行程序、指标和 `is_buggy` 不作为密码学反驳标准。[MIT 完整许可证](https://github.com/WecoAI/aideml/blob/1d8ec4026c67729443294c8b5c0907242d0de38c/LICENSE) SHA-256 `723b16d1701dfb2d280d229ff84f3056df65b6b00ad8419ec6cb7da2fdd8f616`。本次亦核对官方当前 HEAD `ad73d227af481bea3de06f884f41b2993dd6453a`，上述源码和许可证与固定版本逐字节相同。
- ARA 固定提交 `e52a925e9d03b4ada3008653e72f99b04116fca2`。实际参考对象是 YAML 文档：[最小探索树](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/examples/minimal-artifact/trace/exploration_tree.yaml)，SHA-256 `3b24bbd0a9aa1593c9fd200326018029eb0800d8575f57189b75b51d97e905c5`；[ResNet 探索树](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/examples/resnet-ara-example/trace/exploration_tree.yaml)，SHA-256 `679a94f886b042ffdb20928611f97a8fe3b49c2358113b7e60305e374df576ff`。参考 `dead_end`、`why_failed`、`source_refs`、决策及替代方向字段；它们不构成独立证明。[MIT 完整许可证](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/LICENSE) SHA-256 `25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`。

本地适配采用原主张图的独立审查、R13 精确证书、冻结来源、原科研锁及恢复见证，不继承上游程序指标、可变树节点或示例中的“explicit”标签作为权威。

## 离线验证

```powershell
python -B -m unittest discover -s tests -p test_candidate_end_to_end.py -v
python -B -m unittest discover -s tests -p test_candidate_projection.py -v
python -B scripts/verify_r15_offline.py --output <outside-runtime-evidence-directory>
python -B -m unittest discover -s tests -v
python -B research.py check all
```

真实 Windows 入口验收仅复制公开控制器文件到临时样例，不复制个人项目。整数反例允许执行固定 R13 数据验证 worker；审计只接受其精确 argv、固定源码 SHA、空工作目录和最小环境，其余嵌套进程、网络、模型、监督和 Lean 均被拒绝。worker 是受信固定本地代码，不宣称经过操作系统沙箱认证。

玩具材料的本地查新预览保持 `NOVELTY_PENDING`，不伪造创新性审查。原 `runner.record_round` 与 `route_budget.save_ledger` 产生程序性 `NO_PROGRESS` 计数 0→1→2，记录明确不代表科学进展；临时支持工作阈值设为 4，使两次程序性验收不提前触发复评，个人配置不变。B 使用的分配律引理通过原独立 proof/statement 审查，未登记新颖性或已验收贡献。原问题导入、主张独立范围审查及明确 close/start 只能修改相应临时样例权威；裁决本身不改原主张、G8、已验收成果、GOAL 或路线预算。个人项目和既有历史保持不变。
