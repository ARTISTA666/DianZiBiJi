# OCR 改进与留出集验证记录

## 1. 目的和边界

本次工作只改进图片 OCR，不把公开数据写成系统自己的实验数据。

- 数据来源：RUKOPYS 公开手写数据集。
- 数据内容：乌克兰语大学手写材料，不是实验笔记，也不是中文或英文部署材料。
- 开发集：10 页，用于选择预处理和 OCR 方案。
- 留出集：另选 10 页，与开发集无重复；固定方案后只运行一次。
- 评价指标：字符错误率（CER，越低越好）和数字 F1（越高越好）。
- 系统边界：任何机器 OCR 结果都必须人工校对并确认后才能进入 RAG。
- 配置边界：RUKOPYS 实验使用 `ukr`；系统业务默认使用 `chi_sim+eng`。二者不能混作同一语言场景的性能结果。

开发集清单 SHA-256：

`af19e9783aa9100fb09682e9e5c2bc075f34e6b3f4406f176cf0acaae205484d`

留出集选择文件 SHA-256：

`d13886921980567cbd4f8768050405fef90960761c06962c765a477398ebafdd`

留出集清单 SHA-256：

`37bbaa8454e913a48b526e68582c987cd723a49702d5610d08b43765ad890fad`

## 2. 开发集结果

所有方案使用同一批 10 页和同一套标准文本。下表中的时间不包含模型安装和下载。

| 方案 | 微平均 CER | 宏平均 CER | 数字 F1 | 平均每页时间 |
|---|---:|---:|---:|---:|
| Tesseract 原图，PSM 3 | 75.72% | 76.25% | 22.78% | 1.304 秒 |
| Tesseract 裁剪并自动对比度，PSM 3 | 74.91% | 75.09% | 27.37% | 1.062 秒 |
| Tesseract 灰度并自动对比度，PSM 3 | 75.04% | 75.24% | 24.91% | 1.025 秒 |
| **Tesseract 灰度 Otsu，PSM 3** | **74.41%** | **74.67%** | **26.18%** | **0.936 秒** |
| 人工行框 + Tesseract PSM 7（诊断） | 75.37% | 76.20% | 26.17% | 2.132 秒 |
| PaddleOCR v5 移动端检测器 | 75.78% | 74.13% | 48.28% | 8.588 秒 |
| HTRflow + TrOCR base，simple layout | 107.02% | 106.55% | 44.35% | 65.917 秒 |

开发集结论：

1. 灰度 Otsu 的微平均 CER 最低，比原图降低 1.30 个百分点，因此选为系统默认方案。
2. 人工提供准确行框后，CER 仍为 75.37%，说明主要问题是手写文字识别，不是页面分行。
3. PaddleOCR 的整体 CER 没有更低，但数字 F1 明显更高。它可以作为后续数字校验候选，当前不能替代默认 OCR。
4. 未针对 RUKOPYS 微调的 HTRflow/TrOCR 基线 CER 超过 100%，说明插入、删除和替换总数超过标准文本字符数；这不是“负准确率”，也不能换算成准确率。

## 3. 大模型 OCR 试验

PaddleOCR-VL 1.6 做了两种小范围试验，没有进入留出集。

### 3.1 PaddlePaddle 原生推理

- 设备：Apple Silicon，16GB 内存。
- 单页模型初始化约 76 秒。
- 推理运行数分钟仍未完成，占用约 9.5GB 内存，因此人工停止。
- 没有生成可评价结果，不计算 CER。

### 3.2 MLX-VLM 推理

- 第一页耗时 105.22 秒，其中包含首次模型下载；第二页耗时 54.52 秒。
- 第一页有一个区域连续生成编号并达到 2048 字符上限，直接计算的 CER 为 201.25%。
- 第二页也生成大量重复编号，直接计算的 CER 为 153.97%。
- 即使过滤明显重复区域，两页表现仍不稳定，因此停止继续测试。

这些失败结果说明，大模型 OCR 也可能产生重复或虚构内容，不能因为单页效果较好就接入系统。

