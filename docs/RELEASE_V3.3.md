# v3.3：独立监督与安全指南修订

版本：`3.3.0-independent-supervision`。

本次把现有路线预算与科研执行器接入独立监督闭环。所有项目共用 `supervision.py`，新项目通过 `templates/project` 继承管理区；各项目仍以自己的冻结目标、证据和预算为准。实现采用独立职责、结构化提案、持久审计和幂等重放这些通用模式，没有迁移整个运行框架或复制第三方科研系统源码。

公开机制的参照是 [Google Co-Scientist 的独立 Supervisor 与专门代理分工](https://research.google/blog/accelerating-scientific-breakthroughs-with-an-ai-co-scientist/) 和 [LangGraph 的检查点、待完成写入与故障恢复](https://docs.langchain.com/oss/python/langgraph/checkpointers)。本期用现有 Python 控制器实现适合本地密码学项目的监督边界；这属于对公开设计的借鉴，不是这些系统内部算法的完整复现。AI Scientist v2 的候选树留到 v3.5 再按公开实现与验证条件接入。

## 本次实现

1. 每三轮计入路线预算的已验收科研工作触发监督；预算耗尽时，在已有路线复评前执行监督。失败轮次、预览和路线复评不占用周期计数。
2. 独立只读监督进程读取当前项目与控制器，返回 schema 2 的结构化裁决。冻结目标、现有证明义务、核心问题和证据摘要均参与校验。
3. 先保存 `verdict.json`、`evidence_map.json`、`guide.patch`、`guidance.md` 和版本清单，再由控制器在锁内应用管理区补丁。短期调度指南版本化；长期 `AGENTS.md` 修改必须另有理由。
4. 输入或指南冲突时拒绝过期提案；写入失败时恢复原字节。保留失败提案、前后版本及事务日志，重启时先恢复未完成事务。
5. 独立限制监督执行次数、单次时限、累计时长和同次触发重试数。重复触发幂等，失败尝试同样计费；配置与回滚均不重置科研或监督消耗。
6. 统一 `supervision status/history/show/configure/run/rollback` 入口，下一轮自动加载已应用指南。`PAUSE`、`RECOMMEND_STOP` 及需要人工批准的裁决阻止继续自动研究。

监督只调整方法和下一任务，不修改 `GOAL.md`、`STATE.json`、安全模型、证明义务、研究结论、失败证据或路线预算。它的裁决不替代证明审查、原文查新或理论实现门禁。

## 使用

```powershell
Set-Location D:\CryptoResearchController
.\research.cmd --version
.\research.cmd supervision status all
.\research.cmd supervision configure all --enabled on
.\research.cmd watch secagg-research --max-rounds 8
```

全局默认关闭。已开启项目保留原配置、登记起点和消耗记录；首次登记前的历史科研轮次不补算周期监督。`configure` 不调用模型，真实 `run` / `watch` 到达触发点才启动独立监督。手动 `supervision run <项目> --force` 也可能调用模型。

只读检查与人工回滚：

```powershell
.\research.cmd supervision history all
.\research.cmd supervision show secagg-research
.\research.cmd supervision show secagg-research --id REVIEW_ID
.\research.cmd supervision run secagg-research --dry-run
.\research.cmd supervision rollback secagg-research --id REVIEW_ID
```

在桌面版打开 `show` 返回的审计文件路径，先看 `verdict.json` 与证据映射，再看 `guide.patch` 与 `guidance.md`。私有项目及运行状态默认被 Git 忽略；仓库 Git 差异主要展示控制器与模板，项目指南变化应查看保存的审计补丁。全部配置、冲突及回滚规则见 [监督手册](SUPERVISION.md)。

## 验证边界

```powershell
python -m unittest discover -s tests -v
python research.py check all
python research.py supervision status all
python -m unittest discover -s tests -p test_supervision_quality.py -v
```

自动化回归使用临时项目和模拟模型，核对连续偏离核心任务后的重新聚焦提案、版本与范围检查、预算保存、幂等、冲突、进程隔离、失败恢复以及回滚。`tests/research_benchmark/supervision_cases.json` 保存独立预期的偏移与正常样本；`supervision_quality.py` 从已验收控制器收据提取连续辅助工作、缺少主线推进及相同科学证据内容换名重复等调度信号。

这些规则只能核对显式收据与文件内容，不能验证自然语言相关性或数学正确性。已知样本用于离线验证预期信号、裁决及控制器流程，不衡量真实模型的监督准确率，也不能证明提高了开放问题求解率。本次开发不运行真实付费科研或监督轮次。

## 迈向 v4.0

| 版本 | 范围 | 当前状态 |
| --- | --- | --- |
| v3.3 | 独立监督、结构化裁决、安全指南修订、离线回归 | 本次交付 |
| v3.4 | 合并主张、论文、证据、失败路线和证明义务；来源追溯与上游失效传播 | 后续计划 |
| v3.5 | 最多三个活跃候选的有界研究树、证伪优先调度、分支恢复及扩展独立验证 | 后续计划 |
| v4.0 | CryptoResearchBench、不同架构与调度策略对照、经版本化验证的自适应资源调度 | 后续计划 |

v3.2 已有主张依赖图、精确计算与 Lean 接口；v3.4 / v3.5 应在这些接口上扩展。现有 `scripts/discovery_benchmark.py` 是精确整数验证器样例，v3.3 的监督回放是流程回归，它们均不等于完整的 CryptoResearchBench。真实质量评估需要独立答案或反例证书、固定任务与预算，并分别记录错误结论认可、偏移轮次及有效进展。
