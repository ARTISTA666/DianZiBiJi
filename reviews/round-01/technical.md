# Technical Review — Round 01

scope: 论文全文(技术密集区:Ch2 L150-202、Ch4 L412-567、Ch5 L569-895、Ch6 L897-1161、Ch7 L1163-1462;另覆 Ch1/Ch3/Ch8/附录)。
核实基准:`backend/src/`(Rust/Axum 生产实现)、`backend/migrations/`、`backend/app/models|services`(legacy 参考)、`frontend/src/`、`docs/system-evidence/`、`docs/experiments/`。

## Review Summary

总体评分:8/10
风险等级:Medium

本轮逐条核对了论文声称的检索算法参数、权限模型、MCP 工具运行时、数据库 schema、外部服务接入与证据工件,与代码的吻合度在同类工程型论文中属高位:BM25 公式与系数(bm25.rs:180-186)、RRF(rank constant=60、1.0/1.0、0.25/0.75、legacy 0.7/0.3、最低分 0.15、top-6、单文件 ≤3 块,retrieval.rs:210-311/390-410)、分块 700/120(config.rs:141-142)、HNSW 余弦索引(0005 迁移)、实体自然键唯一约束(0012)、图谱置信度 1.0/0.7(knowledge_graph.rs:122-260)、集合型查询图谱上限 ≥30(api/rag/mod.rs:700)、12 个 MCP 工具及其五项安全属性(mcp.rs:550-700,与表 5-5/表 C-1 逐格一致)、六个任务模板、四个提示版本串、DeepSeek 重试策略(408/425/429/5xx×3、1s/2s 上限 30s,ai_provider.rs:195-267/525-526)、敏感外发闸门(permissions.rs:76-95)、审核通过自动抽取(notes.rs:442/762)、`tool_execution_keys` 主键(db.rs:391-400)、Rust 测试 261 个(逐个统计精确吻合)均能在代码中定位。revision `93790d62…` 与 bge-m3/1024 冒烟也有证据文件支撑(system-evidence/ready-revision-bound-*.json、embedding-bge-m3-1024-latest.json)。

主要问题集中在四类:(1) 核心创新点二反复引用的式(5-3) 全文从未给出定义,是唯一 Critical 缺口;(2) "26 张表"的表数声称与其自身 4.5 节枚举(33 张)、附录 B(27 张)和实际 schema(33-34 张)三方互斥,且 `group_projects` 表被正文列出但仓库无定义;(3) 式(4-1) 权限形式化遗漏了全局 `PI` 角色对全部非敏感项目的读分支,这是安全分析层面的实质遗漏;(4) 第六章截图编号系统性混乱(同一张图三个编号)并伴随 LaTeX `\\textwidth` 语法错误。其余为若干处实现描述与代码不符的中小问题(SVG vs Canvas、BM25"进程内缓存"、vector(1024) 固定表述、同义词 17/13 自相矛盾、测试数 105 已过期)和修订遗留的重复句。未发现"听起来高级但没实现"的虚构功能;论文对 legacy 批次与当前 Rust 系统的口径切分(表 7-1)与工件事实一致,自我限定诚实。

## Issues

### ISSUE-001
Severity: Critical
Priority: P0
Location: 全文(1.5 L118;5.2.4 L781-843;5.4 L893;6.3 L1017;6.5 L1035/1056;7.9 L1456;8.2 L1482;8.4 L1496);公式应在 5.2.4 给出
Category: technical/fact-error(公式缺失/正文不完整)
Problem: 式(5-3) 在全文被引用 10 余次(含核心创新点二、图 5-3/图 6-3/图 6-4、7.9 的"角色命中项 4.0 分"、8.4 的"4.0/2.0/1.0 三档对比"),但正文任何位置都没有给出该公式;5.2.4 节只有文字描述与图,无编号公式。式(5-1)、(5-2) 均有定义,唯独被标为图谱注入核心排序器的式(5-3) 缺失,读者无法复现关系评分逻辑。
Evidence: `grep -n "5-3" docs/毕业论文重构稿.md` 命中 L118/722/800/893/1017/1035/1056/1456/1482/1496,均为引用,无定义块;代码实际实现为 backend/src/rag/graph.rs:452-494 `graph_relation_score`(关系类型提示命中 +3.0、词元全等 +3.0、子串包含 +1.0、source=note +0.2、source=note_extraction +0.3、properties.roles 命中数 ×4.0)。
Recommendation: 在 5.2.4 节补出式(5-3) 完整定义(含各系数取值与"取阈值 max(min_score,>0) 后按分排序"的语义),并标注与 `graph_relation_score` 的对应关系;否则创新点二的验证链条(7.6、7.6.4 阈值敏感性)没有可复核的公式基础。
Confidence: High

