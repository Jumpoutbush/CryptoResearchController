# CryptoResearchController v3.4：长期科研知识图谱

将本文件夹放到 `D:\CryptoResearchController`。底座与 `projects/secagg-research`、`projects/falcon-dkg` 使用一个 Git 仓库、同一套命令和中央参数配置。

```powershell
cd D:\CryptoResearchController
.\research.cmd doctor --offline
.\research.cmd --version
.\research.cmd check all
.\research.cmd supervision status all
.\research.cmd run secagg-research --dry-run
.\research.cmd watch secagg-research --max-rounds 8
```

项目目录中同样调用 `research.cmd`，省略项目名。核心功能只需 Python 标准库；无需设置控制器路径和 PYTHONPATH，启动器自动设置中文编码。

- [执行手册](docs/USER_MANUAL.md)：安装、命令、参数、想法、论文、新项目、Git 和故障处理。
- [框架设计](docs/ARCHITECTURE.md)：统一内容、研究闭环、模板扩展和此次修复。
- [整合与验证记录](docs/INTEGRATION_REPORT.md)：清理、证据保留、检查结果及验证范围。
- [主线偏移修复与恢复](docs/MAINLINE_FOCUS.md)：区分路线复评和证明审查，约束旁支预算，并用 `refocus` 显式恢复核心任务。
- [独立科研监督](docs/SUPERVISION.md)：每三轮已验收科研工作及预算复评节点自动审查，安全更新指南，保留独立预算、审计差异和回滚记录。用 `research.cmd supervision configure all --enabled on` 登记现有项目并开启。

按分轮路线图新增的 [R02 事件与恢复协议](docs/SUPERVISION_R02_EVENTS.md) 默认关闭，
开启后仅排队。本地恢复守护只保证稳定事件去重、本地至多一次记账和不自动重复派发；
外部请求已派发但缺少可靠回执时为 `UNKNOWN_EXTERNAL_OUTCOME`，保留预留并等待人工审计。
没有提供方可验证幂等键时，不能保证远端账单恰好一次。本轮没有实现 R03 付费执行器。
- [v3.3 发布与后续路线](docs/RELEASE_V3.3.md)：结构化裁决、指南提案、已知偏移样本回放及 v3.4—v4.0 的分阶段开发边界。
- [v3.4 长期科研知识图谱](docs/RESEARCH_KNOWLEDGE_V3.4.md)：复用现有主张图，关联论文、定理、原始证据、失败路线与证明义务，查询来源及上游失效影响。

新增研究想法：`research.cmd ideas add secagg-research --title "想法标题" --file D:\Materials\idea.md`。选择后单独执行研究。新建项目：`research.cmd new my-project --goal-file D:\Materials\goal.md --title "研究主题"`，材料补齐后调用 `ready` 与 `run`。

数学发现执行说明：[v3.2 数学发现引擎与 idea 初始化](docs/MATHEMATICAL_DISCOVERY_V3.2.md)。v3.4 保留 new --idea-file → initialize → problem import → attempt start/run，持续保存证明义务并独立核查候选。新项目初始化提示词位于 templates/project/prompts/initialize_from_idea.md，首轮自动注入。

v3.1 的技术文献裁决、ideas attach、最终提示词预览、理论质量回执和系统开发前理论门禁继续生效。个人项目与运行状态默认保留在本地；上游主张失效会撤销下游有效状态与相关实现许可。

v3.4 的知识记录保存在现有 `research/discovery/CLAIM_GRAPH.json` 中，复用主张版本、审查和失效语义。先用 `research.cmd knowledge status 项目ID` 只读查看，或用 `knowledge refresh` 显式建立本地来源索引。后续每个已验收科研轮自动刷新索引，再判断独立监督触发；科研和监督均读取有长度上限的知识上下文。原研究状态、预算与历史不迁移；知识检索和刷新不调用模型。追溯包含精确绑定的历史来源，历史命中不代表当前审核通过。

下一阶段按 v3.5 有界候选研究树与独立验证、v4.0 科研质量评价与自适应调度推进。离线回归验证控制流程、来源校验和失效传播，不能据此宣称提高了开放密码学问题的求解率。
