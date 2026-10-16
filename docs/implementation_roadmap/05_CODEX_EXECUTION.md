# 五、把每一轮任务交给 Codex 的方法

## 开发前先做基线保存

在 Codex Windows 桌面版里以 Local 模式打开 `D:\CryptoResearchController`；不要在不含被忽略个人科研文件的新工作树中做状态迁移。建议 Git 分支 `feature/research-supervisor-v3.3`，后续版本再分别建功能分支。执行：

```powershell
cd D:\CryptoResearchController
git status --short
git log --oneline -3
.\research.cmd doctor --offline
python -m unittest discover -s tests -v
```

如果有尚未提交的用户修改，先自行保存/提交，Codex 不得擅自覆盖。独立分支内也可能存在被 Git 忽略的研究目录；不可依赖 Git 分支切换恢复其个人文件。

## 给 Codex 的通用任务文本（每轮替换文件名）

```text
请以 D:\CryptoResearchController 的当前本地源码为准，先核对 Git 状态和版本。
读取 docs/implementation_roadmap/00_INDEX.md、01_BASELINE_AUDIT.md、
02_ARCHITECTURE_AND_CONTRACTS.md、03_INVARIANTS_AND_PERMISSIONS.md，
然后只执行 docs/implementation_roadmap/versions/v3.3/R01_supervision_contract.md。

直接实现本轮规格，先写失败的离线测试，再做最小补丁。
不能运行付费科研轮次，不修改任何 projects/* 的冻结目标、STATE、预算、GATES 或已审查主张。
不跨越当前开发轮次；本轮通过专项测试与全套回归后，输出补丁、测试及回滚说明。
可按仓库真实接口小幅修正规格，并在回执里记录所有差异；不要伪造既有函数或通过状态。
禁止自动推送 GitHub，禁止批量重写科研项目。
```

## 开发过程控制

- 一轮一会话或独立任务；必须交付真实文件补丁与离线测试。
- 只允许一个代理同时修改控制器，另一个审查者可只读审查。合并前检查文件冲突。
- 所有科研项目在开发过程中只读；如需验收，创建临时模拟项目，不复用已有用户项目的实验记录。
- 建议先让 Codex 生成测试，再实施功能；失败用例至少覆盖无效输出、状态过期与事务中断。
- 轮次完成后记录 Git 提交、源码差异、测试命令、实际通过率与尚存限制，更新 `06_PROGRESS_TRACKER.md`。

## 发布前检查

Windows 本地需要验证：`codex --version`、`codex exec --help`、`codex login status`、Python 版本、脚本 UTF-8 输出。无法核实模型可调用时，监督测试只使用模拟执行器。

升级未全面验证前禁止执行 `watch --forever`；不要以重新执行旧研究项目来测试新监督能力。

## 全局启用策略

所有项目自动继承控制器的监督实现，无需在项目里放 Python 监督代码。v3.3 通过验收后，可考虑统一 `supervise enable --all --confirm`（拟新增命令，开发前不可执行），按项目分别记录预算与审计；新项目继承统一策略，但首次自动监督应由用户显式允许或遵守已批准的全局规则。