### ISSUE-002
Severity: Major
Priority: P1
Location: 4.1 图 4-1(L432 "26 张表,字段见附录 B");4.5(L518 "全部 26 张表");附录 B(L1527-1576)
Category: technical/fact-error
Problem: "26 张表"与三方互斥:论文 4.5 节自身枚举了 33 个表名;附录 B 实际列出 27 张(B-1 共 21 张 + 运行时扩展 6 张);当前代码实际 schema 为 Python 模型 24 张 + Rust 运行时 10 张 = 34 张(除内部簿记表 `rust_schema_versions` 为 33 张)。三处数字互相矛盾,且都未与代码对齐。
Evidence: 4.5 L518 枚举 users/groups/group_members/group_projects/projects/project_members/project_reviewers/experiment_notes/note_versions/note_approvals/files/file_ocr_results/search_documents/kg_*/rag_*/ai_*/agent_generation_runs/audit_logs + 9 张运行时表 = 33;`backend/app/models/*.py` `__tablename__` 共 24 张(含正文未提的 `experiment_templates`);`backend/src/db.rs:265-402` 建 10 张(mcp_personal_access_tokens、mcp_http_sessions、agent_sessions/turns/events/messages/steps、agent_pending_actions、tool_execution_keys、rust_schema_versions)。另:4.5 与该断言把 `group_projects` 列为业务状态域表,仓库中无任何模型或迁移定义它,仅出现于 `backend/src/db.rs:33`(运行时 schema 签名检查)与 `backend/migrations/env.py:25`(PRESERVED_LEGACY_TABLES),属 legacy 保留表。
Recommendation: 以 migrations/模型实际清单为准统一表数并写明统计口径(是否含内部表);`group_projects` 要么补出处说明(legacy 保留表),要么从业务状态域清单中移除。
Confidence: High

### ISSUE-003
Severity: Major
Priority: P1
Location: 4.2 用户类型与能力矩阵(L453-472,式 4-1 在 L457-460)
Category: technical/arch-inconsistent
Problem: 式(4-1) 的 Read(u,p)=S(u) OR O(u,p) OR M(u,p) 遗漏了实现中的第四条读授权路径:全局角色为 `PI` 的用户对一切非敏感项目拥有读权限。该路径是系统级读能力(跨项目),既不在式(4-1)、也不在表 4-1 的任何角色行中出现(表 4-1 只描述系统管理员与四类项目级用户),使权限形式化与实现不一致,可能误导安全性论证("非项目成员无法读取项目数据"在非敏感项目上不成立)。
Evidence: backend/src/permissions.rs:56-61 `if user.role == "super_admin" || project.owner_user_id == Some(user.id) || (user.role == "pi" && !project.is_sensitive) { return Ok(true); }`;permissions.rs:220-227 `accessible_project_ids` 对 `pi` 角色单列分支(返回全部非敏感项目);`users.role` 枚举含 PI(backend/app/models/user.py:12)。论文 4.2 L453 只说 `require_admin` 仅放行 SUPER_ADMIN(该句与 backend/src/api/auth.rs:219-227 一致,正确),但未描述 PI 读路径。
Recommendation: 在式(4-1) 增补 Read 的 PI 分支(或明确写出其语义与敏感项目豁免),并在表 4-1 增加 PI(课题组负责人)一行的能力/边界描述。
Confidence: High

