# archive —— 归档区(只进不改,可整体恢复)

- 归档日期:2026-08-29,由证据线(ZCode)执行;全部使用 `git mv`(保留历史),**未删除任何文件**。
- 归档标准:已被后续版本取代、或所属工作阶段已结束超过一个月、或目标文件已不存在的工具链。
- 恢复方式:`git mv` 移回原位或按需复制;各分组用途见下表。

| 子目录 | 件数 | 内容 | 归档原因 |
| --- | --- | --- | --- |
| qoder-night/ | 5 | Qoder 夜间自主迭代协议文件(NIGHT_CONTEXT/LOG/BACKLOG/WORK_REPORT、AGENT-EVALUATION,08-12~13) | 协议期已结束,历史记录 |
| dev-logs/ | 8 | 开发日志(2026-06-05 ~ 2026-08-21,含深度优化记录、确认性证据推进记录) | 历史过程记录,文件名自带日期可检索 |
| thesis-versions/ | 9 | 论文旧版本(初稿 v1-v4、导师审阅版 docx/pdf、feedback_revision、AHNU-LaTeX PDF) | 已被 `docs/毕业论文重构稿.md` 取代;PDF 落后三轮修改 |
| reference-checks/ | 6 | 参考文献核验表×4、reference-audit.json、thesis_toc_pages.json | 初稿时代产物,核验结论已吸收进正稿 |
| advisor-snapshots/ | 9 | 导师反馈核查报告(07-03)、意见对照表(07-12)、对抗式自审、反馈修订对照表、成稿检查清单、图表清单、RAG 对照问题清单、相似项目调研、材料包 zip | 逐条意见已处理完毕;zip 与材料包目录内容重复 |
| design-superseded/ | 8 | 智能体协作设计、engineering-agent-organization、ai-inspection-protocol、ai/dify-rag-setup、开发启动说明、图片 OCR 评价设计、旧版项目梳理 | 早期设计/调研,已被后续实现取代 |
| audit-snapshots/ | 1 | 论文主张-证据状态矩阵(2026-08-13 快照) | 已被三轮优化与新证据(含 3 项安全性质测试)超越 |
| deprecated-scripts/ | 9 | 围绕旧初稿的参考文献核验 + md→docx 工具链(audit/check/prune/restore/expand_references、chapter_stats、check_thesis、chk、md_to_docx) | 目标文件 `docs/毕业论文初稿.md` 已归档 |
| rendered/ | 13MB | 旧版论文的评审页渲染图 | 基于过期版本,仅供参考 |
| advisor-package-2026-06/ | 18MB(21 文件) | 2026-06-13 交付导师的完整审阅材料包(意见对照表×3/参考文献核验×4/成稿清单/图表清单/旧版论文 docx·pdf/experiments·user-guide-assets 子集) | 6 月冻结的历史交付物,项目此后大改;凭证价值保留,活跃区不再维护(2026-09-08 迁入,git mv 保留历史) |

## 注意事项

- 若需对现行重构稿重新执行参考文献核验或转 docx:把 `deprecated-scripts/` 中对应脚本的输入路径改为 `docs/毕业论文重构稿.md`,移回 `scripts/` 并先在旧数据上验证输出。
- 2026-09-08 起新增 `advisor-package-2026-06/`(原 `docs/论文导师审阅材料包/` 目录版整体迁入,git mv 保留历史;与 `advisor-snapshots/论文导师审阅材料包.zip` 等价)。
- `data/real/`(129MB 数据集)与 `agent-work/` 实验工作区(44MB DRAFT)不属于本归档,保持本地不入库。
