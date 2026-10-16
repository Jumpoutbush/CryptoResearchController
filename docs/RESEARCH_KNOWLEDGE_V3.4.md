# v3.4：长期科研知识图谱

版本：`3.4.0-research-knowledge-graph`。

v3.4 先复用 v3.2 的主张图、证据摘要、版本依赖和独立审查，再关联论文、外部定理、证据、失败路线及证明义务。各项目共用控制器实现，知识限定在所选项目中；不会把其他课题的假设或结论自动迁入当前研究。

## 保存位置与原有接口

唯一图文件仍是 `research/discovery/CLAIM_GRAPH.json`。原有 `claims`、`events`、声明历史、审查及工具回执保留；新增长期知识使用可选 `memory` 区中的 `nodes` 和 `events`。旧图不需要迁移，缺少 `memory` 时按空知识区处理。不会生成另一份可独立批准主张的图。

`claim import/show/status/review/invalidate/refresh`、问题池和连续研究尝试继续使用既有接口。知识节点关联主张不等于审核通过，索引论文不等于完成全文技术核查，登记证明义务不等于义务闭合。理论审查及系统实现许可继续核对现有主张的真实有效性。

| 知识类型 | 保存内容 |
| --- | --- |
| `paper` | 论文身份、版本、原文与局部定位 |
| `theorem` | 精确陈述、前提、论文中的定理定位及其依赖 |
| `evidence` | 证明片段、计算记录、实验或技术比较的直接来源 |
| `failed_path` | 失败范围、反例、障碍、重启所需条件 |
| `obligation` | 尚需履行的证明责任、验收条件与支持材料 |

`theorem` 表示被记录的定理陈述，独立审查状态仍由现有主张接口管理。预算耗尽只说明资源使用情况，不据此生成普遍不可能结论。

## 只读查看与首次建立索引

```powershell
Set-Location D:\CryptoResearchController
.\research.cmd --version
.\research.cmd knowledge status all
.\research.cmd knowledge search secagg-research --query "证明义务"
.\research.cmd knowledge search all --query "反例" --kind failed_path --limit 20
```

`status`、`search`、`show`、`trace`、`impact` 为只读操作，均不调用模型，不创建图文件或预算账本。`status all` 和 `search all` 逐个显示项目结果，不建立跨项目数学依赖。

`search --kind claim` 筛选原有候选主张，`--kind source` 筛选直接来源；其余类型对应上表中的知识节点。搜索对当前及历史记录字段、已保存的来源摘录作文字匹配，不执行模型推断或整库全文检索。历史命中只帮助找回旧陈述与来源，不表示该版本当前有效或曾通过全部科学审查。

需要持久化来源索引时，显式执行：

```powershell
.\research.cmd knowledge refresh secagg-research
```

刷新只处理现有本地材料与图谱记录，不进行网页检索、论文下载或模型调用。来源目录、条目或文件存在不代表其内容已被科学核验；自动发现的材料按未验证来源处理。论文、失败路线和旧证明义务可以继续使用原文件格式，控制器不改写这些原文以适配图谱。

只读视图从 `literature`、`proofs`、`research`、`experiments`、`inputs`、`reports`、`ideas` 中发现科学文件，排除 discovery、监督及调度控制记录。已有论文目录、主张台账和证明义务 JSON 条目按原格式读取；失败路线 Markdown 标题用于定位。自动条目只陈列原始记录的声明，不把旧台账的文字状态升级为独立证实。手动刷新或已验收科研轮后的自动刷新才保存这些来源节点及其后续版本和校验事件。

旧台账中明确声明的本地证据路径、`evidence_ids` 会连接到相应来源节点或证据条目；缺失、歧义、不安全路径和摘要不符保留为可审计的未解决依赖。证明义务编号登记为 `addresses` 关联，不能仅凭该关系关闭义务或证明主张。索引器只解析显式字段，不从自然语言猜测证明依赖。

升级安装和只读查询不会为已有项目补写历史图谱，也不会重置 `research/STATE.json`、路线预算、监督预算、尝试历史或既有证据。`refresh all` 不开放；手动持久化操作显式选择一个项目。本次开发只读核对实际项目，不执行项目索引迁移。

