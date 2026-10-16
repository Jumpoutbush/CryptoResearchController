# 六、开发轮次跟踪表

**注意：下面 20 项初始均为未开始。** Codex 开发完成后，由操作者依据测试证据更新状态；不能因为写出了计划文档就勾选完成。

| 轮次 | 内容 | 状态 | Git 提交 | 真实测试回执 | 未闭合缺陷 |
| --- | --- | --- | --- | --- | --- |
| R01 | 监督契约/快照 | DONE | 4b406f92f39b0851101da7b318df4ada01e5f814 | 专项24/24；全量344：343通过/1原平台跳过；check all与doctor --offline退出0 | 无本轮未闭合缺陷；运行链后续接入另按R02—R05验收 |
| R02 | 触发/账本 | DONE | 原实现7257e07；兼容补充ef4ce45cbab272dcb4a4e9724850d691919dd8aa | R02专项50/50；原生全量394：393通过/1平台跳过；check all/doctor退出0 | 无本轮未闭合缺陷；外部账单不保证恰好一次，真实指南应用另按R04验收 |
| R03 | 只读执行 | DONE | 1bfad1bc14608777f8922ae0f9c6ffb801538827 | 专项29/29；真实入口6步离线验收；全量423：422通过/1原平台跳过；check all与doctor退出0 | 按附录仅完成Fake离线验收；真实OS隔离未认证，Codex后端阻断，不可真实上线 |
| R04 | 指南应用 | DONE | 03cb2c2812ca0263fccff42596db893a01b921ab | 专项28/28及门禁补充1项通过；真实入口10步；全量451：450通过/1原平台跳过；旧项目prompt逐字一致 | 真实Codex后端仍阻断；Fake只限临时样例；watch自动消费/应用另按R05验收 |
| R05 | 监督集成 | DONE | 1695bddbf4e9cfe633fe96bf1bb78bec3fe967ab | 专项20/20；原生run/watch/双进程及杀进程恢复通过；全量471：470通过/1原平台跳过；check all/doctor退出0 | 仅离线验收；真实Codex仍阻断，Fake只限注册临时样例；R06另行开发 |
| R06 | 图谱投影 | DONE | a5785130a7816c6739899e37afac9ec504ea2e2c | 专项27/27；双项目原生入口24步；全量498：497通过/1原平台跳过；check all/doctor退出0 | 本轮只读投影已验收；原文页码/失效事件/检索/跨项目复用另按R07—R10；真实监督后端门禁未变 |
| R07 | 原文溯源 | TODO | — | — | — |
| R08 | 失效事件 | TODO | — | — | — |
| R09 | 证据检索 | TODO | — | — | — |
| R10 | 跨项目记忆 | TODO | — | — | — |
| R11 | 候选模型 | TODO | — | — | — |
| R12 | 搜索预算 | TODO | — | — | — |
| R13 | 数学核验适配器 | TODO | — | — | — |
| R14 | 密码学安全审查 | TODO | — | — | — |
| R15 | 分支收束 | TODO | — | — | — |
| R16 | 评估数据集 | TODO | — | — | — |
| R17 | 离线回放 | TODO | — | — | — |
| R18 | 科研指标 | TODO | — | — | — |
| R19 | 影子策略 | TODO | — | — | — |
| R20 | 可观测/发布 | TODO | — | — | — |

推荐状态：`TODO`、`IN_PROGRESS`、`BLOCKED`、`TEST_FAILED`、`DONE`。`DONE` 仅在有成功执行证据和提交哈希时使用。

## 本地核查（2026-10-16）

已先读取 00_INDEX，并仅执行 R01。原 v3.3/v3.4 工作区修改保留；已有相似实现不作为
R02—R10 验收依据。R01 新接口、规格差异和回滚范围见 `../SUPERVISION_R01_CONTRACTS.md`。
本轮仅新增契约、只读快照、准备配置与离线测试，没有接入运行链或消费真实模型预算。
Git 工作区尚有之前的未提交实现，本轮不将基线提交哈希冒充新功能提交。

R01 最终回归：`python -m unittest discover -s tests -v`，344 项、127.230 秒，退出 0。
其中唯一跳过项为既有 POSIX 模拟可执行程序集成测试；24 项新增 R01 专项均未跳过。
专项前先验证缺失模块、快照超限和非法字段等失败用例，再实现与复核修补。
三个实际项目的只读快照均通过结构校验，未建立或改写任何项目账本。
最终交付回执与补丁保存在本次 Codex 会话的 `outputs/R01/`；框架说明见上文路径。

