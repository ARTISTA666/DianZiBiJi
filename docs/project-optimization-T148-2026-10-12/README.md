> status: frozen-evidence
> owner: Codex证据线（T148）

# T148项目优化小型归档

本目录保存本轮代码增量身份、当前自动验证及独立审查、有限混合负载逐请求记录和48次RAG原始响应。主入口为[实施报告](../项目论文增益优化实施与自动验证-T148-2026-10-12.md)，研究结果另见[RAG回顾性对照](../experiments/rag-fair-comparison-T148-2026-10-12.md)，前置条件见[协议v1](../experiments/rag-fair-comparison-protocol-v1.md)。全部结果暂不同步论文，作者/导师验收待定。

- `source-delta-manifest.json`、`delta.patch`：相对本轮捕获的dirty基线，非相对Git HEAD；17个文件中3个新增。
- `qa/QA.json`及Rust日志：实连本轮PG/pgvector，305项测试及fmt/strict Clippy；`script-suite-final.log`为613项脚本通过；`qa/evidence-review.json`为RAG研究证据独立核查；[最终报告复核](qa/final-report-review.json)绑定前一45项清单，45项独立检查通过，0阻断。加入复核记录后的46项最终清单由根线程重新核验。
- `frontend/validation.json`、`review/review.json`：前端9项独立SSE回归、常规检查及无阻断的静态审查。空ID边界指显式空`id:`重置，会话内去重不声明刷新持久性；mock写计数不替代数据库验证。
- `system/`：独立镜像的构建输入/image ID、整栈9通过/9有意跳过、重启探针及其仅限自有项目的调用shim；200次混合请求＋60.261秒350次短浸泡的逐请求/写入核对，环境为hash embedding、小数据和4核Docker VM，非容量或长期稳定性研究。
- `rag/`：48条原始API响应、分析、词面评分轨迹、事实池、预生成核查及冻结SHA；只支持回顾性开发控制，语义主结果未计算，两组词面差值负向。大contexts、questions及官方tokenizer在本地且受冻结清单约束。
- `protected-final.json`：50项旧材料及论文保护检查全部保持。`final-evidence-manifest.json`绑定本目录及结果报告、协议和本轮实际源码。

本地完整工作区为`agent-work/t148-2026-10-12/`，RED/首次失败及最终GREEN日志均保留；未整体暂存或提交。backend/frontend子执行记录中“parent/QA pending”为它们各自释放时快照，最终组合验收以总报告、QA和最终清单为准。
