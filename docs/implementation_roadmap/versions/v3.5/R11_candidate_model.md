# v3.5 · 开发轮次 R11：多候选研究树的数据契约及冻结条件

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

在一个冻结研究目标下登记少量相互竞争的候选构造和可证伪命题，保留分支的前提、关系、证据和否决边界；不能越过既有固定命题接口。

**现有基础：** `problem import/attempt start` 保存不可变问题版本，`engine/discovery_scheduler` 只允许单活动尝试；既有 `research_focus` 已锚定路线。

**进入条件：** v3.4 已能识别问题、证据和候选来源的版本。

## 2. 设计裁决与数据流

### 11.1 候选不是正式结论

候选节点状态 `PROPOSED/SCREENING/READY_FOR_ATTEMPT/ACTIVE/REFUTED/COVERED/RETIRED/CONDITIONAL`，不得提供 `PROVED` 作为模型可直接写入的状态。每个候选固定 `goal_anchor_id`、`problem_id` 或待核验草案、清楚的非平凡创新假设、最邻近工作、必备证明义务、否决判据和预估上下文成本。

### 11.2 树与依赖

父子关系代表“在某假设改变下产生新候选”，必要假设变更必须生成新的候选版本，不覆盖父节点；不同候选共享的引理通过 v3.4 知识图谱引用，未经独立核验的共享边保持候选状态。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `candidate_search/model.py`、`candidate_search/catalog.py`、`candidate_search/validate.py`。
- 存储建议：`state/candidates/<project_id>/catalog.json` + 追加事件；可读的人类摘要位于 `projects/<id>/research/CANDIDATES.md`（可选）。
- 新建 `tests/test_candidate_contract.py`。
- 新增 `candidate list/propose/show` 命令（具体解析在本轮实施后公布）。

## 4. Codex 必须完成的实现步骤

1. 规定唯一键 `project_id + anchor_id + candidate_id + revision`，对同标题项目不合并。
2. 模型提交候选必须同时给出可证伪命题和最接近论文的待核查点，未检索全文时标记 `NOVELTY_PENDING`。
3. 验证“核心目标未改变”，新敌手模型/信任设置属于新修订并需要独立裁决。
4. 每一版本只能新增历史，禁止原地覆盖已经被否决的分支。
5. 添加最多 3 个 `SCREENING/READY/ACTIVE` 活跃候选的配置限制，超限拒绝或要求先退役。
6. 候选创建不自动修改 `STATE.next_task`、不导入固定问题、不触发模型调用。

## 5. 输入、输出与接口约定

示意候选卡：

```json
{
  "id": "C-0001",
  "revision": 1,
  "goal_anchor_id": "真实研究锚点",
  "problem_proposal_file": "research/candidates/C-0001/problem.json",
  "hypothesis": "可被明确反驳的候选声明",
  "closest_prior_work": ["核查过的来源 ID 或待核查占位"],
  "falsification_gate": "具体最小反例或覆盖判据",
  "status": "PROPOSED",
  "evidence_refs": []
}
```

路径和 ID 示例不允许绕过项目边界校验。


## 6. 必做的离线自动测试

- 创建同名不同假设的候选成功且 ID 不同。
- 同一候选原地改变敌手模型被拒绝；显式修订保留旧版本。
- 4 个同时活跃候选时拒绝新激活，已否决候选不占用活跃名额。
- 缺少否决判据/没有与冻结目标的关联时无法进入 `READY_FOR_ATTEMPT`。
- 错误编号、跨项目问题引用、循环分支关系被拒绝。

## 7. 本轮验收标准

- 同时登记 3 个候选，产生稳定、可审计的树结构，未调用模型。
- 原有 `attempt` 数量、权威主张状态及路线预算不变。
- 候选“未审/已否决/待证”含义在 CLI 中明确展示。

## 8. 停止、回滚及禁止事项

禁止从候选注册中直接宣布科研成功，也不允许把修订当作新路线逃避已有预算。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
