> status: frozen-evidence
> owner: Codex 证据线（T-114）

# T114补验汇总与原始工件索引

本目录保存2026年10月1日补验的轻量汇总。完整问题、实际检索上下文、模型响应、逐项判断及API动作日志仍保留在本地 `agent-work/t114-2026-10-01/`，大数据集与实验工作区不提交。

- [结果及局限报告](../t114-supplement-validation-2026-10-01.md)：三批结果、失败、修正和推断边界。
- [旧40条GPT补评](cross-judge-summary.json)：自定义指标及配对区间，不是RAGAS或同一案例评价者一致率。
- [新144条语义分析](semantic-analysis.json)：题级聚合、主检验、两个次比较与Holm校正。
- [生成核验](generation-verification.json)：144/144、38份冻结输入、各臂token和观测用时。
- [Rust运行身份](runtime-identity.json)：镜像、修订、嵌入工件和生产源码身份。
- [GPT角色模拟核验](simulation-verification.json)：原18/24、资料入库补测8/9，四GPT角色、零真人。
- [独立方法QA](methods-qa.json)：10,909项核对通过；不代表10,909个实验样本。
- [专项测试](t114-special-tests.log)及[仓库scripts测试](script-tests-v2-final.log)：51通过；完整检查596通过、1项既有dirty checkout保护相关失败。
- [本地原始工件哈希索引](local-raw-evidence-manifest.json)：列出本地路径、大小与SHA-256，未复制密钥或外发原始材料。

输入、两次完整生成批次及两轮模拟分别保留。补验为公开来源派生资料上的内部验证，GPT会话评审和模拟不替代独立人类金标准、真人可用性研究或长期部署评价。