## R01 本地提交回执（2026-10-16）

用户已明确授权本地提交。此前已验证的监督与知识图谱依赖先独立保存为
`9ad44963082e0b6180b53f71e79d26fe93831647`，随后 R01 独立提交为
`4b406f92f39b0851101da7b318df4ada01e5f814`（Add bounded supervision contracts and read-only snapshots）。
两项提交均不包含私人项目、状态、预算账本或日志；未推送。
上述 IN_PROGRESS/未提交说明是前次回执的历史记录，现在已具备实测证据和真实提交，R01 标记 DONE。

## R02 本地验收与提交回执（2026-10-16）

R01 本地提交和本表更新完成后，才进入 R02。实现提交为
`7257e070c20af2b563197c9b748463797a6c40d1`
（Add durable supervision events and shared-budget reservations）。
本轮变更 12 个控制器、测试及文档文件，不包含私人项目或运行数据。

- `python -B -m unittest discover -s tests -v`：375 项，210.842 秒，退出 0；374 通过、
  1 个原有 POSIX 模拟可执行程序集成测试在 Windows 跳过。
- 最后仅把既有重复测试补强为同 ID 连续三次重放，未再改生产代码；随后执行
  `python -B -m unittest discover -s tests -p "test_supervision_trigger*.py" -v`，
  31 项全部通过，52.007 秒，退出 0。
- `python -B research.py check all`、Windows `research.cmd check all`、
  `research.cmd doctor --offline`、根目录 pending 与项目目录 status 原生命令均退出 0。
- 正常合并、队列写失败保留科研、预留/完成确认中断、输入丢失、真实双进程竞争和
  持锁进程终止恢复均由离线测试覆盖。先复现失败再修复，证据留在本地交付目录。

复用原路线计数、复评判定及监督成本余额；新协议默认关闭，启用时本轮只排队。
843 个私人项目、覆盖配置、状态和日志文件的路径集合及 SHA-256 与开发前完全一致。
GOAL、STATE、预算、研究历史、门禁和证明结论均未改变；未执行真实付费轮次，未推送。
说明见 `../SUPERVISION_R02_EVENTS.md`；本次会话的交付目录为 `outputs/R02/`。
R03 仍为 TODO，不能将旧版相似执行器直接算作 R03 已验收。


## R02 崩溃恢复兼容补充回执（2026-10-16）

根据新增 UPGRADE_20261016/02_R02_CRASH_RECOVERY_ADDENDUM.md 增量核查；
原有 R01/R02 提交与上述历史回执完整保留，不导入附件中的旧追踪表。
本次实现提交 `ef4ce45cbab272dcb4a4e9724850d691919dd8aa`，R01 schema、ID、快照模块及配置原字节未变。

- 触发/预留专项26项、真实runner＋模拟Codex验收7项、崩溃/原生Windows专项17项，合计50项全部通过。
- 原生环境 `python -B -m unittest discover -s tests -v`：394项，204.017秒，退出0；
  393通过、1个既有POSIX平台测试跳过，R02新增测试无跳过；原生junction与符号链接场景通过。
- 首次沙盒全量有4项环境访问错误（junction与临时Git仓库），未改测试或R01；
  junction原生单测通过后，在原生环境完整重跑并取得上述成功结果。
- `python -B research.py check all` 三个项目通过；原生 `research.cmd doctor --offline`
  和 `research.cmd supervise pending --dry-run` 均退出0且返回真实JSON。
- 先复现整账本丢失、孤立完成回执格式、派发见证回滚和未知结果退款等失败，再补修。
  追加见证不累计余额；派发后无回执不退款、不自动重派，已有回执只幂等重放。
- 843个个人项目、配置、状态和日志文件路径及SHA-256与本次开发前完全一致。

补充矩阵第7/8项在R02只确认PROPOSED恢复无额外调用且不写任何指南；
旧指南原子替换失败回归继续保留。新ACTIVE_GUIDE实际CAS/半写恢复仍属R04，未宣称完成。
R03进入条件：本轮代码与测试提交有回执；R01冻结；旧账本和活动尝试保留；
未知外部结果必须审计、不能自动重试；另按R03规格验证隔离只读执行器及真实CLI参数。
本次停止在R02，R03保持TODO。没有真实付费科研/监督轮次，也未推送。