### ISSUE-004
Severity: Major
Priority: P1
Location: 6.5(L967/L993/L1017/L1045)、6.6(L1113-1122 表格;L1124-1157 LaTeX caption)、7.5(L1295)、7.8(L1450)
Category: technical/fact-error(图文编号一致性)
Problem: 第六章八张截图的编号系统性混乱,同一张图在不同位置出现不同编号:知识图谱图在正文为"图 6-11-11"(L1017、7.5 L1295)、在 6.6 索引表为"图 6-11-7"(L1120)、在 LaTeX caption 为"图 6-11-10"(L1147);类似地存在"图 6-9-9/L1118 图 6-9""图 6-10-9/图 6-10-11""图 6-12-8/图 6-12-11/图 6-12-12""图 6-13/图 6-13-12/图 6-13-13"等多重编号(形如"6-11-11"的编号本身即为修订残留)。此外图 7-1 与图 7-2 的 `\includegraphics` 选项写成 `width=0.86\\textwidth`(双反斜杠,L1336/L1374),LaTeX 编译会直接报错。
Evidence: L1120 "图 6-11-7"、L1147 "图 6-11-10"、L1017/L1295 "图 6-11-11" 指向同一素材 `user-guide-assets/06-knowledge-graph.png`;L1336/L1374 `\includegraphics[width=0.86\\textwidth,height=0.4\\textheight,...]`。
Recommendation: 统一重排第六章图号(正文引用、6.6 索引表、LaTeX caption 三处同步),改为单调编号;修正 `\\textwidth`→`\textwidth`、`\\textheight`→`\textheight`。
Confidence: High

### ISSUE-005
Severity: Minor
Priority: P2
Location: 5.1.7(L740)、6.2(L932)、6.5(L1017)
Category: technical/fact-error
Problem: 论文三处称知识图谱可视化"以 SVG 方式绘制关系图",实际前端使用 react-force-graph-2d(Canvas 2D 渲染),不存在 SVG 渲染路径。属实现细节描述错误,不影响功能结论,但与"以看得见的证据呈现实现"的写作立场不符。
Evidence: frontend/src/components/kg-visualization.tsx:14-18(dynamic 导入 `react-force-graph-2d`,渲染为 canvas,提供 zoomToFit 等 canvas API);frontend/package.json:33 `"react-force-graph-2d": "^1.29.1"`。
Recommendation: 改为"以 Canvas 2D 力导向图(react-force-graph-2d)渲染",或如需保留 SVG 表述则说明为示意图性质。
Confidence: High

### ISSUE-006
Severity: Minor
Priority: P2
Location: 7.2(L1189 "共 105 个用例全部通过")
Category: technical/fact-error(数据过期)
Problem: "后端 Python 集成测试套件共 105 个用例"与当前仓库不符:`backend/tests/` 现有 343 个 `def test_` 测试函数。同句的"约 261 个 Rust 单元/集成测试"经逐个统计精确吻合(backend/src 内 261 个 `#[test]`/`#[tokio::test]`),说明 Rust 数字是新口径而 Python 数字是旧口径,两者并存易被质疑统计严谨性。
Evidence: `grep -c "def test_" backend/tests/*.py` 合计 343(test_rag_api.py 52、test_kg_retrieval.py 28、test_maturity_api.py 24 等);`grep -rn "#\[test\]\|#\[tokio::test\]" backend/src | wc -l` = 261。
Recommendation: 重跑 `cd backend && python -m pytest tests -q` 后按实际收集数更新(或注明统计 commit/时点);注意如无 PostgreSQL 夹具部分用例会跳过,应写明"通过/跳过"口径。
Confidence: High(数字不符为直接统计;105 的来源口径需作者说明)

### ISSUE-007
Severity: Minor
Priority: P2
Location: 5.2.2(L762 "17 组同义词展开表")与 5.4(L893 "13 组同义词展开")互斥
Category: technical/fact-error(内部不一致)
Problem: 同一份数据在 5.2.2 说 17 组、在本章小结说 13 组。代码实有 17 个键。
Evidence: backend/src/rag/bm25.rs:16-49 `QUERY_SYNONYMS` 恰含 17 个键(pcr、聚合酶链反应、rt-pcr、wb、western blot、elisa、cck8、cck-8、dmem、fbs、pbs、rna-seq、转录组、htseq、geo、od、光密度)。
Recommendation: 5.4 节改为 17 组(或统一为统计口径一致的数字)。
Confidence: High

