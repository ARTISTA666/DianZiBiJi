# Technical Recheck — Round 01(修改复验)

日期:2026-08-28。执行者:thesis-technical-reviewer(只读复验)。对象:Round 1 Editor 修改的技术性内容(`docs/毕业论文重构稿.md`),逐项对照生产代码 `backend/src/`。

## Review Summary

总体评分:9/10
风险等级:Low

四项复验中三项完全通过;式(5-3)的评分函数逐项与 `graph_relation_score` 一致,阈值与默认值表述准确;唯一问题是新增的"按分数降序取前 10 条"选取描述省略了实现中的笔记来源优先占额等三个选取环节,属可一句话补正的简化表述(Minor)。

## 逐项复验结论

### Item 1 — 式(5-3)及文字说明(L787-802) 对照 `graph_relation_score`

**结论:验证通过(评分函数与阈值),选取描述简化立 1 条 Minor issue(见 RECHECK-001)。**

| 论文表述(行号) | 代码证据 | 判定 |
| --- | --- | --- |
| 关系类型提示命中 +3.0(L792、L802"该命中项计 3.0 分") | `backend/src/rag/graph.rs:458-462`:`hints.contains(row.relation_type)` → +3.0;H(q) 对应 `relation_hints`(graph.rs:511 起,预定义关系类型→触发词映射) | 一致 |
| 词元全等 +3.0 / 子串包含 +1.0,六类文本串(L793、L802"源实体标签、目标实体标签、源与目标实体类型、关系类型及其显示标签共六类小写化文本串") | `graph.rs:463-479`:haystacks 数组恰为 6 项——source_label、target_label(均 inline_text+lowercase)、source_entity_type、target_entity_type、relation_type、relation_label(relation_type);`token == haystack` → +3.0,`else if haystack.contains(token) \|\| token.contains(haystack)` → +1.0 | 一致(六类范围写对) |
| source 实体类型 note +0.2(L794、L802) | `graph.rs:480-482`:`row.source_entity_type == "note"` → +0.2 | 一致 |
| source_type note_extraction +0.3(L795、L802) | `graph.rs:483-485`:`row.source_type.as_deref() == Some("note_extraction")` → +0.3 | 一致 |
| roles 每命中 +4.0(L796、L802"权重最大的评分项") | `graph.rs:486-493`:`properties["roles"]` 数组逐项 `role_query_matches(role, normalized_query)` 计数 ×4.0;normalized_query = `query.to_lowercase()`(graph.rs:129);4.0 确为公式中最大单项系数 | 一致 |
| 阈值"得分大于 0 且不低于最低得分阈值(当前实现默认 1.0)"(L802) | `graph.rs:202-204`:`meets_graph_threshold = score > 0.0 && score >= min_score`;默认值 `backend/src/config.rs:149`(RAG_GRAPH_MIN_SCORE=1.0)、`.env.example:79` 同值 | 一致(措辞精确对应 >0 且 >=min) |
| "取前 10 条"(L802) | 默认 `config.rs:148`(RAG_GRAPH_TOP_K=10)、`.env.example:78`;但实际选取经 `balance_graph_context`(graph.rs:206-273,笔记来源关系优先占额)与集合型查询 `max(top_k,30)`(`backend/src/api/rag/mod.rs:699-703、875-879`),注入前另有 6000 字符预算截断(graph.rs:448-450;api/rag/mod.rs:708-709) | 部分一致 → RECHECK-001 |
| 数学记号 | 指示函数、双重求和、集合基数用法规范;子串项写 `t\neq h \wedge (h\subset t \vee t\subset h)`,因代码为 else-if(相等已先行计 3.0),真子集记号与实现严格对应,无歧义 | 无错误 |

评分函数另有单元测试 `test_graph_relation_score_keeps_python_ranking_components`(graph.rs:880)锁定各分量,与公式互证。

### Item 2 — 5.4 小结"17 组同义词展开"(L918)

**结论:验证通过。**

`backend/src/rag/bm25.rs:16-48`:`QUERY_SYNONYMS` 共 17 个 `m.insert` 键(pcr、聚合酶链反应、rt-pcr、wb、western blot、elisa、cck8、cck-8、dmem、fbs、pbs、rna-seq、转录组、htseq、geo、od、光密度)。5.2.2(L762)点名的 11 个键(PCR/WB/ELISA/CCK-8/DMEM/FBS/PBS/RNA-seq/HTSeq/GEO/OD)全部在表中。基线快照 L893 的"13 组"已正确改为"17 组",两处(5.2.2、5.4)口径一致。

