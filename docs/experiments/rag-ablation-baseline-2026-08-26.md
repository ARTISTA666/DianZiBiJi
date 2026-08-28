# RAG 消融基线补充实验：裸 LLM 臂与 SQL 基线臂

- 执行日期：2026-08-25（文件名日期 2026-08-26 为预分配交付物编号）
- 对照实验来源：`rag-experiment-4.csv`（40 行 = 20 题 × 2 模式，模型 deepseek-v4-flash）；本补充取其中 mode=`project_rag`（普通 RAG）的同一组 20 题。
- 评分规则：`scripts/analyze_rag_experiment.py` 中 `GOLD_RULES`，AST 提取、与实验 4 完全一致——每题若干“可选关键串组”，回答文本需命中全部组（不区分大小写子串包含）。
- 原始数据：`rag-ablation-baseline-2026-08-26.json`

## 执行说明

### Arm A：裸 LLM（无检索）
- 端点：https://api.deepseek.com/chat/completions（OpenAI 兼容，Bearer Token）
- 模型：deepseek-v4-flash；temperature=0.1；max_tokens=1800；stream=false
- 消息：system="你是一名科研助理。请直接回答用户的问题。"（不含任何项目资料）+ user=题目原文
- 失败重试：3 次尝试（退避 1s/2s）。首轮执行时账户余额不足（HTTP 402 Insufficient Balance）致 20 题全部失败；充值后重跑，20/20 成功，以下统计基于重跑结果。
- 脚本：`/tmp/run_bare_llm.py`（python3 标准库 urllib）

### Arm B：SQL 基线（直查结构化库）
- 数据库：docker 容器 `eln-db-1` 内 PostgreSQL 库 `eln`，project_id=1（论文演示项目：KG-RAG 实验流程）。
- 说明：任务描述中的“项目 19”在当前库中不存在，演示数据实际位于项目 1，两臂统一以项目 1 为准。
- 范围：Q06–Q15 结构化可查；Q16–Q19 可用 SQL 聚合，一并执行；Q01–Q05（资料事实型，答案在文档正文）与 Q20（开放式建议）标记 N/A，原因见 JSON 明细。
- 脚本：`/tmp/run_sql_baseline.py`（psql 原始输出逐题留档）
- 数据漂移：当前活库中项目 1 仅存 4 条已审核笔记（实验 4 运行时为 15 条），Q15/Q18/Q19 因此无法取回全部 gold 要点（质粒、离心机等实体已不存在），相应未完成判定如实保留，未做任何修补。

## 汇总

| 臂 | 案例数 | 任务完成数 | 完成率（全部 20 题） | 可查子集完成率 | 可溯源数 | 平均耗时 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 裸 LLM（无检索） | 20 | 2 | 10.0% | —（全量运行） | 0/20（按构造无来源） | 5854.9 ms |
| SQL 基线 | 20（可查 14 + N/A 6） | 11 | 55.0% | 11/14（78.6%） | 14/20（可查题均可追溯到具体表行） | 43.9 ms（可查题） |

参考：实验 4 中普通 RAG 规则化任务完成率 20.0%（4/20）、图谱增强 RAG 70.0%（14/20）（`rag-experiment-4-objective-analysis.md`）。

### 分题型完成率

| 题型 | 题号 | 裸 LLM 完成 | SQL 基线完成（可查/适用） |
| --- | --- | ---: | ---: |
| 资料事实型 | Q01–Q05 | 1/5（20.0%） | N/A（0 适用） |
| 实验对象关系型 | Q06–Q10 | 1/5（20.0%） | 5/5（范围内 100.0%；全 20 题口径 100.0%） |
| 过程追溯型 | Q11–Q15 | 0/5（0.0%） | 4/5（范围内 80.0%；全 20 题口径 80.0%） |
| 综合总结型 | Q16–Q19 | 0/4（0.0%） | 2/4（范围内 50.0%；全 20 题口径 50.0%） |
| 开放式建议 | Q20 | 0/1（0.0%） | N/A（0 适用） |

> 口径说明：实验 4 的分析脚本把 Q16–Q20 归入“综合总结型”；本文按题目性质将 Q20 单列为开放式建议（SQL 基线对其标记 N/A），与任务要求一致。

### 逐题明细