### ISSUE-008
Severity: Minor
Priority: P2
Location: 5.2.2(L758-760 "BM25 实现取参数 k1=2.2、b=0.75,词元得分按经典公式…")
Category: technical/concept-confusion
Problem: 论文给出的打分公式与代码逐字一致,但把它称作"经典公式"不准确:经典 BM25 分子为 tf·(k1+1)、分母为 tf + k1·(1−b+b·|d|/avgdl);实现(及论文公式)分子系数是 2.2(=k1)、分母系数是 1.2(=k1−1),并额外做 raw/(raw+1) 归一化。这是 BM25 的非标准变体,称"经典公式"并给出 k1=2.2 的经典参数命名会使读者与文献比对时产生困惑。
Evidence: backend/src/rag/bm25.rs:180-186 `idf=(((n-df+0.5)/(df+0.5)+1.0)).ln()`、`idf*(tf*2.2)/(tf + 1.2*(1.0-0.75+0.75*dl/avg))`、`raw_score/(raw_score+1.0)`,与论文 L760 公式一致。
Recommendation: 改称"BM25 变体"并注明分子/分母系数的实际含义(或按经典形式重参数化后统一命名);归一化步骤 raw/(raw+1) 也建议在论文中写明。
Confidence: High

### ISSUE-009
Severity: Minor
Priority: P2
Location: 5.2.2(L756 "对全部活跃数据块预计算 BM25 倒排索引(进程内缓存,语料变更时重建)")
Category: technical/fact-error
Problem: 实现没有跨请求的进程内缓存:`Bm25Index::build` 在每次检索请求内对全部活跃块重新构建(逐请求预计算),并非"进程内缓存、语料变更时重建"。描述暗示了一个不存在的缓存失效机制,且掩盖了每次查询全量分词的真实开销。
Evidence: backend/src/rag/retrieval.rs:105-108(`retrieve_with_connection` 内 `let bm25_index = Bm25Index::build(&rows);`,无任何 OnceLock/Mutex 缓存层;全仓库 `Bm25Index` 仅 bm25.rs 定义与 retrieval.rs 此处调用)。
Recommendation: 改为"每次检索对当前项目活跃块现场构建倒排索引(单请求内复用)";若未来加缓存再更新表述。
Confidence: High

### ISSUE-010
Severity: Minor
Priority: P2
Location: 5.2.1(L752 "向量列在数据库中定义为 `vector(1024)`")
Category: technical/overclaim
Problem: 向量列维度不是固定 1024:迁移基线经 legacy 模型定义为 512 维,Rust 启动时按 `EMBEDDING_DIMENSION`(默认 512)检测并重建列为 `vector(n)`;1024 仅在 openai_compatible + bge-m3 配置下生效。该句与附录 B.2 自己的表述("按运行配置确定维度的向量",L1557)也自相矛盾。
Evidence: backend/app/models/rag.py:114 `EmbeddingVector(512)`;backend/src/db.rs:174-200(读取 atttypmod,不匹配即 DROP 列并按 `configured_dim` 重建 + 重建 HNSW);backend/src/config.rs:138(默认 512)、362-379(512 仅 hash 后端、1024 仅 openai_compatible 合法校验)。
Recommendation: 5.2.1 改为"向量列维度按启动配置对齐(生产目标 bge-m3/1024,开发默认 512 哈希替身)",与附录 B.2 口径统一。
Confidence: High

### ISSUE-011
Severity: Minor
Priority: P2
Location: 5.2.3(L775)、7.7(L1432)、7.9(L1456)、8.4(L1496)
Category: technical/fact-error(修订遗留重复文本)
Problem: 四处出现紧跟重复的整句/整段(修订合并残留):L775 "式(5-2)不是当前 Rust 默认实现……为准。"连续出现两次;L1432 "生成正文的真实片段摘录见第六章 6.4 节。"连续两次;L1456 "此外,式(5-3)的评分系数(含权重最大的角色命中项 4.0 分)尚未消融……维度。"连续两次;L1496 "应由未接触模型回答的人员先冻结问题……再至少比较"整句内重复一次。重复的技术断言会干扰审读并显得未定稿。
Evidence: 上述行号原文比对(同句紧邻重复)。
Recommendation: 逐处删除重复句;建议对全文做一次"紧邻重复行"自动扫描。
Confidence: High

