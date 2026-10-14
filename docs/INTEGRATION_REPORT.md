# 整合与验证记录

## 一、整合范围与研究状态

本包以提供的 CryptoResearchController、secagg-research 和 falcon-dkg 压缩包为来源。底座、项目、模板和配置集中到一个可迁移目录，根仓库采用 main 分支；不配置远程地址或导入登录凭据。来源文件摘要和原项目初始 Git 提交见 IMPORT_MANIFEST.json。

两项目 GOAL.md 保留原始字节，已有 STATE 字段值完整保留。Falcon 新增路线编号 NTRU/SHORT_LIFT，仅用于预算记账。SecAgg 保持 C/PIWA 当前任务；两项目 verified_results 为空，发表状态继续为 NOT_ESTABLISHED。

## 二、清理与内容合并

删除控制器的失效 runner_base/model_router、旧安装器和硬编码启动器、多份 runner 备份、安装备份目录、旧锁和测试日志；删除项目嵌套 Git、字节码缓存、沙盒烟雾测试文件、旧路径运行脚本和本地重复模型配置。

有独有研究内容的提案先处理再清理：SecAgg 的八项主张、六项失败边界和已有决策合并到当前台账，保留原证明状态与待独立审查标记；既有模型和下载设置记录在导入提案中。Falcon 从提案恢复八组检索词，补齐种子来源登记，论文内容核验状态保持真实。项目 MIGRATION_NOTES.md 和 MIGRATION_CHECKS.json 记录具体处理。

保留 Falcon 五组历史实验、32 个历史文件、规范 KAT 样本及来源摘要，所有历史文件与输入包逐字节一致。大小写不同且内容不相同的证明文件继续保留。历史计算移到独立复现目录执行，不覆盖归档结果。

## 三、统一执行与扩展能力

- 根目录和项目目录使用同一命令接口；项目目录自动选择当前项目。
- 模型、时间、检索和预算参数采用底座默认、项目覆盖、单次命令覆盖。
- 用稳定项目编号保存预算，搬迁目录后继续记账。
- 新项目由通用模板生成；个性化目标、假设、参数、符号与论文在项目中提供。
- 想法稳定编号、逐版保留；用户选中后固定执行版本，模型不能自行切换版本。
- 每轮自动检查报告、状态、受保护输入、证据链接及项目注册检查；失败隔离并恢复。
- 路线预算达到阈值后专门复评；Git 检查点在调度验收和裁决完成后保存。
- 同一项目互斥，多个项目共享 Git 检查点锁，避免提交混入其他项目的更改。
- 文献查询分批轮转，保留覆盖与累计候选；原文阅读与新颖性判断继续要求实质证据。

## 四、验证结果

| 检查 | 结果 |
| --- | --- |
| 框架单元与集成测试 | 35 项通过 |
| SecAgg 结构与台账 | 通过；两个局部证明仍待独立审查 |
| SecAgg 参考验证器 | 6 项测试通过 |
| Falcon 结构、证据审计及规范样本 | 通过 |
| Falcon 准确代数、奇偶约束、认证界与 KAT | 通过 |
| Falcon 隔离历史复现 | certificate、safebox、lift、gso 四组通过 |
| 两项目预检查 | 无网络、无模型调用，均通过 |
| 完整子进程链模拟 | 两轮研究、一轮追加预算复评、三次局部 Git 提交通过 |
| 模拟程序失败恢复 | 已接收状态与证据恢复，失败材料隔离，无新增提交 |
| 输入保留 | 两项目目标与原状态字段保留；32 个 Falcon 历史文件字节一致 |

控制器测试覆盖预算持久化、目录搬迁、只读查询、想法版本、参数合并、PDF 摘要、注册检查失败、受保护文件恢复、异常状态、立即中止、路线非法变化与 Git 提交范围。完整进程链测试使用模拟 Codex，验证调用与验收机制；不请求真实模型。

本执行环境为 Linux，没有 Windows PowerShell 与可用 Codex 命令行。Windows 启动器已按相对路径和退出码规则检查，仍应在用户本机完成首次 doctor、check、dry-run 和一轮实际 run。此项验证不会改动两个研究项目的证明等级。

## 五、历史实验复现

在 Falcon 项目目录调用：

```powershell
python scripts\replay_historical.py list
python scripts\replay_historical.py certificate
python scripts\replay_historical.py safebox
python scripts\replay_historical.py lift
python scripts\replay_historical.py gso
```

如果日常使用根虚拟环境，替换 `python` 为 `..\..\.venv\Scripts\python.exe`。gso 与 sparse 需 NumPy，可从根目录运行 `python -m pip install -r requirements-optional.txt`，确保使用同一解释器。

复现入口把历史脚本和规范样本复制到 experiments/replays 的新目录，记录命令、源文件摘要、标准输出、错误输出和超时。原历史脚本保留归档内容；独立复现结果需要核对后才用于修订研究结论。
