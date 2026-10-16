# v3.2：数学发现引擎与 idea 初始化执行手册

## 1. 本次升级范围

v3.2 包含 v3.1 的文献技术核查、想法版本、理论贡献审查和理论先行门禁，再加入精确问题、连续研究尝试、候选主张、独立验证接口与依赖失效。默认顺序使用单个深度研究实例；反例审查占用同一尝试预算中的独立调用，不启动并行智能体。

更新器只处理框架和模板，不重新初始化现有 Falcon DKG、SecAgg，不覆盖个人项目、个人参数、研究状态和 Git 元数据。数学发现模式由 attempt start 启用；没有活动尝试的旧项目继续原阶段流程。

## 2. 从 idea 新建项目

以下命令在 D:\CryptoResearchController 的普通 PowerShell 中运行，无需管理员权限。项目目录需要当前用户可写。

```powershell
.\research.cmd new my-project --idea-file D:\Materials\idea.md --title "我的研究主题" --profile generic
.\research.cmd initialize my-project
```

可同时提供 --goal-file，区分明确目标与初始想法。只给 idea 时，原文作为初始 GOAL 内容保存，并登记 IDEA-0001 第1版，不擅自替用户改写目标。new 只复制模板和保存输入；initialize 才调用一次模型。也可沿用 ready → run，首次 INTAKE 会加载相同初始化契约。

只读预览：

```powershell
.\research.cmd prompt my-project --initialize
.\research.cmd initialize my-project --dry-run
```

初始化提示词的模板位置是 templates/project/prompts/initialize_from_idea.md，创建后复制到 projects/my-project/prompts/initialize_from_idea.md。它会实际注入首轮提示词，无需另行粘贴。派生文档清单如下：

| 产物 | 用途 |
| --- | --- |
| research/INTAKE.md、PROJECT_BRIEF.md、NOTATION.md | 解释 idea、精确定义对象与符号、冻结目标 |
| research/CONTRIBUTION.md、THREAT_MODEL.md、COST_MODEL.md | 候选理论贡献、安全前提、完整成本口径 |
| research/PROOF_OBLIGATIONS.json、OPEN_PROBLEMS.md | 必要证明义务与核心障碍 |
| research/BASELINES.md、literature/SEARCH_PLAN.json | 原文核查计划、可比基线和具体检索词 |
| research/PROBLEM_PROPOSAL.json、ROADMAP.md | 精确命题草案与按门禁推进的路线 |
| research/INITIALIZATION.json | 绑定输入摘要、12份文档摘要、草案状态与缺失信息 |

初始化内容一律属于草案。缺失的腐化模型、参数、文献原文等写成具体问题。阻塞缺口使状态为 NEEDS_INPUT 并暂停；READY_FOR_PROBLEM_REVIEW 只表示可以审核精确问题，不表示有理论贡献。未得到原文时不得伪造文献比较。

默认占位检索词不触发初始化前的自动文献抓取。初始化成功后，控制器可用 SEARCH_PLAN 中的 queries 替换尚未被用户修改的占位词。已有自定义检索参数保留。用户输入目录和原始 idea 不被模型修改。

补齐阻塞资料后可运行 initialize my-project --refresh；这会在保留原始资料与历史证据的前提下更新派生文档。已有活动研究尝试须先关闭，防止更换证明前提。初始化更新不重置原路线预算。

## 3. 审核问题，然后开始连续研究

核对 PROBLEM_PROPOSAL 的量词、输入分布、安全目标、假设、输出、短性、成本和不可放宽条件。需要人工决定的参数先补齐。示例中的 P-001 应替换为草案的实际 id。

```powershell
.\research.cmd problem import my-project --file projects/my-project/research/PROBLEM_PROPOSAL.json --reason "已核对 idea、量词和不可放宽约束"
.\research.cmd attempt start my-project --problem P-001
.\research.cmd attempt run my-project --rounds 2
.\research.cmd attempt status my-project
```

start 固定问题版本、目标摘要、当前路线、输入及已选 idea 版本，自动进入 PROOF。它不重置现有路线预算。以后普通 run、watch 也会加载同一活动尝试；attempt run 的优点是未开始尝试时直接报错。项目目录中调用 .\research.cmd 可省略项目名。

