# 12ccad9 审查修复跟踪

来源为用户提供的 `CryptoResearchController-review-12ccad9-20261017.md`。报告固定
`12ccad9be3de89fa1e303a1e648f55991d5ee9fb`，仅作远程静态审查，没有执行复现。
本文件记录后续本地修复；不改写原报告的 FAIL 裁决，不代替独立复审。
本次用户在 R15 开发期间提供该报告，N01—N04 的修复与本轮离线验收一并列明。

| 项目 | 修复范围 | 验证材料 |
| --- | --- | --- |
| N01 固定尝试消费遗忘 | 统一 discovery 权威加载、独立登记及冻结本地恢复；旧数据显式迁移、禁止缺失或回退清零 | `test_review_discovery_authority.py`、`test_discovery_authority_cli.py`；最终审查组与完整回归通过 |
| N02 自适应腐化预算范围 | 精确比较候选与冻结模型的 corruption_budget_scope，不更改原理想接口摘要版本 | `test_review_security_scope.py`；完整双轮自适应样例与范围缺失/双向变化 |
| N03 长期成功映射 | 从原不可裁剪 COMPLETE 接受归档核验，已提交映射重放不依赖展示窗口 | `test_review_candidate_history.py`；真实原本地接受/结算 API |
| N04 cache-only 文档 | 保留原恢复行为，修正说明和 CLI 帮助，区分派生修复与 canonical 持久撤销 | `test_review_cache_only_semantics.py`；普通构建、只读预览、缓存修复与显式刷新 |

## cache-only 的准确语义

普通 `knowledge build` 检测到尚未记录的新失效时停止，不写缓存或观察历史，提示先执行
`claim refresh`。`--dry-run` 只返回诊断；`--cache-only` 是恢复例外，可以更新派生 index，
返回 `pending_revocations`，同时保留 canonical 主张和 R08 观察历史。它不记录持久失效锁，
不授予科学认可，也不代表完成了重新审查。需要持久观察时仍须显式 `claim refresh`。
只读或 cache-only 观察后恢复原字节，不能声称旧认可已经被永久撤销。

## 保护范围

固定尝试的显式迁移与恢复入口如下；参数使用上一条状态输出里的实际 SHA，不能换成旧备份
或随意重算的零消费版本：

```powershell
.\research.cmd attempt authority-status <project>
.\research.cmd attempt authority-enroll <project> --expected-ledger-sha256 <actual_ledger_sha256> --reason "已核对完整旧调用、尝试和证据历史"
.\research.cmd attempt authority-recover <project> --expected-afterimage-sha256 <pending_afterimage_sha256> --reason "只完成原冻结本地后像，不重新派发调用"
```

`authority-status` 纯只读；已登记后的缺失、回退和冲突不能通过再次 enroll 绕过。没有可信
冻结后像时 recover 也不能补造丢失消费。恢复只完成原本地账本事务，不运行科研或重新执行
独立检查；原调用若仍未知，恢复元数据后仍然禁止自动重试。R15 切换遇到底层 pending 时，
先恢复同一冻结 authority 后像，再显式恢复原 switch，不能先覆盖 STATE。
备份须共同保存 `state/discovery/`、`state/discovery_registry/`、
`state/discovery_registration/`、原接受归档及路线见证。完整旧账本须显式核对和登记，
空或无法证明完整的历史不能自动当作零消费迁移。此轮未替个人项目执行这些写操作。

路线有效科研轮、固定尝试实际调用、独立监督消费仍是不同权威；新增登记不是另一份余额。
迁移、恢复或分支切换不得重新派发未知调用、重复结算、删除失败记录或放宽原目标。
个人项目和既有运行文件不自动迁移；真实监督与 Lean 保持阻断，无付费轮次或远程推送。
最终执行命令、失败复现、完整回归、提交和保留校验见本会话 `outputs/R15/` 与实施追踪表。

## 实际离线验收

2026-10-17，审查专项 `python -B -m unittest discover -s tests -p "test_review_*.py" -v`
118/118 通过（281.441 秒），包含原 83 项与新增 35 项。新调用权威 CLI 专项另有 2/2 通过。
全套 `python -B -m unittest discover -s tests -v` 887 项，886 通过、1 项原 POSIX 跳过，
1638.062 秒、退出 0。R15 真实 Windows 临时入口模拟 84 步通过；仅 1 次固定整数 worker，
模型、网络、监督、Lean 全为 0。实际三项目 check all 和 doctor --offline 均退出 0。
145 份公开 Python 源在最终专项、入口和全回归期间 SHA 一致；843 份个人文件路径及 SHA 不变。

修复前的失败证据分别保留；N03 最早 RED 只有工具/消息记录，没有原始落盘日志，未补造。
N04 首次测试失败来自把 Windows 锁标记也算作数据权威变更的夹具观察错误，修正后验证原有
cache-only 行为；它不是额外产品缺陷。T01—T07 的具体方法名、日志摘要和证据级别见
`review-12ccad9-closure-audit.json`，不能把本地修复验收冒充原报告作者的独立复审结果。