### Item 3 — 图 7-1/7-2 `\includegraphics` 反斜杠修正(L1361、L1399)

**结论:验证通过,无遗漏。**

- 修正后两行均为单反斜杠:`\includegraphics[width=0.86\textwidth,height=0.4\textheight,...]`(L1361、L1399),与基线快照 L1336、L1374 的 `\\textwidth`/`\\textheight` 对照,修正属实。
- `grep -F '\textwidth'`、`grep -F '\textheight'` 全文 0 命中,无双反斜杠残留;其余 8 处 includegraphics(L1151-1179,0.82/0.42 口径)基线即单反斜杠,未受影响。
- 全文扩展检查 `grep -E '\\[a-zA-Z]+'`:仅命中 tikz 节点文本内的 `\\` 换行(如 L812、L821 等),该用法在 `align=center` 节点中合法且为原稿固有写法,非错误。

### Item 4 — 图 5-3/图 5-4 latex 围栏修复(L804-830、L840-862)

**结论:验证通过,代码块各自完整、内容未截断。**

- 全文 ``` 围栏 40 条(偶数,awk 统计);基线快照为 37 条(奇数,即图 5-3 块缺闭合围栏、与图 5-4 块嵌套断裂),修复后每块独立配对:式(5-2)L768-773、式(5-3)L789-800、图 5-3 L804-830、图 5-4 L840-862。
- 逐字节 diff:图 5-3 块相对基线唯一差异是补回的闭合围栏行;图 5-4 块与基线完全一致——tikz 内容零改动、无截断。
- tikz 结构完整:图 5-3 的 `\begin{tikzpicture}`/`\end{tikzpicture}` 配对,8 个节点(q/perm/hyb/doc/plain/kg/llm/log)全部定义且被 `\draw` 引用无悬空;图 5-4 同(s/g/e/log/run/rep)。两块均含 `\captionof*{figure}` 图题。
- 附带核对 T2 移动内容:"项目级 RAG 流程包括……不会使用模拟答案替代"已位于 5.2.5(L834,基线中误拼在 L779 行末),三层来源段置于 5.2.6 图 5-4 之后,两小节均位于 5.3(L870)之前,与 5.2 导语(L746)承诺一致。

## Issues

### RECHECK-001
Severity: Minor
Priority: P1
Location: 5.2.4 融合知识图谱的检索增强策略,L802(新增文字说明末句)
Category: technical/oversimplification
Problem: "得分大于 0 且不低于最低得分阈值的关系按分数降序排序,取前 10 条作为图谱上下文"描述的是纯 top-k 选取,与实现的选取管线不符:实现先对笔记来源关系优先占额,集合型查询上限放宽至 30,注入前还有字符预算截断。
Evidence: `backend/src/rag/graph.rs:206-273` `balance_graph_context` 第一轮只选 `source_entity_type == "note"` 的关系(按分数序)直至满额,第二轮才按分数补足其余——当笔记来源关系通过阈值数量达到名额时,得分更高的非笔记关系会被排除,纯 top-k 复现者得到的 [G] 上下文组成不同;`backend/src/api/rag/mod.rs:699-703` 集合型查询(`is_collection_query`,`backend/src/rag/retrieval.rs:505`)limit 取 `rag_graph_top_k.max(30)`;`graph.rs:448-450` 与 `api/rag/mod.rs:708-709` 注入前按 6000 字符预算再截断。另:提示词命中时仅提示词命中的关系参与评分(graph.rs:135-137),聚焦实体预筛(graph.rs:138-144、665 起),均未在 5.2.4 提及。7.6.3(L1373)已单独记载 30 条上限,但 5.2.4 的方法定义未提。
Recommendation: 在 L802"取前 10 条"后补一句,如:"选取时来源为笔记的关系优先占额,不足再按得分补足;集合型意图查询的上限放宽至 30 条(见 7.6.3),注入前另有字符预算截断。"一句即可,评分公式本身无需改动。
Confidence: High

## 需要人工/外部资料核验的清单

- 式(5-3)排版效果(L789-800 的 aligned 环境、`\mathbf{1}`、`\text{note}` 等记号在目标 LaTeX 模板下的渲染)需作者编译确认——代码语义已核实,排版观感无法从 Markdown 判断(与 edit-report"公式排版请作者复核"一致)。
- "ρ 命中归一化查询"(L796)的判定实现为每个 role 的专属关键词表(`role_query_matches`,graph.rs:623 起,如 cell_line→["细胞系","cell line"]),论文以"与归一化查询相匹配"概括,属可接受简化;若答辩需逐条解释角色匹配规则,需作者准备该关键词表作为备查材料。
