# 一、基线源代码核查与复用边界

核查基准：GitHub 仓库 `Jumpoutbush/CryptoResearchController`，提交 `67618536ecd172b2fad24843daf291489e226c2e`。这里只描述已检查到的旧版接口；新接口均是后续开发建议。

| 模块 | 现状（基准源码） | 升级策略 |
| --- | --- | --- |
| `research.py` / `research.cmd` | 现有命令前端，统一根目录/项目目录解析 | 增量增加 `supervise`、`knowledge`、`candidate`、`bench`，保留旧命令 |
| `runner.py` | `advance_one`、`record_round`、`apply_review`、`needs_review` | 只在已验收且事务完成后的边界记录监督事件 |
| `route_budget.py` | `effective_rounds`、`stagnation`、`review_pending`、`last_processed_run` | 作为科研轮次计数的唯一来源，不再建另一套科研预算 |
| `research_focus.py` | `binding`、`anchor_id`、`goal_impact`、`CORE/DIRECT_DEPENDENCY/SUPPORT` | 监督、候选树都绑定同一目标锚点 |
| `runner_core.py` | `build_prompt`、`ProjectTransaction`、`PROTECTED` 和 `PROTECTED_DIRS` | 注入单独监督指南，科研模型始终不能修改该指南 |
| `engine/discovery_scheduler.py` | 单固定问题尝试、候选提案、检查点、证明调用预算 | 候选搜索使用其问题与尝试对象，不能自行取消该限制 |
| `engine/claim_graph.py` | 主张版本、依赖、证明审查、新颖性审查与上游失效传播 | v3.4 增量建设派生索引，`claim_graph` 保持证明等级的权威来源 |
| `research_quality.py` | 研究回执、近邻文献技术比较、安全/成本工作类型 | 监督不能凭描述取代技术审查 |
| `config/defaults.json`、`configuration.py` | 双层模型路由（routine/critical）、严格配置字段校验 | 监督模型独立预算，默认可沿用 critical 路由；增字段必须同步改校验 |
| `templates/project/` | GOAL、STATE、AGENTS、inputs、proofs 等通用初始化 | 添加最小模板能力，禁止逐项目拷贝 Python 代理 |

## 重要现有保护

`runner_core.py` 里 `AGENTS.md` 和 `prompts/continue.md` 已属于受保护内容；`prompts/`、`inputs/`、`ideas/` 也是受保护目录。原控制器对科研轮次有事务快照与失败恢复。**新监督的写入必须在研究事务完成且锁释放之后，经过独立可信校验器执行**。

`engine/discovery_scheduler.py` 明确限制 `strategy='single_deep_reasoner'`。v3.5 引入多候选时，不要悄悄放宽此字段的校验或强行并行运行多个写代理；建议将“候选树搜索”作为更外层的候选选择，而每个活动尝试继续使用单个深度研究者，直到并发正确性经过验证。

## 启动前核查清单

```powershell
cd D:\CryptoResearchController
git status --short
git rev-parse HEAD
.\research.cmd doctor --offline
.\research.cmd check all
python -m unittest discover -s tests -v
```

若发现本地分支已包含监督功能，先逐项对照规格，不重复覆盖。当前真实模型及联网的可用性须由本机 `codex --version`、`codex exec --help` 和登录状态确认。

## 源码定位

- `docs/MAINLINE_FOCUS.md`：主线锚定、`refocus`、路线复评边界。
- `docs/MATHEMATICAL_DISCOVERY_V3.2.md`：固定问题、调用预算、检查点与独立验证。
- `docs/USER_MANUAL.md`：命令接口与 Windows 路径使用。
- `README.md`、`docs/ARCHITECTURE.md`：统一目录与调度架构。