每次调用默认使用现有 critical 模型/推理档；一轮是一次有总时间限制的 Codex 调用。默认交替进行证明探索和反例审查。跨调用恢复的是外部数学状态，不是模型的内部推理状态，也不保证复现某个未公开模型的能力。

问题池在 research/discovery/PROBLEMS.json；问题每次 import 创建不可变版本。导入新版本不会替换正在执行的旧版本。要切换，先关闭当前尝试，再明确 start 新版本。

```powershell
.\research.cmd attempt close my-project --reason "保存当前证明缺口，准备审核修订命题"
.\research.cmd problem import my-project --file D:\Materials\problem-v2.json --reason "补全明确前提"
.\research.cmd attempt start my-project --problem P-001 --version 2
```

## 4. 研究状态、预算与停滞

research/attempts/attempt-0001/CHECKPOINT.json 由本轮模型提交，必须保持全部固定义务，包含精确缺口、候选主张、真实证据和下一决定性行动。模型不能将义务自行标成已证。DISCHARGED 必须关联同一问题版本中经过独立审查的对应主张。

控制器将接受的检查点另存到 state/discovery/checkpoints；调用账本在 state/discovery/项目ID.json，失败和超时也计入尝试预算。失败轮的项目文件恢复，失败调用费用不会通过回滚被抹掉。执行中断留下的 RESERVED 调用仍消耗预算，需要检查实际日志后继续，不自动免费重试。

默认每次尝试6次调用，连续3次没有新的独立审查结果或准确机器反例时暂停，可由用户给理由扩展4次，最多扩展1次；同一问题ID最多3个独立尝试。只增加文本、改名字、重复核查相同见证不会重置数学停滞计数。候选推导仍会保存，用户可据此判断是否值得继续。

```powershell
.\research.cmd attempt extend my-project --reason "已定位具体缺失引理，值得一次有限扩展"
.\research.cmd attempt run my-project --rounds 2
```

路线预算与尝试预算同时生效。原路线需要复评时，活动尝试在额外模型调用前暂停；先 close，再 review，审核后继续。暂停、预算耗尽和证明未闭合不等于命题错误，也不会自行弱化目标。

全局默认在 config/discovery_defaults.json，项目局部覆盖保存在 config/projects/项目ID.json 的 discovery_policy。可以把局部字段写入 JSON 后：

```powershell
.\research.cmd discovery my-project
.\research.cmd discovery my-project --file D:\Materials\discovery-override.json
```

例如 {"initial_round_budget":4,"stagnation_rounds":3}。活跃尝试保留启动时的预算快照；修改默认值影响下一次新尝试。关闭 enabled 会阻止当前尝试继续。目标锁定、依赖失效与独立验证等核心发现规则不能关闭。

## 5. 候选主张与独立核查

模型将新候选写到当前尝试 proposals 目录，并列入检查点 candidate_claim_files 与 evidence_paths；每轮最多2个。控制器只自动导入新的主张ID，状态保持候选。已有主张的修订由用户执行 claim import，不会被模型同名提案覆盖。

```powershell
.\research.cmd claim status my-project
.\research.cmd claim show my-project --id CLAIM-001
.\research.cmd claim import my-project --file D:\Materials\claim-revision.json --reason "修补上游假设"
```

模板在 research/CLAIM_TEMPLATE.json。verification_mode=FORMAL_REQUIRED 时必须给 formal_target 的 file 与 declaration。采用 INDEPENDENT_MANUAL 时须解释形式化适用性以及为何采用独立人工审查；全局 formal_verification=required 可强制正式化路径。

| 核查接口 | 有效边界 |
| --- | --- |
| verify counterexample | 只支持注册的准确整数谓词；不执行 Python eval，不是任意协议安全分析器 |
| verify lean | 未认证隔离时返回 ISOLATION_UNCERTIFIED，不启动 Lean/Lake；无 elan 返回 UNAVAILABLE |
| claim review proof_and_statement | 用户登记独立技术审查，绑定当前声明、前提和证据；结构检查不验证审查人的判断 |
| claim review novelty | 定理级新颖性审查，复用六维原文技术比较与独立推导 |

