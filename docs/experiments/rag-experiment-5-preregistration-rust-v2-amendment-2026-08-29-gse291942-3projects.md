# Exp5 Rust v2 amendment：独立 GSE291942 三项目迁移（agent draft）

> **状态：`AGENT_DRAFT_PENDING_EXTERNAL_SETTER` / `BLOCKED`**。本文件只记录机械迁移后的候选协议，不是正式 preregistration、结果或盲评授权。任何确认性运行必须等待外部 setter 签署和 B0–B9 闸门解除。

## 变更目的

将与 `gse111619` 属于同一 GEO 系列的 `gse111619_raw` 从原三项目设计移除，替换为独立的 `gse291942_arabidopsis_heat`（GSE291942，Arabidopsis heat）。这保留三项目/每项目 20 题/五模式的设计形状，避免把同一项目的处理变体当成独立项目层观察。

若第三项目保留 `smithsonian_joseph_henry`，新设计包含两个现代 GEO 项目和一个历史集合；不得沿用五项目 amendment 的“≥3 个现代数据集”表述。若研究负责人希望三种现代物种项目，则必须另行确认保留 `gse306433_colitis`，那将不是本三项目 bundle。

## 候选设计（尚未冻结）

| 项目 | 题集 | 题数 | 当前状态 |
|---|---|---:|---|
| `gse111619` | `agent-work/question-sets/gse111619_questions_v2_draft.json` | 20 | `AGENT_DRAFT_PENDING_EXTERNAL_SETTER` |
| `gse291942_arabidopsis_heat` | `agent-work/question-sets/gse291942_arabidopsis_heat_questions_v2_draft.json` | 20 | `AGENT_DRAFT_PENDING_EXTERNAL_SETTER` |
| `smithsonian_joseph_henry` | `agent-work/question-sets/smithsonian_joseph_henry_questions_v2_draft.json` | 20 | `AGENT_DRAFT_PENDING_EXTERNAL_SETTER` |

候选 qset 当前 hash、题数和 draft gold 状态见同目录的 `question-set-manifest.json`、`questions.json`、`gold-facts.json`。这些文件保留 `AGENT_DRAFT_2026-08-29` 与空的外部 setter 字段；不得把它们解释为已签署 gold。

方法仍为 `pure_llm`、`bm25_rag`、`project_rag`、`structured_query`、`kg_enhanced_rag`；每项目一次重复、随机化顺序；主估计为 `kg_enhanced_rag - project_rag` 的题目级配对准确率差，项目分层且项目等权 bootstrap。技术失败继续按 v2 protocol 7.2 进入规定分母。

## GSE291942 真实材料绑定

真实输入路径和当前 SHA-256 见 `agent-work/freeze/rag-experiment-5-rust-v2-gse291942-3projects-2026-08-29/corpus-manifest.json`。该 manifest 明确记录：

- `generated_manifest.json` 由现有生成器生成，生成器已排除自身条目，避免数学上不可能的全文件自包含 hash；修复后当前实际 hash 为 `bc6502fa...`；
- 2026-08-16 pre-run corpus snapshot `c94e7879...` 与 run25 runtime snapshot `b6d87575...` 不一致；
- run25 没有 runtime `graph_snapshot_hash`。

所以 run25 只登记为 `DEVELOPMENT_ONLY` 的 100/100 试跑，不能进入本 amendment 的正式分母、统计、附录或论文结论。新的正式运行必须重新绑定 corpus/graph snapshot、索引、模型、prompt、revision 和镜像 digest。

## 外部闸门

1. 外部 setter 独立审阅三项目全部题目、gold facts、reference answers、support docs、forbidden facts 和 refusal 标准，并提供真实 setter ID、authority、时间戳及“未预先查看模型答案”声明。
2. 研究负责人确认三项目边界；不得把本三项目结果描述为五项目或三个现代 GEO 项目。
3. B0 clean revision/`APP_REVISION`、运行时/模型/嵌入/prompt、corpus/graph snapshot 全部可复核后，才允许 formal run。
4. 两名独立方法盲 reviewer 完成 primary modes 的评分；当前 draft、旧 run23、run25 或既有 blind-review 包均不构成盲评结果。

## 版本化产物

本 amendment 配套目录：

`agent-work/freeze/rag-experiment-5-rust-v2-gse291942-3projects-2026-08-29/`

其中包含候选 questions/gold、run/analysis config、question/corpus manifest、freeze manifest 和结果目录映射。旧三项目 freeze、五项目 amendment、旧 raw run 目录和 run25 均保持原样。