| 题 | 题型 | 裸 LLM | SQL 基线 | 未命中要点（臂） |
| --- | --- | --- | --- | --- |
| Q01 | 资料事实型 | ❌ | N/A | A:58℃/58°C;条带最清晰/条带清晰 |
| Q02 | 资料事实型 | ❌ | N/A | A:PCR_protocol_demo.txt |
| Q03 | 资料事实型 | ❌ | N/A | A:cell_assay_reference_demo.txt |
| Q04 | 资料事实型 | ✅ | N/A | — |
| Q05 | 资料事实型 | ❌ | N/A | A:无法确认/无法回答 |
| Q06 | 实验对象关系型 | ❌ | ✅ | A:Taq DNA Polymerase;MgCl2 |
| Q07 | 实验对象关系型 | ❌ | ✅ | A:样本 A/样本A;样本 B/样本B |
| Q08 | 实验对象关系型 | ❌ | ✅ | A:CO2 培养箱/CO₂培养箱 |
| Q09 | 实验对象关系型 | ✅ | ✅ | — |
| Q10 | 实验对象关系型 | ❌ | ✅ | A:转膜仪;凝胶成像系统 |
| Q11 | 过程追溯型 | ❌ | ✅ | A:PCR 条件优化实验 |
| Q12 | 过程追溯型 | ❌ | ✅ | A:细胞活力检测实验 |
| Q13 | 过程追溯型 | ❌ | ✅ | A:Western Blot 蛋白表达验证 |
| Q14 | 过程追溯型 | ❌ | ✅ | A:系统管理员 |
| Q15 | 过程追溯型 | ❌ | ❌ | A:PCR 条件优化实验;细胞活力检测实验;Western Blot 蛋白表达验证 …等15项；B:细胞传代与冻存记录;质粒提取与酶切鉴定;细胞转染效率优化 …等11项 |
| Q16 | 综合总结型 | ❌ | ✅ | A:PCR 条件优化实验;细胞活力检测实验;Western Blot 蛋白表达验证 |
| Q17 | 综合总结型 | ❌ | ✅ | A:58℃/58°C;18%;目标蛋白/蛋白表达降低 |
| Q18 | 综合总结型 | ❌ | ❌ | A:Lipofectamine/EcoRI/HindIII；B:质粒;Lipofectamine/EcoRI/HindIII |
| Q19 | 综合总结型 | ❌ | ❌ | A:PCR Thermal Cycler/荧光定量 PCR 仪;转膜仪；B:离心机 |
| Q20 | 开放式建议 | ❌ | N/A | A:99.8%/320 pg/mL/8%/A260/280 |

### SQL 清单（语义要点）

- Q06：从名为“PCR 条件优化实验”的笔记实体出发，沿 uses_reagent 关系查出全部目标试剂实体名。（`SELECT te.label AS reagent FROM kg_relations r JOIN kg_entities se ON se.id = r.source_entity_id JOIN kg_entities te ON …`）
- Q07：同上，沿 uses_sample 关系查样本实体名。（`SELECT te.label AS sample FROM kg_relations r JOIN kg_entities se ON se.id = r.source_entity_id JOIN kg_entities te ON t…`）
- Q08：“细胞活力检测实验”的 uses_reagent 与 uses_instrument 两组关系合并查询。（`SELECT r.relation_type AS relation, te.label AS object FROM kg_relations r JOIN kg_entities se ON se.id = r.source_entit…`）
- Q09：“Western Blot 蛋白表达验证”的 uses_reagent 关系。（`SELECT te.label AS reagent FROM kg_relations r JOIN kg_entities se ON se.id = r.source_entity_id JOIN kg_entities te ON …`）
- Q10：“Western Blot 蛋白表达验证”的 uses_instrument 关系。（`SELECT te.label AS instrument FROM kg_relations r JOIN kg_entities se ON se.id = r.source_entity_id JOIN kg_entities te …`）
- Q11：反向检索：produces_result 的目标结果实体标签含“退火温度 58”，返回其来源笔记。（`SELECT DISTINCT se.label AS source_note, te.label AS result FROM kg_relations r JOIN kg_entities se ON se.id = r.source_…`）
- Q12：反向检索：produces_result 目标结果含“细胞活力下降约 18”，返回来源笔记。（`SELECT DISTINCT se.label AS source_note, te.label AS result FROM kg_relations r JOIN kg_entities se ON se.id = r.source_…`）
- Q13：反向检索：produces_result 目标结果含“目标蛋白表达降低”，返回来源笔记。（`SELECT DISTINCT se.label AS source_note, te.label AS result FROM kg_relations r JOIN kg_entities se ON se.id = r.source_…`）
- Q14：三条主实验笔记的创建人：experiment_notes.owner_user_id 连接 users.display_name（与 kg created_by 关系一致）。（`SELECT n.title AS note, u.display_name AS creator FROM experiment_notes n JOIN users u ON u.id = n.owner_user_id WHERE n…`）
- Q15：当前项目全部已审核（APPROVED）实验笔记清单。注意：当前库中该项目仅存 4 条已审核笔记，与实验 4 运行时的 15 条相比存在数据漂移，如实记录。（`SELECT title AS approved_note, experiment_date, status FROM experiment_notes WHERE project_id = 1 AND status = 'APPROVED…`）
- Q16：按 experiment_date 落在 2026-06-03 至 2026-06-05 的已审核笔记聚合。（`SELECT title AS note, experiment_date, status FROM experiment_notes WHERE project_id = 1   AND status = 'APPROVED'   AND…`）
- Q17：对上一题时间窗内的笔记集合，沿 produces_result 关系取各自主要结果。（`SELECT se.label AS note, te.label AS result FROM kg_relations r JOIN kg_entities se ON se.id = r.source_entity_id JOIN k…`）
- Q18：每条笔记经 has_experiment_type 归入实验类型，经 uses_reagent 取试剂，输出“实验类型—试剂”归纳对。（`SELECT DISTINCT et.label AS experiment_type, rg.label AS reagent FROM kg_entities n JOIN kg_relations rt ON rt.source_en…`）
- Q19：同上，把试剂换成 uses_instrument 仪器。（`SELECT DISTINCT et.label AS experiment_type, ins.label AS instrument FROM kg_entities n JOIN kg_relations rt ON rt.sourc…`）

