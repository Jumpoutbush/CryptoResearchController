# v3.5 · 开发轮次 R13：精确数学核验与形式证明适配器

> **执行状态：待开发（计划文件）**。本文是交给 Codex 的实施规格，并非已完成的功能说明。
> **基准：** `Jumpoutbush/CryptoResearchController@67618536ecd172b2fad24843daf291489e226c2e`；执行前以本机较新、已提交的源代码为准。
> **轮次类型：** 软件开发轮次；不得消耗任何个人科研项目的研究预算。

## 1. 本轮唯一目标

将已有整数反例、Lean 形式化及符号检验接口封装为**可选择的核验适配器**，明确各自能验证的声明范围与条件，避免“编译通过即论文定理成立”。

**现有基础：** 现有 `engine/falsification.py` 已有受限整数谓词反例；`engine/formal_verifier.py`、`verification_engine.py` 有 Lean/数学检查接口；主张图保存审查状态。

**进入条件：** R11—R12 完成，且 existing verify 相关回归通过。

## 2. 设计裁决与数据流

### 13.1 明确验证等级

统一回执状态：`EXECUTED/COUNTEREXAMPLE_FOUND/NO_COUNTEREXAMPLE_WITHIN_BOUND/TOOL_PASSED_AUDIT_PENDING/UNSUPPORTED/FAILED`。对整数搜索找不到反例，绝不标记全称命题已证。对 Lean 工具的输出，只记录源码、工具链、依赖、公理/声明名摘要；完整自然语言命题对应由独立审查者完成。

### 13.2 适配对象

优先考虑 NTRU 多项式恒等式、模算术关系、简单协议不变量和固定形式声明。复杂模拟安全游戏与分布安全界需要独立密码学审查，不能伪装成可自动判定的整数谓词。

## 3. 修改范围（新增文件均为规划路径）

- 新建 `candidate_search/verifiers/interface.py`、`integer_adapter.py`、`lean_adapter.py`。
- 可选 `symbolic_adapter.py` 仅包装现有确切接口，不应为新特性引入不受控 `eval`。
- 新建 `tests/test_verifier_adapters.py`，正例/伪例/错误绑定夹具。
- 回执写 `state/candidates/<id>/verification/`，指向权威 claim/prob 版本。

## 4. Codex 必须完成的实现步骤

1. 核对现有 verifier 函数参数和有效输入范围，尽量薄适配，不重写其安全校验。
2. 每条验证请求绑定 claim revision、problem SHA、候选修订及输入证据 SHA，防止旧结果重用。
3. 对整数反例输出具体见证，保存可由同一谓词验证器再次确认的机器证书。
4. 对 Lean 输出固定 toolchain、源码及目标 declaration 的哈希，区分工具执行与自然语义审查。
5. 检测 `sorry/admit` 等不允许占位，同时审查目标声明是否被弱化的风险。
6. 所有 `verify` 结果只通过原 `claim_graph` 审查流程影响正式证明状态。

## 5. 输入、输出与接口约定

建议共用接口：

```python
verify(request: VerificationRequest) -> VerificationReceipt
```

`VerificationReceipt` 必须包含 `claim_binding, source_hashes, adapter_id, tool_version, result_status, evidence_files, reproduction_command, limitations`。


## 6. 必做的离线自动测试

- 以一个错误多项式恒等式构造精确反例并成功复查证书。
- 将真命题搜索限制设为很小范围，输出 `NO_COUNTEREXAMPLE_WITHIN_BOUND` 而非 PROVED。
- Lean 声明 `True` 可编译却与目标安全命题不一致，必须显示人工语义审查待完成。
- 工具缺失、超时、SHA 不匹配或未知适配器返回 `UNSUPPORTED/FAILED`。
- 旧 claim 已修订后，先前的验证回执不能再次应用。

## 7. 本轮验收标准

- 至少一个精确反例和一个可重放的形式工具回执（Lean 不可用则给出明确 `UNAVAILABLE` 模拟记录）。
- 所有主张审查等级与原有 `claim_graph` 规则完全一致。
- 不增加不可信代码执行入口。

## 8. 停止、回滚及禁止事项

不能把模型生成的 Python 试验、统计观测或单次模拟器输出称为密码学证明；必须明确验证的是哪一层断言。

## 9. Codex 交付回执

- 填写修改文件列表、设计偏差及理由、`git diff --stat`。
- 提供专项测试与全套回归测试的真实命令、退出码、通过/失败数量。
- 输出一项**独立可复核**的正常路径证据和一项故障注入证据（测试文件/夹具/日志均可）。
- 报告是否改变既有科研项目的 `GOAL.md`、`STATE.json`、预算账本、门禁或任何证明结论；正常答案必须为“均未改变”。
- 使用英文、范围明确的 Git 提交说明；用户未授权时不要推送远端。
