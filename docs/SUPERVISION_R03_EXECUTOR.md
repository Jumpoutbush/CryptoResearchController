# R03 独立只读监督执行器

R03 只消费 R02 已冻结事件，生成 R01 SupervisorProposal 建议和独立完成回执。
不改写项目 GOAL、STATE、GATES、主张等级、研究会话、路线预算或指南。
watch/run 继续保持 R02 的队列行为；自动消费与指南应用尚未接入。

## 入口

```powershell
.\research.cmd supervise pending --dry-run
.\research.cmd supervise executor-info
.\research.cmd supervise execute <项目ID> --event-id <冻结事件ID> --executor fake --dry-run
```

只有 dry-run 完全不预留、不派发、不落盘。去掉 dry-run 会实际消费该事件一次
独立监督预算，默认 fake，产生明确标记 OFFLINE FAKE 的 PROPOSED；这只是测试
传输，不是科学审查，不能作为以后自动应用指南的依据。同一事件不能先 fake 后
再真实调用。请用下面的合成项目脚本验收，不在已有个人项目消耗测试预算。

```powershell
python -B scripts/verify_r03_offline.py --output <本地验收输出目录>
python -B -m unittest discover -s tests -p test_supervision_executor.py -v
```

脚本临时复制控制器代码与公共配置，自建离线样例项目，通过实际 research.cmd
（非 Windows 用 research.py）检查 dry-run、成功、原回执重放、真实模式阻断和
派发后未知结果不重派。输出正常完成回执、未知结果账本和逐步命令/退出码；
不读取或修改个人项目。脚本的两次预留全部在临时监督账本，非开发预算或科研轮次。

## 冻结契约及恢复

- 唯一 schema 是 supervision_contracts.proposal_schema()；R01 文件保持原字节。
  R03 规格中的示意 findings/accepted_findings/requires_approval 不新增为契约字段。
- 只从冻结正文生成一次性 data/source-N.txt 和 JSON 清单，不重读 live 来源、
  复制目录或展开文件中的宿主路径。原 AGENTS 名称不会被自动加载为执行指令。
  控制器仅元数据来源不转为正文；凭据和跨项目路径拒绝进入审查资料。
- 模型/effort 在原 R02 预留中冻结；CLI argv 为列表，提示经 stdin，无 shell 拼接。
  父进程保存输出；日志不共享科研代理 checkpoint/session/last_run。
- 严格 JSON 拒绝重复键、尾随文本、未知字段和非有限数。R01 验证准确来源哈希、
  目标锚点及义务；R03 再核对实际交付来源和明确的命令、URL、目标改写/等级升级请求。
  词法拒绝不能证明自然语言的数学真实性，所有提案仍是未验证建议。
- 成功仅为 PROPOSED；非法为 REJECTED/FAILED，当前绑定变化为 CONFLICT。
  save_completion 的可选 acceptance_guard 在原有锁内决定最终回执状态；
  不改变旧 R02 调用的默认行为。最终 receipt.state 优先于结构校验日志。
- 成本仍只有原 supervision ledger 一份；先保存不可变完成回执再原机制结算。
  重放先恢复已有成本，再判定是否为当前可接收的 R03 建议。旧 R02、陈旧或非法
  提案不会被升级接收，也不改写历史回执。
- 派发但无可信最终回执保持 UNKNOWN_EXTERNAL_OUTCOME，保留风险预留，禁止
  自动重派/退款。仅预留未派发的旧事件也不由新入口擅自接管。

## Windows 隔离门禁

本机 CLI 0.162.1 支持 read-only、结构化输出、独立临时会话和忽略用户配置等参数。
这只能证明参数兼容，不能证明宿主其他项目、CODEX_HOME 凭据和全局状态不可读。
官方说明 Windows unelevated 实现不提供 deny-read 的完整边界；限制读取需采用
受支持的强隔离策略并实测。[权限说明](https://learn.chatgpt.com/docs/permissions)、
[Windows 沙箱说明](https://learn.chatgpt.com/docs/windows/windows-sandbox)。

遵照 R03 升级附录“未验证 Windows 沙箱前仅允许假代理离线验收”，真实 backend
固定返回 BLOCKED_UNVERIFIED_OS_SANDBOX；没有强制开关或降级到可写模式。
已实现 CLI 能力探测、参数准备和受限 stdout transport，但尚未认证可调用的 OS
隔离适配器，不能启用真实/付费监督。此限制也适用于尚未认证的其他平台。
没有安装容器、创建系统账户、改全局配置或请求提权；没有模型调用。

transport 的 Windows Job 在挂起创建后接管子进程，再恢复运行，退出/超时/中断
都关闭 Job 清理子孙；这是进程生命周期约束，不是文件系统或网络隔离认证。
实现依据 [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)。

真实模式后续启用前必须有与确切 exe/版本/profile/工作区绑定的本机证据：快照可读
不可写，其他项目/宿主状态/模拟凭据拒读，子进程继承限制，工具网络被阻断，用户
配置、规则、MCP、hooks 不提供旁路。help、文件只读属性和假代理不算通过。

## 查看审计

在 Codex 桌面版打开根目录，查看：

- state/supervision/<项目>/event_queue/completions/<事件ID>.json：原始有界输出、
  最终状态、独立耗时、model/effort、exit_code、输入/输出哈希和错误分类。
- 同目录 executor-audits/*.json：以内容哈希分别保存预检阻断、输入失败、未知结果，
  早期预检记录不会覆盖后续故障记录；events.jsonl 保持原 R02 操作见证。

这些运行文件受 Git 忽略，应使用文件浏览器查看。R03 没有指南变化可供 Git 差异
审查，也不创建 ACTIVE_GUIDE。后续任务仍需单独授权，不能把本轮当作 R04/R05。
