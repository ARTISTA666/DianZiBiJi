# 系统验证证据汇总

生成时间：2026-07-16T15:52:38.244024+00:00

## 运行与迁移

- 当前环境检查：通过
- 系统：Darwin arm64
- 并发读 smoke：通过 (90/90 requests, p95=31ms)
- 短 soak smoke：通过 (3 cycles, p95=15ms)
- 前端生产依赖审计：通过 (vulnerabilities=0)
- 生产配置预检：skipped_non_production
- 密钥泄漏预检：通过
- 密钥轮换手册：通过
- 灾备策略手册：通过
- 运行指标端点：通过 (requests=361, p95=18ms)
- 监控告警探针：通过
- 反向代理/TLS 模板：通过

## 浏览器端到端测试

| 流程 | 状态 | 耗时(ms) |
| --- | --- | ---: |
| 登录并完成笔记审批 | passed | 1868 |
| 图片 OCR、人工校对、入库、问答和五方法实验形成闭环 | passed | 7417 |
| 独立评价人只能在盲评页面提交评价 | passed | 1567 |

> 问答使用本地固定 LLM 桩，只验证调用和业务闭环，不代表生成模型准确率。

## 自动检索评价

| 模式 | Recall@10 | MRR | nDCG@10 |
| --- | ---: | ---: | ---: |
| bm25 | 0.3792 | 0.2676 | 0.2987 |
| vector | 0.4875 | 0.2630 | 0.3254 |
| hybrid_rag | 0.5631 | 0.2821 | 0.3646 |
| graph_enhanced_rag | 0.9024 | 0.4750 | 0.6072 |

> 题目和事实金标准由项目开发方整理，只能作为内部检索诊断，不能替代独立测试集。

## 知识图谱抽取核验

- 关系数：52
- TP/FP/FN：52/0/0
- F1：1.0000
- 人工签核数：0

> 该核验只覆盖四条固定演示笔记，不能外推到真实跨领域笔记。

## OCR 评价

| 数据集 | 分组 | 运行 | 样本数 | CER | 去空白 CER | 数字 F1 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| smithsonian_joseph_henry | development | htrflow-dev-nested | 5 | 0.8949 | 0.8995 | 0.0000 |
| smithsonian_joseph_henry | development | htrflow-dev-simple | 5 | 0.7893 | 0.8401 | 0.1622 |
| smithsonian_joseph_henry | development | htrflow-dev-spread | 5 | 0.5566 | 0.6195 | 0.1493 |
| smithsonian_joseph_henry | development | tesseract-dev-autocontrast | 5 | 0.7314 | 0.7868 | 0.0465 |
| smithsonian_joseph_henry | development | tesseract-dev-none | 5 | 0.8700 | 0.8928 | 0.0506 |
| smithsonian_joseph_henry | development | tesseract-dev-otsu | 5 | 0.7287 | 0.7841 | 0.0606 |
| rukopys_university | development | oracle_lines_psm7_autocontrast | 10 | 0.7537 | 0.7977 | 0.2617 |
| rukopys_university | development | paddleocr_v5_mobile_eslav | 10 | 0.7578 | 0.8052 | 0.4828 |
| rukopys_university | development | psm3_crop_autocontrast_nodpi | 10 | 0.7491 | 0.7876 | 0.2737 |
| rukopys_university | development | psm3_grayscale_autocontrast | 10 | 0.7504 | 0.7896 | 0.2491 |
| rukopys_university | development | psm3_grayscale_otsu | 10 | 0.7441 | 0.7876 | 0.2618 |
| rukopys_university | development | htrflow-dev-simple | 10 | 1.0702 | 1.1526 | 0.4435 |
| rukopys_university | holdout | final_otsu | 10 | 0.7858 | 0.8282 | 0.1929 |
| rukopys_university | holdout | htrflow-holdout-simple | 10 | 1.1151 | 1.2137 | 0.4381 |

> development 结果用于选模型；只有 split 为 holdout 的固定留出集结果可作为最终测试。

## 备份 smoke

- 备份包校验：通过
- 数据库 dump 可读：True
- 隔离恢复演练：通过
- 路径：`/private/tmp/eln-maturity-backup-20260716T142815Z`

## 完整性

JSON 文件保存每个来源文件的 SHA-256，可据此检查报告是否对应当前原始结果。
