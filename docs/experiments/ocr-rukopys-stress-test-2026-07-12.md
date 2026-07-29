# 真实手写图片 OCR 压力测试

> 2026-07-13 更新：预处理选择、替代模型试验和独立留出集结果见 `ocr-improvement-2026-07-13.md`。留出集微平均 CER 为 78.58%，系统仍不能自动可靠识别连续手写体。

## 1. 数据来源

- 数据集：RUKOPYS v1.6
- 来源：Ukrainian Catholic University
- 许可：CC BY-NC-SA 4.0
- 本次数据：2024 至 2025 年大学考试扫描件
- 标准文本：数据集提供的专业人工标注，不是系统生成文本

RUKOPYS 共提供 1330 张人工标注训练图片，其中大学来源 162 张，专业人员标注 136 张。

这些图片是真实手写材料，但不是实验笔记。本测试只用于检查系统所用 OCR 引擎面对复杂手写体时的表现，不能代替后续真实实验笔记测试。

## 2. 选样方法

选样在运行 OCR 前完成，规则如下：

1. 只保留 `source=university`。
2. 只保留 `annotation_source=annotator`。
3. 只保留手写文字、印刷文字和批注，不混入公式、表格、图片或图形。
4. 每个文字区域必须标为可读。
5. 排除带删除线标记或 `[illegible]` 的页面。
6. 标准文本不少于 350 字符。
7. 对候选文件名排序，再等距选择 10 页，包含首尾页面。

筛选后有 11 页符合条件，固定选择其中 10 页。运行后没有按识别效果替换样本。

选样清单：`data/real/rukopys_university/selection.json`

## 3. 运行配置

- OCR 引擎：Tesseract 5.5.0
- 语言：`ukr`
- 页面分割模式：`PSM 3`
- 图片数：10
- 总运行时间：13.038 秒
- 平均每页：1.304 秒

每张原图、原始 OCR 文本和标准文本均保存 SHA-256。运行记录位于 `data/real/rukopys_university/ocr_run.json`。

## 4. 计算过程

字符错误率公式为：

`CER = 编辑距离 / 标准文本字符数`

本次 10 页标准文本共 10760 个字符，OCR 文本改成标准文本共需要 8147 次插入、删除或替换：

`8147 / 10760 = 0.757156`

因此微平均 CER 为 **75.72%**。各页 CER 的简单平均值为 **76.25%**。删除空白字符后的微平均 CER 为 **79.74%**。

标准文本含 113 个数字标记，OCR 输出含 168 个，完全匹配 32 个：

- 数字精确率：`32 / 168 = 19.05%`
- 数字召回率：`32 / 113 = 28.32%`
- 数字 F1：`22.78%`

完整的逐页字符数、编辑距离和哈希位于 `data/real/rukopys_university/ocr_evaluation_report.json`。

## 5. 结果

Tesseract 对这组真实连续手写体的识别效果差。**75.72% 是错误率，不是准确率。** 因此，当前系统不能宣称可以自动、准确地识别手写实验笔记。

系统现有流程仍有实际作用：它保存机器识别原文，允许审核人对照原图修改，并禁止未确认的文字进入 RAG。该流程可以防止错误 OCR 直接成为检索证据，但不能代替人工校对。

若要提升自动手写识别，需要增加文字行检测和专用手写文字识别模型，再用新的独立留出集评价。本次数据已经用于检查 Tesseract，不能继续当作未见过的最终测试集。

## 6. 文件哈希

| 文件 | SHA-256 |
| --- | --- |
| 上游数据说明 | `0f00f83a109a5e2b109893c570247161a82ca200e1c54d1f0e954908f8e7d9a9` |
| 人工标注元数据 | `51130c9664007b6cded62aba89770dcb3be50151bb5b4a71724f25b74cb21bab` |
| 选样清单 | `6b287433108acc429a07cc0447edc55cfd44c65933fb4a9ab37c112c5fc5386d` |
| OCR 清单 | `af19e9783aa9100fb09682e9e5c2bc075f34e6b3f4406f176cf0acaae205484d` |
| 运行记录 | `3c8f34b2a9a3daad4bcc5b30b83a7ff3c79e722e9dd8329e2fa220c373ac7cda` |
| 评价报告 | `d1cdff47a1d8a563c9e459d087c3a60dc9e79624a444e248dc044a28254aa702` |

## 7. 复现命令

```bash
backend/.venv/bin/python scripts/prepare_rukopys_ocr_subset.py \
  --metadata data/real/rukopys_university/train/metadata.jsonl \
  --output-dir data/real/rukopys_university

docker compose run --rm \
  -v "$PWD:/workspace" -w /workspace backend \
  python scripts/run_ocr_batch.py \
  --manifest data/real/rukopys_university/ocr_manifest.csv \
  --output data/real/rukopys_university/ocr_run.json \
  --language ukr --psm 3

backend/.venv/bin/python scripts/evaluate_ocr.py \
  --manifest data/real/rukopys_university/ocr_manifest.csv \
  --output data/real/rukopys_university/ocr_evaluation_report.json
```

原始 OCR 和运行报告已经冻结。重复执行时不要使用 `--replace` 覆盖现有结果。
