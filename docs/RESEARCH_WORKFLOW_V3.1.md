# v3.1 科研流程与使用说明

## 一、这次落实的五项要求

1. 新项目由模板生成固定文档，用户主要提供目标、想法和论文原文。
2. 新想法支持替换主任务或补充当前主线，版本固定且可追踪。
3. 文献判断核对实际构造、定理、证明条件和成本；作者声明只触发核查。
4. 主贡献要求非平凡密码/安全理论结果；工程工作绑定具体证明或复现义务。
5. 理论贡献和正确性审查完成后才能进入系统实现与系统测试。

相关工作收录、比较基线、贡献覆盖和路线否决分别处理。相关性强且功能可比的论文可以进入基线；否定贡献或改变主线需要更充分的技术依据。理论贡献也可以来自已有原语下的新协议、新安全定理、约化、复杂度结果或结构性障碍，不要求每轮发明新原语。

## 二、新建项目，哪些文档由谁生成

根目录运行：

```powershell
.\research.cmd new my-project --goal-file D:\Materials\goal.md --title "研究主题" --profile generic
.\research.cmd ready my-project
.\research.cmd run my-project
```

新项目首先进入 INTAKE，读取目标并建立最小研究命题。已有两个项目保留现阶段和下一任务，无需重新初始化。

| 类别 | 自动生成的文件 | 用户或代理的后续职责 |
| --- | --- | --- |
| 项目入口 | PROJECT.json、AGENTS.md、RESEARCH_PROFILE.json | 默认可用；按领域增补要求 |
| 研究输入 | GOAL.md、inputs/CONTEXT.md、NOTATION.md、CONTRIBUTION_TARGET.md | 用户提供个性目标、限制与符号；未知部分先留待定 |
| 想法管理 | ideas/INDEX.json、TEMPLATE.md | 用户通过命令新增、更新、选中或附加 |
| 状态与证据 | STATE、CLAIMS、FAILED_PATHS、BASELINES、GATES、DECISION_LOG、PROOF_OBLIGATIONS | 代理按真实结果维护 |
| 理论贡献 | research/CONTRIBUTION.md、ROUND_REVIEW_TEMPLATE.json | 形成明确命题、机制、差异、证明义务和每轮回执 |
| 文献核查 | queries、SEED_PAPERS、RELATED_WORK、NOVELTY_GAP、TECHNICAL_REVIEW_TEMPLATE.json | 论文身份与结论来自原始材料 |
| 证明与必要实验 | proofs、experiments 下的模板和说明 | 理论阶段只做决定性证明和最小数学核查 |
| 报告与论文 | reports/TEMPLATE、paper/CLAIM_EVIDENCE_MAP | 贡献逐条关联真实证据 |

research/INTAKE.md、ROUND_REVIEW.json、具体文献技术记录由首次或对应研究轮实际生成。THEORY_READINESS.json 仅在用户确认理论审查后生成，模板不预填批准状态。

## 三、研究中加入新的想法

### 3.1 新增与更新

```powershell
.\research.cmd ideas add secagg-research --title "新候选引理" --file D:\Materials\idea.md
.\research.cmd ideas list secagg-research
.\research.cmd ideas update secagg-research --id IDEA-0001 --file D:\Materials\idea-v2.md --reason "补充关键条件与反例"
```

不要直接编辑已登记的 v001.md；摘要检查会发现。通过 update 生成新版本，保留旧版本和修改原因。

### 3.2 补充当前主线

```powershell
.\research.cmd ideas attach secagg-research --id IDEA-0001
.\research.cmd run secagg-research
```

attach 固定当前最新版到 STATE.supporting_ideas；保留主任务、路线、阶段和预算。之后每轮提示词都会包含该版本，代理按它与当前主张的依赖关系安排研究。update 之后需要再次 attach 才启用新版本。

移除补充输入：

```powershell
.\research.cmd ideas detach secagg-research --id IDEA-0001
```

### 3.3 明确改为新的主任务

```powershell
.\research.cmd ideas select secagg-research --id IDEA-0001 --route C/PIWA
```

select 会更新主任务；同一数学路线沿用原路线编号，预算继续累计。新增想法与补充想法都不会自行放宽 GOAL。

## 四、文献怎样影响研究

公共规则位于 method/02_LITERATURE_NOVELTY.md 与 method/12_TECHNICAL_LITERATURE_REVIEW.md。每项关键核查保存到 literature/technical_reviews，绑定具体论文版本、文件摘要和项目主张，比较以下六项：功能、敌手、假设、输出接口、参数范围、完整成本。

| 核查结果 | 处理 |
| --- | --- |
| 只有作者声明或缺原文 | 登记待核查，暂停相应首次性表述，继续可独立推进的主线 |
| 相关、功能可比 | 加入相关工作或有条件的基线，不据此否决贡献 |
| 部分重合 | 修订受影响子主张，保留其余研究问题 |
| 实际完全覆盖 | 提交完整技术映射、包含/约化与代价，限定影响范围 |
| 同前提下矛盾 | 给出精确被否定命题、共同前提和决定性见证 |
| 假设或功能不可比 | 保存差异，不能登记为全面覆盖 |

