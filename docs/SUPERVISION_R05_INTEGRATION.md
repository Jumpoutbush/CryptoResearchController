# R05：统一运行链、迁移与恢复

R01—R04 的协议、冻结输入、成本预留及指南事务继续作为权威实现。
`supervision_runtime.py` 只编排它们，不维护第二份科研轮次或成本余额。
默认不迁移个人项目，不写 AGENTS/continue，不补跑启用前的历史监督。

## 启用和停用

```powershell
.\research.cmd supervise enable --all --dry-run
.\research.cmd supervise enable --all --confirm
.\research.cmd supervise enable <project>
.\research.cmd supervise status <project>
.\research.cmd supervise pending <project> --dry-run
.\research.cmd supervise history <project>
.\research.cmd supervise run <project> --dry-run
.\research.cmd supervise recover <project>
.\research.cmd supervise disable <project>
```

生产默认 backend=codex，但 R03 的 OS 隔离门禁仍然阻断真实后端，在预留之前停止。
启用命令不会改变该门禁；因此目前不建议对个人项目启用。开发只在注册的 OS 临时
`crc-r04-fixture-*` 合成控制器里使用 `--executor fake`，不存在生产 Fake 放行开关。
批量操作先列出逐项目上限和已用成本，变更须显式 `--confirm`；没有后台自动迁移。
新模板不创建活动指南、不启用调用。旧 `configure` 和旧 rollback --id 保留兼容。

启用先记录不可回退的 R05 归属及禁用哨兵，沿用原 configure 登记成本，再提交启用状态；任何中断都不能
退回旧真实执行器。归属存在但启用配置丢失时停止，必须恢复原配置或显式停用。
启用水位包括当时最后接受的回执，重新启用也不补跑该历史边界。
启用前核查原预留见证，原账本丢失时禁止零成本重新登记。
停用先于队列、指南和成本历史的解析生效；损坏的历史保留给操作者核查，下一次
研究返回基准提示行为。关闭不删除指南、提案、未知结果或已用成本，也不解除 STOP。

## 运行和恢复顺序

`run`、`watch` 和直接 runner 共用 main：运行循环锁串行化研究调度；单轮在原 route
锁内通过原 ProjectTransaction 验收并提交路线预算。原 post-accept 排队边界保留；
退出科学事务和 route 锁后才消费 R03 回执、R04 预览/CAS 应用。每次重新取锁均重读
当前 STATE、路线和目标绑定。事件通知/监督失败保留 wrapper_accepted 和 last_run，
暂停本次自动运行，退出非零；`disable` 可关闭监督后继续原科学流程。

原知识 refresh 会更新 CLAIM_GRAPH 的旧 memory 元数据；显式启用时先完成这项原有
维护，再冻结监督输入，避免刚生成的快照立即失效。未启用时保持原排队/维护顺序。
R04 严格来源哈希继续适用于应用；提示读取唯一允许的 STATE 差异是 next_task 精确
等于原 generate_directive 对冻结旧任务的确定性包装，其他字段和来源仍须完全一致。
临时路线策略与持久守卫不一致时保守延后至正式复评，不绕过原路线门禁。

恢复使用同一事件、同一预留、同一完成回执和同一指南计划：

- 已接受但通知未落盘：从原已提交研究回执恢复队列，不重跑科学轮次。
- 已预留未派发：等待人工核查，不自动认领旧调用。
- 已派发、结果未知：保留预留，不退款、不自动重试。
- 完成回执已落盘：补原记账，再应用原提案，不重新请求模型。
- 指南替换后未回执：复核原旧/新 SHA，补同一回执；第三种版本拒绝覆盖。
- 路线复评优先于监督；固定 attempt 活动时延后自动指南，不能关闭或更换 attempt。

显式单文件回滚沿用 R04：先查看当前 SHA，然后
`supervise rollback <project> --event <id> --expected-hash <current-sha>`。
控制器源码回退使用本地 Git 提交；个人项目不在源码回退范围，不运行 git clean。

## 离线验收

```powershell
python -B -m unittest discover -s tests -p test_supervision_e2e.py -v
python -B scripts/verify_r05_offline.py --output <outside-project-evidence-dir>
python -B scripts/verify_r04_offline.py --output <outside-project-fault-dir>
python -B -m unittest discover -s tests -v
.\research.cmd check all
.\research.cmd doctor --offline
```

R05 脚本复制公开控制器到临时目录，仅替换其科学子进程入口为显式守卫的合成
输出器；官方 runner 验收、route ledger、research.cmd run/watch、监督执行器和
指南事务均使用实际代码。输出器不调用模型，不构造独立已证明结论。
原生双消费进程只产生一个新预留；R04 故障脚本独立复验 replace 后杀进程/重启恢复。
T01/T02/T03/T05/T06 由专项与入口演练覆盖，T04 继续由 R03/R04 全量安全回归覆盖。

## OpenSource 附录参考

已读取 `implementation_roadmap/UPGRADE_20261016/round_addenda/R05_open_source_addendum.md`。
指定上游 [The Agentic Researcher](https://github.com/ZIB-IOL/The-Agentic-Researcher/commit/82d1e3fec5f78863c70c015d2090b9823966e97b)，
固定 SHA `82d1e3fec5f78863c70c015d2090b9823966e97b`。
[MIT LICENSE](https://github.com/ZIB-IOL/The-Agentic-Researcher/blob/82d1e3fec5f78863c70c015d2090b9823966e97b/LICENSE)，
Copyright (c) 2026 Max Zimmer, Nico Pelleriti, Christophe Roux, Sebastian Pokutta。
仅只读核验，没有安装、复制或执行上游框架/技能。

| 参考源码 | 参考内容 | 本地适配与验证 |
| --- | --- | --- |
| [agentic-researcher](https://github.com/ZIB-IOL/The-Agentic-Researcher/blob/82d1e3fec5f78863c70c015d2090b9823966e97b/agentic-researcher) validate_workspace 342—382、启动1420—1429 | 启动前验证真实目录和边界 | Fake 临时标记先验、真实后端零预留阻断 |
| 同文件 setup_instruction_file 548—569 | 保留既有项目指令文件 | 不覆盖 AGENTS/continue，启用水位、停用原提示 |
| [setup_research_plan.md](https://github.com/ZIB-IOL/The-Agentic-Researcher/blob/82d1e3fec5f78863c70c015d2090b9823966e97b/commands/setup_research_plan.md) 13—34 | 从既有工件恢复上下文 | R02 完成回执补记、未知结果禁止重派、R04 原计划恢复 |

来源 SHA-256：LICENSE `f284a379facaa080a7072863c647a5822869dd25a7d3a7aeda43784a12734dba`；
agentic-researcher `83ab69ccd4e750ef7df920c9658243f8f3b89d479079ddb7ae43da6c5bf41921`；
setup_research_plan.md `8d525bc754e6d2aa1c9776034f8422b0807d55b572f79e4b6a5d3b6b663d59ac`。
上游会话恢复不构成本项目的预算幂等保证；本地仍以 R02/R04 回执为准。
