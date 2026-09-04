# Academic Review — Round 06

## Review Summary
总体评分:6/10
风险等级:Medium
正文（尤其 7.1、7.4、7.6.6、8.3）对实验边界与证据状态的自我披露已达到罕见的透明度，主实验（实验 4）的数字逐项核对与工件一致；但摘要、Abstract 与 8.2 在引用"实验 5"时剥离了 paper_ready=false 的限定语，且 7.6.6 首句"五个项目…180 个案例"与论文自身表 7-12 的"单项目 12×5×3=180"直接自相矛盾——这类摘要层面的过度表述是盲审最容易命中的点。

## Issues

### ISSUE-001
Severity: Critical
Priority: P0
Location: 摘要（行 9）、Abstract（行 19）、1.5 创新点二（行 118）、8.2 核心创新点二（行 1558）；对照 7.6.6（行 1477–1495）
Category: academic/claim-evidence-mismatch
Problem: 摘要与结论把"实验 5"称为"预注册五方法扩展批次"并引用其 27 胜 0 负作为创新点二的验证证据，但未携带 7.6.6 已有的 paper_ready=false 限定；且"预注册"与"冻结题集与 SHA-256 材料指纹链"两个表述与证据文件冲突。
Evidence: 审计产物 `docs/experiments/rag-experiment-5-internal-bundle-audit-2026-08-12.json` 显示 `consistency_passed=false`、`paper_ready=false`、153 项检查未通过，其中包括 `input_freeze_manifest_verifies`（冻结清单校验失败）与 `citation_audit_recomputed_matches_report`（引用审计重算与报告不一致，reported_audit_mismatch=true）——论文 7.6.6（行 1479）只披露了"4 行证据标记越界、检索绑定字段缺失"两项，且声称"冻结题集与 SHA-256 材料指纹链下完成"；预注册协议 v2（`rag-experiment-5-preregistration-rust-v2.md` 行 15）自述"不是已生效的预注册"，五项目修订（行 2）状态为 AGENT_DRAFT_AMENDMENT 待签署。摘要（行 9）"预注册五方法扩展批次(180 个案例)中图谱增强对普通 RAG 配对 27 胜 0 负"无任何限定语。
Recommendation: Editor 可代劳的部分——在摘要、Abstract、行 118 与行 1558 引用处补上与 7.6.6 相同的限定（"内部诊断口径、paper_ready=false、见 7.6.6"），并将"预注册五方法扩展批次"改为"按预注册协议草案运行的五方法扩展批次"；同时在 7.6.6 的未通过项清单中如实补列冻结清单校验失败与引用审计重算不一致两项。彻底解决需把实验 5 推进到确认性状态（外部签署、版本绑定、人工评价）——需新增实验/签署流程，Editor 无法代劳。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P0
Location: 7.6.6 首句（行 1479）与 7.9（行 1534）；对照表 7-12 上下文（行 1481）与证据文件
Category: academic/factual-inconsistency
Problem: 论文声称"五种方法在五个项目……每方法 3 次重复……完成 180 个案例"，但 180 案例批次实际是单一项目（GSE111619）12 题 × 5 方法 × 3 次重复；五项目修订协议中每项目为 20 题。行 1534 进一步把"27 胜 0 负"归因于"5 项目"批次。
Evidence: 论文自身在行 1481 写明"在 GSE111619 内部题集(12 题 × 5 方法 × 3 重复 = 180 案例,全部完成)上"，与行 1479 的"五个项目……180 个案例"直接矛盾；证据文件 `docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md` 明确"单一公开 GEO 项目、12 个问题、5 种方法、3 次重复，共 180 个计划案例"，且其统计验证绑定的是 2026-08-12 的单项目审计产物；五项目运行（runs 20/21/23/24/25）见 `agent-work/reports/status-2026-08-16-paper-blockers.md`，主比较为 2 方法 × 20 题 × 5 项目 = 200 案例送评 198 行，与 180 口径不同。
Recommendation: Editor 修正行 1479 与行 1534 的口径：明确 180 案例批次为 GSE111619 单项目内部题集，五项目修订批次仅完成运行与证据包、其描述性结果未纳入本文表格；"27 胜 0 负"仅归属单项目 12 题批次。此为文字修正，无需新实验。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P1
Location: 7.6.6 RAGAS 段（行 1495）；证据 `docs/experiments/ragas-evaluation-2026-08-26.md`
Category: academic/selective-reporting
Problem: 论文报告实验 5 图谱增强臂 faithfulness 0.816、context recall 1.000，但未披露这些均值是在 judge 大面积失败的子集上计算的（faithfulness 29/36、context recall 31/36、context precision 仅 4/36 有效，33 个样本失败）；论文只披露了 project_rag 与 bm25_rag 两臂未完成。
Evidence: RAGAS 报告"分臂聚合"表标注 exp5/kg_enhanced_rag 为"部分完成"，并警告"均值仅基于有效子集，解释时需谨慎"；论文行 1495 的口径说明仅涵盖两臂余额耗尽与单一 judge 风险，遗漏了图谱增强臂自身的失败单元格。
Recommendation: Editor 在行 1495 补充各指标有效样本数（如"faithfulness 0.816（29/36 有效）、context recall 1.000（31/36 有效）、context precision 仅 4/36 有效未报告均值"），并说明缺分子集的解读限制。无需新实验。
Confidence: High

