# 09. 每轮执行契约（统一控制器强制加载）

必须输出且保存 `reports/<RUN_ID>.md`，报告开头明确 `RUN_ID: <RUN_ID>`。每轮执行至少一个可复核的实质动作，包括原文定理比对、反例脚本、完整引理证明或可复现协议实验。只输出“下一步研究计划”判定本轮无效。

## 报告结构

1. 研究决策：CONTINUE / PIVOT / NEEDS_REVIEW / PAUSE / STOP，及可核查原因。
2. 当前研究目标和冻结前提；本轮要证伪的最小命题。
3. 新文献覆盖状况：精确论文、原文页码/定理、已检查/未检查范围。
4. 实际执行记录：命令、文件、观察值与重要完整推导。正确性与安全性分离。
5. 结论分级：PROVED_FORMAL / PROVED_MANUAL_PENDING_REVIEW / CONDITIONAL / COMPUTATION_CHECKED / EXPERIMENTAL / REFUTED / HYPOTHESIS / UNKNOWN。
6. G0～G8 本轮受影响门禁的状态、证据和未闭合理由。
7. 失败原因、是否禁止重走、下一轮**唯一优先可执行任务**和成功/失败判据。

## 状态写回

更新 `research/STATE.json` 的 `phase`、`decision`、`priority_problem`、`next_task`、`open_obligations`、`publication_status`、`last_run`；保留未涉及的已有字段。`last_run` 必须等于本轮 RUN_ID，下一任务必须具体到可检验结果和证据文件。

补充 `research/CLAIMS.md`、`FAILED_PATHS.md`、`DECISION_LOG.md`、`GATES.json`，不能覆盖历史结论；必要时在原结论附订正及证据。凡声称来源于工具执行的结论必须留工具输出及版本。

## 自动化现实边界

控制器只会检查状态格式、报告存在及标识、证据文件链接和程序退出码；不会自动证明数学定理、安全归约、全部文献覆盖或论文新颖性。若网络服务不可用，记录真实失败并保留研究状态，不能误写成功。