## 登记精确来源

编辑通用模板 `research/KNOWLEDGE_TEMPLATE.json`，替换其中示例 ID、陈述和来源。模板中的占位路径不能直接当作证据导入。以下是一个局部原文已在本项目保存的外部定理记录：

```json
{
  "schema_version": 1,
  "id": "THM-EXTERNAL-001",
  "kind": "theorem",
  "title": "最相近论文中的精确定理",
  "statement": "填写完整量词、输入输出和结论。",
  "sources": [
    {
      "path": "literature/closest-paper.txt",
      "locator": "lines:31-48"
    }
  ],
  "dependencies": [],
  "claim_ids": [],
  "assumptions": ["填写定理全部前提"],
  "metadata": {"scope": "原文定理定位；尚需检查能否应用到当前安全模型。"}
}
```

```powershell
.\research.cmd knowledge import my-project --file D:\Materials\theorem-record.json --reason "登记已定位的原文定理与前提"
.\research.cmd knowledge show my-project --id THM-EXTERNAL-001
```

每条记录要求 `schema_version: 1`、`id`、`kind`、`title`、`statement` 及非空 `sources`。每个来源包含项目内相对路径 `path` 与非空 `locator`。控制器记录实际文件 SHA-256；如果传入 `sha256`，必须与当前文件一致。路径逃逸、来源缺失或校验失败时拒绝导入。

定位可以用 `lines:31-48`、`json:/papers/0`，也可以写原文定位，例如 `page:4; theorem:2.1`。行范围和 JSON Pointer 会检查是否存在；PDF 页码或自然语言定位是可追溯声明，控制器不能据此保证已经读到、理解或核验原定理。

可选 `dependencies` 绑定其他知识节点的当前版本和摘要，按上游在先的顺序导入。`claim_ids` 关联现有主张，帮助检索与追溯；它不是证明边，不自动使关联主张成为已证结论。`assumptions`、`metadata` 和 `external_url` 用于记录前提、适用范围和原文网址；URL 本身不替代本地来源。

原有主张要把知识作为证明依赖时，在完整 `CLAIM_TEMPLATE.json` 草案中添加：

```json
{
  "knowledge_dependencies": ["THM-EXTERNAL-001"]
}
```

随后继续使用 `claim import`，控制器把知识当前版本与摘要保存在该主张的 `knowledge_pins` 中。上面仅显示需要添加的字段，不是可单独导入的完整主张。知识节点的 `claim_ids` 是检索关联；主张的 `knowledge_dependencies` 才使知识失效参与主张有效性检查。旧主张没有该字段时保持原依赖语义。

修改同一 ID 时必须显式重新导入并写原因，旧版本保留。新版本不会沿用旧版本的科学审核结论；相同内容重复登记不能制造新的研究进展。

## 追溯与上游失效

```powershell
.\research.cmd knowledge trace my-project --id THM-EXTERNAL-001
.\research.cmd knowledge impact my-project --id THM-EXTERNAL-001
.\research.cmd knowledge show my-project --id memory:THM-EXTERNAL-001 --revision 1
.\research.cmd knowledge show my-project --id claim:CLAIM-001
.\research.cmd knowledge invalidate my-project --id THM-EXTERNAL-001 --reason "原文假设不满足，暂停复用"
```

`trace` 沿上游定位节点版本、原文摘要和依赖；`impact` 查看受影响的下游知识与主张。知识 ID 和主张 ID 冲突时用 `memory:` 或 `claim:` 前缀消歧。`show --revision` 查看知识历史版本；原有主张历史继续保存在主张记录中。

知识历史搜索结果以 `memory:ID@rN` 标识版本。查看该结果时使用 `show --id memory:ID --revision N`；`trace --id` 选择当前节点，再从追溯输出查看其实际绑定的旧版本，不直接接收历史搜索键。主张历史命中以 `claim:ID@rN` 标识，原始历史保存在 `claim show` 返回的记录中。

