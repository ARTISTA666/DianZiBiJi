# 论文主张—系统版本—实验工件—证据状态矩阵

> 盘点日期：2026-08-13（Asia/Shanghai）  
> 用途：把论文中的主张、产生主张的系统运行时、实验工件身份和当前证据门禁绑定起来。本文档不把推断升级为事实，也不把内部开发批次写成确认性实验。

## 状态定义

| 状态 | 含义 |
| --- | --- |
| `VERIFIED` | 可由仓库文件、运行时快照、版本历史或可复算哈希直接核对。 |
| `INFERRED` | 有多份间接证据支持，但缺少直接绑定；论文中必须使用限定语。 |
| `UNKNOWN` | 当前工件没有足够信息确认；不得补写为具体事实。 |
| `BLOCKED` | 该主张进入确认性论文结论仍被门禁阻塞；不是“暂未检查”。 |

## 实验工件矩阵

| 主张/范围 | 系统版本与运行时 | 实验工件身份与参数 | 证据文件 SHA-256 / 时间 | 版本绑定与状态 | 论文允许写法 |
| --- | --- | --- | --- | --- | --- |
| 实验 4：普通 RAG 与图谱增强 RAG 的单项目成对批次 | 2026-06-11，发生在 Rust 生产迁移 commit `6a119d6d4a1d3c4e695b6f8bc8602b752cfdd3c0`（2026-07-30）之前。历史材料与时间线支持其属于迁移前 legacy FastAPI 原型，**但运行 JSON 未直接记录运行时名称**。 | `docs/experiments/rag-experiment-4-run.json`；20 题 × 2 方法 = 40 条 CSV 行；方法 `project_rag`、`kg_enhanced_rag`；DeepSeek / `deepseek-v4-flash`；嵌入 `BAAI/bge-small-zh-v1.5`，512 维；prompt `rag-v3-local-hybrid-kg-citations`；chunk 700 / overlap 120 / top-k 6 / vector candidate 30 / graph top-k 10 / min score 1.0；语料哈希 `3b47b59c7f9aa34c70fd8f5b86d35e3bc65a18e7b3439e2e632b8c8d747e5c51`。CSV 逐条分数字段可反算 `retrieval_score=0.8v+0.2l`，但 config snapshot 未显式冻结该权重。 | CSV `09f7bf7fdeb9d7199b5c21b44d905a810cbfec3f8366cbb97cad701e50442392`；run JSON `d44b4851ec80cdd9e3eb3ecb9f90d6e6cfebb471f50f2c884c51c123a8d84ca9`；分析 `5f39f91c8cf6da49a807c5cf2ea953b98744530dcf6594e220692882811d2589`。创建 `2026-06-11T16:11:16.896001Z`；完成 `2026-06-11T16:12:45.903211Z`。 | 批次参数、题数、行数和哈希 `VERIFIED`；0.8/0.2 历史行为 `INFERRED`；历史 FastAPI 原型归属 `INFERRED`；精确应用 commit `UNKNOWN`；按确认性结论使用 `BLOCKED`（事后规则、单项目、无独立盲评）。 | “实验 4 是迁移前 legacy FastAPI 原型上的历史单项目成对批次；CSV 分数支持 0.8/0.2 的 `INFERRED` 历史融合行为，但它不能代表当前 Rust 系统，也不构成独立人工准确率证据。” |
| 实验 5：内部探索性五方法批次 | 2026-07-13，发生在 Rust 生产迁移 commit `6a119d6d4a1d3c4e695b6f8bc8602b752cfdd3c0`（2026-07-30）**之前**；工件 `app_revision=unversioned`，不能绑定到当前 HEAD 或某个固定生产版本；历史 report/配置仍以 `BAAI/bge-small-zh-v1.5` 记录，故不能据时间推断为 Rust 运行。与历史材料和配置连续性相符的 legacy FastAPI 归属为 `INFERRED`，不是直接运行时证明。 | `data/real/experiment-5/internal-five-mode-experiment-report.json`；单项目 `project_id=3`；12 题 × 5 方法 × 3 重复 = 180 行；方法 `pure_llm`、`bm25_rag`、`project_rag`、`structured_query`、`kg_enhanced_rag`；seed `20260713`；DeepSeek / `deepseek-v4-flash` / temperature 0.1 / max tokens 1800；嵌入 `BAAI/bge-small-zh-v1.5`，512 维；语料哈希 `2b6b174ed671f3dd20774341c0a88accb8544cfeb04ff0270487ac7a5fb610f9`；题集哈希 `ca3b868748e4771460973a3a2923a829c2397ff90fceb08062b643054e9cd889`；执行计划哈希 `d750782a3cdf7794a8ed1621376c68a16322bb2a54ae5cadaa11d74a7a2fadaa`。 | run-config `0bbc5aafd2c98a7a40a1eac546fb60b728c09b339cb3f5b2d49fff71ddce1c6a`；report `02f877d06de4a57c722f8f52555cbe78e771378745a371e52f0f51545cb842ca`；validation `81f686bf212d1fe30046518d332512a38de22e5de7707c7730443a9cf4653256`；bundle audit `f255a0911a1533d3f183f6b3c804f7f39f5d403743da903764e15d474b27684c`；freeze manifest `2f5f6445fdb995900b24fb19f821716a09057d6e39b153aca9303bce4f6b90a0`。报告生成 `2026-07-13T10:57:51.100870+00:00`；审计生成 `2026-08-13T00:48:15.830198+00:00`。 | 12×5×3、单项目、参数、哈希和 `paper_ready=false` `VERIFIED`；历史 FastAPI 归属 `INFERRED`；`app_revision=unversioned`、逐案例 retrieval binding 缺口 `VERIFIED/UNKNOWN`；外部冻结题集、多项目题集、独立人工盲评和确认性 evidence package `BLOCKED`。 | “实验 5 是单项目 12 题 × 5 方法 × 3 重复的内部探索性开发批次，结果用于描述性和机制诊断，不报告为跨项目或确认性性能结论。” |

