# Evidence Re-verify — Round 09

- 审查对象:`docs/毕业论文重构稿.md`(HEAD bf18e9e 工作区,1975 行)对 `reviews/round-08/baseline-thesis-snapshot.md` 的 45 行 diff(33 增/12 删),覆盖 be2f2a6(两项实验销账)、39adf68(摘要/句式改写+治理成本降格)、2a3d443(图表题注)三批改动。
- 证据工件:`docs/experiments/rust-rerun-paired-2026-09-04.md` / `.csv` / `-report.json`;`docs/experiments/kg-score53-coefficient-ablation-2026-09-04.md` / `.json`;`docs/experiments/rag-experiment-5-internal-descriptive-results-v1.md`(L93 配对表)。全部工件已入库(be2f2a6);脚本 `scripts/ablate_score53_coefficients.py` 已入库。
- 方法:逐块 diff 审读;每个新增数字回溯到工件字段;对 172/197 做了独立重算(从 rag-experiment-4.csv kg 臂 graph_context_json 逐题计数)。

## 逐块审查(PASS/ISSUE)

| # | 位置 | 内容 | 判定 |
| --- | --- | --- | --- |
| 1 | 摘要中文 L13 | "27 胜 0 负(180 个案例)" → "五方法扩展批次又以独立题集复现了同一方向(图谱增强对普通 RAG 零恶化,内部诊断口径,见 7.6.6 节)" | **PASS**。"零恶化"与证据 worse=0 一致且弱于原表述;保留"内部诊断口径";全文 grep 无"27 胜/27胜/180 个案例"残留(仅 7.6.6 L1504 保留 180 个案例的完整描述) |
| 2 | 摘要英文 L25 | "wins 27 paired comparisons and loses none" → "reproduced the same direction on an independent question set (no degraded pairs against plain RAG; internal diagnostic scope, Section 7.6.6)" | **PASS**。与中文逐句同构;"180 cases" 已同步删除;无残留 |
| 3 | 1.5 核心创新点一 L121 | "沿用同一门禁即可,治理成本不随功能数量增长" → "沿用同一门禁,以复用单一门禁控制治理成本为设计目标" | **PASS**。事实断言降格为设计目标 |
| 4 | 8.2 核心创新点一 L1581 | 同上降格,并加括注"(以复用单一门禁控制治理成本为设计目标)" | **PASS**。与 1.5 L121 措辞一致(同一短语原文复用);新增的"治理机制无需随功能扩展重建"属机制设计层陈述,可由"沿用同一门禁"机制事实支撑 |
| 5 | 7.1 新增段 L1237 | 交付系统复现批次:revision 74dad169、运行 #24、40/40、0.9821/0.9286、0.95/0.85、3/17/0、40/40 审计零越界、4 笔记+2 资料+bge-m3、"数字不与实验 4 并列或替换" | **PASS(数字全部命中)**;两处表述 nit 见 Issues 5、6 |
| 6 | 表 7-14 L1239–1249 | 五行指标+表注(McNemar p=0.5、内部开发证据、不与实验 4 并列) | **ISSUE(Low)**:"严格引用审计 40/40"置于普通 RAG 列有歧义(按 JSON by_mode,project_rag 臂单独为 20/20 [S];40/40 是全运行两臂合计);其余数字全对。表注"内部开发证据"与 JSON `evidence_level` 一致 |
| 7 | 图 7-3 latex 块 L1477–1481 | 新增 `\includegraphics{assets/screenshots/11-score53-coefficient-ablation.png}` + 题注 | **PASS(论文侧)**:编号 7-3 与既有图 7-1(09-rag-objective-metrics)、图 7-2(10-kg-threshold-sensitivity)连续无冲突;路径约定与全部既有插图一致;PNG 文件存在于 `docs/user-guide-assets/`。**ISSUE(Medium):该 PNG 未入 git**(同类的 09/10 PNG 均已入库),干净检出重建 PDF 会缺图 |
| 8 | 7.9 L1559 | ①"27 胜 0 负"→"36 个配对案例中改善 27 例、恶化 0 例";②新增式(5-3) 系数消融段(7 变体、172/197、0.9752、≤0.26、休眠参数、图 7-3、边界声明) | **ISSUE(Medium)**:"172/197" 的 197 不可溯源(见 Issues 1);①及其余消融数字全部命中 |
| 9 | 8.2 核心创新点二 L1583 | "配对 27 胜 0 负" → "36 个配对案例中图谱增强改善 27 例、恶化 0 例(内部诊断口径,7.6.6 节)" | **PASS**。计数句式,保留"单项目"与证据等级限定 |
| 10 | 8.4 L1597 | ①同一句式改写;②消融承诺销账:"离线敏感性消融已于 2026-09-04 完成(7.9 节)……确认性运行仍应纳入预注册框架复验";③新增复现批次句"可执行且方向一致(图谱增强 0 恶化、引用审计零违规)" | **PASS**。销账措辞为"获得直接证据/排序稳定",保留预注册复验要求,未把离线重打分升格为答案级结论;③未引入效应量或与 legacy 数字并列 |
| 11 | 附录 A/B/C/D、6.6 交叉引用(L1161、L1603、L1668、L1714、L1727) | 新增"见表 X-Y"句 | **PASS**。各编号在全文唯一,指向紧随其后的既有表格 |
| 12 | 摘要与 7.6.6 的衔接(180 删除) | 摘要不再含 180 | **PASS**。7.6.6(L1504–L1516)完整保留 180 案例设计描述与 27/9/0 配对描述,摘要"零恶化"是 7.6.6 数据的真子集且指向 7.6.6,无孤儿数字、无口径断层 |
| 13 | 红线自洽("内部开发证据/不与 legacy 数字并列") | 新段与既有三条使用规则的关系 | **PASS(带 Low nit)**。7.1 新段与表注两处显式声明"内部开发证据、不并列不替换",8.4 仅用"可执行且方向一致/零恶化/审计零违规",未混用 legacy 数字。nit:同节规则二原文"当前系统证据……不用于任何检索或生成效果比较"仍为绝对表述,新段以"缩小了上述边界"声明例外交代,建议在规则二处加"(交付系统复现批次除外,见下文)"避免读者视为矛盾 |

