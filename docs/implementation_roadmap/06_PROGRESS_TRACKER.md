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
| R07 | 原文溯源 | DONE | baebc92cc412e1cacac173f1540b04e7b11308c4 | 专项24/24；双项目原生入口33步；全量522：521通过/1原平台跳过；check all/doctor退出0 | 定理页、原PDF/提取/审查/主张pin已绑定；未核查位置及排版不作为决定性覆盖；真实监督仍阻断 |
| R08 | 失效事件 | DONE | c7ae0209231670707db4e4af378fd02e19debfc2 | 专项24/24；原生入口32步含进程终止恢复；全量546：545通过/1原平台跳过；check all/doctor退出0 | 原主张图仍唯一权威；本地链无外部防删除锚；R09及以后未进入；真实监督仍阻断 |
| R09 | 证据检索 | DONE | 17c7ba7eae3b419f16a16b6015f32b6a910a35b8 | 审查修复后原生41步；新增审查83/83；全量681：680通过/1原平台跳过；实际三项目检查通过 | 复验d08a8f8；默认关闭；持久失效重审；真实监督/Lean阻断；R11未进入 |
| R10 | 跨项目记忆 | DONE | 04ab51498e87aebd9c9c617361c8669ee91e2123 | 审查修复后原生30步；新增审查83/83；全量681：680通过/1原平台跳过；实际三项目检查通过 | 复验d08a8f8；默认关闭；持久失效重审；真实监督/Lean阻断；R11未进入 |
| R11 | 候选模型 | DONE | 566612a38bafd37635f1c113c0b2c1e4aea7c8a5 | 专项40/40；真实Windows入口35步；全量721：720通过/1既有平台跳过；check all/doctor通过 | 只登记候选；保守归一化去重；CONDITIONAL不能自动READY；真实监督/Lean阻断 |
| R12 | 搜索预算 | DONE | 2ac1e71d83f138364939d79f9fd3e22cb756c1c0 | 候选专项78/78；真实Windows入口63步；全量759：758通过/1既有平台跳过；check all/doctor通过 | 最多3候选的建议窗口；原预算唯一权威；归属不证明提示注入；真实监督/Lean阻断 |
| R13 | 数学核验适配器 | DONE | ce0125947d56e20b3b4690d8005017c30567a965 | 专项27/27；真实Windows入口28步；全量786：785通过/1既有平台跳过；check all/doctor通过 | 固定整数worker仅核验机器谓词；Lean静态预检始终阻断；未审自然语义不升级科学等级 |
| R14 | 密码学安全审查 | DONE | 6e435e965a839812c38b48324a18b7ed751c819c | 专项24/24；真实Windows入口45步；全量810：809通过/1既有平台跳过；check all/doctor通过 | 报告仅REVIEW_FINDING；理想授权须用户冻结pin；独审仍必要；首轮旧IO访问拒绝留档、无改码完整复跑通过 |
| R15 | 分支收束 | DONE | ddca136bbc58f24df4cf6f739dbb2b22ebcb6553 | 专项30/30；审查118/118；Windows入口84步；全量887：886通过/1既有跳过；check all/doctor通过 | 局部裁决无科学接受；原budget唯一权威；N01—N04已修；旧discovery显式迁移；真实监督/Lean阻断 |
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

## R07 本地验收回执（2026-10-16）

先核对R06 a578513/ee2acb4及干净工作区，再读取当前轮规格和OpenSource附录。
实现提交 `baebc92cc412e1cacac173f1540b04e7b11308c4`：复用uploads/PDF index/六维技术审查，只增派生来源、结构化
定理定位、显式版本替代和精确主张/审查/PDF/提取哈希绑定；不根据摘要裁决覆盖。
PaperQA2固定57e89f7223b0960d5ee5ea048c69e3c47e088572（Apache-2.0），
仅借鉴源块与摘要分层，未复制源码/安装框架/运行模型；详情见../KNOWLEDGE_R07_SOURCES.md。
先运行失败测试，再验收24项专项（31.321秒）、33步真实Windows入口
（两个纯临时项目、三版有效合成PDF、官方paper ingest、正常/故障子图）及
全量522项（815.695秒，1项既有POSIX跳过），全部命令退出0。
843个个人项目/状态/预算/日志文件路径及SHA一致，36份既有控制器源码不变，
实际三个项目只读查询无缓存创建且原claim状态不变。R01—R05契约及真实Codex阻断保留。
证据位于会话outputs/R07/；验收后才允许读取R08，不进入R09或后续轮次。

