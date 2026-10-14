> status: frozen-evidence
> owner: Codex（T142独立Word修订与三专家复核）

# T142 精简、引文角标与格式证据导航

本目录保存2026-10-11本轮小型文本证据。对应[修订记录](../论文精简与引文角标复核-T142-2026-10-11.md)。Word、PDF、页面PNG和前三轮候选实物保留本地，不纳入Git；本目录不替代作者/导师验收。

最终Word SHA：`e57b430f9b545319e5346a3935258d0d4afd263955995403c213c0049af5ce69`；最终原生PDF SHA：`6d54f973fee931127b45f3a8da18dca8e4a82ce3a842684f841e8be0ccb14410`，100页A4。最终页面清单SHA：`f998bdad2ab8e7375a226ab5d791bd324ba7fd960e0f8e8ac5e0581e383b258d`。

| 证据 | 内容 |
| --- | --- |
| [逐处精简](accepted-shortening.json)、[可读差异](paragraph-revisions.diff)、[全部修改](changes.json) | 36处语言改写、减324字符、73组上标、12段行距、50表缩进；每项有基线和修订值。 |
| [生成脚本](build_paper.py) | 以T141独立桌面原件构建新版，检查段落身份、数字与引用文字，保持批注精确锚点；脚本为本轮执行快照，不是生产后端。 |
| [Word保护复核](qa/word-protective-aligned-e57b-review.json) | 17组独立检查，含48公式、85参考、16批注、图像、完整附录与50项精确缩进白名单。 |
| [原生导出](native-final-export.json)、[桌面副本](desktop-delivery-verification.json) | WPS最终100页、批注输出0及原件与交付副本字节一致。 |
| [目录](qa/toc-native-final-e57b-6d54-review.json) | 100条目录缓存与原生实际印刷页码一致。 |
| [三线表及实际版心](qa/table-rules-native-final-e57b-6d54-coordinate-review.json)、[补充宽横线检查](pdf-horizontal-edge-final-probe.json) | 98张数据表三线结构及实际PDF横线坐标；50表修正后无越界。 |
| [表格同页文本](qa/table-same-page-native-final-e57b-6d54-text-review.json)、[98表同页闭合](qa/table-same-page-native-final-e57b-6d54-closure.json) | 97表文本定位同页；表6-4下标抽取歧义经第57页原尺寸视觉核验，10个公式及题注、表头、表身均在同页，98表全部闭合。 |
| [上标实际字形](pdf-citation-geometry-final.json)、[检查脚本](check_pdf_citations.py) | 73组方括号与数字整组上标，85书目标签正常基线；逐组实际字号、字体、基线偏移与引用身份核验。 |
| [最终100页清单](native-final-page-manifest.json)、[与去批注候选的像素对照](native-final-pixel-comparison.json) | 16页有水平表格位置变化：23、56、81–93、100；其余84页PNG逐字节一致，可承接本轮已实际查看的原尺寸视觉结论。 |
| [1–33页](backend/native-final-e57b-visual-1-33.json)、[34–67页](figures/native-final-e57b-visual-34-67.json)、[68–100页](qa/native-final-e57b-visual-68-100.json) | 三专家最终身份复验：16页最终原尺寸实视，84页按独立PNG SHA相同承接本轮实际视觉检查；完整100页覆盖。 |
| [主审补充实视](root-final-supplementary-visual-review.json) | 最终56、95、100页补充核验，不冒充主审独立查看全100页。 |
| [保护输入清单](protected-input-hashes.json)、[收工复算](protected-inputs-final-review.json)、[独立输入复核](qa/protected-inputs-native-final-e57b-6d54-review.json) | 主Markdown、桌面T141原Word/PDF和54件T141归档材料，共57项SHA保持；T141既有65项测试源输入亦保持。 |
| [内容边界](qa/content-boundary-native-final-e57b-6d54-review.json)、[格式复核](qa/format-native-final-e57b-6d54-review.json)、[原生Word保护](qa/word-protective-native-final-e57b-6d54-review.json) | 精简不改变数字、方法、引文身份及附录；字体、行距、三线表、标点及标题层级按既有要求复核。 |
| [最终QA闭合](qa/qa-native-final-e57b-6d54-summary.json)、[报告身份映射](qa/final-report-map-e57b-6d54.json) | 最终Word/PDF/页面清单身份绑定，内部检查通过，无待修阻塞。 |

`snapshots/`保留历史导出和阻塞记录：首版带批注标记，去批注版仍有表格水平偏移，31表修正版本又遗漏19张附录表。最终50表修正版本完成实际边界核验；不得把前三版的页数通过解释为交付格式全部通过。旧报告中的原本路径是当时快照，实物移入本地相应历史目录，身份以SHA为准。旧快照正文不回改。

本轮只修论文语言与格式，未改当前运行时代码、未执行新测试或重跑实验。第六章正文、数值与方法边界保持；T141既有测试结果为历史来源，不能改称T142新验证。

[最终证据清单](final-evidence-manifest.json)登记本目录文件SHA、字节数、最终交付身份与视觉覆盖。执行及内部复核已完成；作者/导师验收待定。
