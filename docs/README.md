# 文档导航（docs/）——先读我

> 维护约定：**新增或移动任何 `docs/` 下的 md，必须在本文档登记一行**；文档的生命周期状态写在每篇文档首行的 `status:` 标记里（见第四节）。
> 最后核对：2026-09-08（对应 HEAD `a240c75`，scripts 分域重构 + 文档导航建立）。

## 一、当前真相（只看这一层就够）

需要了解项目现状时，按顺序读：

1. **[项目进展与论文核心思路-2026-09-05.md](项目进展与论文核心思路-2026-09-05.md)** —— 一页式全景（数字截至 09-05，09-06 起的创新点四件套增量未含）
2. **[创新点开发总览.md](innovation/创新点开发总览.md)** —— 三贡献体系（①动态图谱建模更新 ②图谱/证据约束的科研辅助工作流 ③导师监督的语义可视化反馈；学生画像仅展望）
3. **[innovation-supplement-2026-09-08.md](experiments/innovation-supplement-2026-09-08.md)** —— 创新点零调用补证批次（②-D D1 指标重算/②-C C1 追溯命中率/①-A 增量留痕/①-B 引用绑定表 + 阈值单位缺陷发现）
4. **[补证素材论文挂接表-2026-09-08.md](innovation/补证素材论文挂接表-2026-09-08.md)** —— 补证数字→主稿章节候选落点+口径红线（文字线取材入口）
4. **[并线协作状态.md](并线协作状态.md)** —— 多 Agent 开工必读/收工必更新（窗口、任务队列、增量日志）
5. **[任务台账.md](任务台账.md)** —— 全部工作包的登记与状态（复盘入口）
6. 仓库根 [README.md](../README.md)（系统使用）与 [AGENTS.md](../AGENTS.md)（协作规则）

> 归档的历史交付物：导师审阅材料包（2026-06-13 冻结）已移入 archive/advisor-package-2026-06/。
> 历史全景快照：[项目梳理-2026-08-29.md](项目梳理-2026-08-29.md)（08-29 时点的资产地图与遗留清单，**数字已过期**，以 09-05 版为准）。
> 注：09-06 ~ 09-08 的创新点开发与 scripts 分域重构尚未纳入任何全景文档，以 git log 与任务台账为准。

## 二、分区说明

| 目录 | 内容 | 读者 |
| --- | --- | --- |
| `innovation/` | 四个创新点机制文档 + 总览（证据等级、代码位置、回滚 tag） | 全体 |
| `experiments/` | **协议文档**（`*-protocol-v1.md`、预注册）与**带日期的运行结果**（`*-2026-*.md/json/csv`）混放；协议长期有效，运行结果是当时快照 | 证据线 |
| `system-evidence/` | 系统证据（schema、验证汇总、门禁 JSON）；多为脚本生成 | 证据线/QA |
| `operations/` | 运维手册（备份恢复、密钥轮换、发布整改）+ 2 份已收官的计划文档 | 运维/接手人 |
| `coordination/` | 三端协调（ZC/AG/DS 轮次报告、HANDOFF 锚点）；**唯一写者：ZCode**；`handoff/` 子目录存跨会话交接包 | 全体 |
| `testing/` | 用户验收测试计划与观察表模板 | QA |
| `user-guide-assets/` | 使用手册与论文截图素材 | 文字线 |
| `审核意见/` | 导师/盲审逐条回复对照表（06-12/13/15 三轮） | 文字线 |

## 三、路径迁移对照表（2026-09-08 scripts 分域重构）

09-08 `d669743`/`282ca34` 将 `backend/app` 重命名为 `backend/legacy/app`、`scripts/` 按功能域分目录。**2026-09-08 之前的文档/证据里出现的旧路径按此表解析，不要改历史文档本身**：

| 旧路径（2026-09-08 前） | 新路径 |
| --- | --- |
| `backend/app/…`（FastAPI 全部） | `backend/legacy/app/…` |
| `backend/tests/…` | `backend/legacy/tests/…` |
| `backend/migrations/…`、`backend/alembic.ini` | `backend/legacy/migrations/…`、`backend/legacy/alembic.ini` |
| `scripts/check_*.py`（config/backup/tls/secret/health/monitoring/reverse_proxy/long_soak/offsite/paper_material_freshness/rag_*） | `scripts/gates/…` |
| `scripts/*_maturity_gate.py`、`controlled_beta_gate.py`、`confirmatory_review_completion_gate.py` | `scripts/gates/…` |
| `scripts/freeze_*.py`、`export_*_evidence.py`、`capture_embedding_smoke.py` | `scripts/freeze/…` |
| `scripts/evaluate_*.py`、`validate_*.py`、实验类 `run_*.py`、`analyze_rag_experiment.py`、`ablate_score53_coefficients.py`、`rag_experiment_contract.py` | `scripts/experiments/…` |
| `scripts/import_gse*.py`、`prepare_*`、`populate_*.py` | `scripts/data/…` |
| `scripts/generate_*_chart.py`、`generate_thesis_diagrams.py`、`render_*.py`、`summarize_*.py`、`update_rag_evidence_openapi.py`、`verify_refs.py`、`revise_si_docx.py` | `scripts/render/…` |
| `scripts/audit_*.py` | `scripts/audit/…` |
| `scripts/load_smoke.py`、`soak_smoke.py`、`restore_drill.py`（旧位置写法，指这些文件本身） | `scripts/ops/…` |
| `evaluation-lab/` | `tools/evaluation-lab/` |
| `CONVERSATION_MIGRATIONS/` | `docs/coordination/handoff/` |

各域职责速查见 [../scripts/README.md](../scripts/README.md)。
**幽灵脚本**（文档提及但从未存在，历史记录不改）：`verify6.py`、`verify_runtime_schema.py`、`validate_question_sets.py`、`start-backend.sh`。

## 四、文档生命周期状态（每篇文档首行）

每篇文档首行加引用块标记：

- `status: current`（现在算数，改动需遵守域分区）/ `superseded`（已被取代，**保留原文勿删**，`superseded-by` 指向替代者）/ `draft`（未定稿）/ `historical`（当时快照；带日期的运行结果默认此态）/ `frozen-evidence`（哈希锁定，不可改）
- `superseded-by: <文件名>`（仅 superseded 时）
- `owner: <文字线|证据线|Codex|作者|工具生成>`

## 五、归档

- `archive/`（仓库根）：只进不改，分组原因见 [../archive/README.md](../archive/README.md)。
- 归档纪律：只用 `git mv`、零删除、`archive/README.md` 记一行原因。
- 工具留痕（不作事实来源）：`.qoder/repowiki/`（2026-07-23 自动生成，大量描述已废弃的 Python 后端，**勿引用**）；`test-results/`（08-03~07 黑盒测试报告）。
