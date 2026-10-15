# CryptoResearchController v3.2：理论先行与数学发现引擎

将本文件夹放到 `D:\CryptoResearchController`。底座与 `projects/secagg-research`、`projects/falcon-dkg` 使用一个 Git 仓库、同一套命令和中央参数配置。

```powershell
cd D:\CryptoResearchController
.\research.cmd doctor --offline
.\research.cmd check all
.\research.cmd run secagg-research --dry-run
.\research.cmd watch secagg-research --max-rounds 8
```

项目目录中同样调用 `research.cmd`，省略项目名。核心功能只需 Python 标准库；无需设置控制器路径和 PYTHONPATH，启动器自动设置中文编码。

- [执行手册](docs/USER_MANUAL.md)：安装、命令、参数、想法、论文、新项目、Git 和故障处理。
- [框架设计](docs/ARCHITECTURE.md)：统一内容、研究闭环、模板扩展和此次修复。
- [整合与验证记录](docs/INTEGRATION_REPORT.md)：清理、证据保留、检查结果及验证范围。
- [主线偏移修复与恢复](docs/MAINLINE_FOCUS.md)：区分路线复评和证明审查，约束旁支预算，并用 `refocus` 显式恢复核心任务。

新增研究想法：`research.cmd ideas add secagg-research --title "想法标题" --file D:\Materials\idea.md`。选择后单独执行研究。新建项目：`research.cmd new my-project --goal-file D:\Materials\goal.md --title "研究主题"`，材料补齐后调用 `ready` 与 `run`。

当前完整执行说明：[v3.2 数学发现引擎与 idea 初始化](docs/MATHEMATICAL_DISCOVERY_V3.2.md)。支持 new --idea-file → initialize → problem import → attempt start/run，持续保存证明义务并独立核查候选。新项目初始化提示词位于 templates/project/prompts/initialize_from_idea.md，首轮自动注入。

v3.1 的技术文献裁决、ideas attach、最终提示词预览、理论质量回执和系统开发前理论门禁继续生效。个人项目与运行状态默认保留在本地；上游主张失效会撤销下游有效状态与相关实现许可。