## 当前实现/运行时矩阵

| 主张 | 证据与身份 | 状态 | 限定 |
| --- | --- | --- | --- |
| 当前实现代码路径为 Rust 1.88 + Axum，数据库访问由 SQLx 完成 | `README.md`；`backend/rust-toolchain.toml`；`backend/Dockerfile`；`backend/src/api/mod.rs`；`backend/src/permissions.rs`；`backend/src/db.rs`；`backend/sql/0001_initial.sql`。 | `VERIFIED` | 当前仓库 HEAD 为 `89354a9ea09829ade69461aaecb6fce6de287529`；工作树 dirty，不能把 HEAD 单独当作当前实现身份或可复现实验发布版本。 |
| 当前工作区运行时证据可证明 Rust/Axum 对外运行 | `docs/system-evidence/rust-runtime-contract-latest.json` 捕获于 `2026-08-10T12:03:26.888612+00:00`；`docs/system-evidence/local-health-latest.json` 生成于 `2026-08-10T13:04:16.996876+00:00`；均记录 `api_runtime=rust-axum`、`revision=unversioned`。 | `VERIFIED`（运行时类型） / `UNKNOWN`（固定发布身份） | 这批运行时证据不能绑定某个 commit；论文应写“验收环境运行时证据”，不能写成固定版本实验。 |
| 嵌入边界：已核验运行时为 development + `rust-hash-512-v1` 512 维；生产配置约束/目标为 OpenAI-compatible `BAAI/bge-m3` 1024 维 | `README.md`；`backend/src/config.rs` 的 embedding 校验；`docs/system-evidence/local-health-latest.json` 实际记录当前快照为 hash 512 维、`app_revision=unversioned`。 | `VERIFIED`（配置边界与当前快照） / `BLOCKED`（尚无 bge-m3 版本绑定运行证据） | `bge-m3` 是生产配置约束/目标；不能把开发 hash 快照写成论文实验 embedding，也不能声称当前捕获快照已经运行 bge-m3。 |
| 当前系统可作为确认性实验运行版本 | 当前 HEAD dirty，运行证据 `app_revision=unversioned`，实验门禁 `paper_ready=false`。 | `BLOCKED` | 需要 clean/fixed revision、真实外部冻结输入、独立人工盲评和确认性 evidence package；本轮不生成新的确认性结果。 |

### 当前方法文件指纹（HEAD + dirty worktree）

`HEAD=89354a9ea09829ade69461aaecb6fce6de287529` 仅是基线提交；以下方法与运行时相关文件在工作树中存在未提交修改，因此“当前实现”可定位但尚不能登记为稳定 revision。哈希为本轮复算值。

