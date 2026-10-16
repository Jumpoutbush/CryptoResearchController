# a0e23e3 审查修复跟踪

来源是用户提供的 `CryptoResearchController-review-a0e23e3.md`，原独立静态审查固定
`a0e23e3a401919628d6e0b64462a4770274d6129`。该报告没有执行测试，也没有读取个人项目。
此前仅做 R09/R10 检索防护；2026-10-16 用户继续授权完成其余修复，并确认原 R08
“已记录失效后恢复字节仍须重新审查”政策。本文件记录本地修复，不更改原报告的裁决，
不代替独立复审，不启动 R11 或真实付费运行。

| 问题 | 已实现行为 | 对应离线回归 |
| --- | --- | --- |
| F01 旧监督旁路 | 新旧真实入口复用 R03 门禁，旧 live/apply 额外退役；预留和进程启动前阻断 | test_review_supervision_gate.py：公开 run/watch/configure/force、周期与预算入口、伪造 preflight |
| F02 宿主 Lean 执行 | 自动候选和显式 Lean 命令统一返回隔离未认证，不执行宿主程序；无 elan 仍 UNAVAILABLE | test_review_formal_boundary.py：候选含 IO/进程语句也零进程启动；既有人工审查规则保留 |
| F03 接受与多账本事务 | 持久 COMMIT_DECIDED 为单一决定点，之后不回滚项目；原 run 恢复路线、检查回执和后置步骤 | test_review_acceptance.py、test_review_discovery_settlement.py：日志异常、late-write、真实硬退出、可信 READY 恢复、未知检查停止 |
| F04 路线权威丢失 | 独立登记见证和精确最新 SHA；缺失/空/旧账本停止；同 afterimage 本地恢复不重计 | test_review_route_authority.py：首次历史基线登记、缺账/回退、双文件恢复、过期内存 afterimage、真实硬退出 |
| F05 旧监督未知结果重派 | running 无可信完成回执返回 UNKNOWN，保留旧预留/消费/指南；绝不自动重派 | test_review_supervision_gate.py：重复重入不增加 attempt/seconds、不执行模型 |
| F06 普通依赖 pin 不完整 | canonical 校验完整集合、类型、正整数 revision、SHA；关闭受影响及下游认可，不补最新 pin | test_review_claim_authority.py；R09 复用同一守卫，保留当前及历史的整次拒绝 |
| F07 完整旧回执被覆盖 | 新 review/tool 操作追加完整 payload、来源、reason、operation ID、摘要链和前后 slot 引用；当前指针校验 | 同一主张版本连续两次操作可完整恢复；损坏历史关闭认可；缺失旧历史明确 unavailable |

报告 5.3 的指南竞争风险也已在临时夹具复现：两个 freshness 失败分支现在重读指南，
只有本事务 afterimage 可回滚；第三人工版本保留、事务待审计。新增
test_review_guide_cas.py，真实后端仍阻断。知识维护失败先停止，不排队/消费监督事件。
接受验证到提交期间持有 execution 锁；存在 wrapper 待恢复事务时，直接 core 入口停止。

## R08 持久失效与只读边界

已有 `claim refresh` 持锁记录 canonical 分 scope 的失效锁和事件，传播至 A→B→C。
之后恢复原论文、审查或工具日志字节不恢复旧认可；每个受影响 scope 需要独立新审查，
上游有效后下游才能逐级恢复。新 claim revision 不会篡改旧损坏历史或自动改绑最新依赖。

status/context/explain/derive 仍纯只读。普通 build/cache-only 不反写主张权威；
如果旧正面回执出现尚未记录的新失效，先在缓存/history 写入前停止，提示显式
`research.cmd claim refresh <project>`。空图和未审查候选仍可正常构图。
没有落盘的瞬时只读检查无法记住文件已经恢复前的变化，不能宣称每次查询均永久撤销。
索引和观察快照不能成为第二份科学认可权威。

## 恢复与验收范围

state/research_acceptance/、state/route_registry/ 及 discovery settlement 回执是
控制器恢复权威，备份时须与原账本一同保存。原历史和消费不重计、不清零。
只有可信完成回执可自动恢复纯本地结算；未知执行、检查中断无回执、来源/人工内容
冲突时停止审计，不自动重试、覆盖或释放预留。显式预算恢复只接受最新见证 SHA。
本地 SHA 链不能抵御宿主同时整体改写/删除所有权威，没有外部不可回滚存证的承诺。

R09 默认关闭，完整原提示保留；32KiB 限额作用于新增证据数据段（含诊断），不裁剪原提示。
R10 默认关闭，双向授权，只读显式公开材料，所有结果固定 REFERENCE_ONLY/positive_basis=false。
私有 PDF/claim 的当前状态不跨项目读取，变化需要源方复审并重发/撤销，不能声称自动
发现私有上游变化。不同安全模型不自动等价，不提升任何项目证明或新颖性等级；摘要脱敏
由操作员审核，控制器不声称自动脱敏。

本地最终专项83/83；全套681项：680通过、1项既有POSIX跳过，退出0（981.431秒）。
R09原生入口41步、R10原生入口30步、预算原生入口8步通过；完整证据位于会话outputs/review-fixes/。
实际个人项目未启用或迁移，GOAL、STATE、预算和历史未修改；没有推送。