## R03 离线验收与本地提交回执（2026-10-16）

先按 00_INDEX 核对 R02 提交回执及三个实际项目 pending：均无待恢复完成回执、
无 UNKNOWN_EXTERNAL_OUTCOME，原开关和余额保持不变。读取当前 R03 规格与升级
附录，并仅导入对应 R03 附录和共用沙箱安全文档，未覆盖旧追踪表或 R01/R02 记录。
实现提交 `1bfad1bc14608777f8922ae0f9c6ffb801538827`（Add bounded supervision executor and offline acceptance）。

- `python -B -m unittest discover -s tests -p test_supervision_executor.py -v`：
  29项全部通过，70.771秒，退出0；全部无模型调用。
- `python -B scripts/verify_r03_offline.py --output <本地证据目录>`：实际 Windows
  research.cmd 的6步合成项目验收通过；成功、幂等重放、dry-run、真实模式阻断、
  两次未知结果拒绝重派均有JSON与退出码证据，provider_requests=0。
- `python -B -m unittest discover -s tests -v`：423项，314.113秒，退出0；
  422通过、1个既有POSIX平台用例跳过，R03新增专项无跳过。
  全量包含更新后的根入口/新项目模板失败退出码回归及原R01/R02全部测试。
- `python -B research.py check all` 三个项目通过；原生 research.cmd doctor --offline、
  research.cmd supervise pending --dry-run 和 executor-info 均退出0；diff --check通过。
- 841个非缓存个人项目、配置、状态及日志文件的路径集合和SHA-256与开发前完全一致。
  R01契约、快照、默认配置、专项及说明与R01提交原字节一致；没有改变任何
  GOAL、STATE、预算、历史、门禁、证明等级或科研会话。

使用 supervision_executor.py 避免 supervision/ 包覆盖旧 supervision.py；schema直接
复用R01。原R02成本与恢复机制不重做，仅为save_completion添加默认行为不变的
可选锁内acceptance_guard。派发后无回执不退款、不重派；旧完成回执先恢复原记账，
不升级为R03接收；当前绑定变化不返回可用提案。Windows Job仅收束进程生命周期。

本轮DONE严格指附录允许的Fake离线验收路径。CLI 0.162.1参数兼容已实测，
OS层跨项目/凭据拒读与工具网络隔离尚未认证；真实backend固定阻断，未声称真实
沙箱通过。没有安装外部框架、提权或改变全局CLI配置，没有真实付费科研/监督调用。
Fake仅传输测试，不能作为后续自动指南应用依据；实际运行需另有已认证OS适配器。

说明见 ../SUPERVISION_R03_EXECUTOR.md，交付证据位于本次会话 outputs/R03/。
本轮未渲染或应用ACTIVE_GUIDE，没有自动接入watch消费；R04、R05保持TODO。
R03完成后停止，没有推送。


## R04 指南事务、OpenSource参考与本地提交回执（2026-10-16）

先核对R03的1bfad1b/725f683回执和实际队列：三个个人项目没有待恢复回执或
未知结果事件。按00_INDEX读取共同约束、R04指南应用规格及对应OpenSource附录，
仅导入本轮附录，没有改写先前契约或历史追踪。
实现提交 `03cb2c2812ca0263fccff42596db893a01b921ab`（Add transactional supervision guides and protected prompt loading）。

- `python -B -m unittest discover -s tests -p test_supervision_guide.py -v`：
  28项全部通过，163.993秒，退出0。最后补强临时标记撤销后的拒绝重放，
  `... -k fake_rejected -v` 1项通过，7.638秒；最终全量包含该补强。
- `python -B scripts/verify_r04_offline.py --output <本地证据目录>`：真实Windows
  research.cmd的10步临时样例验收通过。包括预览不写、CAS应用、重复重放、实际prompt
  只注入一次、精确回滚、原生子进程在replace后被强制终止、重启补回执且不再次写指南。
  provider_requests=0，指南操作前后原监督成本账本逐字节一致。
- `python -B -m unittest discover -s tests -v`：451项，484.889秒，退出0；
  450通过，1个原有POSIX平台用例在Windows跳过，R04专项没有跳过。