### 失败与偏差记录

- 任务描述称实验数据在项目 19；当前 eln 库中不存在项目 19，演示数据实际位于项目 1（论文演示项目：KG-RAG 实验流程），两臂均以项目 1 为准。
- 数据库为活库且与实验 4 运行时（2026-06/07）相比存在数据漂移：项目 1 现仅存 4 条已审核笔记（实验 4 时为 15 条），导致 Q15/Q18/Q19 的 SQL 查询无法返回全部 gold 要点（如质粒、离心机相关实体已不存在），相应未完成判定如实保留。
- Arm A 首轮执行时 DeepSeek 账户余额不足（HTTP 402 Insufficient Balance），20 题全部失败；账户充值后于同日重跑，20/20 成功。首轮失败记录未计入最终结果。
- Arm A 全部 20 题 status=成功（finish_reason=stop），无单题重试。
- Arm B 查询执行失败数：0。
- API 密钥未在任何输出中出现。

## 与实验 4 两臂的同子集对比

为与补充基线可比，用同一份 `GOLD_RULES`（`scripts/analyze_rag_experiment.py`，AST 提取）对 `rag-experiment-4.csv` 中两臂共 40 条回答重新逐题判定。判定器校验：普通 RAG 复现 4/20、图谱增强 RAG 复现 14/20，未通过题目（普通：Q01、Q06–Q20；图谱：Q13、Q15–Q19）与实验 4 原判定一致，无需校准。

### SQL 臂可查 14 题子集（Q06–Q19）

| 臂 | 完成数 | 完成率 |
| --- | ---: | ---: |
| 裸 LLM（无检索） | 1/14 | 7.1% |
| Plain RAG | 0/14 | 0.0% |
| KG-Enhanced RAG | 8/14 | 57.1% |

裸 LLM 在该子集上唯一通过的题目是 Q09；其另一道通过题 Q04 属资料事实型，不在本子集内。

### 全 20 题口径对照

| 臂 | 完成数 | 完成率 |
| --- | ---: | ---: |
| 裸 LLM（无检索） | 2/20 | 10.0% |
| Plain RAG | 4/20 | 20.0% |
| SQL 基线 | 11/20 | 55.0% |
| KG-Enhanced RAG | 14/20 | 70.0% |

> 口径说明：SQL 臂因活库漂移受损——当前库中项目 1 仅存实验 4 运行时 15 条已审核笔记中的 4 条，Q15/Q18/Q19 的查询无法返回全部 gold 要点（细胞传代与冻存记录等 11 条笔记及质粒、离心机相关实体已不存在）。若剔除这 3 道受漂移直接影响的题目，SQL 臂在其余 11 道可查题上为 11/11（100.0%）；同口径下 Plain RAG 为 0/11、KG-Enhanced RAG 为 8/11（其在 Q13、Q16、Q17 未过，与漂移无关）。各臂完整逐题判定以 `rag-ablation-baseline-2026-08-26.json` 与 `rag-experiment-4.csv` 原始回答为准。
