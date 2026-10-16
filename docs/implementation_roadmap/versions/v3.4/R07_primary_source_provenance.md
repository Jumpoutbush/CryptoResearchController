# v3.4 · 开发轮次 R07：原始论文、定理和引文的版本化溯源

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

为图谱增加原始论文与定理级来源，严格区分摘要检索、全文定位、定理核查和模型推断；避免错误文献覆盖使路线被误杀。

**现有基础：** 现有 `literature/technical_reviews/` 使用六维技术比较，`research_quality.validate_technical_review()` 对全文与哈希有校验，`paper ingest` 保存原始 PDF 摘要。

**进入条件：** R06 图谱节点与边身份稳定且可重建。

## 2. 设计裁决与数据流

### 7.1 来源证据对象

`SOURCE_VERSION` 绑定论文标题、作者、会议/预印本版本、URL、PDF SHA-256、文字提取版本。`THEOREM_SPAN` 必须记录页码/章节/定理标记、文字摘要与对应版本；定位未知为 `LOCATION_UNVERIFIED`，绝不猜测页码。

技术覆盖判断由已有近邻文献审查模板及来源推出。新增图谱只允许把 `UNVERIFIED/RELATED/PARTIAL_OVERLAP/COVERS/CONTRADICTS` 的现有审核结果映射到节点，不允许自己判断“已经覆盖”。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `knowledge/sources.py`、`knowledge/adapters/technical_reviews.py`。
- 增加 `knowledge/source_schema.json` 或等价 Python 数据类。
- 新建 `tests/test_source_provenance.py` 和至少三份虚拟来源文档。
- 扩充 `knowledge explain ...` 输出 `source_file, sha256, location, review_status`。

## 4. Codex 必须完成的实现步骤

1. 复用 `literature/uploads.json`、`pdf_index.json` 和技术审查结果；逐项核对真实结构，不能以猜测字段直接使用。
2. 同一论文不同预印本版本分别建源节点，新增 `SUPERSEDES` 引用但保留旧证据。
3. 将每项“定理级覆盖”边绑定一份已有 `technical_review` 和其全文哈希；无此证据时是候选关系。
4. 设计引文引用串，例如 `project::source_sha::section/page::review_sha`，仅作为数据 ID，不能替代真正原文核对。
5. 原 PDF 缺失、重复上传、提取失败或页码偏移时，输出具体状态和恢复动作。
6. 图谱构建不主动进行网络下载；原文更新只走现有 `paper ingest`/`fetch` 合法接口。

## 5. 输入、输出与接口约定

建议返回结构：

```json
{
  "source_id": "project:sha256:paper",
  "version": "作者原文版本（核查后填写）",
  "source_sha256": "实际哈希",
  "location": "第 x 页／定理编号，待人工核对",
  "review_status": "FULLTEXT_CHECKED 或 LOCATION_UNVERIFIED",
  "technical_review_path": "项目相对路径或 null"
}
```

标签与枚举最终应和已有 `research_quality` 模式保持映射清晰。


## 6. 必做的离线自动测试

- PDF/文字提取文件被替换后，来源校验拒绝旧定理引用。
- 两个版本的同一论文不能因为标题相同被视为内容相同。
- 无全文只有搜索结果摘要时，禁止 `COVERS` 级判定被新图谱主动赋予。
- 含虚假页码、相对上级目录、SHA 不匹配的人工引文记录被拒绝。
- 重建图谱时无任何网络调用、无源码写入。

## 7. 本轮验收标准

- 最少一条技术审查可以从主张边追溯到实际原始 PDF 摘要、论文版本和定理位置。
- 未核查的定位被显式标记且不会进入定理覆盖证明。
- 新增来源索引不改变任何旧技术审查裁决。

## 8. 停止、回滚及禁止事项

无法获得原 PDF 时记录 `MISSING_PRIMARY_SOURCE` 并阻止使用该来源支持决定性否决。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
