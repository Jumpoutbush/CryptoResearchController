# v3.4 R07 开源融合附录：论文定理来源与版本锚定

> 这是原版 `versions/v3.4/R07_*.md` 的**补充实施规格**，原文仍是基础契约。现有代码优先，新增内容不得倒逼重做先前轮次。科学进展与开发提交分别验收。

## 一、本轮明确交付

记录论文版本、原始 PDF、页/定理区间、公式提取可信度，把检索命中与技术覆盖裁决分开。

## 二、对应的公开实现 / 已有代码

[PaperQA2](https://github.com/Future-House/paper-qa)：`src/paperqa/agents/main.py` 的检索—聚证结构；旧 technical reviews 六维比较。外部仓库读取时核对当前许可证并固定 SHA；不得直接安装运行整个系统。

## 三、推荐修改位置（以本机已实现模块为准）

1. `knowledge/sources.py` 和来源段落 schema
2. `tests/test_source_provenance.py`；扩充 `literature/technical_reviews` 映射

## 四、本轮实现及技术取舍

1. 数据记录 PDF SHA-256、版本、定位、短文本摘要和文字抽取器版本
2. 建立 SOURCE→SPAN→CLAIM→REVIEW 映射，未知页码必须标 LOCATION_UNVERIFIED
3. 保留原有六维比较作为权威原文技术审查接口，增强引用目标的哈希
4. 对 PDF 数学上下标与符号无法可靠提取时须提示原页面复核
5. 拒绝根据摘要直接声称已有工作完全覆盖

## 五、必须增加的失败测试

1. 相同标题的预印本 v1/v2 不错误合并
2. 论文定理的量词和本项目敌手模型冲突时不能给 COVERS
3. PDF 摘要变化时索引正确过期
4. 数学公式抽取有错时保持 MATH_RENDER_UNCERTAIN

## 六、本轮退出条件

能从一条主张定位到明确的原始文件、定理位置和版本，错误原文来源不可通过技术审核。

**统一禁止项**：不能改写个人项目 `GOAL.md`、研究成果状态或独立审查回执；不能默许模型把候选变已证明；不得因添加新模块重置已有科研轮次预算。每轮记录外部源码的具体上游提交、许可证、参考函数/文件、替代原理及必要适配测试。

## 七、补充公开研究/验证基准

参考 `UPGRADE_20261016/12_PUBLIC_RESEARCH_EVIDENCE_REFERENCES.md`。OpenAI Math 的已发布数学工件、PaperBench 的独立复现评分和 Google Science One 的证据链审计只能在对应的权限与安全定义下复用；实现时记录核对的上游 SHA 和本地适配测试，禁止据此自动升级数学主张状态。
