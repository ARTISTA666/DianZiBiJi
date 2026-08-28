# agent-work 产出清单（MANIFEST，更新于 2026-08-16）

> 完整文件哈希见运行时生成的列表；本清单列出关键交付物。仓库其余文件不在本 agent 修改范围。

## 核心交付物

| 文件 | 说明 |
|---|---|
| README.md | 工作区说明与所有权约定 |
| LOG.md | 全程执行日志 |
| question-sets/gse111619_questions_v2_draft.json | 题集候选 20 题（GSE 处理后语料） |
| question-sets/gse111619_raw_questions_v2_draft.json | 题集候选 20 题（GSE 原始语料） |
| question-sets/smithsonian_joseph_henry_questions_v2_draft.json | 题集候选 20 题（Joseph Henry 手稿） |
| question-sets/gse306433_colitis_questions_v2_draft.json | 新增题集候选 20 题（GSE306433 小鼠结肠炎） |
| question-sets/gse291942_arabidopsis_heat_questions_v2_draft.json | 新增题集候选 20 题（GSE291942 拟南芥高温胁迫） |
| scripts/validate_question_sets.py | 题集协议校验器 |
| scripts/import_joseph_henry.py | JH 语料导入（项目 9） |
| scripts/run_pilot_experiments.py | pilot 运行器（含自动续跑） |
| scripts/compute_fact_coverage.py | 自动事实覆盖率计算 |
| scripts/b6_precision_simulation.py | B6 敏感性模拟 |
| scripts/build_blind_review_package.py | 主比较盲评包构建器（2026-08-16 加固：v1 来源失败关闭 + 占位符去标识化） |
| scripts/audit_blind_review_offline.py | 离线盲评包审计器（来源 v1 失败关闭 + 198 行五项目结构审计） |
| scripts/compute_formal_fact_coverage.py | run 20/21/23 三项目自动覆盖率计算（仅描述性） |
| scripts/compute_formal_fact_coverage_5projects.py | run 20/21/23/24/25 五项目自动覆盖率计算（仅描述性） |
| scripts/prepare_new_geo_datasets.py | 两套新 GEO 数据的知识文档/样本表生成器 |
| scripts/import_new_geo_datasets.py | 两套新 GEO 数据的系统导入器 |
| scripts/build_new_geo_question_sets.py | 两套新题集构建器 |
| scripts/smoke_jh_query.py | JH 重跑前 kg_enhanced_rag 单题冒烟 |
| analysis/b6-precision-sensitivity-latest.{json,md} | B6 输出 |
| runs/gse111619/run-16-evidence-v1.json + check.json | 通过 v1 校验的证据包（PASS） |
| runs/gse111619_raw/run-17-evidence-v1.json + check.json | 通过 v1 校验的证据包（PASS） |
| runs/smithsonian_joseph_henry/run-18-evidence-v1.json + check.json | 通过 v1 校验的证据包（PASS） |
| runs/gse111619/run-20-evidence-v1.json + check.json | 正式批次证据包（bge-m3；PASS） |
| runs/gse111619_raw/run-21-evidence-v1.json + check.json | 正式批次证据包（bge-m3；PASS） |
| runs/smithsonian_joseph_henry/run-22-evidence-v1.json + check.json | 历史正式批次证据包（FAIL：case 58 `[G编号]`，不追溯修复，已被 run 23 替代） |
| runs/smithsonian_joseph_henry/run-23-evidence-v1.json + check.json | JH 重跑证据包（bge-m3；**PASS**，94 completed + 6 pure_llm technical failures） |
| runs/gse306433_colitis/run-24-evidence-v1.json + check.json | 新增小鼠结肠炎证据包（bge-m3；**PASS**，98 completed + 2 kg technical failures） |
| runs/gse291942_arabidopsis_heat/run-25-evidence-v1.json + check.json | 新增拟南芥高温胁迫证据包（bge-m3；**PASS**，100/100） |
| runs/formal-batch-fact-coverage-2026-08-16-5projects.json | run 20/21/23/24/25 五项目自动覆盖率（仅描述性） |
| runs/formal-batch-fact-coverage-2026-08-16.json | run 20/21/23 自动事实覆盖率（仅描述性） |
| runs/batch2-fact-coverage.json | pilot 三项目自动覆盖率汇总 |
| paper-material/*-appendix.md | 官方渲染器生成的论文附录材料（五项目） |
| blind-review/formal-batch-2026-08-16-5projects/ | 五项目主比较盲评包（198 行/100 题，来源 run 20/21/23/24/25 全部 v1 PASS） |
| blind-review/formal-batch-2026-08-14/ | 历史三项目盲评包（已被五项目包替代） |
| reports/status-2026-08-16-paper-blockers.md | 本轮障碍清扫与五项目扩展报告 |

## 证据等级

全部产物为 `INTERNAL_DEVELOPMENT / DRAFT / NOT_FROZEN`：
- 题集为 agent 起草候选，待外部命题者复核签名；
- pilot 运行在 dev 嵌入（rust-hash-512-v1）、非冻结题集上，仅支持管线可行性与机制描述；
- 正式批次 run 20/21/23/24/25 使用 bge-m3 且五项目 v1 证据包均通过；但题集未外部签署、无独立双人盲评、APP_REVISION 未绑定；
- 确认性结论仍阻断于 B0/B1/人工盲评（详见 reports/status-2026-08-16-paper-blockers.md 与 LOG.md 2026-08-16 节）。

