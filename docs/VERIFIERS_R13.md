# R13：绑定精确命题的核验适配器

R13 对既有整数谓词和 Lean 输入检查增加统一请求与工具回执，不建立新的证明接受状态。验证元数据只写入 `state/candidates/<project>/verification/`；候选目录、主张图、问题、GOAL、STATE 和预算保持原有权威。真实 Lean、监督和模型调用继续阻断。

## 准备冻结请求、执行和复查

```powershell
.\research.cmd candidate verify-prepare <project> --id C-0001 --claim LEMMA-1 --adapter integer-v1 --bounds -3 3 --max-cases 10000 --max-seconds 3 --wall-timeout 5 | Set-Content -Encoding UTF8 <request.json>
.\research.cmd candidate verify <project> --request <request.json>
.\research.cmd candidate verification-show <project> --request-id <V-id>
.\research.cmd candidate verification-recheck <project> --request-id <V-id>
```

准备、展示和复查均只读。`verify` 只保存冻结请求、派发开始见证和工具完成回执，不执行科研轮次。项目参数沿原目录自动解析；不存在把任意命令、Python 文件或待执行符号程序交给适配器的参数。

请求通过 `VerificationRequest` 的 JSON 对象表达，Python 入口为 `candidate_search.verifiers.interface.prepare_request(...)`、`verify(project, request)`、`show(project, request_id)` 和 `recheck(project, request_id)`。

每项请求固定以下内容：

- 原项目身份、目标锚点及 GOAL 内容 SHA。
- 候选 ID、修订和输入契约 SHA；原固定问题 ID、版本和问题 SHA。
- 原主张 ID、修订、完整声明 SHA 和依赖版本；现有审查历史必须有效。
- 项目输入、证据、Lean 源码及依赖配置等实际来源的精确内容 SHA。
- 本地适配器、固定整数工作进程、既有算术解析器、Lean 输入检查和进程生命周期代码的 SHA，以及 Python 版本。
- 注册的机器谓词、精确声明名和资源上限。

`request_id` 是完整冻结请求的 `V-<SHA256>`。准备后任何相关主张、候选、问题、来源、目标或工具实现改变，旧请求都无法静默套用新输入。历史回执保留，可通过 `verification-show` 查看 `fresh=false` 及失效原因；复查或执行过期请求返回 `FAILED`。不得删除旧回执来伪造从未核验的状态。

## 工具等级和退出码

统一词汇为 `EXECUTED / COUNTEREXAMPLE_FOUND / NO_COUNTEREXAMPLE_WITHIN_BOUND / TOOL_PASSED_AUDIT_PENDING / UNSUPPORTED / FAILED`。它们都是工具等级，不能作为正式证明、创新性或完整安全模型的接受等级。

| 状态或字段 | 作用与限制 |
| --- | --- |
| `COUNTEREXAMPLE_FOUND` | 保存原机器谓词的精确整数见证；仍须独立检查它对自然语言命题及候选的适用范围 |
| `NO_COUNTEREXAMPLE_WITHIN_BOUND` | 只在记录的点数、区间和时间界内未发现反例，不能推出全称命题已证 |
| `UNSUPPORTED` | 未支持的适配器、没有机器谓词或 Lean 不可用；保留原工具原因，不下载工具 |
| `FAILED` | 请求过期、输入非法、执行失败、资源限制、未知中断或证书复查失败 |
| `positive_basis=false`, `scientific_acceptance=false` | 本轮所有回执都不能直接成为正面科学接受依据 |
| `statement_match=REQUIRES_INDEPENDENT_REVIEW` | 工具输入与自然命题、安全定义、量词及假设的对应仍须独立审查 |

`verify` 和 `verification-recheck` 对 `FAILED / UNSUPPORTED` 返回退出码 2，并输出完整结构化 JSON。其他正常工具结果返回 0。历史展示本身可以返回 0，但必须检查其中的 `fresh` 和工具状态；“成功显示文件”不表示结果仍适用。

## 精确整数适配器

`integer-v1` 复用原 `engine.falsification` 的受限 AST 解析和精确见证检查，支持整数多项式、有限模算术关系及可表达的简单不变量。不使用 `eval`，不接受函数调用、任意 Python、浮点统计或自定义代码。复杂密码学模拟游戏、分布界与不可表达的安全语义不属于该接口的自动判定范围。

