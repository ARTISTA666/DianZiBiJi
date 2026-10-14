> status: current
> owner: 软件仓库维护者

# 软件文档导航

公开仓库提供软件使用、运维、机制说明，以及运行和测试依赖的协议、数据与历史验证记录。论文草稿、审稿、个人核验、协作和交付归档仅在本地维护。本机原研究材料导航保存在 `README.local.md`，不随仓库同步。

历史验证记录只说明对应版本与运行条件，不代表当前部署通过，也不代替独立人工评价。冻结结果与协议中的事实和限制保持原样。

## 入门

- [项目介绍、配置、启动与验证](../README.md)
- [用户使用手册](用户使用手册.md)
- [开发分工、运行时约束与检查命令](../AGENTS.md)
- [历史软件设计](../archive/README.md)

## 发布与维护约定

新增或移动公开 Markdown 文档须登记于本导航；新文档首行标明 `status` 和 `owner`。协议更新另起版本，冻结结果不因代码重构而回改。个人研究记录受 `.gitignore` 排除，不应通过强制添加重新发布。

## 使用与概览

- [用户使用手册](<用户使用手册.md>)

## 运维与发布

- [backup-restore](<operations/backup-restore.md>)
- [controlled-beta-launch](<operations/controlled-beta-launch.md>)
- [final-maturity-evidence](<operations/final-maturity-evidence.md>)
- [secret-rotation](<operations/secret-rotation.md>)

## 测试计划与模板

- [user-acceptance-test-plan](<testing/user-acceptance-test-plan.md>)
- [user-test-observation-template](<testing/user-test-observation-template.md>)

## 功能机制与设计

- [GraphRAG学生画像-设计文档](<innovation/GraphRAG学生画像-设计文档.md>)
- [动态知识蓝图机制-v1](<innovation/动态知识蓝图机制-v1.md>)
- [图谱可视化语义映射-v1](<innovation/图谱可视化语义映射-v1.md>)
- [智能体工作流与思维链-v1](<innovation/智能体工作流与思维链-v1.md>)
- [预警与人工审核闭环-v1](<innovation/预警与人工审核闭环-v1.md>)
- [预警与人工审核闭环-v2](<innovation/预警与人工审核闭环-v2.md>)

同目录内的 JSON、CSV、图片等配套资产保持原路径，可按相应文档引用定位。

## 实验协议、数据与验证记录