自动否决/转向还要求该受影响主张确实是核心路线必要条件。预算耗尽、证明暂未闭合、工具失败、摘要相似均不能独立触发科学否定。证据不完整时追加有依据的任务或暂停，不虚构失败定理。

## 五、理论质量怎样约束

全局配置在 config/research_policy.json；如需项目例外，在底座 config/projects/项目名.json 的 research_policy 中覆盖。核心逻辑位于 research_quality.py。

每轮 research/ROUND_REVIEW.json 绑定运行编号，明确核心问题、理论义务、非平凡性依据、任务类别、贡献类型与本轮变化的证据。没有新证据可以如实使用 NO_PROGRESS，无需编造定理。

候选主路线必须给出精确性质、核心机制、最相近成果、标准组合无法直接推出的理由及证明义务。改背景、组合现成模块、缓存、参数调优、微基准和系统集成作为工程支持登记。连续两轮只做前期支撑，默认触发任务复评。

允许的主要理论贡献包括密码原语、安全定义、协议构造、安全定理、约化/分离、复杂度定理、下界/不可能性。证明未闭合时保留条件性状态；接口检查不把它提升为已证明。

## 六、理论通过后才写系统代码

### 6.1 理论阶段

未获理论许可时，IMPLEMENTATION、SYSTEM_TEST、EXPERIMENT 阶段在模型调用前被拦截。代理不能靠把 GATES 写成 PASS 自行进入系统开发。

前期确有必要的数学核查只允许放在 proofs/checks 或 experiments/math_checks。先写 MATH_CHECK_PLAN.json，说明待检命题、为何需要代码、成功/失败标准、文件与时间预算。默认每轮最多两份新增/修改代码、合计160行；计划的单次时间预算最多10秒，执行时应使用相应工具超时。文件范围和行数由程序检查，执行器另有单轮总超时。

原有结构、数据完整性和准确代数检查继续运行。新写完整协议、服务、接口、容器、集成测试或性能基准需要先通过理论门禁。

### 6.2 用户确认理论审查

查看当前状态：

```powershell
.\research.cmd theory status secagg-research
```

完成审查后，用户在终端执行下列命令；文件名替换为真实证据：

```powershell
.\research.cmd theory approve secagg-research --claim SEC-CL-NEW --contribution research/CONTRIBUTION.md --correctness proofs/MAIN_THEOREM.md --novelty literature/NOVELTY_GAP.md --reviewer "实际审查者" --reason "已核对贡献、最相近原文和完整正确性证明"
```

涉及新安全结论时同时指定 `--security proofs/SECURITY_PROOF.md`。这条命令记录用户的审查确认，绑定目标、路线、想法、用户输入、关键模型文件和证据摘要。它不要求用户修改原始项目已有结构，所需证明文件须真实存在。局部主张获批只支持该主张的系统实现，其他开放问题继续保留。

随后明确进入系统阶段：

```powershell
.\research.cmd ready secagg-research --phase IMPLEMENTATION --task "仅实现已批准主张 SEC-CL-NEW 对应的协议模块，固定接口与验收标准"
.\research.cmd run secagg-research
```

证据或关键输入变更后许可失效；先返回理论阶段修订。撤回许可：

```powershell
.\research.cmd theory revoke secagg-research --reason "新反例要求重新审查"
.\research.cmd ready secagg-research --phase PROOF --task "复核新反例，修订受影响定理并闭合原有正确性缺口"
```

## 七、哪些文件真正控制提示词

每轮加载公共 method/00～16、领域 profiles、项目 AGENTS/continue、RESEARCH_PROFILE 的读取材料、选中的主/补充想法与输出回执契约。本更新接入了公共 prompts/stages 与项目同名阶段文件。audit 使用 REVIEW 阶段；项目 independent_review.md 和 NOVELTY 阶段 novelty_audit.md 也会加载。

预览最终提示词，无模型调用、无状态更新：

```powershell
.\research.cmd prompt secagg-research
.\research.cmd prompt secagg-research --output D:\Materials\prompt-preview.txt
```

输出文件已存在时拒绝覆盖。该内容包含项目材料，应按个人研究资料保存。

## 八、更新与个人数据

本次更新包没有 projects、config/projects、state、论文、登录配置或 .git。更新器只替换清单内的框架文件，保留现有模型、预算默认和领域注册表，合并个人目录忽略规则，新增质量配置；已有质量配置会保留。运行中的项目锁会阻止更新。

先 stop 并等当前轮完成。解压更新包到独立目录，运行 apply_update.py --target D:\CryptoResearchController --apply。框架旧文件备份到 backups/framework-update-时间；检查失败时自动恢复。--rollback 可按备份目录恢复，更新后的文件有新改动时会拒绝直接覆盖。

已有个人项目不重新生成文档、不重写状态；下一研究轮会按新提示契约生成质量回执。新增输入文档只由新项目模板生成，旧项目可继续通过 ideas 命令提供材料。

个人目录被 .gitignore 忽略后，个人报告和状态仍在本地保存，框架 Git 提交不再包含它们；需要自行备份个人项目及运行证据。
