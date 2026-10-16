# Controller-owned supervision guides

ACTIVE_GUIDE.md is generated only by the trusted controller from a validated
R03 proposal. Research agents must not create, edit or delete this directory.
GOAL, security assumptions, frozen problem, proof obligations, gates and route
review directives take priority. A guide never certifies a theorem.

The next research prompt loads a verified guide once, after AGENTS.md and
prompts/continue.md. Changed inputs expire it; untracked edits or incomplete
replacement require operator recovery. User instruction files are not rewritten.

Preview, apply with the exact old hash, rollback with the exact current hash,
and guide-recover are available through the root research.cmd supervise entry.
Full old/new bytes, SHA-256, diff and application receipts are retained in the
controller's state/supervision/<project>/event_queue/guide-* artifacts. Restore
these local artifacts together; Git cannot restore ignored project files.

In R04 the real Codex backend remains blocked. Fake proposals may be applied only
inside explicitly registered disposable synthetic fixtures created by the offline
acceptance harness; there is no allow-fake switch for personal projects.
# R05 默认关闭与恢复

新项目直接复用统一 `run/watch` 监督链，无需项目专用脚本。活动指南由可信控制器
在显式启用后生成；模板不创建 ACTIVE_GUIDE。`supervise enable <project>` 选择生产
Codex 后端，但当前 OS 隔离门禁仍阻断；Fake 仅用于注册临时夹具。
`supervise disable <project>` 关闭自动监督及指南注入，保留全部历史和预算。
`supervise recover <project>` 复用原回执/计划，不重跑研究、不重试未知外部结果。
