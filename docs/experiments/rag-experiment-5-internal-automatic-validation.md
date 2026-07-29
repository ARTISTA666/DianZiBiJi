## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: validate
- Origin Date: 2026-07-13T11:03:50.736077+00:00
- Verification Status: ANALYZED
- Version Label: validation_v1

# 实验 5 内部五方法自动验证

- 总体置信度：CAUTION
- 行完整性：通过
- 冻结包运行后校验：通过

## 问题聚类配对比较

| 方法（相对混合 RAG） | 平均覆盖差 | 95% bootstrap CI | 改善/持平/下降问题数 |
| --- | ---: | --- | ---: |
| pure_llm | -0.2889 | [-0.4917, -0.1111] | 0/6/6 |
| bm25_rag | +0.0833 | [-0.0972, +0.3056] | 2/8/2 |
| structured_query | +0.6611 | [+0.3972, +0.8889] | 10/1/1 |
| kg_enhanced_rag | +0.6389 | [+0.3889, +0.8472] | 9/3/0 |

## 重复稳定性

| 方法 | 三次覆盖完全一致的问题 | 比例 | 问题内平均标准差 |
| --- | ---: | ---: | ---: |
| pure_llm | 12/12 | 1.0000 | 0.0000 |
| bm25_rag | 11/12 | 0.9167 | 0.0196 |
| project_rag | 11/12 | 0.9167 | 0.0196 |
| structured_query | 12/12 | 1.0000 | 0.0000 |
| kg_enhanced_rag | 12/12 | 1.0000 | 0.0000 |

## 警告

- Frozen repeat-level sign and McNemar p-values treat repeated generations as independent and must not be used as confirmatory inference.
- Bootstrap intervals are post-run methodological validation and are not multiplicity-adjusted.
- Alias-based fact coverage is not factual accuracy, association correctness or citation validity.
- The single developer-authored project does not establish external validity.

## 统计谬误扫描

覆盖：11/11

| 类型 | 严重度 | 说明 |
| --- | --- | --- |
| Simpson's Paradox | NOTE | Category cells contain only 1-3 questions; subgroup reversal is not estimated reliably. |
| Ecological Fallacy | NOTE | Inference remains at question level; no individual-level claim is made. |
| Berkson's Paradox | CAUTION | The benchmark is a selected single GEO project rather than a representative project sample. |
| Collider Bias | NOTE | No covariate adjustment or conditioning model is used. |
| Base Rate Neglect | NOTE | Fact coverage is not a diagnostic probability and is reported with its denominator. |
| Regression to the Mean | NOTE | There is no pre-post extreme-group selection. |
| Survivorship Bias | NOTE | All planned cases completed; no failed case was removed. |
| Look-Elsewhere Effect | CAUTION | Four comparisons and several metrics are reported without multiplicity correction. |
| Garden of Forking Paths | CAUTION | Inputs were frozen before generation, but clustered bootstrap validation was added post-run to correct pseudoreplication. |
| Correlation != Causation | CAUTION | Differences on this benchmark do not establish general method superiority across projects. |
| Reverse Causality | NOTE | No directional causal relationship is estimated. |

## 复现性

外部 API 响应具有随机性，不做逐字重跑判定；本轮报告同一冻结协议下的三次重复。
