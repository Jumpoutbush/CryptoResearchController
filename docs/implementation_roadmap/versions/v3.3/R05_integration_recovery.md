# v3.3 · 开发轮次 R05：端到端调度、旧项目兼容与灾难恢复

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

把事件、模型监督、指南应用嵌入统一入口，完成 v3.3 的模拟端到端闭环、操作命令和停用回退；默认不对用户现有项目自动调用模型。

**现有基础：** 原 `research.py.run/watch`、`runner.py` 已可连续科研，但 watch 的成功判据依赖 `last_run`；监督事件不应被误计科研轮次。

**进入条件：** R01—R04 均通过并完成一次成功/失败事件模拟。

## 2. 设计裁决与数据流

### 5.1 顺序设计

`accepted research → route ledger commit → (若需先 route review) → event QUEUED → supervisor proposal → validate/apply guide → next research round`。

监督与正式路线复评必须相互独立。每次监督具有自己的事件及调用预算，`last_run` 只有科研/复评原接口更新。若监督超时或发生冲突，已验收科研结果保留，并按照明确的错误策略暂停下一次自动监督或延后处理。

### 5.2 迁移

新项目从模板继承支持，但默认 `enabled=false`。既有项目无需批量写入 `AGENTS.md` 或 continue；运行 `supervise enable <项目>` 才启用自动审查。手动 `run` 和 `watch` 都必须走同一个调度钩子。框架验证后应支持**统一开启所有登记项目**的显式管理命令，避免逐项目修改脚本；须先预览每个项目及独立调用预算，禁止自动补跑历史监督。

## 3. 修改范围（新增文件均为规划路径）

- 增强 `research.py` 子命令：`supervise enable/disable/status/pending/run/history/apply/rollback`（按项目选择/授权）。
- 更新 `runner.py`、`supervision/scheduler.py`，保证 postcommit 事件可靠处理。
- 添加 `tests/test_supervision_e2e.py`、故障注入夹具和只读迁移测试。
- 更新 `docs/USER_MANUAL.md`、`docs/ARCHITECTURE.md` 与新建项目模板说明。

## 4. Codex 必须完成的实现步骤

1. 构造三个虚拟已接受科研轮回执（由测试模拟器和官方验收接口生成），不改 SecAgg/Falcon/PRC 的实际状态。
2. 运行 `supervise pending`，FakeSupervisorExecutor 返回合法提案，应用器写受控指南。
3. 模拟第 4 个科研轮，截获 `build_prompt`，检查指南确实生效，且没有改写 GOAL。
4. 注入监督崩溃与重启，检查已有研究 run ID、route epoch、科研预算毫无变化。
5. 强制路由复评和周期触发同时发生，检查内置复评先完成、监督合并一次。
6. 验证 `supervise disable` 后行为与基准一致，且不删除监督历史。

## 5. 输入、输出与接口约定

推荐用户操作（具体参数依实现后 `--help` 为准）：

```powershell
.\research.cmd supervise status secagg-research
.\research.cmd supervise enable secagg-research
.\research.cmd supervise pending --dry-run
.\research.cmd supervise history secagg-research
.\research.cmd supervise disable secagg-research
# 规划：批量开启须先查看每个项目预算并明确授权
.\research.cmd supervise enable --all --dry-run
.\research.cmd supervise enable --all --confirm
```

**这些是拟实现的新命令，不属于 `67618536` 现有版本。**


## 6. 必做的离线自动测试

- 旧 `run/watch/refocus/review/attempt` 全部回归。
- 老项目缺少指南文件时可用，首次监督后正常注入。
- STOP/NEEDS_REVIEW/活动 attempt 不因监督自动恢复或更换固定问题。
- 断电/锁争用/双进程同时消费均不重启科研轮次、也不重复监督付费。
- Windows 编码、项目目录调用、标准库依赖和无 Codex 时的离线测试通过。

## 7. 本轮验收标准

- v3.3 的 T01—T06 全部通过。
- 有真实演示：三轮有效研究 → 监督一次 → 指南一次性变更 → 下一轮提示注入。
- 提供操作和回滚命令及完整故障状态记录；默认关闭自动监督。

## 8. 停止、回滚及禁止事项

若监督链出现阻断性缺陷，停用 `supervise` 应即时回到基准研究逻辑。严禁为“发布成功”补写科研有效轮数、解除 STOP 或改变 `G8` 审查状态。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
