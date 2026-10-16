# R11：冻结目标下的版本化候选登记

R11 仅登记和检查研究候选，不调用模型，不导入固定问题，不建立科研尝试，也不修改下一轮任务。候选记录位于 `state/candidates/<project_id>/catalog.json`；现有项目、问题、主张、预算和恢复机制继续拥有原有权威。

## 命令与操作范围

在控制器根目录执行以下命令；从项目目录执行时可以省略项目参数。登记前，先通过原有 `problem import` 明确冻结的问题版本，或在项目 `research` 目录准备一个待核验问题草案。

```powershell
.\research.cmd candidate anchor <project>
.\research.cmd candidate list <project>
.\research.cmd candidate propose <project> --file <candidate.json> --reason "登记具体假设"
.\research.cmd candidate show <project> --id C-0001 --revision 1
.\research.cmd candidate revise <project> --file <new-revision.json> --expected-revision 1 --reason "明确改变了哪项假设"
.\research.cmd candidate status <project> --id C-0001 --status SCREENING --expected-revision 2 --reason "开始检查具体否决条件"
```

`propose` 不会覆盖已有 ID。修改假设、敌手模型、信任设置或来源时，必须使用显式 `revise` 和当前版本号。新修订保留旧版本，重新进入 `PROPOSED` 或 `CONDITIONAL`；不会沿用 READY 状态或证明结论。错误的预期版本号拒绝写入。

候选卡必须包含以下字段：

| 字段 | 含义 |
| --- | --- |
| `schema_version`, `id`, `title` | 版本 1；项目内稳定候选 ID；标题不作为身份 |
| `goal_anchor_id` | `candidate anchor` 返回的当前冻结锚点 |
| `problem_id`, `problem_version` | 项目内固定问题及精确版本；与草案路径二选一 |
| `problem_proposal_file` | 项目 `research` 目录内的合法问题草案；仍须核验、导入后才能准备尝试 |
| `hypothesis`, `nontriviality_argument` | 明确可证伪的构造假设及非平凡点 |
| `closest_prior_work` | 非空列表，每项为 `{source_id, check, full_text_checked}`，记录原文近邻及待核查点 |
| `falsification_gate` | 最小反例入口或直接覆盖判据 |
| `proof_obligations` | 固定问题全部证明义务 ID |
| `assumptions`, `immutable_constraints`, `domain`, `quantifiers`, `security_model` | 精确问题和模型边界，不能减少冻结前提、约束或改变量词、定义域 |
| `estimated_context_bytes` | 正整数上下文成本估计，不是预算授权 |
| `dependency_claims` | `{id, revision, spec_sha256}` 列表，绑定现有主张的精确版本 |
| `evidence_refs` | 项目内允许研究、证明、文献或实验目录中的证据路径列表 |
| `failure_scope`, `restart_conditions` | 候选失败的适用范围及允许重新提出的条件 |
| `parent` | 可选 `{id, revision}`；固定父候选的精确版本，拒绝循环及跨目标关系 |

模型、量词等数值或文字相符只表示输入契约一致，不是密码学等价性证明。阈值检查只核对冻结字段的精确结构，不能理解任意自然语言或代数表达式并证明腐化界的强弱；精确假设仍须由用户冻结。引入额外安全模型或假设会成为 `CONDITIONAL`，本轮不提供自动独立裁决来使其生效。减少固定腐化门槛不能伪装成原目标的候选。

## 状态、去重与审计

状态词汇保留 `PROPOSED / SCREENING / READY_FOR_ATTEMPT / ACTIVE / REFUTED / COVERED / RETIRED / CONDITIONAL`。命令不允许手动设为 `ACTIVE` 或声明 `PROVED`。`READY_FOR_ATTEMPT` 只表示调度前置条件满足，仍显示 `UNREVIEWED_CANDIDATE`、`positive_basis=false` 和 `NOVELTY_PENDING`；R11 不会创建实际尝试。它不能替代后续的论文级查新或独立科学审查。

READY 前，现有主张图必须确认每个依赖版本及 SHA 仍然匹配，且达到 `INDEPENDENTLY_REVIEWED`。未核实、失效或发生版本变化的定理不能由候选卡自证。来源变更、冻结目标变更、固定问题丢失等情况会拒绝 READY 或在只读输出中列出阻断原因。

活跃上限计算每个候选最新版本中的 `SCREENING / READY_FOR_ATTEMPT / ACTIVE`，默认最多 3 个。可选 `config/candidate_policy.json` 格式为 `{"schema_version":1,"max_active_candidates":3}`，只能将上限收紧至 1—3。已否决或退役候选释放名额，历史保留；独立候选及已有子候选不会被祖先的否决自动改写。