- `python -B research.py check all`三个项目通过；research.cmd doctor --offline、
  supervise pending --dry-run、executor-info均退出0；diff --check通过。
- 三个实际项目只读build_prompt与R03版本逐字一致；只保存提示哈希/长度，未修改原文件。
- 全量回归后843个个人项目、私有配置、状态和日志文件（含已有缓存）的路径及SHA-256
  与开发前完全一致。R01 schema/快照/配置/专项，以及R03执行器和原成本恢复源码
  保持原字节。GOAL、AGENTS、continue、STATE、预算、历史、门禁、证明等级均未变。

原R02不可变回执、hash-chain见证、路径安全和route/core/queue锁顺序直接复用。
指南状态单独投影APPLIED，原成本reservation保持PROPOSED，不写第二份成本账本。
新增模块采用supervision_guide.py以避免覆盖旧supervision.py；旧rollback --id兼容保留。
计划保存完整旧/新字节、diff及来源绑定，失败恢复只识别原旧/新SHA；第三种版本拒绝覆盖。
来源过期撤销未提交指南，回滚后原事件不生成第二版。安全inputs要求冻结覆盖，未捕获的
新约束不能被默默忽略；主张状态复核只读，不能升级科学结论。

OpenSource附录已实际纳入设计参考：ARA固定上游
`e52a925e9d03b4ada3008653e72f99b04116fca2`，许可证MIT（2026 Orchestra Research）。
参考research-manager的Layer Mutability、Edit procedure、Provenance for revisions，
及rigor-reviewer的Evidence Relevance、Falsifiability Quality、Scope Calibration。
具体URL、许可证/来源SHA-256和本地适配测试映射见 ../SUPERVISION_R04_GUIDES.md
及本次outputs/R04/opensource-reference.json。仅只读核验来源，没有复制、安装或执行外部系统。

本轮真实Codex后端继续阻断；Fake只在注册的临时合成控制器/项目应用，无生产放行开关。
科研代理对supervision/的新增、修改、删除由原ProjectTransaction识别并恢复；普通read_order
不能重复加载或绕过指南校验。没有真实付费科研/监督调用，没有推送。
最终回执和正常/故障证据位于本次会话outputs/R04/。本轮结束，R05保持TODO，未自行进入。

## R05 运行链接入与恢复验收（2026-10-16）

核对R04 03cb2c2/a5b274f回执及三个实际项目：未启用，无待办/未知结果。
按00_INDEX读取R05、迁移/恢复公共文档和对应OpenSource附录后增量接入。
实现提交 `1695bddbf4e9cfe633fe96bf1bb78bec3fe967ab`。

- `python -B -m unittest discover -s tests -p test_supervision_e2e.py -v`：
  最终20项全部通过，151.949秒，退出0。
- `python -B scripts/verify_r05_offline.py --output <外部证据目录>`：真实Windows
  research.cmd watch前三轮、run第四轮（项目目录调用）、停用后第五轮通过；
  prompt指南计数[0,0,0,1,0]；dry-run不写，恢复不重跑研究；双进程同事件竞争
  只有一份新增预留，一方正常完成、一方因锁争用退出2，provider_requests=0。
- `python -B scripts/verify_r04_offline.py --output <外部故障目录>`：10步原生
  replace后杀进程/恢复演练退出0，原状态、路线和成本字节不变。
- `python -B -m unittest discover -s tests -v`：最终471项，593.053秒，退出0；
  470通过、1个原有POSIX平台用例跳过。T01—T06由专项、原生入口与既有安全回归覆盖。
- `python -B research.py check all`三个项目通过；原生doctor --offline及
  supervise enable --all --dry-run退出0；diff --check通过。
- 最终843个个人项目、私有配置、状态和日志文件（含既有缓存）路径及SHA完全一致；
  三个实际项目prompt与R04逐字一致。R01契约/快照/默认配置/专项、R03执行器、
  原队列和成本传输7份源码保持原字节，没有重置预算、改写证明或科研历史。

复用原R02预留/完成回执和R04指南事务；运行循环锁外消费，route/core/queue锁序保留。
启用有历史水位、归属标记和禁用哨兵；丢失配置停止，丢失成本不重新零登记；
紧急停用保留坏队列/账本并恢复基准提示。未知结果、旧预留不自动重派。
固定活动尝试延后指南；正式复评优先，第六轮周期/复评合并一份快照。
仅允许提示阶段STATE.next_task等于原generate_directive对冻结任务的确定性包装，
应用阶段仍严格比对所有来源；原memory维护先于启用后的快照冻结，避免即时失效。

