# 主线偏移修复与恢复

本修复基于提交 `4d84222bd0b737719e00bf6946d8f0a9d95afe78`，处理普通 `run` / `watch` 路线调度中的旁支累积。固定命题发现引擎的检查点、独立核验和理论就绪门禁继续生效。

## 原因与修复

| 原有行为 | 影响 | 修复后的行为 |
| --- | --- | --- |
| 预算复评追加 `--audit`，要求审查上轮结果，并加载项目独立审稿提示 | 最后一个旁支引理被继续深入，主目标缺少重新选择任务的机会 | 自动复评使用 `--route-review` 和专门任务选择提示，明确判断旁支是否必要；证明审查仍有独立入口 |
| `PROOF` / `COUNTEREXAMPLE` 的 `SUPPORT_ONLY` 回执可以被新的证据文件计作进展 | 文献补证和勘误反复清零停滞 | 支持性状态不计主线进展；仍保留成果、消耗轮数。连续支持性轮次达到现有阈值后安排复评，默认阈值为 2 |
| 模型持续改写 `priority_problem` 和 `next_task` | 局部问题可以逐步替代核心研究任务 | 控制器在路线账本固定核心问题，绑定 GOAL 摘要、路线和选中想法；模型改写任务不会改变锚点 |
| 恢复只能改任务或停机状态，缺少保留预算的专用入口 | 容易清零预算、重新开始旁支，或误将待审材料认可 | `refocus` 显式安排下一核心任务，保留已用轮数、证明状态、开放义务与历史材料，追加预算另行记录 |

日志新增 `MAINLINE_SCOPE`、`MAINLINE_PROGRESS` 与原因。`SUCCEEDED`、回执合格或证据链接有效，仍然只表示执行及结构检查通过。

## 每轮如何绑定主线

`ROUND_REVIEW.json` 增加 `goal_impact`，具体锚点由提示词注入。填写 `anchor_id`、`scope`、`target_obligation`、`before`、`after`、`next_mainline_task`。范围有三个：

- `CORE`：直接改变核心构造、安全义务、成本界或决定性的文献覆盖判断。
- `DIRECT_DEPENDENCY`：直接依赖；另填 `consumer_claim` 与 `dependency_argument`，说明主方案哪一步使用它，以及缺少它会阻断什么。
- `SUPPORT`：暂不能建立直接使用关系的背景、勘误或辅助材料。

有用的核心反例可以使用 `contribution_type=NONE`，无需虚构原创贡献。结果状态须如实填写：例如确实反驳了固定前提下的候选时用 `REFUTED`；只有支持作用时用 `SUPPORT_ONLY`。

控制器检查锚点匹配、前后义务有变化、路线信号与回执共享本轮变动证据，并检查证据内容是否已计数。改名后的相同证据不能重新计数。旧回执或错误关联仍保留为未分类工作，不会通过它们清零主线停滞。

这些检查验证关联声明与证据结构。它们不能自动证明声明的数学相关性或定理真实性；技术判断和科学门禁仍须独立处理。

## 复评如何继续

`REFOCUS` 使用原路线剩余预算重新选任务。`EXTEND` 受已有自动延期上限约束。两者都必须提交 `next_task` 及 `next_goal_impact`，明确当前缺口、拟判定的结果和直接核心关联，且保持 `STATE.decision=CONTINUE`。

未被主构造使用的旁支引理可以保持待审，同时推进不依赖它的任务。若核心任务确实依赖尚未验证的命题，应明确条件或安排必要审查。模型发出的 `STOP`、`PAUSE` 或 `NEEDS_REVIEW` 仍会被尊重，控制器不会自动覆写它们。

## 已暂停项目的恢复

更新框架本身不会改动项目的 `STATE.json` 或已有预算。首次读取旧账本时，缺少锚点的路线以冻结 `GOAL.md` 建立默认核心问题，避免沿用已经偏移的 `priority_problem`；只读检查不写账本。

在仓库根目录执行，先检查当前项目：

```powershell
.\research.cmd check secagg-research
.\research.cmd status secagg-research
```

依据具体报告选择下一任务。下面的恢复命令适用于已确认当前暂停来自未使用旁支的情形：

```powershell
.\research.cmd refocus secagg-research --task "回到冻结 GOAL：整理已确认反例形成的设计约束，选择一个尚未解决的核心构造、安全或成本义务，写出直接依赖和成功失败判据；已有结论只引用，不重复补证。" --reason "当前任务已深入未被主构造使用的旁支，保留其待审状态并恢复核心研究。" --extra-rounds 4
.\research.cmd prompt secagg-research
.\research.cmd watch secagg-research --max-rounds 4
```

`--extra-rounds 4` 在已用预算上显式增加 4 轮。例如已用 6、原预算 6，将变成已用 6、总预算 10；自动延期次数和历史计数不清零。`watch --max-rounds 4` 限制本次调用次数，期间如有复评会占用一次调用。无需修改 `G0` 至 `G8` 或将外部审查改为已通过。

若需要更明确的核心问题，可在 `refocus` 增加 `--problem "具体核心研究问题"`；它不修改 GOAL、研究路线或选中的想法。默认阶段为 `FALSIFICATION`，可用 `--phase CONSTRUCTION` 等选择合适阶段。新的任务与原因写入决策日志，旧任务、旧锚点及追加预算写入路线事件。

存在固定命题 `attempt` 时，先用其检查点和关闭流程处理，再进行路线级恢复；`refocus` 不会丢弃该尝试。若显式停止标记仍在，命令会提示使用 `clear-stop`；若 `last_run` 与账本不一致，先核查外部修改，不能直接清账继续。

## 验证范围

回归覆盖支持性证明/反例、必要核心反例、旧回执、目标改动、重复证据、路线复评提示、保留预算的恢复、活动锁、固定命题保护和写入失败恢复。端到端测试运行真实前端、封装器、单轮进程链，模型输出由本地模拟程序提供。

在当前机器执行完整验证：

```powershell
python -m unittest discover -s tests -v
.\research.cmd check all
```

源码仓库不包含个人项目；交付前的 `check all` 不能替代本机 `secagg-research` 的结构与代数检查。Windows 启动器及真实模型请求需在本机运行验证。
