# R01：监督契约与只读快照

依据 `implementation_roadmap/00_INDEX.md` 的分轮顺序，本轮只实现 R01。
本地此前的 v3.3/v3.4 版本号不表示这份新路线图的验收项已经全部完成。

## 兼容范围

新增 `supervision_contracts.py`、`supervision_snapshot.py`，避免与现有
`supervision.py` 发生 Python 包名冲突。原监督执行器、运行配置、指南、
`run/watch/refocus/attempt` 及已登记项目保持原行为。

`config/supervision_defaults.json` 是新事件协议的准备配置：默认关闭，周期三轮，
每事件最多一次调用，快照上限 262144 字节，指南上限 12288 字节，模型层级为 critical。
R01 只读取并验证这些限制；没有调度或模型消费逻辑，不能用该文件更改现有监督开启状态。
原来的 `config/supervision_policy.json` 和项目覆盖继续由旧执行链使用。

## 稳定接口

```python
from supervision_snapshot import build_snapshot
from supervision_contracts import (
    event_schema, proposal_schema, defaults_schema,
    make_event, validate_event, validate_proposal, transition_event,
)

snapshot = build_snapshot(project, last_n=3)
event = make_event(snapshot, "PERIODIC")
validate_event(event, snapshot)
```

`build_snapshot` 返回普通 JSON 对象，不创建任何文件、目录、锁或账本。
`make_event` 要求快照中有真实的持久化路线纪元和已验收轮次；没有账本时返回的
快照明确保留 `route_epoch=null`，不能凭空生成监督触发轮次。
事件创建和 `transition_event` 只是纯数据转换；事件落盘、去重消费和预算预留属于 R02。
事件消费时必须调用带 `snapshot` 的验证器，不能用单独的结构校验冒充来源鉴权。

事件使用公共 07 文档的 `trigger_type/state/focus` 字段，不接受 R01 示例中的
`trigger/status/goal_anchor_id` 作为别名。`event_id` 固定绑定项目、纪元、真实 run ID、
触发类型和目标锚点；创建时间、处理状态和清单变化不会制造新的触发身份。

所有 Schema 对象递归使用 `additionalProperties=false`，Python 验证器严格区分
布尔值和整数。合法动作仅为 `KEEP_GUIDE/REFOCUS_RECOMMENDED/PAUSE_RECOMMENDED/ESCALATE`。
没有文件写入字段、预算重置动作、定理批准动作或停止项目动作。
提案必须引用快照中完整捕获的科学来源和精确摘要；截断、缺失、控制记录或重复引用均拒绝。
旧项目没有编号义务时，非聚焦建议可用 `next_obligation_id=null` 表示未知；
`REFOCUS_RECOMMENDED` 必须指定实际冻结义务，不能创造替代义务。

## 快照的来源与诚实边界

固定选择 GOAL、PROJECT、AGENTS、continue、STATE、威胁模型、证明义务和既有主张/问题池；
按原路线账本的持久验收收据选择最近至多三份报告，再加入明确引用的证据、精确版本想法。
报告必须具有匹配的 `RUN_ID`。有效轮数、持久 run ID 和 STATE 必须相容。
来源缺失逐条写入 `missing`，不会用别的报告冒充 LATEST，也不会创建空主张图。

近邻技术核查采用明确披露的选择策略：至多十二个本地命名 review JSON 文件，加上原有
主张/回执显式引用的材料；连同声明的原文和推导路径一起绑定。额外候选注明未选择，
不会把这种文件名启发式筛选称为相关性判定或完整文献查新。

逐文件 manifest 保存来源范围、相对路径、完整文件大小及 SHA-256、捕获字节、
遗漏字节、截断状态、省略原因和验证范围。控制器配置和路线账本只提供摘要元数据，
不复制运行环境或凭据。路径穿越、跨项目路径、符号链接和 Windows junction 均拒绝。
每个源在抽取结束重新核对摘要，发现并发变化即拒绝快照。

GOAL 必须完整且为有效 UTF-8。内容 SHA-256 是目标的精确版本；不存在编号版本注册时
`goal_version.number=null` 并记录原因。原始文本中的命令和“已经证明”等自称都是数据。
文件总体保持保守来源等级；具体已审主张的级别只从原 `claim_graph.status` 读取，
保存在 `verification_scopes` 中并固定主张 ID 和 revision，不将整份文件认证为已证明。
抽取器不调用 `claim_graph.refresh`，不更新任何科学审查状态。

256 KiB 限额同时约束正文与完整规范 JSON（包括清单、缺失说明和封装）。
正文按 UTF-8 字节截断，逐项记录精确遗漏；元数据与完整 GOAL 已经超限时直接拒绝。
`limits.serialized_bytes` 是完整 JSON 的实际字节数。序列化须使用
`json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':'))`。
相同输入的清单及输入快照摘要不受 mtime、枚举顺序或采样时钟影响。

## 验证、回滚与后续轮次

专项命令：`python -m unittest discover -s tests -p test_supervision_contract.py -v`。
完整验证继续运行仓库要求的 unittest、`research.cmd check all` 和 `doctor --offline`。
正常路径可复核 `test_snapshot_is_deterministic_and_does_not_write_or_execute`；
故障注入可复核 `test_manifest_schema_rejects_invalid_trust_and_sizes_even_with_recomputed_hashes`
和 `test_snapshot_identity_is_not_rebound_between_two_project_reads`。

本轮只增加独立模块、准备配置、测试及文档。停用本轮接口不需要回滚研究状态；
保留原监督文件和历史即可。回退源码时仅回退本轮新增文件，不还原或删除任何科研项目。

已核查的后续差异仍保留待办：R02/R05 的复评优先级，R03 的一次性只读工作区，
R04 的独立 ACTIVE_GUIDE，以及 R06 的可重建派生索引。它们不能因旧版已有相似功能就
被自动勾选通过；后续继续按索引逐轮实现。
