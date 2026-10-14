> status: frozen-evidence
> owner: Codex（证据线；backend-engineer、QA、code-reviewer独立复核）

# T141 论文整改证据（2026-10-11）

本目录记录作者授权的17项内容/格式整改，完整说明见[整改记录](../论文深审问题整改-T141-2026-10-11.md)。只保存文本证据；Word、PDF、逐页图片和Rust构建产物留在本地。本轮基线原稿、主Markdown与历史实验保持，当前Rust代码修复另有回归证据。

最终[Word](/Users/yusong/Desktop/1005-深审整改版-2026-10-11.docx) SHA-256为`501184b1d12d5611709606f24feed69437e6d862ff12d27a292a2f91fe1df948`；原生WPS[PDF](/Users/yusong/Desktop/1005-深审整改版-2026-10-11.pdf)为`bfd769f53d297732793833d8a5c46df5dae32c6dd02869a0ca0168dd3dfa9165`，含封面和附录共100物理页。[交付复制证明](delivery-copy-proof.json)核对桌面副本与检查对象一致。

## 稿件内容及保护

- [逐项文字与引文映射](changes.json)：456项段落记录，85条原有文献只重编号，98张数据表；记录数量包括精简与引用调整，不代表456项独立缺陷。
- [独立内容及当前实现审核](content-review-native-delivery.json)：48原生公式、85参考条目身份与引用映射，当前6个Rust文件及静态提示注册表核对。
- [Word保护检查](word-protective-native-indent-final-release-review.json)：公式、批注、原有致谢、数据字典、关系和来源样例；[第六章数值差异](chapter6-paragraph-native-indent-final-release-numeric-diff.json)逐一说明授权口径调整，历史结果保持。
- [冻结材料及Rust输入](frozen-and-rust-input-native-indent-final-release.json)：215件T136材料、118件T139证据、6件T140审核材料和65项本轮实际Rust执行输入保持；[主Markdown原文保护](main-markdown-preservation.json)与本轮开工HEAD逐字节比较。

## 原生分页与视觉验收

- [WPS导出证明](native-export-proof.json)、[100页图片身份清单](native-release-page-manifest.json)及[100项目录核对](toc-native-indent-final-release-review.json)绑定同一最终Word/PDF。
- [1–33页](visual-review-native-delivery-1-33.json)、[34–67页](visual-review-native-delivery-34-67.json)、[68–100页](visual-review-native-indent-final-release-68-100.json)合计覆盖100页；检查包含题注/表头/表体完整同页、图字与公式可读及正文版心。相同图片按实际PNG字节SHA继承已完成的原尺寸实视；变化页面重新原尺寸检查，不以仅扫描缩略图代替。
- 首次100页原生导出检查发现越界表格和PDF批注标记。最终与首次导出相比14页变化、86页字节相同；最后一轮只改变36、45、46、67、99页，另95页相同。不同导出身份的清单及历史审核均保留，不将带阻塞项的旧报告算作最终通过。
- [算法边框修改](algorithm-border-fix.json)及[算法保护复核](algorithm-native-indent-final-release-border-review.json)；[目录缓存调整](toc-changes.json)只改3处页码。
- [三张用例表](native-table-width-fix.json)、[D-4记录表](native-d4-width-fix.json)、[表1-1](native-table1-width-fix.json)、[另五表宽度](native-five-table-margin-fix.json)共10表统一8504twips；[五表水平位置](native-five-table-indent-fix.json)仅将既有缩进0改140twips。[独立XML及实际PDF位置检查](native-indent-final-release-five-table-position-only-review.json)证明其余XML与ZIP部分相同、横线两端在正文版心内。

## 当前Rust修复与真实执行

- [本轮增量代码差异](current-delta.patch)对照开工时已有dirty代码，未将既有未提交改动算成本轮成果；[源文件身份](current-source-manifest.json)、[新增机制回归](implementation-verification.json)及[旧契约失败证据](regression-red-evidence-review.json)保存。
- [提示版本与模板SHA注册表](prompt-version-registry.json)和[独立复核](prompt-registry-independent-review.json)核对v2的三项实际静态模板。静态模板指纹不冒充包含用户输入和动态上下文的完整请求身份；旧v1记录保持，旧预览在v2执行前返回409。
- [全量Rust执行报告](rust-final-validation.json)与[输入清单](validation-input.json)：隔离快照`9548e83d4f887630385e2b818292e2b8a5afbf36`，65项输入与主树一致；Rust1.88.0、隔离PostgreSQL16/pgvector；fmt、严格locked/all-targets/all-features Clippy及287库＋2入口＝289测试全部通过，失败/忽略均0。未改API结构，不把前轮前端/脚本/E2E结果算成本轮新验证。

## 身份、范围与验收

[最终证据清单](final-evidence-manifest.json)给出本目录文件SHA、来源及最终交付身份；[独立QA总审](qa-native-indent-final-release-final-review.json)汇总保护、分页、目录、视觉及输入核查。[交付身份独立复核](native-indent-final-release-identity-and-copy-review.json)核对本地最终副本一致。

执行及独立内部验收完成，100页全部覆盖、15项Word保护及100目录通过，最终证据封存；作者/导师验收待定。英文自然正文抽取失败、非显著主检验、旧GPT裁判来源元数据缺失及不同历史快照等边界保留。本轮修订未重评或回填冻结分数，也未产生新的真人或真实生物实验结果。
