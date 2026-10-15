# {{PROJECT_TITLE}}

在本目录调用 `research.cmd`，自动选择当前项目。首次补充材料后执行 `research.cmd ready`，再执行 `research.cmd run`。统一手册见 ../../docs/USER_MANUAL.md；需要加入想法时执行 `research.cmd ideas add --title "研究想法" --text "可检验的问题与成功判据"`。
# 根据 idea 初始化

根目录可以仅提供原始 idea：`research.cmd new 项目ID --idea-file D:\Materials\idea.md`，也可以同时提供 `--goal-file`。随后运行 `research.cmd initialize 项目ID`。

本项目的初始化提示词在 `prompts/initialize_from_idea.md`，首轮 INTAKE 会自动加载。它生成12份派生研究文档和 `research/INITIALIZATION.json`；缺失定义和资料保留为具体待确认项。可用 `research.cmd prompt 项目ID --initialize` 预览完整提示词。系统代码继续受理论审查门禁控制。
