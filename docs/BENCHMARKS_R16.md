# R16：冻结题库、独立金标准与隔离门禁

R16 建立六类可独立评分的小型任务集，校准的是证据检查和评分器。离线夹具通过不表示科研代理质量提高、开放问题已解决或密码协议已经安全。正式基准计数必须另有真实的操作系统隔离证据；目录分开、自报 `true`、提示词限制和普通进程的权限列表均不能代替读取拒绝验证。

## 先复用现有基准

| 现有材料 | 实际能力 | R16 的复用与边界 |
| --- | --- | --- |
| `tests/research_benchmark/cases.json` | 4 个公开整数样例：平方非负、符号错、模等式误用、线性查询泄漏 | 复用精确谓词和原 `engine.falsification.check_witness`；不复制第二个整数解释器，不把公开 expected 当作隐藏答案 |
| `scripts/discovery_benchmark.py` | 在 `[-3,3]` 中搜索精确见证，输出 `SEARCHED_NOT_FOUND / EXACT_COUNTEREXAMPLE` | 保留原 smoke 入口；有限搜索未发现反例不算普遍证明，也不测真实模型发现能力 |
| `tests/research_benchmark/supervision_cases.json` | 5 个合成已验收收据序列，覆盖支持工作偏移、改名重复、核心停滞及必要直接依赖、必要反例两个边界 | 复用原 `supervision_quality.assess_quality / from_ledger`；不新增第二套偏移检测器，不把 `ON_TRACK` 当作数学正确 |
| `tests/test_supervision_quality.py` | 使用生产接口核对上述正负例及重复、旧锚点、历史缺失、预算不变 | 继续作为系统回归；不合并为真实科研成功率 |

旧公开样例中的答案已经公开，不能追认为盲测。R16 的题目、金标准、评分器版本和来源分别钉住；生产控制器状态与个人科研预算不成为题库材料。

## 六类最小任务

| 类别 | 最小题目 | 校准目标 |
| --- | --- | --- |
| 论文或定理覆盖 | `BENCH-LIT-001` | 对照明确的原文位置或经审查的合成推导检查包含关系，缺前提或误称新颖性不能通过 |
| 精确数学反例 | `BENCH-CE-001` | 用原精确谓词检查证书；伪造见证或忽略原前提不能通过 |
| 安全漏洞 | `BENCH-SEC-001` | 检查明确的合成攻击与原模型对应，错误归约不能代替安全论证 |
| 未闭合障碍 | `BENCH-OPEN-001` | 评估量词、限制条件和未知声明是否准确，不因没有新证明自动判失败 |
| 研究偏移 | `BENCH-DRIFT-001` | 检查冻结主线、收据和证据的联系，必要依赖不能误判为无关工作 |
| 状态恢复 | `BENCH-REC-001` | 检查保留预算、未知结果停机和受控恢复，不能用重跑未知调用获得通过 |

六题是起始最小集。规格中的 30 题是后续目标，不用重复题目、重命名或缺少独立金标准的题目补足数量。合成教学题明确标记为合成材料，不假称来自某篇真实密码学论文。

## 公开输入与私有金标准

公开任务保存冻结目标、输入、允许工具、模型与资源上限、预期产物和来源文件。代理快照只能包含这部分内容；不得包含 oracle、参考答案、隐藏见证、评分细则或评价器私有路径。公开源码、测试夹具、版本控制历史本身如果已经暴露答案，就不能提供盲测保密性。

金标准由评价器侧显式登记，记录精确版本、任务输入 SHA、oracle SHA、评价器版本、审查者与原因；无独立金标准时状态保持 `PENDING_CURATION`。原任务文本和来源变动使旧登记过期，需要新版本及审查记录；不能悄悄改答案后继续使用旧认可。

`score_fixture` 是确定性评分器校准接口：即使正例判定正确，也固定返回 `NOT_ISOLATED` 和 `formal_counted=false`，科研质量增益保持 `NOT_MEASURED`。它不运行研究代理、不访问个人课题、不写科研主张或预算，也不会解除真实监督、Lean 或模型执行的既有阻断。

操作系统隔离探测必须区分公开输入可读、私有 oracle 不可读，并绑定实际进程、权限边界、输入及工具版本。探测失败、缺失或不支持的平台都不能进入正式计数；一次探测回执也不能授权另一进程、另一目录或后续模型运行。R16 的局部读取拒绝证据不等于完整网络、工具链或真实监督沙箱认证。

Windows 的局部探测由父进程临时模拟实际 AppContainer 子进程 token，调用内核文件接口核对公开可读及私有拒绝，并记录实际执行者。它不能写成“真实科研代理直接读取 oracle 已被阻止”，也不解除正式代理的 `NOT_ISOLATED`。固定探测 child、token 模拟与真实模型进程是不同的执行范围。

## 操作入口