## R08 本地验收回执（2026-10-16）

进入条件：先完成并验收R07 baebc92/b6adb65，才读取R08及OpenSource附录。
实现提交 `c7ae0209231670707db4e4af378fd02e19debfc2`：图schema2，原子保存追加事件和精确快照，再替换可删缓存；
旧pin与当前修订对照、三层claim/memory/source/review原因、独立proof/novelty/
formal/contribution失效范围、只读diff、重复同步去重、损坏历史拒绝、显式cache-only恢复。
保留失败分支；机器反例保留原假设、机器命题摘要、witness、范围，不扩张REFUTES权限。
ARA固定e52a925e9d03b4ada3008653e72f99b04116fca2（MIT），只借鉴typed依赖和追加轨迹，
未复制第三方代码或执行框架。实现边界及原权威“字节恢复可恢复旧审查”语义见
../KNOWLEDGE_R08_LINEAGE.md；正式修订/撤销后仍须原接口重新绑定并独立审查。
先运行失败专项，再验收24项专项（56.551秒）、R06兼容27项、
真实Windows入口32步（原始PDF损失A→B→C、版本diff、正式修订、
真实进程在历史提交后退出78并恢复、历史篡改拒绝后显式重建缓存）以及
全量546项（1167.893秒，1项既有POSIX跳过），命令均按预期退出。
843个个人文件路径/SHA一致；除CLI接入外35份既有控制器源码逐字不变；
三个实际项目仅只读投影，cache/history均ABSENT，原claim状态不变。
回执/实际命令/正常及故障子图/完整历史证据在会话outputs/R08/。
真实Codex监督后端继续阻断；无真实付费科研/监督调用，无推送。
R08验收后停止。R09—R20保持TODO，不宣称整个v3.4或v4.0已发布。

## R09 本地验收回执（2026-10-16）

R09 本地验收完成
实现提交：17c7ba7eae3b419f16a16b6015f32b6a910a35b8
重连后D盘只读：本轮Git提交与追踪表保存在C盘公开源码副本local-r09-r10分支。
R09运行时代码已在中断前应用到D并完成下列实际回归；D的HEAD及追踪表待恢复写权限后同步。
先核对 R08 c7ae020/a0e23e3 回执及既有未知结果记录，再读取当前规格与 OpenSource 附录。
新增精确问题/版本/义务/主张检索、必要依赖与反例优先、完整出处、32KiB整体预算、
遗漏清单、当前源清单核对及可选提示注入。默认关闭时与冻结 R08 提示函数逐字节一致。
保留完整 GOAL/STATE/原安全指令；只读 context 不写缓存、历史、账本或科研文件。
元数据在图构建后按实际字节核对 manifest，拒绝旧锚点/新图混用。

用户审查意见：只修 R09/R10 直接相关项。新增普通依赖 pin 完整性检索防护，
坏绑定拒绝整次上下文，不补 pin、不改 canonical。F01—F07 剩余及 R08 字节恢复
契约差异登记 docs/REVIEW_A0E23E3_FOLLOWUP.md，不宣称全部修复。
上下文只表示当前权威快照，不补造已丢失的同版本审查历史。

实际命令均以 D:\CryptoResearchController 为 cwd：
python -B -m unittest discover -s tests -p test_knowledge_retrieval.py -v
  25/25通过，25.482秒。
python -B scripts/verify_r09_offline.py --output <本会话外部证据目录>
  40步实际 Windows research.cmd；正常/预算/注入/PDF丢失/损坏依赖/
  历史损坏/进程终止恢复；全部按预期退出，provider_requests=0。
python -B -m unittest discover -s tests -v
  571项，865.049秒；570通过，1项既有POSIX跳过。
python -B research.py check all
python -B research.py doctor --offline
git diff --check

843个个人项目/状态/预算/日志文件路径/SHA完全一致，33份其它既有控制器源码不变。
未启用个人项目检索、未运行真实科研/监督/Lean、未推送。R03新真实执行器仍阻断；
F01旧监督入口尚待修复，不能将新门禁结论扩展到整个软件。
PaperQA2 固定57e89f7223b0960d5ee5ea048c69e3c47e088572（Apache-2.0），
只借鉴召回/排序/证据阶段分离，未复制安装运行；精确来源见opensource-reference.json。
完整命令、正常与故障上下文、文件清单和补丁在本目录；R09回执提交后才进入R10。

