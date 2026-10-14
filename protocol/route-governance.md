# 通用研究路线预算与自动裁决协议

## 控制权分离

- 所有预算默认值、项目专属覆盖和调度执行均在 CryptoResearchController 下；不要求科研项目在 PROJECT_POLICY.json 设定预算。
- 项目内仍然保存 `GOAL.md`、`research/STATE.json`、报告、证明与失败路线证据。这些是科研记录，不是预算配置。
- 原有研究执行与证据验收由 runner_core.py 负责。新增 route runner 只处理预算、路线复评与策略决策。

## 轮次

`--rounds` 是**本次启动最多调用多少次原控制器**；`--route-budget` 是**当前路线跨启动累计有效研究轮次上限**。

只有原控制器退出码为 0，STATE.last_run 更新，且对应报告存在并达到最低长度，才记一有效轮。
强制路线复评轮独立记入审计记录，不消耗有效研究预算。失败、超时和重复回执不能计入轮数。

## 停滞与实质进展

由 agent 提交 `research/ROUTE_SIGNAL.json`，controller 检查 run_id、证据路径以及本轮文件摘要变化。只能认定“提交了有变化的研究材料”，仍不表示证明真实成立、结论新颖或论文可投。
缺失、无效或者没有新增证据的进展回执计入连续停滞轮；达到阈值触发路线复评。

## 预算耗尽

流程为 `研究 → 审查是否达到预算/停滞门槛 → 强制路线复评 → 延期/候选预研/暂停`。需要追加预算时按 extension_round_budget 计算，最多追加 max_extensions 次。

复评必须保存 `research/ROUTE_VERDICT.json`，记录论证、失败分类和候选的目标兼容性。候选能自动接管的条件至少包括明确新命题、可查验的证据路径、对 GOAL 的显式兼容声明、下一轮最小证伪任务。接管只赋予候选 **FEASIBILITY / 初步可行性预研** 状态，不得自动宣称之前路线在数学上不可行。

任何修改 GOAL 中不可放宽条件的方案必须暂停请求人工许可；缺乏证据时同样暂停。对涉及准确性、恶意安全门槛和输出语义的变更尤需谨慎。

## 原始状态安全

未经审查的证据不能写入 STATE.verified_results；控制器从不自动把 `publication_status` 升至 DRAFT_READY 或把 `phase` 升至 DONE。自动切换只能修改未证的当前路线、下一研究问题和执行阶段。

## 失败分类

准确区分 `EXPLICIT_COUNTEREXAMPLE`、`LITERATURE_OVERLAP`、`UNACCEPTABLE_COST`、`PROOF_OPEN`、`INSUFFICIENT_EVIDENCE`、`EXECUTION_FAILURE`。预算用尽属于资源与研究管理事实，不属于数学不可行性证明。
