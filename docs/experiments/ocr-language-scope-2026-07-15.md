# OCR 语言场景与证据边界

## 1. 业务配置

系统目标语言场景为中文和英文实验记录、试剂标签及仪器截图。后端默认配置为：

- Tesseract 语言：`chi_sim+eng`
- 图像预处理：`grayscale_otsu`
- 页面分割模式：`PSM 3`
- 入库约束：保存机器原文；审核人对照原图校正并确认；未确认文本不得进入 RAG。

容器显式安装 `tesseract-ocr-chi-sim` 与 `tesseract-ocr-eng`。服务启动后的实际调用方法会写入结果记录，例如 `tesseract:chi_sim+eng;preprocess=grayscale_otsu;psm=3`。如果配置的语言包缺失，接口直接报错，不会退回到其他语言或静默返回占位文本。

## 2. RUKOPYS 压力测试

RUKOPYS 是乌克兰天主教大学发布的乌克兰语手写文本识别数据集，覆盖历史档案、现代作业和考试等连续手写材料。项目对 RUKOPYS 的固定留出集运行使用 `ukr`，得到 CER 78.58%、数字 F1 19.29%。

该数据与项目部署场景存在三重错位：

1. 语种不同：乌克兰语对中文、英文。
2. 文字系统不同：西里尔字母对汉字与拉丁字母。
3. 材料领域不同：通用历史与教育手稿对实验记录、标签及仪器读数。

因此，RUKOPYS 数字不用于估计中文或英文 OCR 准确率。其用途是跨语种、复杂手写体失效压力测试：当机器输出质量很差时，系统仍保留原始结果、要求人工确认，并阻止未确认文本进入知识库。

## 3. 当前可报告与不可报告的结论

| 证据 | 可报告结论 | 不可报告结论 |
|---|---|---|
| `chi_sim+eng` 配置、语言包检查和自动测试 | 系统调用链支持中英文混合 OCR，缺包时显式失败 | 中英文实验记录识别准确率 |
| OCR 人工确认与入库权限测试 | 未确认机器文本不能进入 RAG | 人工确认可自动修复全部错误 |
| RUKOPYS `ukr` 留出集 | 跨语种复杂手写输入下基线效果差，必须保留人工门控 | 中文/英文部署 CER、数字 F1 |
| Smithsonian 英文实验记录开发集 | 英文历史实验笔记的方案探索结果 | 独立英文确认性结果 |

当前没有带独立标准转录的真实中文实验记录、中文标签或中文仪器读数测试集，因此不报告中文 CER 或数字 F1。英文 Smithsonian 材料目前也只有开发用途结果，不能替代冻结留出集。

## 4. 后续同领域评价要求

后续应分别收集中文和英文真实实验记录、试剂标签及仪器截图，每类保留独立标准转录；在样本冻结后使用业务默认 `chi_sim+eng` 运行，报告 CER、去空白 CER、数字 F1、人工校对时间和未确认入库拦截率。RUKOPYS 继续保留为压力测试，不与同领域性能结果合并。

数据集来源：Dmytro Voitekh, Volodymyr Zmiivskyi, Oleksii Molchanovskyi. *RUKOPYS: Ukrainian Handwritten Text Recognition Dataset*. Ukrainian Catholic University, 2026, CC BY-NC-SA 4.0. <https://huggingface.co/UkrainianCatholicUniversity/rukopys>.