## R10 本地验收回执（2026-10-16）

R10 本地离线开发验收完成（2026-10-16）
实现提交：04ab51498e87aebd9c9c617361c8669ee91e2123
先验收并提交 R09 17c7ba7/d934e19，才读取 R10 规格及对应 OpenSource 附录。
代码、追踪表及本地提交均已应用到实际 D:\CryptoResearchController。
此前受限会话未完成的回归日志已保留。权限恢复后，6项Git/目录联接/符号链接用例
全部通过，再安全同步R09实现与回执，应用R10并在实际D盘重新完成以下验收。

新增双向白名单、源/目标一致的摘要 SHA、目标模型 SHA 固定、公开文本来源核验、
权限撤销、不读私有来源、命名空间冲突与七维模型映射。输出固定 REFERENCE_ONLY、
positive_basis=false，始终要求目标项目独立审查。源 owner 预览保留问题与主张假设并集；
接收方只读显式公开胶囊与文本，绝不调用源项目 derive 或读取 PDF/日志/源码。
当前私有原文状态明确 NOT_READ_OR_REVALIDATED；只公开源变化可立即核验，私有变化须
源 owner 复核后重新发布/撤销。相同文本不等于安全等价，静态腐化结果不自动迁入自适应模型。
默认关闭，不自动注入提示，不写研究状态、claim graph、verified_results、预算或历史。

实际验收命令（以下 cwd 均为实际 D:\CryptoResearchController）：
python -B -m unittest discover -s tests -p test_cross_project_isolation.py -v
  23/23通过，31.68秒。
python -B -m unittest discover -s tests -p test_knowledge_e2e.py -v
  4/4通过，9.335秒。
python -B scripts/verify_r10_offline.py --output <本会话外部证据目录>
  30步实际 Windows research.cmd/受保护 Python 入口；两个纯临时 NTRU 项目；
  双向许可、私有文件拒读、公共来源过期、撤权不回查缓存、目标模型 pin、重建与 T07-T09。
python -B -m unittest discover -s tests -v
  598项，864.834秒；597通过，1项既有 POSIX 平台跳过。
python -B research.py check all  （实际 D 三个项目通过）
python -B research.py doctor --offline  （实际三个项目、Python/Git/控制器根核对通过）
git diff --check

843 个实际个人项目/状态/预算/日志文件路径和 SHA 完全一致；36份其它控制器源码逻辑不变：
35份保持原字节，configuration.py仅Git检出时转换换行，规范化内容与R09提交及基线一致。
正常引用 normal-reference.json、反向引用 reverse-reference.json、origin-proof-chain.json、
公开来源过期 stale-reference.json、撤权 revoked-reference.json、模型 pin 拒绝及修订上下文
均在 entry-acceptance-final/。实际命令和退出码见 verified-acceptance.json。
额外交付演练覆盖公开改动备份、固定提交 ff-only、幂等、额外人工编辑、守卫改动拒绝、
活跃 watch 锁；私有合成文件保持不变。R09通过仅含公共提交的本地bundle同步；
R10复用既有公共源码更新/备份事务，并在实际D盘完成实现及追踪回执提交。

ARA 固定 e52a925e9d03b4ada3008653e72f99b04116fca2，MIT，具体文件/哈希见 opensource-reference.json。
只借鉴来源/主张/工件分层；权限、白名单、撤权和映射均为本地 R10 实现；未复制、安装、
执行上游代码或技能。离线验收零模型/网络请求；没有真实付费科研/监督、Lean执行或推送。
上游仅做只读来源核对，不属于科研执行。
R03 新真实执行器继续阻断；旧监督旁路 F01 尚待修复，不能泛称全软件已统一阻断。
F01-F07 其余修复与 R08 字节恢复契约差异按用户选择登记待办，不擅自改变旧契约。
v3.4 T07-T09 离线开发闭环通过；不宣称已解决全部审查问题或可付费生产部署。
完成 R10 后停止，R11-R20 保持 TODO，未进入后续轮次。

