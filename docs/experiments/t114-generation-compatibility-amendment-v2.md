> status: current
> owner: Codex 证据线（T-114）

# T114 生成接口兼容性修正 v2

本文件是 [补充验证协议 v1](t114-supplement-validation-protocol-v1.md) 的操作性修正，与 v1 一同构成 v2 的冻结协议。v1 已绑定首批冻结哈希，保留原文及当时状态，不回改任何生成结果。旧40条GPT评判和角色模拟不受此修正影响。

## 修正原因

首批适配器未显式指定 thinking 开关。实际响应含 reasoning_content，部分请求返回 HTTP 200 后没有非空 content，依预定规则登记失败。旧适配器未保存空答的原始JSON，此处仅依据实际200/ValueError日志确认空答；推理耗尽预算是结合成功响应的reasoning_tokens和官方说明作出的机制解释，不能宣称已逐条读取失败响应的finish_reason。

生产 Rust 的 backend/src/ai_provider.rs 已在请求中设置 thinking.type=disabled。实验适配器漏传该参数，因此首批不是生产调用参数的完整复现。[DeepSeek官方思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)记载默认启用思考模式，且该模式下temperature不生效。v1所写temperature=0.1仅为请求值，不能声称其当时有效。

## 第二批冻结内容

v2只补入固定 thinking={type: disabled}，使实验适配器与生产接口一致；空答/截断的原始响应、用量及finish_reason先保存再判状态。请求模型仍为deepseek-v4-flash（实际返回model字段单列），temperature=0.1，max_tokens=1000，最多两次尝试。完整重跑12题×4臂×3次共144条，不能只补第一批失败项，也不合并两批挑选最好答案。

第二批字节复用第一批questions、contexts、原始Rust检索响应、图谱、批准笔记及运行身份；随机案例计划不变。文档base4000字符、补充16000字符；同一嵌入工件、语料与图谱快照。全部必需事实、禁止断言、语义主评分提示及统计方案保持相同，并在第二批首次请求前重新绑定冻结。第一批结果单列为兼容性受限批次；v2作为操作修正后的主要重测批次。此修正发生于观察服务空答之后，须明确记录，不能将第二批描述为没有先行服务试验的独立确认性实验。

事实题主指标仍由独立GPT判断正确实体字段绑定及实际证据支持，10个事实题与2个纯资料不足题分开；问题为统计单位，重复先按题汇总，主D-A与次D-B/D-C定义不变。第二批开始后不得根据回答再改规则或预算。

## 文件与历史保留

- 第一批：agent-work/t114-2026-10-01/rust-retest。
- 第二批：agent-work/t114-2026-10-01/rust-retest-v2。
- 适配器修正版：scripts/experiments/run_t114_rust_retest_v2.py。
- 第一批历史规则、回答和失败保留，最终报告同时列明计划与有效数。