### ISSUE-004
Severity: Major
Priority: P1
Location: 7.3 评价协议（行 1310）、7.6.1（行 1381）、7.7 盲评段（行 1512）、8.3 限制三（行 1568）
Category: academic/evaluation-independence
Problem: 全部问答质量结论（4→14、p=0.0020、覆盖 3→12、消融对比）的最终判定依赖作者自建的事后答案要点规则与同源 LLM judge（judge 模型 deepseek-v4-flash 与被评生成模型相同），独立人工评价至今为 0。
Evidence: 论文已多处如实声明（行 1381"规则制定者可能已经接触回答内容"、行 1568"未经研究者签核的结果不写入本文"），与 `docs/experiments/human-review-current-status-2026-07-12.md`（已保存评分 0 条、评价人 0 名）一致；但这不改变盲审视角下的核心有效性缺口：主结论建立在循环设计风险未被独立证据闭合的状态上。
Recommendation: 需新增实验/数据——完成独立人工盲评签核（40 条或 198 条盲评包）方可闭合；Editor 无法代劳。文字层面 Editor 可在摘要行 9"人工盲评待签核"处再压缩表述，避免被误读为已有部分人工结果。
Confidence: High

### ISSUE-005
Severity: Major
Priority: P1
Location: 摘要（行 9）、Abstract（行 19）；对照 7.4（行 1339）
Category: academic/misleading-framing
Problem: 摘要句"三个生物医学场景(35 条已审核笔记、357 个实体、445 条关系)上,普通 RAG 与图谱增强 RAG 分别完成 4 题和 14 题"把三项目图谱总量与仅项目一的问答实验并置，易使读者误以为问答实验覆盖三个项目。
Evidence: 7.4 行 1339 明确"项目二、三仅用于验证图谱构建流程可运行,未进入问答质量比较"；7.4 行 1318 说明问答语料为项目一（15 条笔记、177 实体、237 关系、7 份资料）。
Recommendation: Editor 在摘要与 Abstract 该句中加限定，如"问答对照实验以项目一为封闭语料（三项目合计规模仅用于图谱构建统计）"。无需新实验。
Confidence: High

### ISSUE-006
Severity: Major
Priority: P1
Location: 1.5 创新一（行 108、115）、8.2（行 1556）
Category: academic/overclaim
Problem: "首次把业务审核状态确立为 AI 可用知识的前置条件"中的"首次"是绝对化优先权主张，其支撑仅为表 1-1 对 4 条代表性路线的对照（"所综述的代表性路线中未见报告"），"首次"与限定语之间强度不匹配。
Evidence: 行 108 同时写"首次……该闭环在所综述的代表性路线中未见报告(表 1-1)"；表 1-1（行 65–70）仅覆盖 openBIS、普通 RAG、GraphRAG/LightRAG 与本文四行。
Recommendation: Editor 删除"首次"二字，统一为"在本文所综述的代表性路线中未见报告"（行 115 与 1556 已是该口径），即可消除优先权主张与证据范围的不匹配。无需新文献（若要保留"首次"则需系统性检索新文献——Editor 无法代劳）。
Confidence: High

### ISSUE-007
Severity: Major
Priority: P1
Location: 1.5 创新三（行 120–121）、7.7（行 1510）、8.2 创新三（行 1560）
Category: academic/claim-evidence-mismatch
Problem: 创新点三"固定任务型智能体的安全运行时"的效果证据仅为四类任务"能生成并保存来源对账"加三项安全性质测试，生成内容本身无任何忠实度或质量度量——"可控"有机制证据，"可用/忠实"无评价证据。
Evidence: 行 1510 自认"该实验只验证四类任务能生成并保存证据;内容忠实度未做独立评分"；安全性质测试仅 3 项 Rust 集成测试（行 1245）。
Recommendation: 需新增实验/数据——对四类生成任务做来源编号逐项对账统计（可自动）与小型人工评价（忠实度/可用性评分）方可支撑创新点三的效果面；Editor 无法代劳。文字层面 Editor 可将行 120 的"验证证据"表述收紧为"机制验证（安全属性、来源对账），生成质量未评价"。
Confidence: High

