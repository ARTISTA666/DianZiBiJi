> status: frozen-evidence
> owner: Codex

# T146摘要逐句精校证据归档

本目录保存2026-10-11开工、2026-10-12完成的摘要修订与内部复核快照。任务记录见[精校报告](../论文摘要逐句精校-T146-2026-10-11.md)，执行与内部检查通过，作者及导师验收待定。十个摘要段落之外的Word内容和格式保持，旧输入23项全部通过SHA复核。

交付文件为[桌面新版Word](/Users/yusong/Desktop/1005-摘要语句精校版-2026-10-11.docx)，SHA-256为`0b38c0df1cdcca0f0c2c017283c863fe219b02aa565b53888fe4b47dfbf2bae8`；基线T145 Word SHA-256为`b9336e8dfef93921f2ff4fc4291c4465c91facaa23b5040c6cc74005959438bf`。原生内部PDF为100页A4，SHA-256为`945b5d41ed367fe5d3006b7ab47e4c97aa2e9e390f1af9d9917ce5e93aa27415`。PDF、页面PNG及Word保留在本地`agent-work/t146-2026-10-11/`，大文件不入库。

- `changes.json`：十段摘要的原文和改文及文本变更身份。
- `english-final-0b38-check.json`及所引用的`english-final-ea02-check.json`：最终英文身份与语义核对，明确两份检查的继承范围。
- `candidate-final-0b38-abstract-protection-review.json`：最终Word28项保护检查。
- `protected-input-baseline.json`：开工旧输入清单。完整基线内容库存及早期只读审校原件保留在本地，其身份见`local-evidence-index.json`。
- `native-export.json`：标准质量原生PDF导出设置及最终Word/PDF身份。
- `native-final-0b38-945b-toc-review.json`：100条目录及100页分页验证。
- `native-page-comparison.json`、`source-native-visual-baseline.json`、`root-native-visual-review.json`及最终QA视觉记录：97页精确SHA承接，3页本轮实际原尺寸复核；38页为文字渲染差异，未改正文。
- `qa-final-0b38-945b-native-review.json`及`qa-final-report-map.json`：最终QA总评及所引用报告的身份；`native-final-0b38-945b-abstract-scope-parity-review.json`、`native-final-0b38-945b-visual-changed-pages-review.json`、`native-final-0b38-945b-page38-glyph-difference-review.json`、`native-final-0b38-945b-visual-100-closure-review.json`与`native-final-0b38-945b-protected-inputs-review.json`保存语义、实际视觉、字形差异、100页覆盖和23项旧输入复核。
- `desktop-delivery-check.json`：桌面交付副本与候选相同、T145桌面源保持。
- `final-evidence-manifest.json`：本目录所有快照的字节数与SHA、最终产物及只读输入身份。

通用渲染89页且中文字体缺失，只用于诊断；原生100页输出承担最终分页与版面验收。未将诊断分页当作交付页数，未把旧候选检查冒充最终检查。原件、旧归档、主Markdown及代码未修改，独立Word写窗释放。