整数机器声明示例：

```json
{"domain":"INTEGER","variables":["a","q"],"preconditions":["q > 1","a % q == 0"],"conclusion":"a == q"}
```

```powershell
.\research.cmd verify counterexample my-project --claim CLAIM-001 --bounds -3 3
```

可用 --witness 提供变量到整数的 JSON 映射。验证器按顺序核对前提，再检查结论；找到的准确见证只否定注册的机器谓词，人工数学声明的对应仍需审查。没有反例仅表示有限范围未找到，绝不关闭全称证明义务。默认每次最多10,000个候选、3秒。

候选声明含机器谓词时，控制器在接受研究轮后执行受限整数核查。formal_target 经过统一隔离门禁，当前不启动宿主 Lean/Lake。结果不产生自动正确性或新颖性审批。

## 6. Lean 环境及范围审核

Lean 是可选安装的外部证明工具。框架的 Python 部分不需要第三方依赖。证明工程放在项目 proofs/lean；需要固定版本的 lean-toolchain、lake-manifest.json，以及已经安装/构建好的对应库。版本应固定为 leanprover/lean4:v具体版本，不能使用浮动 stable/nightly。

```powershell
.\research.cmd verify lean my-project --claim CLAIM-001 --file proofs/lean/Check.lean --declaration MyNamespace.target
.\research.cmd claim show my-project --id CLAIM-001
```

当前没有认证的 OS 隔离后端，因此自动候选核查和显式 `verify lean` 都在任何进程启动前返回 `ISOLATION_UNCERTIFIED`。不探测 Lean 版本、不复制审计源码、不继承宿主凭据执行候选，不运行 elan/Lake/Lean 或安装命令。输入路径、固定工程和未完成证明标记仍检查；静态扫描不构成隔离保证。

工具成功状态为 TOOL_PASSED_AUDIT_PENDING。独立审查者仍须核对完整日志、精确量词、前提、定义、导入、自定义公理及主/辅结论覆盖范围。将研究模板 FORMAL_AUDIT_TEMPLATE.json 中 verdict 改为 MATCHED_AND_AUDITED，填入 claim show 输出的 formal_receipt_sha256，并填写实际审核结论后：

```powershell
.\research.cmd claim review my-project --id CLAIM-001 --kind formal_audit --evidence research/formal-audit.json --reviewer "独立审查者" --reason "已核对声明、依赖与公理"
```

当前没有自动 Comparator 集成或 OS 级 Lean 沙箱，故宿主执行保持阻断。已有合法工具回执及独立审查规则保留；模拟成功回执的单元测试不证明真实隔离或形式证明已经通过。

采用人工独立审查时：

```powershell
.\research.cmd claim review my-project --id CLAIM-001 --kind proof_and_statement --evidence research/independent-proof-review.md --reviewer "独立审查者" --reason "核对所有前提和证明步骤"
```

提案者不能登记为同名独立审查者。审查证据改变、源文件改变或上游修订后，状态自动退回待验证。身份独立性是操作员的真实责任；名字不同本身不能证明独立性。

## 7. 新颖性、依赖失效与系统开发门禁

先完成 literature/technical_reviews 中最相近原文的技术比较，再按 literature/THEOREM_NOVELTY_TEMPLATE.json 填写定理级新颖性报告，绑定 claim show 的 spec_sha256。

```powershell
.\research.cmd claim review my-project --id CLAIM-001 --kind novelty --evidence literature/theorem-novelty.json --reviewer "独立审查者" --reason "已完成最相近定理原文核查"
.\research.cmd claim invalidate my-project --id CLAIM-001 --reason "确认上游符号错误"
.\research.cmd claim status my-project
```

主张图在 research/discovery/CLAIM_GRAPH.json，保存声明版本、证据摘要、依赖版本、审核及事件。上游撤回、修订、证据变化或准确机器反例会使所有受影响下游显示 PENDING_REVALIDATION。只修好上游不足以自动恢复旧下游：必须显式重新绑定新版本并复核。旧版本及推导保留。