## 已核实无误的主要声称(抽样列举,供其他评审参考)

- 表 5-5 / 附录 C 的 12 个工具名、风险级、需确认、幂等键、scope 与审计动作逐格一致(mcp.rs:550-700)。
- 六类任务模板注册与"四类已验证、两类未验证"状态(mcp.rs prompt_definitions;models.rs/agents.rs)。
- 提示版本串:`rag-v9-source-and-graph-citations`/`rag-v10-history`(api/rag/mod.rs:1989)、`agent-v10-evidence-ledger`(api/agents.rs:34)、`agent-orchestrator-v1`(api/agent_runtime.rs:30、db.rs:313)。
- RRF/多样性/最低分阈值/top-6/候选 30/分块 700/120、集合型查询资料 top-12 与图谱 ≥30(config.rs:141-150;retrieval.rs:288-296;api/rag/mod.rs:700)。
- 审核门禁:草稿/退回不入图,APPROVED 自动抽取(conf 1.0/0.7,knowledge_graph.rs:122/155/183/221/260;notes.rs:442/762 "auto_extract_note_kg")。
- 笔记六态流转与 `note_versions`/`note_approvals`(app/models/note.py:11-16)。
- `agent_pending_actions` 唯一 (user_id,tool_name,idempotency_key)、`tool_execution_keys` 同主键(db.rs:372-400)。
- DeepSeek 接入与重试(ai_provider.rs:150/195-267/525-526;Retry-After/1s/2s/上限 30s;408|425|429|500..=599)。
- OCR 管线 pdftotext(Poppler)+ tesseract(ocr.rs:149/226);嵌入 hash 替身(embedding.rs:52-54/157-167)。
- `require_admin` 仅 super_admin(auth.rs:219-227);`require_external_ai` 敏感闸门默认关闭(config.rs:539-541 测试;permissions.rs:76-95)。
- 证据工件存在:`docs/experiments/`(rag-experiment-4 系列、kg-relation-gold-audit-53/after-fix、ablation-2026-08-26)、`docs/system-evidence/`(ready-revision-bound-2026-08-21T02:40:49Z.json 内容含 revision `93790d62…`;embedding-bge-m3-1024-latest.json 含 bge-m3/1024 配置;validation-results.json、local-health-latest.json);`scripts/validate_gse111619.py`、`backend/sql/0001_initial.sql` 均存在;Rust/Python 共享安全向量文件(backend/tests/security_vectors.json,security.rs:286-290 include_str)。

## 需要人工/外部资料核验的清单

1. 生产部署当前 `EMBEDDING_DIMENSION`/`EMBEDDING_BACKEND` 实际取值:证据文件显示 2026-08-21 冒烟为 openai_compatible+bge-m3/1024,但当前运行实例是否仍为该配置需人工确认(论文 2.5/4.1/7.1 的"生产目标 bge-m3 1024"以该冒烟为据)。
2. 实验 4/5 工件数值与论文表格的逐项一致性(日志 446-485 的 40 条回答、TP=52/FP=1/FN=0、表 7-8/7-10/7-12/7-13 各统计量、语料哈希 `3b47b59c…`):工件文件存在且命名吻合,但本轮未逐条打开 CSV/JSON 复算,建议人工或脚本复算一轮。
3. "105 个 Python 用例"的统计口径与时点(当前仓库 343 个测试函数):需作者说明 105 对应哪个 commit/收集条件,或按最新运行结果更新(ISSUE-006)。
4. 附录 D 三个 GSE111619 文件的 SHA-256 是否与 `scripts/validate_gse111619.py` 复算结果一致(本轮未执行校验脚本)。
5. `group_projects` 表在实际数据库实例中是否仍以 legacy 形式存在,以及论文是否应继续把它列为业务状态域表(仓库内无定义,仅 Rust 启动签名检查与 Alembic 保留清单引用,见 ISSUE-002)。
6. 7.2 声称的浏览器走查 8 场景内容与 `docs/system-evidence/validation-results.json` 内部字段(场景名、耗时 107s、2026-08-10 快照)的逐项对应,需人工打开 JSON 比对(本轮仅验证文件存在)。