实际算术检查只在固定可信工作进程中进行：

```text
<current-python> -I -B <controller>/candidate_search/verifiers/trusted_integer_worker.py
```

标准输入只接受机器谓词及区间、点数和时间界的 JSON；工作目录为空临时目录，环境不继承 API 密钥、PYTHONPATH 或用户工具配置。控制器复用原 `ProcessTree` 管理生命周期和强制墙钟超时。硬上限为 10000 个整数点、3 秒算术搜索和最多 15 秒工作进程墙钟；输出也有长度限制。

这些限制只约束可信数据处理进程的输入、资源和生命周期，`os_deny_read_or_network_isolation_certified=false`。本轮没有声称具备操作系统层面禁止文件读取或网络的完整沙箱，不允许据此开放生成代码执行。

反例回执记录具体赋值、边界、实际测试点数和原谓词。控制器在保存前调用原纯函数 `check_witness` 再验一次；`verification-recheck` 使用同一原谓词复查证书，不重启工作进程。真命题在 10000 点未出现反例仍只得到 `NO_COUNTEREXAMPLE_WITHIN_BOUND`，不会写入 `PROVED`。

## Lean 适配器保持阻断

```powershell
.\research.cmd candidate verify-prepare <project> --id C-0001 --claim LEMMA-1 --adapter lean-v1 --proof-file proofs/lean/Check.lean --declaration exact_target | Set-Content -Encoding UTF8 <lean-request.json>
.\research.cmd candidate verify <project> --request <lean-request.json>
```

`lean-v1` 只调用原只读 `formal_verifier.preflight`。原工具链固定要求、来源哈希和未完成证明标记检查继续复用；存在 `sorry / admit / sorryAx` 等占位会拒绝。未安装 elan 时输出统一 `UNSUPPORTED`，同时保留原 `UNAVAILABLE` 记录。有工具路径且静态输入通过时仍输出 `UNSUPPORTED / ISOLATION_UNCERTIFIED`，`execution_started=false`。不会调用 Lean/Lake、版本探测、下载工具或执行项目配置。

明显的 `theorem ... : True` 目标会产生 `TRIVIAL_TRUE_DECLARATION` 风险提示，但该静态提示不是完整 Lean 解析器。自然语言量词、假设、声明类型、公理、导入依赖和实际密码学目标是否对应，全部保持独立审查待办。即使别处能够编译这条 `True`，也不能认证原有非平凡命题；本轮从未真实编译该样例。

回执中的固定 toolchain、源码和声明哈希表示验证对象，工具版本显示未探测，不把工具链文件里的字符串冒充真实执行版本。`TOOL_PASSED_AUDIT_PENDING` 是保留的统一工具词汇，本轮没有通过配置、环境变量或 CLI 绕过真实 Lean 阻断的入口。

## 恢复、权威与复现

写操作沿原路线锁、科研执行锁和候选锁串行执行，再加验证记录锁。每次首次执行先持久保存冻结请求和 `STARTED` 见证，再生成完成回执。回执绑定请求、见证、内容哈希和完整工具结果。

同一完整请求已有可信完成回执时只返回旧回执，不再次执行。`STARTED` 已存在却缺少完整回执时，返回 `UNKNOWN_LOCAL_VERIFICATION_OUTCOME`，禁止自动重试；请求缺失、见证损坏或回执冲突也要求保留记录并审计。配对文件只能检测局部丢失或冲突，不能抵抗用户同时删除、替换或回滚全部本地权威。

回执包含来源、工具版本、证据文件、原请求的复现命令和范围限制。本轮没有 `apply` 命令，不自动把反例、统计结果或工具结果写成主张结论。正式证明状态继续完全服从既有 `claim_graph` 独立审查流程；候选的归属或工具运行成功不能替代原有证据要求。

## 固定公开参考

所有上游仅参考职责和材料组织，未复制、安装、检出工作副本或运行代码；以下完整可用文件从 GitHub 官方 Git 对象只读核对，完整记录随 R13 验收工件提供。