## 数字溯源表(新增数字 → 工件 → 一致性)

**A. 表 7-14 与 7.1 新段 ↔ `rust-rerun-paired-2026-09-04-report.json` / `.md`**

| 论文数字 | 工件字段 | 一致性 |
| --- | --- | --- |
| 运行 #24、40/40 完成 | `experiment_run.id=24`,`total_cases=40, completed_cases=40, failed_cases=0` | 一致 |
| `/ready` revision `74dad169` | 仅记录于 `.md` 配置表(`74dad169181c…`,/ready 端点);JSON/CSV 不含该串 | 一致(md 为已入库工件并被论文显式引用);溯源等级:工件级而非机读级,可接受 |
| Micro 事实覆盖率 0.9286 / 0.9821 | `objective_evaluation.mode_summary[*].micro_fact_coverage` = 0.9286 / 0.9821 | 一致 |
| 封闭集 exact 17/20(0.85) / 19/20(0.95) | `closed_set_exact_correct_cases` = 17 / 19;`closed_set_exact_case_accuracy` = 0.85 / 0.95 | 一致 |
| 配对(20 对)改善 3、持平 17、恶化 0 | `paired_comparison.improved_cases=3, tied_cases=17, worse_cases=0, paired_case_count=20` | 一致 |
| 严格引用审计 40/40 带标记、越界 0;图谱臂 20/20 [G]、越界 0 | `citation_marker_audit.answers_with_source_marker=40/40`,`kg_answers_with_graph_marker=20/20`,`all_citation_indices_in_range=true`,`invalid_*_rows=[]` | 一致(但 40/40 是两臂合计,置于普通 RAG 列有歧义,Issue 3) |
| 平均时延 7100.4 ms / 9688.1 ms | `mode_summary[*].mean_response_ms` = 7100.4 / 9688.1 | 一致 |
| McNemar 精确双侧 p=0.5 | `paired_comparison.mcnemar_exact_two_sided_p=0.5`(基于封闭集 exact 不一致对 2/0;覆盖率 3/17/0 的 sign test p=0.25) | 一致(与 md 呈现方式相同);可选加注基础口径,Issue 7 |
| corpus 与 graph snapshot 哈希 | JSON `config_snapshot_json.corpus_snapshot_hash / graph_snapshot_hash`;CSV 逐行仅含 `corpus_snapshot_hash` 列(graph 哈希在运行级配置) | 哈希值一致;"逐行记录"对 graph 哈希过强,Issue 4 |
| 语料 4 条笔记、2 份 GSE111619 资料、bge-m3 | `.md` 诚实性边界段同文 | 一致 |
| 证据等级"内部开发证据" | JSON `evidence_level="internal development evidence; not an independent blind evaluation"` | 一致 |

