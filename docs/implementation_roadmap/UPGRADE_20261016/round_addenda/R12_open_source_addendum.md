# v3.5 R12 开源融合附录：证伪优先的有界研究调度

> 这是原版 `versions/v3.5/R12_*.md` 的**补充实施规格**，原文仍是基础契约。现有代码优先，新增内容不得倒逼重做先前轮次。科学进展与开发提交分别验收。

## 一、本轮明确交付

只在已有高价值候选之间排序下一项可证伪任务，不新建独立研究轮次账本。

## 二、对应的公开实现 / 已有代码

[AIDE agent.search_policy](https://github.com/WecoAI/aideml/blob/main/aide/agent.py)；[OpenEvolve database](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/openevolve/database.py)。外部仓库读取时核对当前许可证并固定 SHA；不得直接安装运行整个系统。

## 三、推荐修改位置（以本机已实现模块为准）

1. `candidate_search/scheduler.py`、`candidate_search/cost_accounting.py`
2. `tests/test_candidate_scheduler.py`、`tests/test_candidate_budget.py`

## 四、本轮实现及技术取舍

1. 先按论文直接覆盖、决定性反例、安全游戏障碍过滤，再允许进入构造比较
2. 候选收益评估依赖真实证据和可计算开销；LMM/Elo 分数只作附带信息
3. 共同使用 route_budget 的 effective_rounds，固定问题继续由原 attempt 预算记账
4. 候选切换仍须通过原 `problem import/attempt close/start` 权限边界
5. 排序日志写入候选审查历史与选择原因，以便监督代理复查

## 五、必须增加的失败测试

1. 三个分支不会创造三个新的路线预算
2. 固定 attempt 活跃时没有悄悄切换问题
3. 同等证据下排序可决定性重放
4. 候选自称成本更低却未证安全时不能直接胜出

## 六、本轮退出条件

能在三候选中推荐一条基于决定性证据的下一任务，研究消耗量与旧账本严格一致。

**统一禁止项**：不能改写个人项目 `GOAL.md`、研究成果状态或独立审查回执；不能默许模型把候选变已证明；不得因添加新模块重置已有科研轮次预算。每轮记录外部源码的具体上游提交、许可证、参考函数/文件、替代原理及必要适配测试。