- [Numina-Lean-Agent `tutorial/usage.md`](https://github.com/project-numina/numina-lean-agent/blob/1c9af8a52e715f22fede766425ba3d3b95526132/tutorial/usage.md)，提交 `1c9af8a52e715f22fede766425ba3d3b95526132`，源文件 SHA-256 `52d2ce4626aed6c5f48b434ee9986dcf9f79e8cfc38ec97b4a2eec73392e2b34`。参考逐题目标、结果 JSON 和工具轨迹的组织方式，不引入 Claude 调用、权限绕过、技能加载或任意项目执行。[该版本 README](https://github.com/project-numina/numina-lean-agent/blob/1c9af8a52e715f22fede766425ba3d3b95526132/README.md) 声明 MIT，但整棵已跟踪树中没有完整 LICENSE/LICENCE/COPYING 文件；许可证全文 SHA 记录为空，不猜测或补造，不复用代码。
- [OpenEvolve `Evaluator`](https://github.com/algorithmicsuperintelligence/openevolve/blob/a1e9d91eecde612f0efc8e8e31f59b36998248c0/openevolve/evaluator.py)，沿 R12 固定提交 `a1e9d91eecde612f0efc8e8e31f59b36998248c0`，源文件 SHA-256 `0b14a5b3b145f4b2d808aad3ef3dcea830d22f69d9113400abac62f1d74075fb`。参考 `evaluate_program`、`_cascade_evaluate` 和 `_create_cascade_error_context` 的廉价前置检查、阶段失败和结果保留；不加载项目 evaluator 模块或采用经验指标证明安全性。[Apache-2.0 完整许可证](https://github.com/algorithmicsuperintelligence/openevolve/blob/a1e9d91eecde612f0efc8e8e31f59b36998248c0/LICENSE) SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。
- [OpenAI Math](https://github.com/openai/math/tree/1581d4cbdd69a0faf34b2089614fe2a814316a6a)，提交 `1581d4cbdd69a0faf34b2089614fe2a814316a6a`。核对其不同验证阶段和修订组织；[lean/README.md](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/lean/README.md) SHA-256 `292ff9d539f494158dfbf68d989ba85a82782a4343b2fe43088f8fa62525bf1b`，[lean/formalization.yaml](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/lean/formalization.yaml) SHA-256 `5a8a164259591208886cd018416e61552665265ec9e20cff636f9d51117c2278`。[Apache-2.0 完整许可证](https://github.com/openai/math/blob/1581d4cbdd69a0faf34b2089614fe2a814316a6a/LICENSE) SHA-256 `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`。只借鉴论文与形式声明分级关系，不移植数学内容或推断未公开模型机制。
- [原 LeanDojo README](https://github.com/lean-dojo/LeanDojo/blob/7a9f600b250a89a62e991c05ffe81ba033018e6e/README.md)，提交 `7a9f600b250a89a62e991c05ffe81ba033018e6e`，SHA-256 `ea303b9f712b2511790986ae7f0f6ba3eba20c455538b9ef8b918572783c77c7`。已确认原库弃用提示，仅作历史接口资料，不作为新依赖。[MIT 完整许可证](https://github.com/lean-dojo/LeanDojo/blob/7a9f600b250a89a62e991c05ffe81ba033018e6e/LICENSE) SHA-256 `886299eb430744b244f935c5e84b8813c8d275c42a4dc558d11048d20468f630`。

共享附录中的 PaperBench 和 Science One 只提供当前讨论背景；本轮没有实现其评分或后续基准功能，也没有宣称复刻完整系统。

## 离线验收

```powershell
python -B -m unittest discover -s tests -p test_verifier_adapters.py -v
python -B scripts/verify_r13_offline.py --output <outside-runtime-evidence-directory>
python -B -m unittest discover -s tests -v
python -B research.py check all
```

真实 Windows `research.cmd` 样例在含空格的临时目录创建精确玩具命题。错误多项式恒等式生成并复查机器反例；真谓词在 10000 点搜索后仍不标证明；未执行的 elan 标记和缺失工具环境分别复现隔离未认证及 `UNAVAILABLE`，明显弱化成 `True` 的声明仍待语义审查。源码内容和主张版本变化会使旧回执失效。

样例审计钩子只允许固定 Python、`-I -B`、固定可信工作进程路径及其源码 SHA、空工作目录和最小环境；其他进程和全部网络操作拒绝并记录。最终要求仅有预期整数工作进程、没有拒绝记录、模型/监督/Lean/网络执行全部为零。每项适配器操作前后逐字节比较临时项目、原主张、候选目录、预算和配置。明确的源码改动及原 `claim import` 是故障夹具输入，不是适配器自动修改。
