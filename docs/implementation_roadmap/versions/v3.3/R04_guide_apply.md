# v3.3 · 开发轮次 R04：监督指南安全落盘与提示词注入

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

用可信模板把监督建议的结构化字段转换为项目内**单独、版本化、受保护**的 `supervision/ACTIVE_GUIDE.md`，由下一轮研究提示确实读取；模型不能修改源目标、研究状态和科研门禁。

**现有基础：** 既有 `AGENTS.md` 和 `prompts/continue.md` 已被 `runner_core.PROTECTED` 保护；`build_prompt` 已按固定顺序读取它们。

**进入条件：** R03 已能提供通过 schema 验证的提案和来源绑定。

## 2. 设计裁决与数据流

### 4.1 为什么采用独立文件

从源文件中抽取受控指南会冲突于旧版受保护输入；新增 `supervision/ACTIVE_GUIDE.md`（只有可信控制器可写）更易审计。生成指南区分：核心义务、待证事项、下一步可证伪任务、输入证据及禁止误判范围。

### 4.2 应用必须是事务

校验结构化输出 → 可信模板渲染 Markdown → 核对 `goal_anchor_id` 与源码 SHA → 核对 `old_guide_sha256`（无文件时固定空版本）→ 生成 diff → 保留旧内容 → 临时文件写入并 fsync → 原子替换 → 回执落盘。崩溃时根据新旧 SHA 决定恢复或补写回执，不能对同一事件再合成第二个版本。

指南注入必须在科研模型读取 `AGENTS`/continue 之后，并重申不能推翻 GOAL 与固定问题。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `supervision/guide.py`：validate, preview_diff, apply, rollback。
- 在 `runner_core.build_prompt` 增加显式读取 `supervision/ACTIVE_GUIDE.md`，并添加不可覆盖的提示词优先级说明。
- 在 `runner_core.PROTECTED`/`PROTECTED_DIRS` 中将 `supervision` 标记为科研模型只读。
- 在 `templates/project/supervision/README.md` 中描述生成文件的来源、加载顺序、恢复方法。
- 新建 `tests/test_supervision_guide.py`。

## 4. Codex 必须完成的实现步骤

1. 旧项目未含 `supervision` 目录时照常启动；监督启用时由可信控制器按需建立。
2. 限制指南最多 12 KiB，章节标题由可信模板生成；模型只提交有证据的任务和判据字段。凡要求更改预算、修改目标或认可证明的字段，均拒绝自动应用。
3. 实施前重读目标 SHA、route epoch、选中想法和最新 accepted_run_id，任一变化则将提案变 `REJECTED_STALE`。
4. 任何自动变更只涉及 `supervision/ACTIVE_GUIDE.md`；改变 `AGENTS.md` 的长期策略需另设人工批准流程且不纳入自动写入。
5. 保留旧版内容和 SHA 的独立历史，不允许拿 Git 恢复被忽略的个人项目文件。
6. 提供只读预览、应用、回滚三个入口，由现有注册命令解析器暴露。

## 5. 输入、输出与接口约定

示例受控指南的内容结构：

```markdown
# 当前监督指南

## 冻结目标摘要（仅引用）
引用 GOAL 文件及哈希，不修改原文。

## 当前核心证明义务
写明既有义务编号和当前验证状态。

## 下一项可证伪任务
只选一个明确的研究问题。

## 成功与否决判据
列出可核对输出和反例。

## 不应重复的旁支
引用已归档失败路线，不允许假定已证。
```

拟增接口：`research.cmd supervise apply <项目> --event <ID>`、`research.cmd supervise rollback <项目> --event <ID>`；若自动应用模式启用，仍执行同一校验器。


## 6. 必做的离线自动测试

- 两次 apply 同一事件仅产生一个指南版本和一个应用回执。
- 外部手动改动指南，CAS（比较并替换）冲突时拒绝覆盖。
- `build_prompt` 明确包含当前指南；旧未安装项目提示词保持原样。
- 模型试图修改 `supervision/ACTIVE_GUIDE.md`，旧科研事务识别并拒绝。
- 指南写入失败模拟在临时文件/原子替换/回执后，三处都能自洽恢复。
- 含“已证明安全”“改变 GOAL”“把预算加 100”的危险提案不得自动应用。

## 7. 本轮验收标准

- 受控指南被下一科研轮实际加载。
- 保护列表能阻止科研代理直接改变指南；监督不能改长期目标。
- 对已有研究项目只读运行 `build_prompt`，输出校验无字段回归。

## 8. 停止、回滚及禁止事项

模型提出合法 `PAUSE_RECOMMENDED` 时只保留建议，不能覆盖既有 `STATE.decision`；原有路由复评决定正式暂停、聚焦或延期。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
