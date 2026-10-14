> status: current
> owner: Codex证据线（T150）

# T150盲审整改审查归档

主入口为[逐项清单](../盲审报告逐项整改与未闭环清单-T150-2026-10-14.md)。本目录保存修改、复算与保护记录；自动复核不是作者、领域人类专家或导师验收。

| 入口 | 内容 |
| --- | --- |
| [证据索引](evidence/README.md) | 导师核验包、六提交／三仓身份、便携复算、敏感排除及14项缺口 |
| [修改记录](review/revision-audit.json) | 原稿／Word SHA、逐处文本、元数据及五图遮挡 |
| [文献核查](review/bibliography-corrections.json) | 九官方条目、八修改、两字段待查 |
| [截图复核](qa/word-screenshot-redaction-independent-review.json) | 实际查阅、坐标及像素保护 |
| [最终结构核验](qa/word-ooxml-final-independent-review.json) | 公式、表格、实验值、引文、身份页、关系及媒体 |
| [最终语义审查](review/final-readonly-semantic-review.json) | 76目录缓存、五PNG及原有修订保护 |
| [最终渲染比较](review/final-render-comparison.json) | 101页，96页像素一致承接；五变化页实视 |
| [1—35页](review/root-visual-review-pages1-35.json) | 根线程基线原尺寸逐页审查 |
| [36—70页](qa/word-visual-review-pages36-70.json) | QA基线原尺寸逐页审查 |
| [71—101页](review/render-pages-71-101-visual-review.json) | 审稿线程基线原尺寸逐页审查 |
| [31页最终继承](review/render-pages-71-101-final-inheritance.json) | 最终版逐页RGB相同核对 |
| [最终目录实视](review/final-toc-visual-review.json) | 修改后6／7两页实际审查 |
| [目录映射](qa/word-toc-cache-replacements.json) | 100项目录，76缓存修正；WPS刷新另列 |
| [QA总记录](qa/qa-summary.json) | 关系、性能、词法RAG、安全范围与缺口 |
| [最终清单](final-evidence-manifest.json) | 交付身份、执行／验收状态和归档校验 |

视觉检查由AI实际查看页图完成，不冒充人类验收。基线Word ebe61a10…、PDF f47ee881…；最终Word9035845e…、内部PDF86808671…。原稿既往原生WPS100页，当前字体完整LibreOffice101页，不能混称同一排版结果。正式打印检查和学院细则待完成。

证据包含内部来源／身份信息，不能直接作为匿名盲审附件；完整历史bundle未完成发布审查，只受控本地保存。PDF和PNG供内部核验，论文仅交付Word。源码和历史实验未改。
