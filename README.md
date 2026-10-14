# CryptoResearchController：统一自动科研框架

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

新增研究想法：`research.cmd ideas add secagg-research --title "想法标题" --file D:\Materials\idea.md`。选择后单独执行研究。新建项目：`research.cmd new my-project --goal-file D:\Materials\goal.md --title "研究主题"`，材料补齐后调用 `ready` 与 `run`。
