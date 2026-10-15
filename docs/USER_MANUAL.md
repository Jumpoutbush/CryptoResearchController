# 统一自动科研框架执行手册

## 一、放置与首次检查

将 ZIP 中的 `CryptoResearchController` 文件夹解压到 `D:\`，最终根目录为 `D:\CryptoResearchController`。底座、两个研究项目、日志和研究预算都从这个根目录定位。包内已包含一个初始化后的根 `.git`；两个子项目共用它。新解压目录可直接使用，原有目录请先整体保留，再换用整合目录，避免旧脚本混入。

在 PowerShell 中执行：

```powershell
cd D:\CryptoResearchController
.\research.cmd list
.\research.cmd doctor --offline
.\research.cmd check all
.\research.cmd run secagg-research --dry-run
.\research.cmd run falcon-dkg --dry-run
```

`check` 运行结构与已有证据检查；`--dry-run` 打印所选模型和路线预算，不调用模型、不访问网络、不写预算。已有两项目继续保留原先的目标和研究任务；新模板项目需要执行 `ready` 启用。

### 1.1 Python 与必要软件

需要 Python 3.10 或更新版本、Git，以及已经登录的 Codex 命令行。框架核心只依赖 Python 标准库。论文文字提取可以安装 PyMuPDF；部分 Falcon 历史数值实验另需 NumPy。已有可用 Python 时无需重装。

可选：在根目录建立共享 Python 环境，并安装论文处理工具：

```powershell
py -3 scripts\bootstrap.py --init-git --install-pdf-tools
```

若没有 `py` 启动器，将上述 `py -3` 换成 `python`。该命令只在用户明确运行时安装依赖；以后 `research.cmd` 自动使用根 `.venv`，无需激活。

检查 Codex 登录：

```powershell
codex --version
codex login status
.\research.cmd doctor --auth
```

未登录时执行 `codex login` 完成原有账户登录。框架继承当前登录；不需要配置付费接口密钥。模型名称和推理强度沿用原配置，账户是否可调用由实际 Codex 返回结果决定。

### 1.2 环境变量如何处理

| 变量 | 本框架处理 | 用户操作 |
| --- | --- | --- |
| `CRYPTO_CONTROLLER_HOME` | 不用于定位，旧值不会把日志导向 C 盘 | 可删除旧变量；无需设置新值 |
| `CRC_PYTHON` | 可指定 Python 可执行文件的完整路径 | 仅在希望固定解释器时设置 |
| `PYTHONUTF8` | 启动器为本次进程设置为 `1` | 无需永久设置 |
| `PYTHONIOENCODING` | 启动器为本次进程设置为 `utf-8` | 无需永久设置 |
| `PYTHONPATH` | 底座与项目通过脚本路径和相对目录导入 | 无需设置 |
| `PATH` | 用于发现 Git、Codex 与默认 Python | 保留已有安装路径 |
| `CODEX_HOME` | 继续使用现有 Codex 配置和登录位置 | 无需更改；更改后可能需要重新登录 |

需要临时指定 Python 时：

```powershell
$env:CRC_PYTHON = 'D:\Python313\python.exe'
.\research.cmd doctor --offline
```

将例子替换为真实解释器路径。框架本身的代码、项目、状态、日志与失败材料位于根目录；Python、Git、Codex 的安装和既有登录缓存可以继续使用原有位置。

## 二、日常只需这些命令

### 2.1 从根目录调用

```powershell
cd D:\CryptoResearchController
.\research.cmd run secagg-research
.\research.cmd run falcon-dkg
.\research.cmd status
```

`run` 默认执行一轮，完成后退出。研究代理返回后，底座还会自动执行该项目注册的结构与代数检查，任何检查失败都会隔离本轮修改。调用时按阶段选模型：普通任务默认 `gpt-6.1-sol / xhigh`；证伪、正确性、安全性、证明及复评默认 `gpt-6-astra / max`。`--audit` 和强制路线复评使用审查配置。

### 2.2 从项目目录调用

项目目录中可以省略项目名，同一套命令直接使用：

```powershell
cd D:\CryptoResearchController\projects\secagg-research
.\research.cmd status
.\research.cmd check
.\research.cmd run
.\research.cmd watch --max-rounds 8
```

进入 Falcon 项目后同样执行。`research.ps1` 也提供入口；常规使用 `.cmd` 可避免 PowerShell 脚本执行策略影响。

### 2.3 连续研究和停止

```powershell
.\research.cmd watch secagg-research --max-rounds 8
.\research.cmd watch falcon-dkg --forever
```

`watch` 默认最多八次调用；`--forever` 明确启用持续运行。每次调用可能是研究轮，也可能是达到预算后的路线复评。状态暂停、程序失败、没有新报告、停止请求均会使循环退出。停滞触发复评后，由证据决定追加、同目标换路线或暂停。

在另一个 PowerShell 窗口请求当前轮完成后停止：

```powershell
cd D:\CryptoResearchController
.\research.cmd stop secagg-research
```

恢复时：

```powershell
.\research.cmd clear-stop secagg-research
.\research.cmd watch secagg-research --max-rounds 8
```

需要立即中止使用 `Ctrl+C`。失败轮的修改将被隔离并恢复已接收状态。不要在运行期间用其他程序编辑同一项目的状态；想法、材料和参数更新命令会检查项目锁。

## 三、预算与调用参数

### 3.1 底座提供默认预算

默认初始路线预算六轮，连续三轮无新增实质证据触发复评，每次追加四轮，最多追加两次。预算结束意味着安排路线复评；否决路线需要给出证据和适用范围。失败执行不计入有效研究轮次。

查看和保存项目预算：

```powershell
.\research.cmd budget secagg-research
.\research.cmd budget secagg-research --set 10 --stagnation 4 --extension 4 --max-extensions 2
.\research.cmd budget secagg-research --clear
```

保存的参数位于底座 `config\projects\secagg-research.json`，不需要往研究项目里复制预算逻辑。`--clear` 恢复全局预算默认值，保留模型等其他项目参数。

只覆盖本次调用：

```powershell
.\research.cmd run secagg-research --route-budget 10 --stagnation-rounds 4 --rounds 2
```

已使用轮数保留在账本中。修改预算上限不会清零已有使用量；返回旧路线会继承原预算记录。

### 3.2 修改模型、超时与论文下载

```powershell
.\research.cmd config secagg-research
.\research.cmd config secagg-research --model gpt-6.1-sol --effort xhigh --critical-model gpt-6-astra --critical-effort max
.\research.cmd config secagg-research --max-seconds 2400 --pause-seconds 10
.\research.cmd config secagg-research --pdf-download on --pdf-limit 3 --pdf-max-mb 25
```

自动下载默认关闭，开启后只下载可识别的 IACR ePrint 原文，并核查文件头和大小。其他论文可以直接上传或导入；不根据不确定的元数据猜测下载地址。

临时调用参数不改持久设置：

```powershell
.\research.cmd run falcon-dkg --model gpt-6.1-sol --effort xhigh --max-seconds 1800
.\research.cmd run secagg-research --no-fetch
.\research.cmd run secagg-research --offline
```

`--no-fetch` 跳过该轮控制器文献刷新；`--offline` 使用本地论文和缓存，模型调用仍需要联网。需要关闭研究代理外部网络和网页搜索时，在项目配置中设置：

```powershell
.\research.cmd config secagg-research --network off --web-search disabled
```

参数优先级为：本次命令参数 → 底座项目覆盖 → 底座默认。完整当前值可用 `config` 和 `budget` 查看。

## 四、添加、更新与选中研究想法

### 4.1 登记想法

建议内容包含研究目标、精确候选问题、允许假设、最相近成果、准备尝试的突破点与否决判据。短内容直接写参数，长内容从 UTF-8 文本文件导入。

```powershell
.\research.cmd ideas add secagg-research --title "增量授权的新候选" --text "写明待检命题、约束、反例和成功判据"
.\research.cmd ideas add falcon-dkg --title "短性保持整数回升" --file D:\Materials\idea.md
.\research.cmd ideas list secagg-research
.\research.cmd ideas show secagg-research --id IDEA-0001
```

想法使用稳定编号，每次修改保留独立版本。新增想法只登记材料；当前研究任务保持原状态。

### 4.2 更新与激活

```powershell
.\research.cmd ideas update secagg-research --id IDEA-0001 --file D:\Materials\idea-v2.md --reason "补充新反例和更严格的授权定义"
.\research.cmd ideas select secagg-research --id IDEA-0001
.\research.cmd run secagg-research
```

`select` 是用户明确选择：固定选中版本，更新下一任务并记录裁决，研究从查新与证伪开始。更新想法后若要执行新版本，再次 `select`；已有选中版本继续保持。与同一数学路线有关的想法可使用相同 `--route`，共用该路线预算记录；不要为了回避预算反复创建不同路线编号。

## 五、论文材料与研究状态

### 5.1 导入论文

```powershell
.\research.cmd paper ingest secagg-research --file D:\Papers\paper.pdf --title "论文标题" --url https://eprint.iacr.org/2026/123
.\research.cmd fetch secagg-research --offline
```

例子网址只是命令格式示例，请替换为真实原文地址。文件进入所选项目 `literature\pdfs`，来源与 SHA-256 摘要登记到 `literature\uploads.json`。也可直接将 PDF 放入该目录，再执行 `fetch --offline` 生成文字索引。需要 PyMuPDF 才能提取正文；扫描 PDF 会显示需要文字识别，无法自动恢复数学排版。

联网刷新：

```powershell
.\research.cmd fetch secagg-research
```

每次最多轮转查询八个检索词；`SEARCH_COVERAGE.json` 记录实际查询覆盖，`CATALOG.json` 保留累计候选。Crossref 和 ePrint 公告提供发现入口，研究代理继续核对论文全文、最相近定理与引用关系。

### 5.2 核心文件

| 要看或修改的内容 | 位置 |
| --- | --- |
| 最终目标和不可放宽条件 | 项目 GOAL.md |
| 用户背景、符号及个性资料 | inputs 及已有领域研究文件 |
| 当前任务、裁决、阶段 | research/STATE.json；通过 ready --task 可明确调整下一任务 |
| 主张、失败路线、基线和门禁 | research 下的对应台账 |
| 用户研究想法及版本 | ideas/INDEX.json、各想法版本文件 |
| 正式证明和实验 | proofs、experiments |
| 最近已接收研究报告 | reports/LATEST.md |
| 运行日志及模型返回 | 根 logs/项目编号 |
| 路线使用量及复评 | 根 state/routes/项目编号.json |
| 失败调用材料与原因 | 根 state/failed_runs/项目编号 |

### 5.3 审查与恢复

```powershell
.\research.cmd review secagg-research
.\research.cmd review secagg-research --prepare
```

前者执行一轮对抗审查；后者生成 `research\PRO_REVIEW_REQUEST.md`，供用户送交独立研究者或其他会话。审查反馈保存到项目研究目录后，用 `ready --task` 指定回应问题并恢复：

```powershell
.\research.cmd ready secagg-research --task "读取独立审查反馈，先复核其中的最小反例并修订受影响主张"
.\research.cmd run secagg-research
```

若报告和状态被其他程序改过，底座会发现 `last_run` 不一致。确认外部报告真实且应接纳后，才使用 `run --route-sync`。该参数不补计外部研究轮次。

## 六、将模板应用到新项目

准备一个个性化目标文件，至少说明问题、输入输出、必须满足的条件和希望超越的基线；已有论文随后导入即可。其他固定结构由底座生成。

```powershell
cd D:\CryptoResearchController
.\research.cmd new my-project --goal-file D:\Materials\goal.md --title "新研究主题" --profile generic
.\research.cmd check my-project
.\research.cmd paper ingest my-project --file D:\Papers\seed.pdf
.\research.cmd ready my-project
.\research.cmd run my-project
```

可选配置为 `generic`、`mpc_secagg`、`ntru_lattice`。初始检索入口从项目标题生成；首次接入任务会继续细化检索、符号、安全定义和最小命题。用户可更新 `literature\queries.json`，并在 `inputs` 提供个性化约束；公共方法无需再复制维护。

新模板固定生成目标、状态、主张台账、失败路线、基线、威胁模型、证明义务、门禁、论文阅读卡、实验计划、报告契约及论文证据映射。新增专业方法时在根 `profiles` 放入文件，再在 `config\profiles.json` 注册路径。项目的数学内容和论文身份由真实材料建立。

## 七、Git 与备份

本包包含一个根仓库和整合检查点；不带原包中的嵌套 `.git`、登录凭据、远程地址和运行锁。每个已接收研究轮次尝试提交所选项目的科学结果与路线账本，存在用户已暂存更改时会跳过自动提交，以保留用户工作。

```powershell
cd D:\CryptoResearchController
git status
git log --oneline -5
```

用户手动更新目标、想法和配置后可提交：

```powershell
git add config projects templates docs
git commit -m "Update research inputs and configuration"
```

设置远程仓库后，用户自行 `git push`；框架不自动对外发布。PDF 正文、文字缓存、日志、恢复快照和复现临时目录默认不进入 Git。备份整个研究工作时，应包含用户论文原文和本地运行目录，不能只依靠 Git。

如果 Git 提示目录所有权不同，先确认该目录确实由自己管理，再按 Git 返回的具体路径配置 `safe.directory`；框架不写全局信任通配符。

## 八、故障定位

| 现象 | 处理 |
| --- | --- |
| 找不到 Python | 运行 py -3 --version；或将 CRC_PYTHON 设为真实 python.exe 路径 |
| 找不到 Codex 或 Git | 检查 PATH 并重新打开终端，执行 doctor |
| 提示 Codex 未登录 | 运行 codex login status；需要时执行 codex login |
| 模型或推理强度不可用 | 读最新 logs；通过 config 改为账户可用配置，不会自动换模型 |
| 结构检查失败 | 执行 check；按缺失文件或失效证据链接补充材料 |
| 项目锁占用 | 同一项目已有执行；使用 stop 等其完成，不删除正在持有的锁 |
| 有 STOP_REQUESTED | 确认准备继续后执行 clear-stop |
| 超时或半更新报告 | 查看 logs 与 state/failed_runs；缩小下一任务后重跑 |
| NEEDS_REVIEW 或 PAUSE | 查看报告与路线裁决，给出具体恢复任务，再 ready |
| PDF 没有正文 | 安装 PyMuPDF；扫描件先进行文字识别并核对公式 |

## 九、验证范围与官方参考

整合包通过本地结构检查、历史证据校验、控制器自动化测试和独立目录复现。当前环境没有可调用的 Codex 命令行及 Windows PowerShell，因此真实账户模型请求和 Windows 运行仍需首次 `doctor`、`check`、`--dry-run` 后用一轮 `run` 验证。

Codex 配置、网页搜索、项目根识别与沙盒参数参考官方文档：

- [配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)
- [命令行参考](https://learn.chatgpt.com/docs/developer-commands?surface=cli)

两个研究项目继续保持原先未闭合的证明与发表状态，整合检查不改变研究结论等级。

## 十、v3.1 工作流更新

新增想法补充、原文技术裁决、理论质量及系统开发门禁请以 [v3.1 使用说明](RESEARCH_WORKFLOW_V3.1.md) 为准。新项目默认先完成 INTAKE；系统阶段需 theory approve。个人项目不进入框架更新包，已忽略的研究目录也不会自动进入框架 Git 检查点。
# v3.2 新增操作入口

完整的新项目操作、初始化文件清单、连续证明尝试、Lean 和反例接口见 [数学发现执行手册](MATHEMATICAL_DISCOVERY_V3.2.md)。已有项目可以继续原命令，新建项目推荐：

```powershell
.\research.cmd new my-project --idea-file D:\Materials\idea.md
.\research.cmd initialize my-project
.\research.cmd problem import my-project --file projects/my-project/research/PROBLEM_PROPOSAL.json --reason "已核对量词和约束"
.\research.cmd attempt start my-project --problem P-001
.\research.cmd attempt run my-project --rounds 2
```

初始化提示词随新项目复制到 prompts/initialize_from_idea.md。核对实际问题编号；有阻塞资料缺口时先补齐。上面的问题登记命令应在审核草案后执行。普通 PowerShell 可调用 research.cmd，无需管理员或修改执行策略。
