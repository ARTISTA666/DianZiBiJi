## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: run + validate
- Origin Date: 2026-07-13
- Verification Status: ANALYZED
- Version Label: non_human_completion_v1

# 非人工实验完成交接记录

## 1. 完成范围

截至 2026-07-13，当前项目中不需要人工判断、人工命题或人工签字的实验执行、自动评分、回归测试和证据导出已经完成。

### 五方法真实模型实验

- 运行编号：8。
- 数据范围：一个开发者整理的 GSE111619 内部基准，不是外部确认性测试集。
- 方法：纯 LLM、BM25 RAG、项目混合 RAG、直接结构化查询、图谱增强 RAG。
- 规模：12 题 × 5 方法 × 3 次重复，共 180 个案例。
- 结果：180/180 完成，0 失败；随机种子 `20260713`，执行顺序随机化。
- 自动覆盖率：纯 LLM 0.0000、BM25 RAG 0.4271、项目混合 RAG 0.3021、直接结构化查询 0.9062、图谱增强 RAG 0.9062。
- 结构化查询出现 27 次禁用事实命中；图谱增强 RAG 为 0 次，事实精确率为 1.0。
- 问题聚类比较中，图谱增强 RAG 相对项目混合 RAG 的平均覆盖差为 `+0.6389`，问题级 bootstrap 95% CI 为 `[+0.3889, +0.8472]`。
- 冻结包运行后仍为 14/14 文件哈希通过；重复生成不能作为 36 个独立问题使用，确认性解释采用问题级聚类结果。

原始证据：

- `data/real/experiment-5/internal-five-mode-experiment.csv`
- `data/real/experiment-5/internal-five-mode-experiment-report.json`
- `data/real/experiment-5/internal-five-mode-validation.json`
- `docs/experiments/rag-experiment-5-internal-automatic-validation.md`
- `docs/experiments/rag-experiment-5-internal-freeze-manifest-v2.json`

### OCR 自动实验

- RUKOPYS 开发集与留出集各 10 页，均已完成固定 HTRflow/TrOCR CPU simple-layout 运行和自动 CER 评价。
- RUKOPYS 是乌克兰语连续手写材料，实验使用 `ukr`；系统业务默认 `chi_sim+eng` 面向中文和英文资料。该实验仅为跨语种失效压力测试，不是中英文部署准确率。
- 开发集微平均 CER 107.02%，数字 F1 44.35%；留出集微平均 CER 111.51%，数字 F1 43.81%。
- CER 超过 100% 表示编辑次数超过标准文本字符数，不是准确率，也不是负准确率。
- HTRflow/TrOCR 未改善固定 Tesseract 留出结果，因此不接入系统默认 OCR。

原始证据：

- `data/real/rukopys_university/runs/htrflow-dev-simple/`
- `data/real/rukopys_university/holdout/runs/htrflow-holdout-simple/`
- `docs/experiments/ocr-improvement-2026-07-13.md`

### 自动回归与证据

- 后端容器测试：134 passed。
- 脚本测试：47 passed。
- 前端类型检查：passed。
- 前端生产构建：passed。
- 隔离浏览器 E2E：3 passed，覆盖审批、OCR/RAG/五方法闭环和独立盲评权限。
- `docs/system-evidence/manifest.json` 中 9 个文件的 SHA-256、字节数和文件列表全部复核通过。
- 自动验证汇总收录 14 个 OCR 运行，运行环境检查通过。

## 2. 已准备但不得自动完成

- 运行 8 已自动暴露方法隐藏批次 `R8AB588365B1D`，共 180 条，已评 0 条、待评 180 条。
- 现有 `blind_reviewer` 账号只有读取和评价权限；第二名真实评价人尚未确定。
- 系统会保存每名评价人的独立评分，但程序和模型不得代替真人填写准确性、可追溯性、1—5 分质量和签字。

## 3. 只剩人工前置或人工判断的实验事项

1. 由未参与当前答案生成的外部人员为多项目确认性实验编写并冻结问题、答案要点和排除规则。当前运行 8 只能作为单项目内部开发证据。
2. 确定第二名独立评价人，并由两名评价人分别完成方法隐藏评分；完成后才能运行一致率和 Cohen's kappa 汇总。
3. 若要声称真实实验笔记 OCR 效果，需要人工提供同领域图片及独立标准转录，或完成盲态人工校对；公开 RUKOPYS 压力测试不能代替该证据。
4. 论文或学校要求的身份信息、声明、授权书和签名必须由本人完成。

在这些人工输入出现前，没有其他可独立执行且不会伪造人工结论的实验步骤。