```powershell
.\research.cmd benchmark list
.\research.cmd benchmark show --case BENCH-CE-001
.\research.cmd benchmark validate
.\research.cmd benchmark bundle --case BENCH-CE-001 --destination <new-public-bundle-directory>
.\research.cmd benchmark register-oracle --case BENCH-CE-001 --oracle-file <curated-oracle.json> --private-root <outside-controller-evaluator-directory> --reviewer <independent-reviewer> --reason "独立核对题目的原始材料、精确见证、输入版本和全部适用前提，并保留本次审查的责任记录。"
.\research.cmd benchmark validate --private-root <outside-controller-evaluator-directory>
.\research.cmd benchmark score-fixture --case BENCH-CE-001 --response <response.json> --private-root <outside-controller-evaluator-directory>
.\research.cmd benchmark history --case BENCH-CE-001 --private-root <outside-controller-evaluator-directory>
.\research.cmd benchmark diff --case BENCH-CE-001 --private-root <outside-controller-evaluator-directory> --from-version 1 --to-version 2
.\research.cmd benchmark isolation-status
```

未登记私有金标准时 `validate` 返回 `PENDING_CURATION`；六类都经独立登记后，评价器侧检查可以返回 `CALIBRATION_READY`，正式计数仍为 false。正常负答产生 `FAIL` 回执并返回退出码 0；缺材料、过期或非法输入为 `STALE_OR_INVALID`，退出码 2。查询与登记不会派发科研轮次。

`show / bundle / register-oracle / score-fixture` 可以显式选择 `--version`；`--dataset-root` 指向含 `manifest.json` 的题库目录，默认是 `evaluation/benchmarks`。私有登记目录必须在控制器和公开工作区之外，不能放到已被代理打开的根目录中。登记人不能与题目作者相同，原因至少 32 个字符。单项登记同时保存不可覆盖的 oracle 文件、版本记录和追加索引；`history / diff` 展示版本变化及责任人。没有登记独立金标准的公开任务，不会自动生成“已通过”答案。

## 固定的公开参考

本轮只读获取 GitHub 官方 Git 对象及 Google Research 的公开文本，未检出、安装、运行或复制第三方实现，未下载 PaperBench LFS 数据或执行其模型评分器。完整字节哈希与适配记录见 `outputs/R16/opensource-reference.json`。

- **PaperBench**：实际仓库路径为 [openai/frontier-evals/project/paperbench](https://github.com/openai/frontier-evals/tree/b78dab1da774a6456b1ed9c48c9ff194ee3ff36d/project/paperbench)，固定提交 `b78dab1da774a6456b1ed9c48c9ff194ee3ff36d`。[MIT 完整许可证](https://github.com/openai/frontier-evals/blob/b78dab1da774a6456b1ed9c48c9ff194ee3ff36d/LICENSE.md) SHA-256 为 `2c31cbfc07eff294f2a6ec1efcb4ddac1c78759201af7cdad1a4bc3802e1768f`。实际核对 `Judge.judge / Judge.grade`、`GradedTaskNode`、`score_from_children`、`run_judge`、`JudgeOutput.success`、JudgeEval 的 `calculate_judge_scores / compute_metrics`。参考执行、复现与评分的阶段分离和对评分器本身做正负例校准；不复制模型评分、GPU 调度或加权分数，也不把无效评分排除后产生的数字当作本地科研成功率。
- **ARA**：复核提交 `e52a925e9d03b4ada3008653e72f99b04116fca2` 的[最小过程树](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/examples/minimal-artifact/trace/exploration_tree.yaml)与[扩展过程树](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/examples/resnet-ara-example/trace/exploration_tree.yaml)。实际是 YAML 过程证据文档，没有可移植的评分函数。参考来源、失败原因及分支记录；`support_level` 不授予证明认可。[MIT 完整许可证](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/LICENSE) SHA-256 为 `25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`。
- **OpenAI Math**：复核固定且当前未变的提交 `1581d4cbdd69a0faf34b2089614fe2a814316a6a`，重读 [README](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/README.md)、[Lean 说明](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/lean/README.md)和[形式化工件索引](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/lean/formalization.yaml)。参考稿件、版本和不同验证阶段的区分；没有导入其数学结论或内部研究过程。[Apache-2.0 完整许可证](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/LICENSE) SHA-256 为 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。
- **Science One**：只参考 [Google Research 官方架构说明](https://research.google/blog/science-one-framework-a-verifiable-autonomous-research-framework-via-chain-of-evidence/)中的证据链和独立审计方法。官方将它描述为实验研究原型；本次没有核实可移植的完整官方源码仓库，因此没有虚构代码提交 SHA、许可证、内部调度或复现结果。

## 验证方式

```powershell
python -B scripts/discovery_benchmark.py
python -B -m unittest discover -s tests -p test_supervision_quality.py -v
python -B -m unittest discover -s tests -p test_benchmark_cases.py -v
python -B scripts/verify_r16_offline.py --output <outside-runtime-evidence-directory>
```

真实 Windows 入口验收使用临时复制的公开控制器，六类各一个正响应及一个错误响应，另验任务变更过期、OPEN 未解不判科学失败、快照不含 oracle、隔离失败不能正式计数。oracle 只生成在临时评价器侧，不写入真实 `D:\CryptoResearchController\state`，不启动模型、真实监督或 Lean，不对个人科研项目作科学裁决。

状态恢复题检查合成记录中的输入、已消费 run、冻结后像和禁止重派的回答；它不为真实运行的恢复过程发证。原控制器的崩溃恢复、预算高水位和未知结果门禁继续由原专项与全套回归覆盖。