### 3.3 HTRflow + TrOCR

为完成无需人工干预的手写 OCR 对照，使用 HTRflow 0.2.6、`Riksarkivet/yolov9-lines-within-regions-1` 和 `microsoft/trocr-base-handwritten`，固定 CPU、simple layout、batch size 8。模型未针对 RUKOPYS 微调，开发集和留出集均使用同一配置。

| 分组 | 页面数 | 微平均 CER | 宏平均 CER | 去空白 CER | 数字 F1 | 总时间 |
|---|---:|---:|---:|---:|---:|---:|
| 开发集 | 10 | 107.02% | 106.55% | 115.26% | 44.35% | 659.173 秒 |
| 留出集 | 10 | 111.51% | 109.08% | 121.37% | 43.81% | 437.840 秒 |

HTRflow 成功完成了页面分行、文字识别和结果导出，但文本质量低于 Tesseract 固定方案。该结果只证明流程可运行和通用模型不适配当前乌克兰手写样本，不证明 HTRflow 或 TrOCR 对其他语言、版式或经领域微调后的效果。

原始记录：

- `data/real/rukopys_university/runs/htrflow-dev-simple/run.json`
- `data/real/rukopys_university/runs/htrflow-dev-simple/evaluation.json`
- `data/real/rukopys_university/holdout/runs/htrflow-holdout-simple/run.json`
- `data/real/rukopys_university/holdout/runs/htrflow-holdout-simple/evaluation.json`

## 4. 留出集结果

固定方案为：Tesseract 5.5.0、`ukr`、PSM 3、`grayscale_otsu`。留出集没有用于调参。

| 指标 | 结果 |
|---|---:|
| 页面数 | 10 |
| 微平均 CER | 78.58% |
| 宏平均 CER | 81.20% |
| 去空白微平均 CER | 82.82% |
| 数字 F1 | 19.29% |
| 总识别时间 | 5.969 秒 |
| 平均每页时间 | 0.597 秒 |

原始记录：

- `data/real/rukopys_university/holdout/final_otsu/run.json`
- `data/real/rukopys_university/holdout/final_otsu/evaluation_report.json`

留出集结果低于开发集，说明该方法对乌克兰语连续手写体的稳定性不足。论文中不能写“系统可以准确识别真实手写实验笔记”，也不能把该结果解释为中文或英文 OCR 准确率。

同配置 HTRflow/TrOCR 留出集微平均 CER 为 111.51%，未改善该边界，因此不接入系统默认 OCR。

## 5. 系统改动

系统默认在 Tesseract 前增加灰度 Otsu 预处理。实现使用 OpenCV 的 `cv2.threshold` 和 `THRESH_OTSU`，不自行实现阈值算法。替换前对开发集和留出集共 20 张图片做了逐像素对比，处理结果与原实验文件完全一致，因此不改变上面的实验数据。系统记录完整方法，例如：

`tesseract:chi_sim+eng;preprocess=grayscale_otsu;psm=3`

运行边界保持不变：

1. 保存机器原文。
2. 审核人对照图片修改文本。
3. 保存校对文本、确认人和确认时间。
4. 文件变化后原确认结果失效。
5. 未确认的图片 OCR 不允许进入 RAG。

## 6. 最终结论

本次改进得到一个速度较快、开发集上小幅改善的预处理方案；新增 HTRflow/TrOCR 对照也没有解决复杂乌克兰语手写体识别问题。系统业务运行仍使用 `chi_sim+eng`。当前真正可靠的能力是“中英文机器预识别 + 人工确认 + 审计留痕”，不是自动得到准确手写文本。RUKOPYS 的作用是证明即使 OCR 在跨语种复杂手写输入上明显失效，系统也不会静默把错误文本当作知识。中文和英文同领域准确率仍需使用真实实验记录、标签与仪器读数及独立标准转录重新评价。

参考：

- Tesseract 图像质量建议：<https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html>
- PaddleOCR 通用 OCR 文档：<https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html>
- PaddleOCR-VL Apple Silicon 文档：<https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL-Apple-Silicon.html>