OpenSource参考The Agentic Researcher固定SHA
`82d1e3fec5f78863c70c015d2090b9823966e97b`（MIT），只读核验validate_workspace、
setup_instruction_file及恢复计划，未安装或运行；来源哈希及测试适配见
../SUPERVISION_R05_INTEGRATION.md和outputs/R05/opensource-reference.json。

R05离线进入条件已满足；真实Codex继续阻断，Fake仅注册临时样例，没有实际付费轮次、
启用个人项目或推送。依本次用户授权，提交本回执后才读取并继续R06，R07以后保持TODO。

## R06 只读证据投影与历史pin验收（2026-10-16）

先核对R05实现1695bdd及追踪回执5e498f2，确认20项专项、471全量和正常/故障
原生入口验收通过；实际项目未启用且无未知结果待办。仅在R05提交后读取R06及对应
OpenSource附录，未读取R07以后开发文档。实现提交
`a5785130a7816c6739899e37afac9ec504ea2e2c`。

- `python -B -m unittest discover -s tests -p test_knowledge_projection.py -v`：
  最终27项全部通过，16.014秒，退出0。
- `python -B scripts/verify_r06_offline.py --output <外部证据目录>`：两个不同前提
  合成项目、24步实际Windows research.cmd入口通过，退出0，provider_requests=0。
  使用官方problem/claim/attempt接口；真实查询展示CLAIM→OBLIGATION→PROBLEM_VERSION→GOAL；
  跨项目ID、删除缓存精确重建、项目目录调用、人工改证据及损坏缓存恢复均通过。
- `python -B -m unittest discover -s tests -v`：最终498项，580.267秒，退出0；
  497通过、1个原有POSIX平台用例跳过；本轮新增专项无跳过。
- `python -B research.py check all`三个项目通过；原生doctor --offline退出0；
  diff --check通过。完整命令、退出码、源摘要及原生正常/故障证据保存在outputs/R06/。
- 三个实际项目只读投影成功，原claim status逐项不变，均未创建个人缓存；
  843个个人项目、私有配置、状态和日志文件路径及SHA与R06开发前完全一致。
  原R01—R05、claim_graph、旧knowledge_graph/history等17份源码保持原字节；
  GOAL、STATE、预算、历史、门禁与证明结论均未改变。

复用claim_graph.status、problem_compiler.pool、旧只读memory视图、原route/attempt回执。
新增knowledge包只生成state/knowledge/index.json可删缓存，不调用refresh/save/模型。
schema_version=1、builder_version=R06.1；稳定项目/实体/原ID/版本，边保留来源SHA与scope。
JSON缓存采用原原子写和route/core/queue锁序；status/explain从live资料派生，不信任缓存。
当前主张完整继承proof/novelty/失效原因，历史版本不提升；claim/memory pin同时校验
版本与spec SHA，多级历史链保留。旧GOAL和memory冻结目标不重绑，路线重访不重写
原run纪元。过期审查来源标待刷新，证明/新颖性/形式审查状态分开继承。
失败文本仅unverified/containment，工具记录不能独立证明；机器反例仅依canonical裁决。
来源中途变化或构建写入失败保留旧缓存；损坏缓存可显式重建，不写回任何科学状态。

接口使用knowledge.build.build(controller,project)以对齐既有显式控制器路径助手；
CLI保证与configuration.ROOT一致。旧knowledge和claim入口保留，只增build/explain及
status.projection；新模板默认不创建缓存。限制和操作见../KNOWLEDGE_R06_PROJECTION.md。

OpenSource参考ARA固定SHA `e52a925e9d03b4ada3008653e72f99b04116fca2`（MIT，2026
Orchestra Research），只读核验logic/claims、trace/exploration_tree及research-manager
对应类型/来源/失败轨迹规范。具体源码链接、许可证与SHA-256及测试映射已记录，
没有复制、安装或执行上游系统/技能。

没有实际付费科研/监督轮次，没有启用个人项目或推送；真实Codex仍阻断。
本次连续两轮开发完成，停在R06，R07—R20保持TODO。
