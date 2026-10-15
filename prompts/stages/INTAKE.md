# 项目接入

读取用户目标与材料，生成 research/INTAKE.md。明确输入输出、冻结条件、候选贡献、最相近成果和最小可证伪命题；缺失材料如实列出。
# 数学问题编译

将 GOAL、用户想法和安全约束整理为 research/PROBLEM_PROPOSAL.json，采用 research/PROBLEM_TEMPLATE.json 的模式。旧项目没有模板时读取底座 templates/project/research/PROBLEM_TEMPLATE.json。逐项保留原目标，不确定的参数、前提和命题保持待确认；不能自行放宽。用户用 problem import 登记确认后的精确问题，再用 attempt start 开始连续探索。初始提案仍需核对，不代表已成立的贡献。