**B. 7.9 系数消融段 ↔ `kg-score53-coefficient-ablation-2026-09-04.json` / `.md`**

| 论文数字 | 工件字段 | 一致性 |
| --- | --- | --- |
| 7 个变体档位 | `meta.variants` 共 8 项(baseline + role=2.0/1.0/0.0、exact=2.0、partial=2.0、hint=1.0、bonuses=0) | 一致(变体 7 个;"4.0/2.0/1.0/0"中 4.0 为基线锚点,计数自洽) |
| 幸存关系集与实验 4 完全一致(172/197) | `summary[*].survivors_min_score>=1.0` baseline=variant=172;**候选池实测 = 172 条**(逐题 n_cand 合计;rag-experiment-4.csv kg 臂 graph_context_json 原始记录 172 条:17 题×10 + Q3=1 + Q16=1 + Q5=0) | **不一致**:"197" 在 JSON/CSV 中均不存在(仅为关系 ID 1971/1975/1976 的子串);唯一 ID 93、三元组 93,任何口径均不等于 197。正确表述应为"全部 172 条候选关系均幸存"。md 工件自身(L10/L30/L42)同样误写 197。→ **Issue 1** |
| 排序一致率最低 0.9752 | `summary["hint=1.0"].kendall_tau_consistency=0.9752`(全档位最低;其余 1.0/0.9895) | 一致 |
| [G] 引用位次平均位移不超过 0.26 | `citation_position_shift_mean` 最大 0.26(hint=1.0;partial=0.14,其余 0),`citation_refs_total=58` | 一致 |
| top-10 集合重合率全部档位 0.91;左纵轴 0.975–1.0 | `mean_top10_set_overlap=0.9053`(全部变体);τ 范围 0.9752–1.0 | 一致(0.9053→0.91 与 md 同一舍入口径) |
| 角色命中 4.0 属休眠参数(项目 1 仅 1 条关系 roles 非空) | `.md`:"53 条关系仅 1 条非空(data_boundary)";JSON `meta.roles_source` 同口径 | 一致 |
| "该消融只覆盖图谱输入层的选择稳定性,答案内容敏感性需完整重跑" | `.md` 边界说明同文 | 一致 |

**C. 摘要/7.9/8.2/8.4 的 36 配对案例 ↔ `rag-experiment-5-internal-descriptive-results-v1.md` L93**

| 论文表述 | 证据 | 一致性 |
| --- | --- | --- |
| "36 个配对案例中改善 27 例、恶化 0 例"(7.9 L1559、8.2 L1583、8.4 L1597) | L93:`kg_enhanced_rag | 0.6389 | 27/9/0 | 0 | 27/0 | 0 |`(improved/tied/worse=27/9/0,27+9+0=36) | 一致,未超出证据 |
| 摘要"零恶化"(中 L13 / 英 L25) | 同上 worse=0;另 L1517 表头注"improved/tied/worse 为 36 个配对案例计数" | 一致(弱化表述,且保留"内部诊断口径") |
| 7.6.6 L1516 "覆盖差值均值 +0.6389,27 例改善、9 例持平、0 例恶化(sign p≈0,McNemar p≈0)" | L93 同值 | 一致 |

**D. 图 7-3 素材**:`docs/user-guide-assets/11-score53-coefficient-ablation.png` 本地存在(2026-09-04 19:12),但 **未入 git**(同类 09/10 PNG 均已入库)→ Issue 2。

## Issues(Severity/Priority/Location/可否 Editor 代劳)