### ISSUE-008
Severity: Minor
Priority: P2
Location: 7.3（行 1310）末句"回答可追溯性另有 [S]/[G] 引用审计独立度量(7.6.6 节)"
Category: academic/dangling-reference
Problem: 7.6.6 节没有任何 [S]/[G] 引用审计的内容，该前向引用悬空；且实验 5 审计中引用审计的重算与报告不一致（reported_audit_mismatch=true，3 项摘要字段不匹配），若将引用审计作为"独立度量"写入评价体系，需说明其审计状态。
Evidence: 全文检索"引用审计"仅命中行 1310；`rag-experiment-5-internal-bundle-audit-2026-08-12.json` citation_audit 节点记录 recomputed 与 reported 的 3 项 mismatch（invalid_marker_rows 4 对 0 等）。
Recommendation: Editor 二选一：把行 1310 的指引改为指向实际存在的工件（如实验 5 审计 JSON 的 citation_audit 字段或 6.4 的来源编号对账），并在 7.6.6 未通过项中补列引用审计重算不一致；或删除该半句。无需新实验。
Confidence: High

### ISSUE-009
Severity: Minor
Priority: P2
Location: 5.1.5（行 749）
Category: academic/editing
Problem: 同一段内相邻两句重复："审核后入图谱因此成为本文可信知识管理的核心做法。审核后入图谱是本文可信知识管理的核心做法,也是它区别于普通知识图谱系统的主要特征之一。"
Evidence: 行 749 原文两连句主谓宾几乎完全相同，属编辑残留。
Recommendation: Editor 合并为一句，保留后者（含"区别于普通知识图谱系统"的增量信息）。无需新实验。
Confidence: High

### ISSUE-010
Severity: Minor
Priority: P2
Location: 1.5 创新点二（行 118）
Category: academic/editing
Problem: 同一段内"回答中的每项事实以 [S]/[G] 编号引用来源块与关系,每次调用保存语料哈希、提示版本、检索配置、Token 与时延,业务、AI 操作与通用审计三层日志贯通,支持按日志编号回放复核"几乎逐字出现两次（"方案要点"与"与已有工作的差异"两处）。
Evidence: 行 118 中该句在方案要点句群与差异句群各出现一次，重复约 60 字。
Recommendation: Editor 在"与已有工作的差异"处删除重复句，仅保留差异论证本身。无需新实验。
Confidence: High

### ISSUE-011
Severity: Minor
Priority: P2
Location: 1.3（行 74、行 80）
Category: academic/structure
Problem: 行 74 声称三个子问题"与第七章的 RQ1/RQ2/RQ3 一一对应"，但行 80 的子问题三标题未标 RQ，而是把 RQ3 定义为其"反面刻画"（固定 top-k 一跳检索的失效机制），一一对应关系在标签层面不成立。
Evidence: 行 76"子问题一(可追溯,RQ1)"、行 78"子问题二(关系证据,RQ2)"、行 80"子问题三(可控生成)：……该问题的反面刻画(……,RQ3)……"。
Recommendation: Editor 将行 74 的"一一对应"改为"子问题一、二分别对应 RQ1、RQ2，子问题三的适用边界刻画对应 RQ3"，或在行 80 为子问题三补显式 RQ 标注。无需新实验。
Confidence: High

### ISSUE-012
Severity: Minor
Priority: P2
Location: 7.2 自动化测试段（行 1237）
Category: academic/verifiability
Problem: "346 项通过、11 项跳过""264 个 Rust 单元/集成测试"两个计数本轮未能从仓库工件独立复核（测试套件收集在本评审环境中未产出结果），作为论文中的精确数字其来源工件未在正文或附录标注。
Evidence: 行 1237 给出精确计数但未指向任何留档工件（对比行 1245 的 3 项测试明确给出证据路径 docs/system-evidence/agent-safety-property-tests-2026-08-28.md）。
Recommendation: 需人工核验——由证据线重跑两套测试套件确认计数并在行 1237 附加留档路径；Editor 可先统一加"运行记录见附录/证据目录"的指引。本轮标 Confidence: Low。
Confidence: Low

## 最严重三个问题
1. ISSUE-001：摘要/Abstract/8.2 以"预注册"名义无限定引用 paper_ready=false 的内部诊断批次（且"冻结指纹链"表述与审计未通过项冲突）——盲审一票否决式风险，Editor 可立即加限定语止损。
2. ISSUE-002：7.6.6"五个项目…180 个案例"与论文自身表 7-12 的"单项目 12×5×3=180"自相矛盾——属事实性硬伤，必须修正口径。
3. ISSUE-004：全部质量结论的判定链（事后规则 + 同源 judge）缺独立人工评价闭合——本轮红线内无法由 Editor 解决，需新增人工盲评签核。