## 2026-10-16 审查修复及R09/R10最终复验

实现提交 `d08a8f89f2ac47ba7c614b3dfd31e7d6bef15780`，基于R10回执24d32d7。用户继续授权完成原审查剩余修复，
并明确采用原R08政策：持久记录失效后恢复原字节仍须独立新审查。

F01/F05：新旧真实监督统一门禁，旧live/apply退役，未知running保留预留且不重派。
F02：自动及显式Lean入口均阻断未认证宿主执行，无elan保持UNAVAILABLE。
F03：持久COMMIT_DECIDED，验证/接受持core锁；原run恢复路线和可信检查回执，
未知检查停止审计；late-write/打印异常/真实硬退出不回滚已接受成果或重复记账。
F04：独立route_registry见证，缺失/空/旧预算停止，显式登记/精确恢复，不清零。
F06/F07：canonical普通pins完整验证，追加完整review/tool回执及摘要链，
旧缺失历史不补造。R04两处freshness竞争已修：第三人工指南版本始终保留。

python -B -m unittest discover -s tests -p 'test_review_*.py' -v
  83/83通过，104.164秒。
python -B -m unittest discover -s tests -v
  681项，680通过、1项既有POSIX跳过，981.431秒，退出0。
python -B scripts/verify_r09_offline.py --output <外部证据目录>
  41步真实Windows research.cmd合成入口，0 provider请求；默认提示原字节保留。
python -B scripts/verify_r10_offline.py --output <外部证据目录>
  30步，双向授权/私有拒读/七维模型映射/来源失效/撤权和闭环通过。
预算原生入口8步通过；真实进程os._exit覆盖接受决定、路线落账、检查未知、
READY回执及最终结算中断；原run/消费去重，第三SHA拒绝，不重跑模型/工具。
python -B research.py check all：实际三个项目通过。
python -B research.py doctor --offline：实际D盘根目录/环境通过。

843个个人文件路径/SHA完全一致；GOAL、STATE、消费、个人研究历史不变。
R01契约/snapshot及R02scheduler/calls/ledger/process源码保持原字节，默认配置未改。
所有功能修复位于实际D盘，未启用或迁移个人项目，未运行真实模型/Lean、未推送。

R08明确观察入口为claim refresh；普通build/cache-only遇到尚未记录的新失效停止，
不反写canonical；status/context/explain仍只读。瞬时只读检查不构成持久失效记录。
R10公开来源SHA可核验，私有PDF/claim当前状态不跨项目读取，须源方重发/撤权。
不能据离线回归声称真实OS隔离已认证、科学结论已证明或原独立报告已改判。
详见docs/REVIEW_A0E23E3_FOLLOWUP.md及本会话outputs/review-fixes/。
R09、R10完成并通过本次复验；R11—R20保持TODO，停止后续开发。

## R11 候选目录本地验收回执（2026-10-16）

进入前核对R10的04ab514/24d32d7及审查修复d08a8f8/8b01388，39份回执文件摘要一致，
实际三个项目监督事件为空，接受事务与发现调用均无待恢复/未知结果。按00_INDEX读取
共同约束、当前R11和对应OpenSource附录，未提前读取R12—R14规格。

实现提交 `566612a38bafd37635f1c113c0b2c1e4aea7c8a5`：冻结目标、路线纪元和完整安全输入；
问题精确版本或不可变草案快照；父版本和历史事件；保守科学内容去重；三个活动名额；
范围化否决与重启条件；READY复用现有主张独立审查状态。模型输入不能直接激活或证明，
差异模型保持CONDITIONAL，未提供自动放宽目标或独立裁决通道。

实际命令（cwd均为D:\CryptoResearchController）：

- `python -B -m unittest discover -s tests -p test_candidate_*.py -v`：40/40通过，28.074秒，退出0。
- `python -B scripts/verify_r11_offline.py --output <本会话outputs/R11/entry-final>`：35步真实Windows
  research.cmd临时样例，正常树/修订留史/第四活跃拒绝/未审定理拒绝/弱化阈值和循环拒绝，退出0。
  审计钩子拒绝网络和嵌套工具执行；模型、真实监督、Lean执行均0，原科研与预算文件逐字不变。
- `python -B -m unittest discover -s tests -v`：721项，720通过、1项既有POSIX跳过，
  961.695秒，退出0。113份公开Python文件在完整执行期间摘要一致。
