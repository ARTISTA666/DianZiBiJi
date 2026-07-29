# Smithsonian 真实实验笔记 OCR 候选数据

## 数据身份

- 收藏机构：Smithsonian Institution Archives Center, NMAH
- 项目：Home Journal Invention Notebook, Volume 1
- 项目编号：7578
- 候选页：NMAH-AC0124-0000005-41
- 内容：1881 年 5 月 27 日 Bell 与 Charles Sumner Tainter 的录音圆盘实验记录
- 原页与已复核转录：https://transcription.si.edu/view/7578/NMAH-AC0124-0000005-41
- PDF 地址：https://transcription.si.edu/pdf/7578/NMAH-AC0124-0000005-41

Smithsonian 页面标明该页转录已经完成。转录由数字志愿者完成并经过复核，可作为独立标准文本候选。

## 使用边界

Smithsonian 的项目说明允许个人、教育和其他非商业用途，并要求注明收藏机构与项目名称。本项目只用于毕业论文中的非商业系统验证，正式使用时仍需在论文和数据清单中注明来源。

## 当前状态

2026-07-12 尝试下载时，Codex 外部下载操作因当前使用额度被系统拒绝。因此本目录目前没有原始 PDF、页面图片、标准文本或 OCR 结果，也没有任何准确率数据。

下载恢复后按以下顺序处理：

1. 下载原始 PDF，并记录文件 SHA-256。
2. 从 PDF 导出页面图片和 Smithsonian 已复核转录。
3. 在不查看标准转录的情况下运行系统 OCR，并由校对人员只对照原图修改。
4. 冻结原始 OCR、校正文本和标准文本。
5. 使用 `scripts/evaluate_ocr.py` 生成字符错误率报告。

示例命令：

```bash
python scripts/evaluate_ocr.py \
  --manifest data/real/smithsonian_tainter/ocr_manifest.csv \
  --output data/real/smithsonian_tainter/ocr_evaluation_report.json
```

`ocr_manifest.csv` 的表头见 `docs/experiments/ocr-evaluation-manifest-template.csv`。
