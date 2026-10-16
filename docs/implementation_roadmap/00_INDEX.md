# CryptoResearchController v3.3—v4.0 分轮开发实施手册

**目标：**在现有控制器上增量建立独立科研监督、结构化记忆、候选搜索与独立验证、科研评价和安全调度，避免逐项目特化。

**当前状态：**本文档包是开发规格，不包含对用户本机仓库的直接修改，不表示已执行任何研究轮次或产生新的密码学定理。

**基准提交：**`67618536ecd172b2fad24843daf291489e226c2e`（2026-10-15）。本地较新的提交优先；先检查 `git status` 与源码实际接口。

## 一、升级路线

| 版本 | 开发轮次 | 核心产物 | 最小发布判据 |
| --- | --- | --- | --- |
| v3.3 | R01—R05 | 独立监督事件、只读监督代理、可审计指南和恢复 | 模拟三轮已接受研究后仅触发一次监督，下一轮加载指南；故障零污染 |
| v3.4 | R06—R10 | 基于现有 `claim_graph` 的统一证据索引 | 能根据真实证据链说明一条主张的支持、依赖、失效与出处 |
| v3.5 | R11—R15 | 有界候选研究树、验证适配器、分支裁决 | 多候选无预算逃逸；失败分支可复查、可复现、可恢复 |
| v4.0 | R16—R20 | 密码学科研基准、离线回放、质量评价、影子策略 | 基于隐藏标准答案测量真实能力增益，策略回退可复现 |

## 二、每轮阅读顺序

先读 [01 基线核查](01_BASELINE_AUDIT.md)、[02 全局契约](02_ARCHITECTURE_AND_CONTRACTS.md)、[03 不变量与权限](03_INVARIANTS_AND_PERMISSIONS.md)，然后只读当前轮次文档。完成后更新 [06 实施追踪表](06_PROGRESS_TRACKER.md)。

### v3.3 · 监督与指南

- [R01 固定监督契约与只读快照](versions/v3.3/R01_supervision_contract.md)
- [R02 触发器与独立预算账本](versions/v3.3/R02_event_trigger.md)
- [R03 只读 Codex 监督与结构化裁决](versions/v3.3/R03_readonly_executor.md)
- [R04 安全指南修订与真实提示注入](versions/v3.3/R04_guide_apply.md)
- [R05 端到端接入、迁移和恢复](versions/v3.3/R05_integration_recovery.md)

### v3.4 · 科研知识图谱

- [R06 证据图只读投影与类型系统](versions/v3.4/R06_knowledge_projection.md)
- [R07 原始论文与定理级溯源](versions/v3.4/R07_primary_source_provenance.md)
- [R08 事件溯源与失效传播](versions/v3.4/R08_invalidation_lineage.md)
- [R09 分级证据检索与上下文构建](versions/v3.4/R09_evidence_retrieval.md)
- [R10 跨项目只读复用与闭环测试](versions/v3.4/R10_cross_project_memory.md)

### v3.5 · 候选研究树

- [R11 候选问题树与冻结约束](versions/v3.5/R11_candidate_model.md)
- [R12 有界搜索调度与预算隔离](versions/v3.5/R12_branch_scheduling.md)
- [R13 数学核验适配器](versions/v3.5/R13_verifier_adapters.md)
- [R14 密码协议安全审查](versions/v3.5/R14_security_review.md)
- [R15 候选裁决、收束与故障恢复](versions/v3.5/R15_branch_resolution.md)

### v4.0 · 科研评价

- [R16 基准题库与隐藏标准答案](versions/v4.0/R16_benchmark_cases.md)
- [R17 决定性离线回放](versions/v4.0/R17_replay_harness.md)
- [R18 指标、消融与证据报告](versions/v4.0/R18_metrics_ablation.md)
- [R19 影子自适应调度](versions/v4.0/R19_shadow_adaptation.md)
- [R20 观测、发布与回滚演练](versions/v4.0/R20_release_operations.md)

## 三、如何在 Codex 桌面版执行

1. 打开本地 `D:\CryptoResearchController`；首轮核对当前分支、源码及个人项目是否有未提交修改。
2. 把本包放在仓库 `docs/implementation_roadmap/`；从 [05 开发执行手册](05_CODEX_EXECUTION.md) 复制启动指令。
3. 一次只交给 Codex **一份 Rxx 文档**；不允许“把 R01—R20 全做完”的大跨度代理调用。
4. 每轮先写本轮失败回归测试，再修改最少的控制器源文件；用户科研项目保持只读。
5. 本轮通过测试后才允许执行下轮；各版本的发布门禁不能被代理自行改成通过。

## 四、与现有旧版监督任务文档的差异

先前的监督任务曾提出直接修改 `AGENTS.md` 和 `prompts/continue.md` 的受控区。这个包建议**优先引入单独的生成文件** `projects/<id>/supervision/ACTIVE_GUIDE.md`，由 `runner_core.build_prompt()` 显式注入。理由是二者已经被既有科研事务机制保护，直接改写容易引入权限冲突和用户手写内容合并风险。

以后如果需要修改 `AGENTS.md` 的长期方法，请走**显式用户批准的补丁通道**，不要让周期监督自动替换该文件。现有 `--route-review` / `refocus` 负责正式路线裁决，监督层提供建议和下一轮指导，不应同时充当路线账本的第二真相源。

## 五、主要配套文档

- [01 基线核查](01_BASELINE_AUDIT.md)
- [02 架构及契约](02_ARCHITECTURE_AND_CONTRACTS.md)
- [03 冻结不变量与权限](03_INVARIANTS_AND_PERMISSIONS.md)
- [04 全版本验收矩阵](04_ACCEPTANCE_MATRIX.md)
- [05 Codex 开发执行手册](05_CODEX_EXECUTION.md)
- [06 实施追踪表](06_PROGRESS_TRACKER.md)
- [07 数据契约与事件协议](07_SCHEMAS_AND_EVENT_PROTOCOL.md)
- [08 迁移与灾难恢复](08_FIXTURES_MIGRATION_AND_ROLLBACK.md)