追溯结果同时保留当前视图与精确绑定的历史：`nodes` / `edges` 展示当前状态，`frozen_nodes` / `frozen_edges` 展示该推导实际绑定的版本及来源快照。上游后来修订时，不能用当前版本的陈述冒充旧证明当时引用的版本。`unresolved_pins` 明确列出找不到完整快照的绑定，不能静默用最新来源补上。历史快照用于复查依赖，不使旧版本自动成为当前有效结论。

图谱快照保存当时登记的陈述、依赖及来源绑定，包括路径、定位、SHA-256 与已有摘录；它不会自动备份整份旧论文。复核历史全文时，应按对应摘要找到原件。

来源摘要变化、来源删除、冻结目标变化、上游知识被修订或显式失效，会使依赖链下游进入需要重新核验的状态；绑定该知识的原有主张也继续核对其冻结约束与正确性门禁。来源仍有漂移时，旧摘要不能让关联主张继续获得实现许可。明确失效及已登记的上游版本修订不会因为换回旧文件自动解除：需要显式重新绑定，并按原有审查接口复核。

只读查询发现的文件哈希漂移不会落盘或制造历史事件。如果仍是同一保存版本，并且文件完整恢复为原字节，原来源摘要可再次匹配。自动来源在 `refresh` 时生成新版本后，手动登记的下游知识和主张仍绑定旧版本，必须重新登记依赖；自动索引条目可以随明确来源链接修订，但仍是未核验来源。显式 `invalidate` 持久保存失效原因，自动刷新不能清除。需要正式撤回来源时，应登记明确失效，不能只临时改动文件。

图谱刷新只保存校验结果和事件，不覆盖原论文、失败记录、证明义务或研究状态。手动 `invalidate` 需要说明失效范围与原因，历史保留；恢复时以明确修订登记新版本，不删除失效事件。

## 权限与运行方式

写图操作沿用项目路线锁和科研执行锁，避免在正在执行的项目中并发覆盖图谱。只读查询可以查看当前已保存数据。图文件采用原子替换；校验失败不提交部分新节点。

科研代理和独立监督使用图谱帮助找到长期证据；冻结目标、安全定义、原始证明义务及独立审查门禁仍决定允许的研究范围。新项目从 `templates/project` 继承同样的指南与知识模板，无需项目专用代码。

## 自动研究中的刷新与失败处理

原有 `run` / `watch` 入口自动接入知识索引。每个通过控制器验收的科研轮，在保存已有路线与尝试结果、完成 `discovery.finalize_wrapper` 后刷新知识索引，再判断独立监督是否到达触发点。科研提示词和独立监督请求均注入有长度上限的只读知识上下文，优先显示已失效依赖和相关长期记录；需要完整证据时继续打开原始文件和追溯结果。

索引刷新不调用模型，也不追加科研或监督预算。刷新失败时，`logs/<项目ID>/latest-status.json` 的 `knowledge_index` 保存失败原因，控制器返回 `KNOWLEDGE_INDEX_FAILED` 并以退出码 3 停止本次后续监督及连续运行。已经验收的研究结果和已用预算保留，不能因索引失败重算为未执行。修复来源或图谱问题后，可先用 `knowledge refresh` 与只读查询确认，再继续原研究入口。

手动 `knowledge import`、`refresh`、`invalidate` 继续沿用项目锁；自动刷新在已验收轮的执行锁保护下进行。升级安装、查询和本次离线验证不会启动真实科研轮次，也不会为实际项目提前刷新图谱。

## 离线验证与范围

```powershell
python -m unittest discover -s tests -v
python research.py check all
python research.py knowledge status all
```

回归检查使用临时项目与本地材料，覆盖旧主张图兼容、来源定位、摘要与版本绑定、修订历史、知识及主张的失效传播、命令只读、既有锁、状态与预算保存。测试不会启动真实科研或监督模型。

本版本实现可追溯的知识管理与有效性控制。自然语言陈述的数学正确性、论文阅读完整性和科学新颖性仍需要原文与独立技术审查；图谱收录和离线测试通过均不能替代这些证据。
