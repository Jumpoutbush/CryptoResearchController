# R07/R09：借鉴 PaperQA2 的论文检索、可追溯证据与成本约束

**上游阅读入口**：[PaperQA2 README](https://github.com/Future-House/paper-qa) · [`src/paperqa/agents/main.py`](https://github.com/Future-House/paper-qa/blob/main/src/paperqa/agents/main.py)。上游使用迭代检索、证据聚合及重排；默认依赖可选模型与嵌入工具，最新 v5 要求 Python 3.11+。现有控制器 Python 3.10+ 核心必须保持可工作。

## 一、最低可实现的证据处理管线

`检索计划 → 元数据与论文版本 → PDF SHA-256 → 文本/数学区域提取 → 带锚点的片段索引 → 两阶段检索 → 技术级对照 → 人工/独立确认 → 图谱引用`。

每一层都保存结构化回执，源文件和版本变化时由统一缓存失效机制重建。只有摘要不能标记 `FULLTEXT_CHECKED`；数学公式抽取失败必须标记 `MATH_RENDER_UNCERTAIN` 并引用原 PDF 版面。

建议的段落记录（草案，最终由 R07 固定）：

```json
{
  "source_id": "paper-2026-001",
  "source_sha256": "64位实际十六进制摘要",
  "version_label": "eprint-v2-or-camera-ready",
  "locator": {"page": 8, "section": "5", "theorem": "Theorem 2"},
  "extraction": {"engine": "pymupdf-pinned", "status": "MATH_RENDER_UNCERTAIN"},
  "quote_hash": "实际段落字节摘要",
  "claim_id": "CLAIM-001",
  "support_role": "CANDIDATE_SOURCE"
}
```

示例中的页码/定理编号仅为格式说明。生产文件须引用真实位置、来源摘要和模型可核验的短引文，不允许凭空填写。

## 二、文献技术审查不能停在“语义相似”

借鉴 PaperQA2 可以快速缩小候选原文范围，但研究结论还需明确六维差异：`功能、敌手、假设、输出、参数、代价`。旧版 `research_quality.validate_technical_review` 已具备六维结构检查，优先扩展现有接口。

对每个候选近邻论文，至少记录原文明示的定理及假设，并独立推导从它到本项目主张是否存在低成本黑盒组合。不能只引用作者摘要或模型回答宣布“完全覆盖”。

## 三、最小增量模块

- `knowledge/sources.py`：保留原始 PDF/来源版本与哈希。
- `knowledge/spans.py`（可选）：结构化定理/算法片段，原 PDF 页标识和提取质量。
- `knowledge/retrieval.py`：确定性字面索引第一阶段；按需接入可选语义重排器。
- `literature/technical_reviews/`：沿用现有六维比较结果，绑定 span ID，不另建权威审查数据库。

搜索加速仅决定证据阅读顺序，不自动改变验证等级。默认无 API 密钥、无嵌入服务时应提供确定性全文/关键词检索，并且没有额外收费。

## 四、必须通过的反例与测试

1. 同名论文 arXiv/ePrint/会议版本不同时，不合并为同一来源哈希。
2. 一个定理的量词限定为静态敌手，但本项目要求自适应敌手时，系统不能判为完全覆盖。
3. PDF 抽取漏掉不等式符号、上下标或脚注时，必须保留 `MATH_RENDER_UNCERTAIN` 与原始页锚点。
4. 撤稿/失效论文的索引和缓存必须使对应“可信证据”过期并触发审查（不能自己判数学结论假）。
5. 用户论文私有时，禁用向外部服务上传片段和嵌入；除非用户为该项目授权。
6. 检索结果正文包含提示注入，不能被解释为控制器命令。
7. 低端离线环境不安装 PaperQA2 也能完成文献入库、原文哈希和基础词项检索。