- `python -B research.py check all`：实际三个项目通过；`python -B research.py doctor --offline`通过。
- 暂存区`git diff --cached --check`通过。全回归后仅删除测试文件EOF多余空行，AST逐字等价，
  未改生产代码；字节差异单独留在post-test-whitespace.json，不冒充第二次完整回归。

843个个人项目/状态/预算/日志文件路径和SHA完全一致；23份既有监督契约、预算、恢复、
主张及执行门禁文件保持原字节。LLNL固定c8342c0e28474d134f80caa6b9668470ebf55258，
AIDE固定1d8ec4026c67729443294c8b5c0907242d0de38c，两者MIT；参考文件、函数和许可证
全文SHA见CANDIDATES_R11.md及outputs/R11/opensource-reference.json。未复制安装运行上游代码。

详见docs/CANDIDATES_R11.md，本会话outputs/R11包含真实命令、正常及故障JSON、文件清单和摘要。
本轮不导入固定问题、不开始尝试、不改STATE/权威主张/消费；没有付费调用或推送。
真实监督与Lean继续阻断。R11回执提交后才进入R12；R15及以后未授权进入。

## R12 有界候选调度本地验收回执（2026-10-16）

先验收并提交R11的566612a/5d045bf，再读取当前R12和对应OpenSource附录。
实现提交 `2ac1e71d83f138364939d79f9fd3e22cb756c1c0`，9份公开文件，不含个人研究记录。

新增确定性只读plan和schedule-status、完整快照CAS的待审select、派发前bind-attempt，
以及可信原回执的map-run。候选窗口沿用1—3上限，保留已准入分支，再按事实补充候选；
超额明确延期，窗口外不能选择。所有选择仍execution_allowed=false，不自动导入问题或
关闭/启动attempt；活动attempt只延期。STOP/NEEDS_INPUT/初始化缺口、未结算或未知调用、
STATE与原路线last_run漂移、接受事务待恢复、预算耗尽或待复评均阻断准备。

原route/attempt/独立监督及R02预留见证保持唯一消费权威。新历史只记选择和调度归属，
不增减有效轮数、不退款、不重派。先绑定零调用的原owner，再核验原终态settlement；
ACCEPTED还要求原COMPLETE包装器回执、精确锚点与路线纪元。旧运行不能事后按问题ID猜归属。
candidate_injection_proven=false，记录不证明科研代理已读候选卡，也不提升科学等级。
选择历史中断只重放同一冻结操作；高水位不匹配或未知结果停止审计。

实际命令（cwd均为D:\CryptoResearchController）：

- `python -B -m unittest discover -s tests -p test_candidate_*.py -v`：78/78通过，139.279秒，退出0；
  包含40项R11和38项R12，新增三候选窗口、预算守恒、旧plan CAS、预绑定、可信回执及本地事务中断恢复。
- `python -B scripts/verify_r12_offline.py --output <本会话outputs/R12/entry-final>`：63步真实Windows
  research.cmd通过。临时样例调用原runner.record_round与save_ledger模拟0→1→2验收消费，
  不在新模块手工增量；双进程唯一选择、未知拒映射、失败回执幂等、窗口外拒选、STOP/复评/耗尽均覆盖。
  模型/网络/监督/Lean调用均0，只有显式原控制器API改变临时预算，个人项目不参与。
- `python -B -m unittest discover -s tests -v`：759项，758通过、1项既有POSIX跳过，1077.909秒，退出0。
- `python -B research.py check all`：实际三个项目通过；`python -B research.py doctor --offline`退出0。
- 暂存区和工作区diff --check通过；119份公开Python文件在最终专项/入口/全回归期间摘要完全一致。

843个个人文件路径和SHA不变；27份R01/R02/审查修复门禁与R11候选契约文件保持原字节。
先行76项/52步回执已标pre-frontier归档，最终验收采用上面的78项/63步，不混用旧结果。
文献自动覆盖没有独立来源时保持UNKNOWN，已有显式COVERED分支排除；成本仅展示测量事实，
共享引理已审查不等于候选整体安全，因此不凭自报便宜排名，也没有模型自评/Elo预算分配。

