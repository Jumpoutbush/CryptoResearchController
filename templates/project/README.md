# {{PROJECT_TITLE}}

在本目录调用 `research.cmd`，自动选择当前项目。首次补充材料后执行 `research.cmd ready`，再执行 `research.cmd run`。统一手册见 ../../docs/USER_MANUAL.md；需要加入想法时执行 `research.cmd ideas add --title "研究想法" --text "可检验的问题与成功判据"`。
# 根据 idea 初始化

根目录可以仅提供原始 idea：`research.cmd new 项目ID --idea-file D:\Materials\idea.md`，也可以同时提供 `--goal-file`。随后运行 `research.cmd initialize 项目ID`。

本项目的初始化提示词在 `prompts/initialize_from_idea.md`，首轮 INTAKE 会自动加载。它生成12份派生研究文档和 `research/INITIALIZATION.json`；缺失定义和资料保留为具体待确认项。可用 `research.cmd prompt 项目ID --initialize` 预览完整提示词。系统代码继续受理论审查门禁控制。

# 长期科研知识

`research.cmd knowledge status` 只读查看图谱，`research.cmd knowledge refresh` 显式汇总已有来源；`search --query 关键词`、`show --id 知识ID`、`trace --id 知识ID` 和 `impact --id 知识ID` 用于检索、追溯和查看下游影响。图谱复用 research/discovery/CLAIM_GRAPH.json；原研究状态、预算及历史保留。结构化知识示例为 research/KNOWLEDGE_TEMPLATE.json，完整语义见 ../../docs/RESEARCH_KNOWLEDGE_V3.4.md。

每个已验收科研轮自动刷新索引后再判断独立监督触发，科研和监督均读取有长度上限的只读知识上下文。`trace` 同时提供当前状态与精确绑定的历史快照；历史命中不表示当前通过。索引失败保留已验收结果及预算并停止本次后续监督，原因见运行状态的 `knowledge_index`。
