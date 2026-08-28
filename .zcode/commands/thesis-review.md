---
description: 运行硕士论文多 Agent 审核优化(Coordinator 编排 6 Reviewer 并行审核 + Editor 修改)
argument-hint: [范围,如"全文"或"第五章 5.2";留空=全文一轮]
---

你是 thesis-coordinator。读取并严格遵守 `agent-work/thesis-agents/thesis-coordinator.md` 的角色定义与轮次流程,对论文 `docs/毕业论文重构稿.md` 执行一轮完整审核优化。

用户指定的范围:$ARGUMENTS(为空时默认全文)。

执行要求:
1. 按轮次目录 `reviews/round-NN/` 归档产物(报告、consolidated-issues.md、baseline 快照、edit-report.md)。
2. 6 个 Reviewer 必须在同一条消息中并行调用;Editor 串行;Coordinator 不直接修改正文。
3. 每轮最多派发 5 个 P0/Major 问题;无 Critical/Major 即停止。
4. 结束时输出:本轮 issue 汇总、已修复项(git diff 佐证)、遗留问题与停止原因。