AIDE沿固定1d8ec4026c67729443294c8b5c0907242d0de38c（MIT），OpenEvolve固定
a1e9d91eecde612f0efc8e8e31f59b36998248c0（Apache-2.0）；具体函数、源文件和完整许可证SHA
见docs/CANDIDATES_R12.md及outputs/R12/opensource-reference.json。仅只读核验Git对象，未复制安装运行。

本会话outputs/R12保存真实命令、正常/故障JSON、源码摘要和文件清单。未改变个人GOAL、STATE、
预算、历史、门禁或证明结论，真实监督及Lean继续阻断，无付费轮次或推送。
R12回执提交后才进入R13，再逐轮完成R14；R15及以后不进入。

## R13 数学核验适配器本地验收回执（2026-10-16）

先核对R12的2ac1e71/ade5d70及既有审查修复回执，再读取当前R13、对应OpenSource附录及
共享公开研究材料。实现提交 `ce0125947d56e20b3b4690d8005017c30567a965`，13份公开文件。

薄适配复用旧整数AST/精确见证和Lean输入预检；旧search/run默认记工具回执语义不变。
新请求冻结candidate/claim/problem修订、目标、来源、工具源码、Python版本与原资源策略。
request/STARTED/receipt配对持久化；完整完成幂等重放，缺失冻结输入或未知结果不自动重跑。
反例保存机器证书并用原check_witness复核；只读recheck不派发第二个搜索。
核验元数据没有apply入口，不写canonical主张、科学接受、候选状态、STATE或消费。

整数检查仅执行固定受信data-only工作进程，空临时cwd/最小环境、原ProcessTree强制超时，
资源上限取原策略与10000点/3秒/15秒wall的较小值。它不是任意程序执行后端，
os_deny_read_or_network_isolation_certified=false。Lean仅静态预检，不执行版本探测、
Lean/Lake或下载：缺失工具保留UNAVAILABLE，有工具标记仍ISOLATION_UNCERTIFIED。
True弱化目标和未完成标记明确提示；语义、公理与原密码学目标的对应始终待独立审查。
工具统一词汇不等于PROVED；10000点未发现反例仍只NO_COUNTEREXAMPLE_WITHIN_BOUND。

实际命令（cwd均为D:\CryptoResearchController）：

- `python -B -m unittest discover -s tests -p test_verifier_*.py -v`：27/27通过，43.669秒，退出0。
- `python -B scripts/verify_r13_offline.py --output <本会话outputs/R13/entry-final>`：真实Windows
  research.cmd临时样例28步通过，35.815秒。精确错误多项式反例与证书复查、10000点真式、
  True静态弱化/无elan回执、来源和claim版本过期、完成重放不执行均覆盖。
  审计仅允许2个固定整数worker，其余模型/网络/监督/Lean执行均0，原预算/状态逐字不变。
- `python -B -m unittest discover -s tests -v`：786项，785通过、1项既有POSIX跳过，
  1105.123秒，退出0；127份公开Python文件在最终专项/入口/全回归期间摘要一致。
- `python -B research.py check all`：实际三个项目通过；`python -B research.py doctor --offline`退出0。
- 暂存diff --check通过；311份范围外既有文件、843个个人文件路径及SHA完全一致。
  EOF空行清理发生在最终冻结前，完整回归之后没有修改生产或测试源码。

Numina固定1c9af8a52e715f22fede766425ba3d3b95526132，README声明MIT但完整许可文件未找到，
故许可证全文SHA为空，不复制代码。OpenEvolve沿a1e9d91eecde612f0efc8e8e31f59b36998248c0
Apache-2.0；OpenAI/math固定1581d4cbdd69a0faf34b2089614fe2a814316a6a Apache-2.0；
LeanDojo核对弃用声明仅作历史参考，不引入依赖。全部源文件/许可证摘要见
docs/VERIFIERS_R13.md与本会话outputs/R13/opensource-reference.json，只读核验未安装运行。

R13全部实际日志、正常/故障JSON、变更清单与来源摘要保存于outputs/R13。
个人GOAL/STATE/预算/研究历史与证明结论不变；真实监督/Lean继续阻断，无付费调用或推送。
R13回执提交后才进入R14；R14完成后停止，不进入R15，也不宣称完整v3.5/v4.0已发布。

## R14 协议安全义务审查本地验收回执（2026-10-17）

