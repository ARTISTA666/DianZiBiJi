# RAG 实验 5 预注册修订：2026-08-16 五项目主比较扩展

> 状态：AGENT_DRAFT_AMENDMENT，待外部命题者签署后生效。
> 基础协议：`docs/experiments/rag-experiment-5-preregistration-rust-v2.md`。

## 1. 修订原因

原协议第 5.1 节按“最低 3 个项目”设计。2026-08-16 复核发现，前三批数据中：
- GSE111619 处理后语料与 GSE111619 原始语料来自同一 GEO 系列；
- Smithsonian Joseph Henry 语料为 19 世纪历史手稿。

为了让现代独立语料不少于 3 套并覆盖人、动物、植物三类场景，本修订在首个相关正式回答前新增两个公开 GEO 项目：
- GSE306433：小鼠结肠炎基质细胞 RNA-seq，6 样本；
- GSE291942：拟南芥高温胁迫 RNA-seq，18 样本。

## 2. 新增项目与冻结输入

| 项目 key | GEO | 项目内问题数 | seed | questions_sha256 | 语料冻结记录 |
|---|---|---|---|---|---|
| gse306433_colitis | GSE306433 | 20 | 2026081601 | `7cd09ff75fcb8938e7f27112b39d80bc6c5ff647ec5585b9785f197605e1343f` | `agent-work/freeze/gse306433_colitis-prerun-freeze-2026-08-16.json` |
| gse291942_arabidopsis_heat | GSE291942 | 20 | 2026081602 | `7b475ee89eccc6e4ddb330e131198438cd9c8a1f4bc7c81fc4a2d0088ce4f0c8` | `agent-work/freeze/gse291942_arabidopsis_heat-prerun-freeze-2026-08-16.json` |

新增题集文件：
- `agent-work/question-sets/gse306433_colitis_questions_v2_draft.json`
- `agent-work/question-sets/gse291942_arabidopsis_heat_questions_v2_draft.json`

两个题集均通过 `agent-work/scripts/validate_question_sets.py`；`setter_id` 仍为 `AGENT_DRAFT_2026-08-16`，必须由外部命题者复核签署。

## 3. 五项目运行身份

| 项目 key | run id | 状态 | v1 证据包 |
|---|---|---|---|
| gse111619 | 20 | completed | PASS |
| gse111619_raw | 21 | completed | PASS |
| smithsonian_joseph_henry | 23 | completed_with_errors（6 个 pure_llm 技术失败） | PASS |
| gse306433_colitis | 24 | completed_with_errors（2 个 kg_enhanced_rag 技术失败） | PASS |
| gse291942_arabidopsis_heat | 25 | completed | PASS |

历史 run 22 不追溯修复，由 run 23 替代。

## 4. 主比较人评规模

主比较仍固定为 `kg_enhanced_rag` vs `project_rag`：
- 预定案例：5 项目 × 20 题 × 2 方法 = 200；
- GSE306433 run 24 的 2 个 `kg_enhanced_rag` 技术失败按原协议第 7.2 节自动记 0 且不送人评；
- 实际送评：198 行/每名评审者；
- 准确性分母仍为全部 200 个预定案例，技术失败记 0。

## 5. 边界与未改变项

- 题集/金标准仍待外部命题者签署；
- 运行仍发生在 dirty worktree + `APP_REVISION=unversioned` 的开发环境，B0 未绑定；
- 自动事实覆盖率仍只是 alias-based 开发诊断，不是人工准确率；
- 不因项目数增加而改变“最低规模而非功效证明”的解释边界；
- 原协议第 5.1 节“其余三方法探索性人评子样本在 v3 修订中冻结”仍然未做，本修订不送探索性人评。
