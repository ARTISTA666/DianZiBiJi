> status: frozen-evidence
> owner: Codex（T143最终小型文档证据归档）

# T143 时间说明精简证据导航

本目录只保存本轮文字差异、最终文档身份和只读审查文本。论文以T142桌面Word为基线另存，最终Word `d6cd81c1f183e6828c8b382e8b9e0022e5eec724b4b44c5692f3197275bef0dd`，原生100页PDF `a615a43d0a5b6f2e80974201d464c4d818cd152b5776289a5ea0518bf9aa279a`。大文件、PDF、图片与原始材料仅本地保存。执行及独立内部复核完成，作者/导师验收待定；具体范围见[主记录](../论文具体时间说明精简-T143-2026-10-11.md)。

- [最终证据清单](final-evidence-manifest.json)：本目录所有小型材料SHA及最终交付身份；清单不哈希自身。
- [45段变更](changes.json)、[逐处差异](paragraph-revisions.diff)、[日期检索记录](time-scan.json)：删除范围可逐段审计，检索结果不等于全部应删除。
- [独立最终内容审查](reviewer/final-45-content-review.json)、[QA逐段时间范围审查](qa/content-date-scope-candidate-d6cd-review.json)：批次身份、必要指标和来源语义保持。
- [Word保护审查](qa/word-candidate-d6cd-protection-review.json)、[只读基线](qa/baseline-protection-e57b.json)：精确45段白名单、反向还原完整XML、引文/公式/图表/附录保护。
- [原生导出](native-final-export.json)、[实际目录核查](qa/toc-native-final-d6cd-a615-review.json)、[PDF引文几何](pdf-citation-geometry-final.json)、[引文检查器](check_pdf_citations.py)：WPS完整100页输出、批注关闭、实际字形与基线验证。
- [实际横线坐标](qa/table-rules-native-final-d6cd-a615-coordinate-review.json)、[表格文本定位](qa/table-same-page-native-final-d6cd-a615-text-review.json)、[98表最终闭合](qa/table-same-page-native-final-d6cd-a615-closure.json)：97表文本完整同页，表6-4以本轮57页实际视图补充公式下标抽取歧义。
- [100页PNG清单](native-final-page-manifest.json)、[16变化/84相同页像素对照](native-final-pixel-comparison.json)、[QA实看9变化页和57页](qa/native-final-d6cd-a615-visual-qa-pages.json)、[backend实看7变化页](backend/native-final-d6cd-a615-visual-7-pages.json)、[主审增补实看](root-supplementary-visual-review.json)、[QA视觉输入校验](qa/visual-input-native-final-d6cd-a615.json)：本轮16变化页全部原尺寸实看，84个相同PNG承接[T142最终前33页](../thesis-format-T142-2026-10-11/backend/native-final-e57b-visual-1-33.json)、[中34页](../thesis-format-T142-2026-10-11/figures/native-final-e57b-visual-34-67.json)、[末33页](../thesis-format-T142-2026-10-11/qa/native-final-e57b-visual-68-100.json)。不把旧页伪写成本轮重新观看。
- [100页视觉最终闭合](qa/native-final-d6cd-a615-visual-100-closure.json)、[最终QA汇总](qa/qa-native-final-d6cd-a615-summary.json)、[最终QA路径/SHA清单](qa/final-report-map-d6cd-a615.json)：只采用d6cd/a615最终身份，16变化页本轮实看与84页相同SHA承接闭合，无待修问题。
- [53项保护基线](qa/protected-input-baseline.json)、[主审最终校验](protected-inputs-root-final-review.json)、[QA最终校验](qa/protected-inputs-native-final-d6cd-a615-review.json)、[桌面副本校验](desktop-delivery-verification.json)：主稿、T142原Word/PDF和50件旧归档均未改。
- [37段候选变更快照](snapshots/changes-37-paragraphs-b91.json)、[37段候选审查快照](snapshots/reviewer-date-time-scan-and-candidate-review-b91.json)：早期候选漏删8处E2E整场耗时，随后补删；仅历史材料，不替代最终45段审查。

归档内检查器保留实际运行时的本地相对输入路径；要复跑，使用`agent-work/t143-2026-10-11/`中的原运行副本，或显式指向本地最终Word/PDF与T142引用清单。此目录不是重新运行软件测试或实验的证据。