| 文件 | 作用 | SHA-256 | 状态 |
| --- | --- | --- | --- |
| `backend/src/rag.rs` | RRF/legacy-weighted 检索融合实现 | `18145407330730dbf35d07c01f76d2c72f8c7dd10604f0f63ea6e0e54d7651c3` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |
| `backend/src/config.rs` | `rrf-v1` 默认值与 embedding 配置校验 | `120896840c0363ca5a66a3d327165c656584b82ad92f0e1ab30f128e30e9515a` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |
| `backend/src/api/rag.rs` | retrieval snapshot 与 API 证据出口 | `460e3955e1dc01c6df0bf7334814251dd65185263ba3a53996071c66ab18602e` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |
| `backend/src/permissions.rs` | 权限边界实现 | `d4a75c878c34fd13423ad04b28e1d12eb3ea1f8a6536adc31860daeda4b5630c` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |
| `backend/src/api/mod.rs` | Axum 路由与 handler 组织 | `6fb82ed35dded42d0eddcf20b2b34bace0e1435a427df27f237cec5f391d43dc` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |
| `backend/Dockerfile` | 生产 Rust 镜像构建路径 | `d2b4e08dce63a03e8515740ba5d29107e1ab58bf615a06895686548f0829a38d` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |
| `backend/sql/0001_initial.sql` | SQLx/PostgreSQL 初始 schema | `8f2c23cc046abd487d8459559c7ef4a41acf82dc1d2000468adc8d903458b122` | `VERIFIED` 文件指纹 / `BLOCKED` 稳定版本 |

## 论文源文件与版本分叉

| 文件 | 角色判断 | SHA-256（2026-08-13 复算） | 状态与动作 |
| --- | --- | --- | --- |
| `docs/毕业论文初稿.md` | 内容最完整的当前 Markdown 主稿候选（权威性由仓库结构推断，尚未有单独 manifest） | `d06a15f11d868fb7458da2ef11705788697b9034d23941b553ae90457a899b1b` | `INFERRED`；本轮已校准，作为后续继续修订的首选候选。 |
| `docs/论文导师审阅材料包/毕业论文初稿.md` | 材料包内同源但有内容分叉的 Markdown 副本 | `2aecd5628dc52538633b969d05076562aa731d09f279e0fca416f97eab2176cb` | `INFERRED`；本轮同步同一运行时边界，但仍不是由 manifest 证明的唯一权威源。 |
| `docs/毕业论文_导师审阅版.docx` | Word 派生审阅件，存在手工排版/修改风险 | `ec3230d6fa05754f676d797bbf79b09d226352960c754904c51ea5fc417750c4` | `UNKNOWN/BLOCKED`；本轮未修改，待确认 Markdown 权威源后重新渲染并人工检查。 |
| `docs/毕业论文_导师审阅版.pdf` | PDF 派生审阅件 | `d5079595acd818cab58c641c54a0fadf2f1773cecb9e9d12d476cfea33df7ee0` | `UNKNOWN/BLOCKED`；本轮未修改，当前仍可能保留旧 FastAPI/FastEmbed 图文。 |
| `docs/论文导师审阅材料包/毕业论文_导师审阅版.docx`、`docs/论文导师审阅材料包/毕业论文_导师审阅版.pdf` | 材料包内审阅件分叉 | DOCX `f148364cfd01ac21a9f6c5b3b7717c1a7811b174604d58fd1d46930d897d1940`；PDF `d5079595acd818cab58c641c54a0fadf2f1773cecb9e9d12d476cfea33df7ee0` | `UNKNOWN/BLOCKED`；本轮不覆盖 Word 手工修改。 |

## 图 6-1 工件身份

| 工件 | 状态 | 说明 |
| --- | --- | --- |
| `scripts/generate_thesis_diagrams.py` → `architecture()` | `VERIFIED` | 现有确定性 SVG 生成源已改为 Rust + Axum；嵌入框区分“已核验 development/hash 512”“OpenAI-compatible bge-m3 目标”和“尚无版本绑定运行证据”。 |
| `docs/user-guide-assets/17-system-architecture.svg` | `VERIFIED` | SHA-256 `5a9f944efb3a4156a0565c3329a3720ee8753f965ab32135f31b92c54f9eca80`；与生成函数的语义内容一致。 |
| `docs/论文导师审阅材料包/user-guide-assets/17-system-architecture.svg` | `VERIFIED` | SHA-256 `2e2930319e8578779eb7707771753d796c823f537492a4696dd2952ffff445e2`；与主 SVG 的语义内容一致，字节差异仅为行尾格式（LF/CRLF）。 |
| `docs/user-guide-assets/17-system-architecture.png` | `BLOCKED` | SHA-256 `f9c34d2f5378843c4de72ada2180b6da25dffbce3e263ad7d1a43174852d5a6d`；这是旧派生 PNG。仓库没有可靠的 PNG 重生成调用链，本轮不截图伪造，待确定渲染流程后更新并同步 Word/PDF。 |

## 当前论文门禁结论

截至 bundle audit `2026-08-13T00:48:15.830198+00:00`，`paper_ready=false`。阻塞项为：`app_revision_is_bound`、`external_freeze_inputs_present`、`multi_project_question_set_ready`、`independent_human_review_present`、`confirmatory_evidence_package_present`。因此当前实验可以支持历史批次的描述性/机制诊断主张和系统工程证据，不能支持确认性准确率、跨项目泛化或当前 Rust 固定版本优于其他方法的结论。
