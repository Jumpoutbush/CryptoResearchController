# 公开科研证据与评价工程：OpenAI Math、PaperBench、Science One

## 一、阅读范围

这些公开成果能帮助定义“可信研究记录”和“如何评价科研代理”，但其公开材料不等于可以复刻的完整自主科研控制器。下列来源用于设计接口与验证方法，**不要推断未知的内部调度、训练和思维过程**。

| 来源 | 已核对公开内容 | 建议借鉴 | 对应轮次 |
| --- | --- | --- | --- |
| [OpenAI Math](https://github.com/openai/math) | `preprints/`、`lean/README.md`、`lean/formalization.yaml`、`reasoning_traces/`、`history.md` 保存不同验证阶段的数学稿件和证明材料 | 数学主张版本、不完全形式化状态、纠错历史与论文—形式声明关系 | R07/R08/R13/R18 |
| [OpenAI PaperBench](https://github.com/openai/frontier-evals/tree/main/project/paperbench) | 论文复现任务、分层评分细则；执行、复现、评分分阶段隔离 | CryptoResearchBench 任务细分、独立评分容器、评价器本身的校准 | R16/R17/R18 |
| [Google Science One Framework](https://research.google/blog/science-one-framework-a-verifiable-autonomous-research-framework-via-chain-of-evidence/) | 公开科学证据链和主张审计的研究方法 | claim→论文证据→执行工件→审查回执的链式审计及错误引用检测 | R07/R08/R14/R18 |
| [LeanDojo](https://github.com/lean-dojo/LeanDojo) | Lean 源码提取和程序化交互示例（仓库 README 已标注原库弃用） | 作为理解证明状态与检索接口的资料；不作为默认新依赖 | R13 |

## 二、密码学科研必须增强的断言

OpenAI Math 的公开 README 明确包含不同验证状态的稿件，部分未形式化结果可能有问题。系统不能把“论文已生成”“模型提出推导”“Lean 某处通过”当成同一等级。每条候选应登记：`结论全文、前提、对应形式声明、原文出处、工具回执、人工审查、修订历史`。

PaperBench 的执行—复现—评分分离尤其值得复制到科研评价流程：被测代理只能访问题目与允许的工具；复现者在隔离工作区使用冻结输出；评分者访问独立 rubric/隐藏反例，不接收被测代理自己给的可信评级。对数学研究加入“安全定义一致性”和“反例适用范围”项目。

Science One 的证据链审计为 R07—R08 提供方法参考：一条声称来自论文的数学结论，需要完整覆盖所引用定理的量词、困难假设、输入输出与限制条件；一条声称来自实验的性能结果，需要可复核原始数值、工具版本和命令。不能让文献摘要承担定理级审查。

## 三、对应的最低增量验收

- **R07**：错误页码、错误定理版本、错误公式提取必须触发 `SOURCE_UNVERIFIED`。
- **R08**：上游定理撤销或修订，所有派生依赖重新进入待核验状态，不删除历史版本。
- **R13**：自然语言定理与 Lean 目标量词不同，工具成功也阻止标记主张为已证明。
- **R16**：公开案例与隐藏标准答案分目录，评价器不向研究代理暴露答案。
- **R17/R18**：从“运行成功”到“独立复现通过”再到“安全/新颖性认可”分级计数，不进行无依据的加权总分。

## 四、外部代码边界

OpenAI Math 是科研工件库，重点是可验证材料组织；Science One 主要提供公开架构和研究报告，尚不能把它当作已核查可直接移植的官方完整代码仓库。PaperBench 已公开评分与基准相关代码，但与密码学任务不同，需要重新设计安全定理和原文核查的金标准。LeanDojo 原仓库有弃用提示，不推荐新项目依赖旧代码而忽略维护状况。

实际移植前核对对应仓库具体许可证与版本；本实施包不复制任何第三方源码。
