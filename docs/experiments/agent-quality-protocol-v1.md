# Agent 五任务质量评估协议 V1

## 范围与结论边界

本协议覆盖实验总结、周报、阶段报告、文献综述和异常检测五类固定任务。冻结题集位于 `evaluation-lab/agent-quality/gold-v1.json`，对应生产提示契约 `agent-v10-evidence-ledger`。

题集是可公开检查的合成科研场景，适合做确定性回归和真实提供方冒烟；当前提示契约为 `agent-v10-evidence-ledger`。它不覆盖 Rust API 的数据库取数、资料排序、18,000 字上下文预算和结果落库，因此不能单独证明 Agent 全链路质量，更不能替代科研用户人工评审。

## 自动指标

- 事实一致性：每个金标准事实的必要关键词是否出现在回答中。
- Citation recall：每个已覆盖事实附近是否出现允许的 `[N]`、`[F]` 或 `[R]` 来源编号。
- Citation precision：回答中的唯一来源编号是否能与同段落、同一事实的金标准证据对应。未知编号、悬空编号和跨段落“借用”编号计为无效。
- 拒答/边界：是否出现题集明确禁止的过度推断或虚构结论。
- 运行指标：逐题记录模型、请求 ID 是否存在、延迟和 token 用量。

自动门槛为事实一致性、citation precision、citation recall 均不低于 0.90，边界通过率为 1.00，且五个冻结任务逐题通过；自动通过后，`human_review_status` 仍保持 `pending`。

## 运行方式

离线复算已有回答：

```bash
backend/.venv/bin/python scripts/evaluate_agent_quality.py --answers /path/to/answers.json
```

输入格式为 `[{"id": "experiment-summary-01", "answer": "..."}]`，也可放在对象的 `answers` 字段中。只有显式指定 `--output` 才写出报告；报告不含回答正文。

真实 DeepSeek 验收：

```bash
backend/.venv/bin/python scripts/validate_real_agent_quality.py
```

脚本默认不落盘、不输出提示词、回答或密钥，只输出指标、回答 SHA-256、模型、延迟和 token 用量。执行前必须确认本地安全配置已存在。

## 人工盲评

每题由至少两名未参与题集编写的科研用户独立给 1–5 分，分别评价：事实正确、引用可追溯、边界克制、结构可用、语言清晰。评审人只能看到匿名回答和冻结证据，不应看到模型名；分歧超过 1 分时由第三人复核。

上线人工门槛建议：每个维度均值不低于 4.0，任何回答不得因虚构关键实验结论或错误引用获得通过。人工结果应另存带日期的归档文件，不能回写或修改 V1 金标准。