先验收并提交R13的ce01259/5aef5ff，核对既有审查修复与843份个人文件基线，再读取
当前R14和对应OpenSource附录。实现提交 `6e435e965a839812c38b48324a18b7ed751c819c`，
9份公开文件；只增通用模块、模板、CLI、样例和测试，不为个人协议编写专用监督器。

协议卡覆盖安全游戏、参与者、腐化时机/阈值、泄漏、掉线/中止、模拟器、归约损失、
组合范围、定理依赖与MPC/认证PIR/ZK三类比较。复用R13真实candidate/claim/problem/goal
冻结请求，额外绑定原主张图、当前独审状态及审查证据实际摘要；修订、失效或审查变化
使旧报告STALE。报告元数据与原科学权威分离，无apply、不改候选状态或原审核接口。

原固定模型须明确结构化维度及用户冻结ideal_interface_sha256，义务卡不能自行授权
秘密输入或模拟器可编程性；缺少或不匹配时NEEDS_INPUT，不解析自由文本来猜授权。
原有项目没有自动迁移、回填pin、导入新问题或改安全阈值。静态不能冒充自适应；
自适应累计/逐轮腐化范围须明确。超阈值、越轮或静态换合谋集合的轨迹OUT_OF_SCOPE，
不称作原冻结假设下的攻击。有限数据拒绝位/公开输出/模拟器缺口只是待独审检验计划，
不执行协议程序、模型、Lean或监督。全部输出REVIEW_FINDING，安全门禁、科学接受及
construction_progression_allowed始终false，真正确认仍经原claim独立审查流程。

原论文复用R07真实PDF/提取/版本/页码/定理及技术比较链；SOURCE_LOCATION_ONLY不证明
前提完整或归约适用。删前提、端到端归约缺失、未授权理想输入、跨轮未定义均明确指出。
成本无分解UNASSESSED，归约参数/位宽/轮数/失败事件/损失界缺失列具体待办；直接组合
最多POTENTIALLY_COVERED，不自动认定覆盖或创新。中断缺冻结请求/STARTED/完整报告
保留UNKNOWN且不自动重审；同一可信完整请求幂等返回原报告。

实际命令（cwd均为D:\CryptoResearchController）：

- `python -B -m unittest discover -s tests -p test_security_review*.py -v`：24/24通过，54.209秒，退出0。
- `python -B scripts/verify_r14_offline.py --output <本会话outputs/R14/entry-final>`：真实Windows
  research.cmd临时样例45步通过，67.954秒。正常义务、三类范围化攻击/缺口、缺模型与来源、
  自授权拒绝、前提/成本/标准框架比较、SHA/claim修订失效、幂等和未知中断均覆盖。
  模型、网络、监督、Lean及嵌套程序执行全部0；科研/预算仅在明确的原夹具操作中变化。
- `python -B -m unittest discover -s tests -v`：最终完整重跑810项，809通过、1项既有POSIX
  模拟可执行文件测试跳过，1165.090秒，退出0；132份公开Python文件在两次完整回归期间
  摘要完全一致，没有为使测试通过修改旧机制或安全门禁。
- 首次完整回归810项有1失败、1跳过（1159.873秒，退出1）：旧端到端用例准备三轮时，
  临时C盘夹具的原acceptance原子替换遇WinError 5访问拒绝。原日志独立留档；具体占用
  原因未确认，未断言杀软或R14因果。唯一用例独立复跑两次分别1/1通过（6.359/6.039秒），
  随后源码不变从头全套重跑得到上一项绿灯，不能把单用例复验冒充完整回归。
- `python -B research.py check all`：实际三个项目通过；`python -B research.py doctor --offline`退出0。
- 暂存diff --check通过；323份范围外旧文件、843个个人文件路径与SHA完全一致。

ARA官方固定e52a925e9d03b4ada3008653e72f99b04116fca2，实际参考Markdown rigor-reviewer
及review-dimensions清单，MIT全文SHA为25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a。
具体源文件摘要见docs/SECURITY_REVIEW_R14.md与outputs/R14/opensource-reference.json；
外部技能仅作为资料阅读，没有激活安装、复制实现或执行上游指令。