否决或覆盖时必须给出范围、证据和重启条件，不能直接重开同一终局版本：

```powershell
.\research.cmd candidate status <project> --id C-0001 --status REFUTED --expected-revision 2 --disposition <disposition.json> --reason "明确失败边界"
```

`disposition.json` 包含 `scope`、`restart_conditions`、`evidence_refs`。否决仅是登记的分支裁决，不能升级共享引理或修改已有科学证明状态。

去重使用 NFKC、大小写和空白归一化后的精确科学内容及问题内容。只换标题、候选 ID 或上下文成本不能产生第二条候选路线；旧的已否决候选也参与去重。该检查不能判定任意数学表述是否同义。完整语义等价和创新性判断仍须独立审查。候选登记完全不申请路线或独立尝试预算。

候选和状态操作都追加带前序哈希的事件。目录中的物化记录必须能够由事件重放得到；事件哈希、历史版本、父节点和目标绑定不一致时停止。CLI 复用原有项目锁及科研执行锁，目录更新还使用候选锁和原子 JSON 写入。普通文件哈希只能检测局部意外损坏，不宣称能够抵抗用户同时重写全部本地权威。

## OpenSource 参考与替代原则

仅参考结构和职责划分，未复制、安装或执行上游代码，不引入其模型调用、解释器或排名成功标准。以下提交和完整许可证文件的字节哈希已通过 GitHub 官方 API 与原始文件只读核对。

- [LLNL Co-Scientist `app/agents.py`](https://github.com/llnl/open-ai-co-scientist/blob/c8342c0e28474d134f80caa6b9668470ebf55258/app/agents.py)，提交 `c8342c0e28474d134f80caa6b9668470ebf55258`。参考 `GenerationAgent.generate_new_hypotheses`、`ReflectionAgent.review_hypotheses`、`EvolutionAgent.evolve_hypotheses` 和 `ProximityAgent.build_proximity_graph` 的生成、批评、父节点及近邻职责。[MIT 许可证](https://github.com/llnl/open-ai-co-scientist/blob/c8342c0e28474d134f80caa6b9668470ebf55258/LICENSE)，完整文件 SHA-256 `d9c21bfd91791529b4a75ffe18b33ad46da74d7e9100f148c16697952f22f380`；源文件 SHA-256 `7b9e8beb1490288da48be4af6bccc1642a570b14d69d97bce27b98805ea57379`。上游生成仅提示避免重复并保证 ID 唯一，进化中的相似度检查是注释示意；本地使用确定性契约去重，不把模型打分当作原创性结论。
- [AIDE `aide/journal.py`](https://github.com/WecoAI/aideml/blob/1d8ec4026c67729443294c8b5c0907242d0de38c/aide/journal.py)，提交 `1d8ec4026c67729443294c8b5c0907242d0de38c`。参考 `Node`、`Node.__post_init__`、`Node.stage_name`、`Journal.append` 和 `Journal.get_best_node` 的节点身份、父子关系与历史集合。[MIT 许可证](https://github.com/WecoAI/aideml/blob/1d8ec4026c67729443294c8b5c0907242d0de38c/LICENSE)，完整文件 SHA-256 `723b16d1701dfb2d280d229ff84f3056df65b6b00ad8419ec6cb7da2fdd8f616`；源文件 SHA-256 `6539cac937ef65af1ee6f05c6434ec66c2d3c268460c74f13eba4fa7bf9b6020`。本地以不可变候选输入版本和已钉住的父版本替代可执行代码及指标节点，不继承代码执行或按指标认定科学成功的机制。

## 离线验收

```powershell
python -B -m unittest discover -s tests -p test_candidate_contract.py -v
python -B scripts/verify_r11_offline.py --output <outside-runtime-evidence-directory>
python -B -m unittest discover -s tests -v
python -B research.py check all
```

真实入口模拟只复制公开控制器代码和根配置，在含空格的临时目录创建两个同名玩具项目。子进程的 Python 审计钩子阻断网络访问和任何嵌套进程执行，核对未发生调用，再保存正常树、重复拒绝、活跃上限拒绝、未审主张拒绝、修订历史和错误边界等 JSON。临时样例的项目状态、预算、问题、主张和配置前后逐字节相同；候选目录是唯一新增权威记录。本轮不运行个人科研、真实监督或 Lean。