- [agent-quality-protocol-v1](<experiments/agent-quality-protocol-v1.md>)
- [agent-quality-real-2026-08-10](<experiments/agent-quality-real-2026-08-10.md>)
- [auto-eval-standard-survey-2026-08-26](<experiments/auto-eval-standard-survey-2026-08-26.md>)
- [controlled-beta-gate-latest](<experiments/controlled-beta-gate-latest.md>)
- [e2e-maturity-gate-latest](<experiments/e2e-maturity-gate-latest.md>)
- [human-review-current-status-2026-07-12](<experiments/human-review-current-status-2026-07-12.md>)
- [human-review-protocol-v1](<experiments/human-review-protocol-v1.md>)
- [human-review-readiness-2026-07-11](<experiments/human-review-readiness-2026-07-11.md>)
- [human-review-readiness-2026-07-16](<experiments/human-review-readiness-2026-07-16.md>)
- [innovation-ablation-2026-09-07](<experiments/innovation-ablation-2026-09-07.md>)
- [innovation-supplement-2026-09-08](<experiments/innovation-supplement-2026-09-08.md>)
- [kg-heldout-T136-2026-10-10](<experiments/kg-heldout-T136-2026-10-10.md>)
- [kg-heldout-T136-protocol-v1](<experiments/kg-heldout-T136-protocol-v1.md>)
- [kg-relation-gold-audit-after-fix-summary](<experiments/kg-relation-gold-audit-after-fix-summary.md>)
- [kg-relation-gold-audit-summary](<experiments/kg-relation-gold-audit-summary.md>)
- [kg-score53-coefficient-ablation-2026-09-04](<experiments/kg-score53-coefficient-ablation-2026-09-04.md>)
- [kg-threshold-sensitivity](<experiments/kg-threshold-sensitivity.md>)
- [method-masked-review-validation-2026-07-12](<experiments/method-masked-review-validation-2026-07-12.md>)
- [non-human-experiment-completion-2026-07-13](<experiments/non-human-experiment-completion-2026-07-13.md>)
- [ocr-evaluation-protocol-v1](<experiments/ocr-evaluation-protocol-v1.md>)
- [ocr-image-validation-2026-07-11](<experiments/ocr-image-validation-2026-07-11.md>)
- [ocr-improvement-2026-07-13](<experiments/ocr-improvement-2026-07-13.md>)
- [ocr-language-scope-2026-07-15](<experiments/ocr-language-scope-2026-07-15.md>)
- [ocr-rukopys-stress-test-2026-07-12](<experiments/ocr-rukopys-stress-test-2026-07-12.md>)
- [ocr-runtime-e2e-2026-07-12](<experiments/ocr-runtime-e2e-2026-07-12.md>)
- [rag-ablation-baseline-2026-08-26](<experiments/rag-ablation-baseline-2026-08-26.md>)
- [rag-evidence-package-protocol-v1](<experiments/rag-evidence-package-protocol-v1.md>)
- [rag-experiment-3-objective-analysis](<experiments/rag-experiment-3-objective-analysis.md>)
- [rag-experiment-4-objective-analysis](<experiments/rag-experiment-4-objective-analysis.md>)
- [rag-experiment-5-freeze-audit-2026-07-12](<experiments/rag-experiment-5-freeze-audit-2026-07-12.md>)
- [rag-experiment-5-internal-automatic-validation](<experiments/rag-experiment-5-internal-automatic-validation.md>)
- [rag-experiment-5-internal-descriptive-results-v1](<experiments/rag-experiment-5-internal-descriptive-results-v1.md>)
- [rag-experiment-5-preregistration-rust-v2-amendment-2026-08-16-5projects](<experiments/rag-experiment-5-preregistration-rust-v2-amendment-2026-08-16-5projects.md>)
- [rag-experiment-5-preregistration-rust-v2-amendment-2026-08-29-gse291942-3projects](<experiments/rag-experiment-5-preregistration-rust-v2-amendment-2026-08-29-gse291942-3projects.md>)
- [rag-experiment-5-preregistration-rust-v2](<experiments/rag-experiment-5-preregistration-rust-v2.md>)
- [rag-experiment-5-preregistration](<experiments/rag-experiment-5-preregistration.md>)
- [rag-fair-comparison-T148-2026-10-12](<experiments/rag-fair-comparison-T148-2026-10-12.md>)
- [rag-fair-comparison-protocol-v1](<experiments/rag-fair-comparison-protocol-v1.md>)
- [rag-paper-evidence-index-v1](<experiments/rag-paper-evidence-index-v1.md>)
- [rag-serialized-baselines-2026-09-14](<experiments/rag-serialized-baselines-2026-09-14.md>)
- [ragas-evaluation-2026-08-26](<experiments/ragas-evaluation-2026-08-26.md>)
- [real-llm-regression-2026-07-16](<experiments/real-llm-regression-2026-07-16.md>)
- [rust-rerun-paired-2026-09-04](<experiments/rust-rerun-paired-2026-09-04.md>)
- [rust-retrieval-pilot-protocol-v1](<experiments/rust-retrieval-pilot-protocol-v1.md>)
- [README](<experiments/t114-2026-10-01/README.md>)
- [t114-generation-compatibility-amendment-v2](<experiments/t114-generation-compatibility-amendment-v2.md>)
- [t114-simulation-data-precondition-amendment-v3](<experiments/t114-simulation-data-precondition-amendment-v3.md>)
- [t114-supplement-validation-2026-10-01](<experiments/t114-supplement-validation-2026-10-01.md>)
- [t114-supplement-validation-protocol-v1](<experiments/t114-supplement-validation-protocol-v1.md>)

同目录内的 JSON、CSV、图片等配套资产保持原路径，可按相应文档引用定位。

## 系统契约与验证证据

- [agent-safety-property-tests-2026-08-28](<system-evidence/agent-safety-property-tests-2026-08-28.md>)
- [architecture-and-flow](<system-evidence/architecture-and-flow.md>)
- [database-schema](<system-evidence/database-schema.md>)
- [knowledge-graph-sample](<system-evidence/knowledge-graph-sample.md>)
- [validation-results](<system-evidence/validation-results.md>)

同目录内的 JSON、CSV、图片等配套资产保持原路径，可按相应文档引用定位。
