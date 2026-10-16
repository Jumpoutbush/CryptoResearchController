# v3.5 R13 开源融合附录：数学验证适配器与形式命题对应

> 这是原版 `versions/v3.5/R13_*.md` 的**补充实施规格**，原文仍是基础契约。现有代码优先，新增内容不得倒逼重做先前轮次。科学进展与开发提交分别验收。

## 一、本轮明确交付

把精确整数反例、符号计算和 Lean 工具接入统一回执，同时阻止形式化缩弱定理。

## 二、对应的公开实现 / 已有代码

[Numina-Lean-Agent](https://github.com/project-numina/numina-lean-agent/blob/main/tutorial/usage.md) 的逐题工具轨迹；[OpenEvolve evaluator](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/openevolve/evaluator.py) 的分级检查。外部仓库读取时核对当前许可证并固定 SHA；不得直接安装运行整个系统。

## 三、推荐修改位置（以本机已实现模块为准）

1. `candidate_search/verifiers/*` 对旧验证器的轻量包装
2. `tests/test_verifier_adapters.py`

## 四、本轮实现及技术取舍

1. 所有验证结果注明具体前提、检查命题版本、工具版本、源码与依赖哈希
2. 有限范围未找到反例只能产生 NO_COUNTEREXAMPLE_WITHIN_BOUND
3. Lean 编译成功须另核验全部公理、声明类型、自然语言量词与精确对应
4. 采取 OpenEvolve 式廉价阶段先行，但所有程序核验运行在隔离进程与资源界内
5. 保留已有 verify lean 和 claim review 的权威审查等级，不造第二套接受状态

## 五、必须增加的失败测试

1. 量词被弱化后编译通过，系统不允许认证原命题
2. 整数谓词 10000 点未反例不标 PROVED
3. 代码抛异常/超时留下完整工具结果，不污染 claim 状态
4. 目标源码被修改后旧回执自动失效

## 六、本轮退出条件

统一工具回执可复查、可由现有 claim review 审查，未审的数学证明仍为候选。

**统一禁止项**：不能改写个人项目 `GOAL.md`、研究成果状态或独立审查回执；不能默许模型把候选变已证明；不得因添加新模块重置已有科研轮次预算。每轮记录外部源码的具体上游提交、许可证、参考函数/文件、替代原理及必要适配测试。

## 七、补充公开研究/验证基准

参考 `UPGRADE_20261016/12_PUBLIC_RESEARCH_EVIDENCE_REFERENCES.md`。OpenAI Math 的已发布数学工件、PaperBench 的独立复现评分和 Google Science One 的证据链审计只能在对应的权限与安全定义下复用；实现时记录核对的上游 SHA 和本地适配测试，禁止据此自动升级数学主张状态。