本会话outputs/R14保存最终命令、原始失败和复跑、正常/故障JSON、来源摘要及修改清单。
个人GOAL、STATE、预算、历史及证明结论均未改变；真实监督和Lean继续阻断，无付费调用或推送。
R11—R14逐轮验收与本地提交完成，停止在R14；R15及以后保持TODO，未进入或宣称完整版本发布。

## R15 分支收束与 12ccad9 审查修复回执（2026-10-17）

先核对 R14 的 6e435e9/12ccad9 及首次 IO 失败、两次单例和无改码完整复跑，
再读取 R15 与对应 OpenSource 附录；未提前读取 R16。实现提交 `ddca136bbc58f24df4cf6f739dbb2b22ebcb6553`。
用户在验收前提供 12ccad9 静态报告，新增 N01—N04 一并修复并单列证据，原报告 FAIL 保留。

精确反例与原独立范围审查共同支持 REFUTED；COVERED 要求 R07 原文、页码、定理及技术
包含映射，正例使用临时 PDF 夹具验收。缺材料保持 CONDITIONAL，RETIRED 不强制创建科学主张。局部否决不推及父问题
或全族，归档保留假设、原因、重启条件、原轮数、未闭合义务及 SUPPORT/DIRECT_DEPENDENCY。
知识检索只把归档作为非正面历史依据；机器回执缺失或 canonical 持久审查撤销使其待核验。

显式 CLOSE 与 START 复用原尝试前后像和共享路线预算；不改 selected_idea、不自动 run。
独立 intent/witness 和高水位历史控制本地恢复，单侧丢失、第三方 STATE、stale checkpoint、
STOP/review/unknown 均阻断旧执行入口。重算请求哈希不能伪造科学裁决、phase、来源或轮数。
同问题多候选需精确原归属；旧未绑定尝试须显式认领；重启须新构造和原独立审查回执。

N01 为原 discovery 主账本增加统一权威、登记和冻结 pending 后像。缺失或回退不遗忘已用
调用和独立尝试；旧完整数据显式按 SHA 登记，未知外部结果不重派。本轮未迁移个人项目。
N02 比较完整自适应预算 scope，原 ideal interface 摘要契约不变；N03 首次历史映射核对原
COMPLETE 归档与 owner/settlement/epoch/anchor/count，重放原保护历史不依赖展示窗口。
N04 保留 cache-only 只修派生索引的例外，不记录 canonical latch 或 R08 观察事件。

实际命令（cwd 为 D:\CryptoResearchController，均退出0）：

- `python -B -m unittest discover -s tests -p test_candidate_end_to_end.py -v`：30/30，210.206秒。
- `python -B -m unittest discover -s tests -p "test_review_*.py" -v`：118/118，281.441秒，含原审查83项与新增35项。
- `python -B -m unittest discover -s tests -p "test_candidate_*.py" -v`：候选兼容118/118；各专项有重叠，不相加当作独立测试总数。
- `python -B scripts/verify_r15_offline.py --output <本会话outputs/R15/entry-final>`：真实 Windows research.cmd 临时样例84步，185.18秒；受信整数worker恰好1次，其余模型/网络/监督/Lean全部0。
- `python -B -m unittest discover -s tests -v`：887项，886通过、1项原POSIX模拟可执行文件跳过，1638.062秒；145份公开Python源在最终验收期间SHA一致。
- `python -B research.py check all`：实际三个项目通过；`python -B research.py doctor --offline`通过。
- 暂存 diff --check 通过；321份实现范围外旧文件未改，843个个人文件路径及SHA完全不变。

AIDE journal 固定1d8ec4026c67729443294c8b5c0907242d0de38c，另核对当前HEAD同源码；
ARA trace 固定e52a925e9d03b4ada3008653e72f99b04116fca2，均核对MIT全文SHA，仅参考失败保留
与来源组织，未复制/安装/运行上游。详细文件和许可摘要见CANDIDATES_R15及本会话来源回执。

原RED与最终命令留档；N03最早RED仅工具/消息记录，无落盘日志，未补造。
N04首次失败是夹具把Windows锁标记也算成权威变更，修正观察范围后验证原既有行为。
没有把两者误称为额外产品缺陷。T01—T07与来源级别见review-12ccad9-closure-audit.json。
个人GOAL、STATE、预算、历史和证明结论未改；真实监督/Lean继续阻断，没有付费轮次或推送。
R15回执提交后才进入R16；本任务完成R16后停止，不自行进入R17。