项目采用发现引擎后，theory approve 要求对应主张通过正确性、声明和定理级新颖性审查，且该主张的依赖闭包已覆盖所有关键问题义务。Lean 适用时还需通过该路径。部分引理成立可以算进展，但不自动开启系统实现。

```powershell
.\research.cmd theory approve my-project --claim CLAIM-001 --contribution research/CONTRIBUTION.md --correctness research/independent-proof-review.md --novelty literature/theorem-novelty.json --reviewer "研究负责人" --reason "确认理论贡献与正确性"
.\research.cmd ready my-project --phase IMPLEMENTATION
```

安全论证需要时增加 --security 绑定审查证据。系统工作只支持被批准的主张；主张或依赖失效后许可也失效。未经许可的系统阶段在模型调用前被阻止。理论阶段生成系统源码会被拒绝并回滚；只允许与具体义务绑定且有预算的最小数学核查。提示词与事后文件检查无法保证模型绝不在一次调用中产生无效代码，故应同时保留前置阶段门禁和有限预算。

## 8. 哪些文件控制什么

| 层次 | 文件 |
| --- | --- |
| 初始化提示词 | templates/project/prompts/initialize_from_idea.md，复制到新项目 prompts/ |
| 通用研究规则 | method/00–17，领域规则 profiles/ |
| 阶段与深度提示 | prompts/stages/、deep_proof.md、adversarial_review.md、theorem_novelty.md |
| 模型和执行参数 | config/defaults.json；项目 config/projects/ID.json |
| 数学发现预算 | config/discovery_defaults.json；项目 discovery_policy |
| 理论先行门禁 | theory_gate.py、research_quality.py、config/research_policy.json |
| 问题与尝试 | engine/problem_compiler.py、deep_reasoning.py、discovery_scheduler.py |
| 独立核查 | engine/falsification.py、formal_verifier.py、verification_engine.py |
| 结论复用与有效性 | engine/claim_graph.py、research_evaluator.py |

增加新想法继续使用 ideas add/update/attach。单纯新增尚未选中的 idea 不影响当前尝试；attach/select 或更换已固定版本会改变研究输入，旧尝试需保存缺口后关闭并重新开始，避免悄悄更换证明前提。

## 9. 环境变量、验证和能力范围

Python 3.10+。research.cmd 优先使用 CRC_PYTHON 指向的 python.exe，其次根目录 .venv\Scripts\python.exe，再尝试 py -3 和 python。通常无需手动设置变量，也不要设置 PYTHONPATH 或旧的 CRYPTO_CONTROLLER_HOME；位置按脚本路径确定。启动器设置 PYTHONUTF8=1、PYTHONIOENCODING=utf-8。

```powershell
$env:CRC_PYTHON = 'D:\CryptoResearchController\.venv\Scripts\python.exe'
.\research.cmd doctor --offline
.\research.cmd check all
python -m unittest discover -s tests -v
python scripts/discovery_benchmark.py
```

只有需要指定解释器时设置 CRC_PYTHON，指向文件本身；无需管理员权限。将 Codex、Git、elan 安装目录加入用户 PATH，重新打开 VS Code 终端后检查。PDF 提取库及 Lean 按需安装，不影响纯框架检查。

tests/research_benchmark/PROTOCOL.md 给出已知正确定理、错误候选和开放问题的对照评估方案。离线测试和模拟 Codex/Lean 仅验证控制逻辑；没有运行付费模型实验，没有证明此框架提高了开放问题求解率，也不保证生成理论贡献。人工批准是具体证据的责任确认，Python 的结构检查不能代替数学证明。

公开资料参考（2026-10-15 核对）：[OpenAI 公告](https://openai.com/index/sharing-ai-progress-in-mathematics/)、[成果仓库](https://github.com/openai/math)、[Comparator 范围说明](https://github.com/openai/math/blob/main/lean/ComparatorChallenges/README.md)、[Lean 工具链管理](https://lean-lang.org/doc/reference/latest/Build-Tools-and-Distribution/Managing-Toolchains-with-Elan/)。这里实现可公开描述的工作流，不推断其未公开训练或内部推理架构。
