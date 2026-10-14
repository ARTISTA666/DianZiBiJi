> status: frozen-evidence
> owner: Codex

# T145 图6-5底部说明删除证据

本目录保存本轮收工的小型快照。交付为[桌面新版Word](/Users/yusong/Desktop/1005-图6-5说明删除版-2026-10-11.docx)，SHA `b9336e8dfef93921f2ff4fc4291c4465c91facaa23b5040c6cc74005959438bf`。原生WPS内部PDF SHA `e12ca56e79e001488e12a6b46225ab384c47c7e12bda526908e6a3b859cb3482`，100个A4物理页。大型Word/PDF/PNG保持本地，没有进入本归档。

- [Word裁剪差异](changes.json)：图6-5所在段落仅新增bottom裁剪14368和两个同比显示高度，没有改写图片字节或正文。Word裁剪可逆，原图像素仍嵌入，不宣称不可恢复删除。
- [独立内容保护](qa/candidate-b933-native-crop-protection-review.json)：32项检查通过；正文、图题、48公式、85书目、73引用、108表/98三线表及所有媒体字节保持，62项旧输入未变。
- [原生导出](native-export.json)、[逐页SHA比较](native-page-comparison.json)和[root原尺寸实视](root-visual-review.json)：只有物理63页变化，99页继承与T144已审PNG的精确相同SHA。第63页两行说明不再显示，标题、方法和柱形数值、坐标轴与独立图题完整同页，无拉伸或重叠。
- [实际目录](qa/native-final-b933-e12-toc-review.json)及qa目录中的最终总结保存独立原生复核；身份及全部文件SHA见[最终清单](final-evidence-manifest.json)。不把99继承页称为本轮重新实视。
- [桌面副本核对](desktop-delivery-verification.json)、[渲染方法](render-method-disclosure.json)：交付Word与候选字节一致。通用LibreOffice诊断为89页，与WPS不同，仅作诊断；实际100页以WPS为准。

执行及内部复核完成，作者/导师验收待定。未改主Markdown、原稿或旧冻结材料，未运行新软件测试或实验，未暂存或提交。