| # | Severity | Priority | Location | 描述 | 可否 Editor 代劳 |
| --- | --- | --- | --- | --- | --- |
| 1 | **Medium** | High | 论文 L1559"(172/197)";工件 `kg-score53-coefficient-ablation-2026-09-04.md` L10/L30/L42 | **197 不可溯源**:消融候选池实测 172 条(逐题合计,机读 JSON 与源 CSV 一致),且阈值 1.0 下 172 条全部幸存(baseline=variant=172);"197"仅作为关系 ID 子串存在于 JSON。盲审者按工件重算会得到 172,与"172/197"矛盾。**修复**:论文改为"幸存关系集与实验 4 完全一致(候选池 172 条全部幸存)"或"(172/172)";工件 md 的"共 197 条候选关系记录/172/197"需证据线同批修正(本复审只读,未改) | 论文侧可;工件 md 侧需证据线 |
| 2 | Medium | High | `docs/user-guide-assets/11-score53-coefficient-ablation.png`(论文 L1479 引用) | 图 7-3 素材 PNG 未入 git(同系列 09/10 已入库);干净检出或 CI 重建 PDF 将缺图。修复:随下一次证据线提交 `git add` 该文件 | 可(机械入库,建议随证据线提交并按归属标注) |
| 3 | Low | Medium | 表 7-14 L1245 严格引用审计行 | "40/40 带标记"置于普通 RAG 列有歧义(该臂单独为 20/20 [S];40/40 为两臂合计)。建议改行标签为"[S] 审计(全运行 40/40)、越界 0 / [G] 审计(图谱臂 20/20)、越界 0"或移入表注 | 可 |
| 4 | Low | Low | L1237"corpus 与 graph snapshot 哈希由后端逐行记录";L1239"含逐行 snapshot 绑定" | CSV 逐行仅记录 corpus_snapshot_hash;graph_snapshot_hash 记录于运行级配置快照(JSON config_snapshot_json)。建议改为"corpus 哈希逐行记录、graph snapshot 哈希记录于运行配置快照,均由后端落库" | 可 |
| 5 | Low | Low | L1237"仅作两项用途:证明成对对照协议……" | "证明"宜降为"验证/支持"(工件自身口径为"可以完整执行并产出方向一致的结果",属可实现性结论);同时建议在 7.1 规则二句末加"(交付系统复现批次除外,见下文)"消除与新段的字面冲突 | 可 |
| 6 | Low | Low | 摘要中文 L13 / 英文 L25 | 相对 8.2/8.4 的"单项目五方法扩展批次",摘要丢了"单项目"限定(7.6.6 的协议修订批次含多项目运行且未纳入本文)。建议摘要恢复"单项目"二字以对齐正文指称 | 可 |
| 7 | Info | Low | 表 7-14 表注 L1249 | McNemar p=0.5 基于封闭集 exact 不一致对(2/0),覆盖率 3/17/0 对应 sign test p=0.25;现表述与工件呈现一致、且已声明"仅作方向性描述",如需更严谨可注"基于封闭集 exact 判定" | 可(可选) |
| 8 | Info | — | L1237 revision `74dad169` | 该 revision 仅记录于 `.md` 工件(来自 /ready 端点),JSON/CSV 不含;工件已入库且被论文显式引用,溯源链可接受,无需改动 | — |

## 结论

**总体判定:有条件通过(1 项 Medium 数字问题 + 1 项 Medium 资产入库问题须处理;其余为 Low/Info 措辞项)。**

- 三批新增内容的机制性表述与两个 2026-09-04 实验工件高度一致:表 7-14 与 7.1 段的全部数字(0.9286/0.9821、17/20、0.85、19/20、0.95、3/17/0、7100.4/9688.1、40/40、20/20、运行 #24、74dad169、4 笔记+2 资料)逐一命中机读 JSON;7.9 消融段除"172/197"的分母外全部命中(7 变体、0.9752、≤0.26、0.91、休眠参数、输入层边界声明)。
- "36 个配对案例改善 27 例、恶化 0 例"句式(7.9/8.2/8.4)与摘要中英"独立题集复现同一方向/零恶化"口径互相一致,均不超出 descriptive-results 27/9/0 的证据范围,且均保留"内部诊断口径/paper_ready=false"限定;摘要删除 180 后与 7.6.6 衔接完好,无孤儿数字。
- 未发现"验证了/证明了"类越界升级:消融销账保留"输入层稳定/答案内容需重跑/预注册复验"三重边界;复现批次仅声明"可执行且方向一致/审计零违规",未与 legacy 数字并列,红线自洽。
- **合入前必须处理**:Issue 1(172/197 → 172,论文与工件 md 同批修正)、Issue 2(11-score53 PNG 入库)。Low 项(表 7-14 审计行歧义、"逐行记录"粒度、"证明"措辞、摘要"单项目")可由 Editor 在同一窗口内代劳。
