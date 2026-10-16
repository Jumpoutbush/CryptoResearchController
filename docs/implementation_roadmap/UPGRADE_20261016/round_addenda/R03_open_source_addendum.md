# v3.3 R03 开源融合附录：只读监督执行器与独立评审

> 这是原版 `versions/v3.3/R03_*.md` 的**补充实施规格**，原文仍是基础契约。现有代码优先，新增内容不得倒逼重做先前轮次。科学进展与开发提交分别验收。

## 一、本轮明确交付

在 R02 已记录且可恢复的监督事件上实现一次权限受限的 Codex 监督，不共享科研代理写能力。

## 二、对应的公开实现 / 已有代码

[The Agentic Researcher](https://github.com/ZIB-IOL/The-Agentic-Researcher)：`INSTRUCTIONS.md`、`container/` 的隔离原则；[LLNL Co-Scientist](https://github.com/llnl/open-ai-co-scientist/blob/main/app/agents.py)：反思角色边界。外部仓库读取时核对当前许可证并固定 SHA；不得直接安装运行整个系统。

## 三、推荐修改位置（以本机已实现模块为准）

1. `supervision/executor.py` 的真实/模拟后端
2. `method/SUPERVISOR_REVIEW.md` 与结构化候选输出契约
3. `tests/test_supervision_executor.py` 及提示注入负例

## 四、本轮实现及技术取舍

1. 从 R01 冻结 manifest 构建脱敏的单项目只读审查目录，校验源哈希及主线锚点
2. 审查输出只允许 KEEP_GUIDE / REFOCUS_RECOMMENDED / PAUSE_RECOMMENDED / ESCALATE，并绑定真实证据路径
3. 工具/进程权限必须在操作系统层隔离，Codex 提示词“只读”只是补充
4. Codex CLI 参数依据本机 `codex exec --help` 验证；模拟执行器先实现并禁止默认联网
5. 监督只记录原文覆盖疑点或数学审查请求，不自发改变 `STATE/GATES/GOAL`

## 五、必须增加的失败测试

1. 来源文本提示模型执行 `git reset` 或改 GOAL 仍被拒绝
2. 输入存在 `.env`、其他项目路径、符号链接，快照全部过滤
3. 非法 JSON、无证据建议、目标哈希变化不会被接收
4. 模型超时/崩溃后 R02 事件可审计恢复且不自动再派发

## 六、本轮退出条件

可信执行器与模拟器同一结构化接口；未验证 Windows 沙箱前仅允许假代理离线验收。

**统一禁止项**：不能改写个人项目 `GOAL.md`、研究成果状态或独立审查回执；不能默许模型把候选变已证明；不得因添加新模块重置已有科研轮次预算。每轮记录外部源码的具体上游提交、许可证、参考函数/文件、替代原理及必要适配测试。
