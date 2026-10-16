# R04 受控指南应用与恢复

R04 只把已结算、已确认的 R03 建议交给可信模板生成单独的
`supervision/ACTIVE_GUIDE.md`。GOAL、AGENTS、continue、STATE、GATES、路线预算、
主张等级和原监督成本账本保持不变。R01 schema 不增加字段，R03 真实后端继续阻断。

## OpenSource addendum 参考与适配

已读取并导入 `UPGRADE_20261016/round_addenda/R04_open_source_addendum.md`，
本轮使用其中 ARA 的证据优先工件原则作为设计参考。

- 上游 [ARA 固定提交](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/commit/e52a925e9d03b4ada3008653e72f99b04116fca2)：
  `e52a925e9d03b4ada3008653e72f99b04116fca2`。
- [LICENSE](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/LICENSE)：
  MIT，Copyright 2026 Orchestra Research；SHA-256
  `25ba8a25365fdc8475b0f7b4818d8ea629cb69d24e30632b0e1a95c759d7368a`。
- [research-manager](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/skills/research-manager/SKILL.md)：
  参考 Layer Mutability、Edit procedure、Provenance for revisions。当前视图与不可覆写
  历史分离，保留来源和完整修订版本，冲突显式记录。
- [rigor-reviewer](https://github.com/ARA-Labs/Agent-Native-Research-Artifact/blob/e52a925e9d03b4ada3008653e72f99b04116fca2/skills/rigor-reviewer/SKILL.md)：
  参考 Evidence Relevance、Falsifiability Quality、Scope Calibration。
  存在引用不等于证明充分；任务、成功条件、证伪条件分别呈现，不能升级科学结论。

| 参考原则 | 本地适配 | 必要验证 |
| --- | --- | --- |
| 当前视图和历史分离 | ACTIVE_GUIDE + 不可变 plan/receipt + 原 R02 操作见证 | 重复 apply、两版 rollback、历史损坏拒绝 |
| 修订来源追溯 | 绑定 R01 event/snapshot、R03 completion/proposal SHA 和旧/新指南 SHA | 来源/最新验收轮次/目标变化拒绝 |
| 冲突保留 | CAS，恢复只认可已记录的旧/新版本 | 第三种 SHA 不覆盖，人工编辑保留 |
| 结论范围与证伪要求 | 可信章节，引用转义，不增加 proof authority | 危险中英文结论/命令拒绝，Markdown 和字节上限 |

通过公开 GitHub 固定 SHA 页面和 raw 文本只读核验，未安装、执行或复制上游系统，
未把上游 SKILL 作为本地高权限指令加载。没有新增第三方运行依赖。
公开 API 匿名限流、git 代理不可用时使用 HTTPS 固定版本核验；详细文件哈希见本轮交付回执。

## 入口与权限

```powershell
.\research.cmd supervise preview <项目> --event <事件ID>
.\research.cmd supervise apply <项目> --event <事件ID> --expected-hash <旧SHA或ABSENT>
.\research.cmd supervise rollback <项目> --event <事件ID> --expected-hash <当前SHA>
.\research.cmd supervise guide-recover <项目> --event <事件ID>
```

旧 `rollback --id review-...` 入口保留。预览不落盘、不结算成本、不请求模型。
R04 不自动消费队列，也不接入 watch 自动应用。PAUSE/ESCALATE 和需人工批准的
建议保持 ADVISORY_ONLY，不修改 STATE 或预算；没有隐含的强制批准参数。

目前仅允许在临时根 `crc-r04-fixture-*`、位于 OS 临时目录且没有 .git，并由测试
控制器注册项目标记的合成样例中应用 Fake。门禁取自持久 R03 回执 backend，
没有允许个人项目 Fake 的 CLI 开关。真实 backend 不会被 R04 解禁。

## 事务与恢复

1. 校验原 R03 完成回执及完成/结算见证，不调用模型或预算恢复函数。
2. 核对目标锚点、route epoch、想法、最新已验收轮次及全部冻结来源哈希。
   安全 inputs 必须在冻结 manifest 中完整覆盖；未捕获约束不能被默默忽略。
   只读核对现有主张状态，禁止 refresh/save 或升级等级。
3. 可信模板转义候选文本，最终 Markdown 含元数据最多 12 KiB（UTF-8）。
4. 持原 route/core/queue 锁，以旧 SHA 比较交换；无文件固定使用 ABSENT，空文件
   与不存在有不同版本。固化完整前后字节、diff、来源绑定，再原子替换。
5. 应用回执持久化后追加原操作日志的 GUIDE_APPLIED；队列投影 APPLIED，原成本
   reservation 保持 PROPOSED，原预算账本一个字节不写。

同事件只能创建一个计划；重复调用重放原回执，不覆盖后来的版本。回滚只允许
当前确切版本，恢复完整旧字节或原本不存在状态；已回滚事件不能重新应用。

普通写入失败回到旧版本；强制终止后若当前是新完整 SHA，补原回执；若仍是旧 SHA，
继续同一已固化计划。第三种 SHA 拒绝覆盖。回执已落盘但 ACK 丢失只补 ACK；
已确认历史或回执丢失则停止，不能重新合成。未提交新指南遇来源过期，恢复旧版并
保存 REJECTED_STALE 终止回执。同一事件不渲染第二版。

## 下一轮提示与保护

build_prompt 在原 AGENTS/continue 之后只加载一次校验通过的指南，重申 GOAL、
固定问题、安全模型、证明义务、门禁和 route-review 优先。普通 read_order 不加载
supervision 内容，防止别名绕过校验。原无指南项目的提示文本保持不变。

输入或主张状态变化后输出 EXPIRED 通知，不注入旧任务；人工篡改或替换后事务未完成
时要求恢复。仅预备但旧版完整的失败事务可继续读取上一份合法指南。
整个 supervision/ 由现有 ProjectTransaction 保护，科研代理新建、删除或篡改都会被拒绝并恢复。

本轮验收入口：

```powershell
python -B -m unittest discover -s tests -p test_supervision_guide.py -v
python -B scripts/verify_r04_offline.py --output <本地证据目录>
```

脚本只生成临时合成项目，经实际 research.cmd 完成预览、应用、重放、真实 prompt
构建、回滚、强制终止控制器及恢复，输出正常/故障回执和 diff。个人项目保持只读。
运行工件在 `state/supervision/<项目>/event_queue/guide-*`，受 Git 忽略，使用桌面版
文件浏览器查看；代码和模板变化可看 Git 差异。恢复只处理该指南，不能回滚科研历史。
