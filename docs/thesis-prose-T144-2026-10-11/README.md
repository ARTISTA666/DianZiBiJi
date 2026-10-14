> status: frozen-evidence
> owner: Codex

# T144 语言精校与批注、封面日期清理证据

本目录为本轮结束时的小型不可回改快照。新版为[桌面Word](/Users/yusong/Desktop/1005-表述精校无批注版-2026-10-11.docx)，SHA `4261c0cc08263ba5bb70e97fae444fb5998a5a206d83e2ceed6b57e8cec901dc`。内部WPS原生PDF SHA `b6ec3b5052a06540ba1fb9ef6b2c112ffd81805539bf67572394b1cfba6f484e`，100个A4物理页。大型Word/PDF/PNG留在本地agent-work，不进入本归档；用户交付格式仅Word。

- [最终逐段变更](final-changes.json)、[可读差异](paragraph-revisions.diff)：103处语言调整涉及78段、三处封面日期清空；另同步一个目录页码缓存。与当前作者源35e9接续，正文字符净增575（语言+609、日期-34）。
- [批注/日期清理清单](qa/comments-and-cover-removal-inventory-35e9.json)：16条批注、28标记，两批注包件与声明清除；模板样式保持。
- [初次语言修改](edits-manifest.json)、[目录缓存修复](toc-cache-repair.json)、[跨页引文修复](citation-break-repair.json)：完整保留df765→c4d4→4261的顺序与SHA，旧Word快照位于本地candidate-df765-before-toc-repair.docx及candidate-c4d4-before-citation-break-repair.docx。
- [最终Word保护](qa/candidate-4261-final-protection-review-v2.json)、[语言承接映射](qa/final-word-4261-review-map.json)：38项保护全通过，另103项上下文语言审阅和追加DPR改写均通过。48个公式的原数学结构保持；原公式内的批注引用属授权删除，原始哈希警报和仅归一该标记的修正版均保留。
- [原生目录](qa/native-final-4261-b6ec-toc-review.json)、[引文实际字形](qa/native-final-4261-b6ec-citation-geometry-review.json)、[横线坐标](qa/native-final-4261-b6ec-table-coordinate-review.json)、[表体文本定位](qa/native-final-4261-b6ec-table-same-page-review.json)：100目录、73整组上标、98严格三线表；公式表文本判定另以真实原尺寸视觉闭合。
- [100页视觉映射](native-final-visual-100-closure.json)、[最终页面清单](native-final-page-manifest.json)：43页继承与T143完全相同的已验PNG，57变化页本轮实视。最终13/14重新实视，55变化页与本轮初版已实视PNG同SHA；逐页明确来源，不冒称所有页本轮重新查看。
- [root最终实视](root-final-visual-review.json)包括三日期清空、目录和表6-4全表/10式，最终13/14的[56]归句末；backend和reviewer原尺寸报告分别保留在对应子目录。
- [独立QA总结](qa/qa-native-final-4261-b6ec-summary.json)、[精确报告映射](qa/qa-final-report-map.json)、[100页独立证据核对](qa/native-final-4261-b6ec-visual-100-independent-review.json)和[98表闭合](qa/native-final-4261-b6ec-table-98-closure-review.json)：最终Word与原生PDF身份绑定，所有检查通过；QA另亲看最终第57物理页的完整公式表，未发现剩余问题。
- [桌面交付和37项保护输入](desktop-delivery-verification.json)、[渲染方法](render-method-disclosure.json)：最终Word副本一致。通用LibreOffice诊断渲染为89页，与WPS不同，未用于页数验收；实际最终WPS100页作为权威分页。

初 `qa/native-df765-f815-toc-review.json` 的7.3缓存失败真实保留；最终为65页，已闭合。reviewer初次物14的孤立[56]意见保留，最终13/14实视确认解决。带df765、c4d4、f815的报告属于当时实物，不能单独充当最终4261/b6ec验收；引用最终映射和QA总结。

执行与独立内部复核完成，作者/导师验收待定。没有重跑软件测试或实验，没有改写冻结科研结果；原件、主Markdown及前轮材料保持。所有小型文件身份见[最终清单](final-evidence-manifest.json)。
