# thesis-agents —— 硕士论文多 Agent 审核优化系统

> 归属:本目录为 `agent-work/` 约定下的 agent 产物(角色定义,非实验材料)。
> 运行产出(评审报告、issue list)存放在仓库根 `reviews/round-NN/`。

## 系统组成

| Agent | 定义文件 | 权限 | 职责 |
| --- | --- | --- | --- |
| thesis-coordinator | `thesis-coordinator.md` | 只读(不改正文) | 流程编排、合并去重、排序、派发修改、复审决策 |
| thesis-structure-reviewer | `thesis-structure-reviewer.md` | 只读 | 章节职责、重复、逻辑链、内容错位 |
| thesis-academic-reviewer | `thesis-academic-reviewer.md` | 只读 | 研究问题、证据充分性、学术表达、贡献包装 |
| thesis-innovation-reviewer | `thesis-innovation-reviewer.md` | 只读 | 创新点成立性、盲审视角质疑 |
| thesis-technical-reviewer | `thesis-technical-reviewer.md` | 只读 | 技术描述正确性、架构自洽、图文一致 |
| thesis-skeptical-reviewer | `thesis-skeptical-reviewer.md` | 只读 | 倾向拒稿评审,攻击盲审致命伤 |
| thesis-writing-reviewer | `thesis-writing-reviewer.md` | 只读 | AI 味、套话、术语一致性、图表引用 |
| thesis-editor | `thesis-editor.md` | **唯一**可修改 `docs/毕业论文重构稿.md` | 仅执行 Coordinator 批准的修改任务 |

## 运行机制(当前 Harness:ZCode)

- ZCode 原生 subagent = Agent 工具(`general-purpose` / `Explore` 两种内建类型),运行时状态在 `~/.zcode/cli/agents/<sess>/<agent>/`。
- 当前版本**没有**文档化的"项目级自定义 subagent 类型注册格式",因此角色定义以 Markdown 文件保存在本目录,由 Coordinator 在 spawn prompt 中注入:"读取并严格遵守 agent-work/thesis-agents/<agent>.md"。
- Reviewer 的只读性靠角色定义 + Coordinator 事后 `git status` 审计保证(内建类型无按角色的工具白名单)。
- 并行:Coordinator 在**同一条消息**里发出多个 Agent 调用,Reviewer 即并行执行;Coordinator 与 Editor 串行。
- 原生入口:`/thesis-review [范围]`(定义在 `.zcode/commands/thesis-review.md`)。

## 目录约定

```
reviews/
  round-01/
    structure.md academic.md innovation.md technical.md skeptical.md writing.md
    consolidated-issues.md          # Coordinator 合并后的 prioritized issue list
    baseline-thesis-snapshot.md     # Editor 修改前的论文快照(审计基线)
    edit-report.md                  # Editor 修改报告
  round-02/ ...
```

## 硬约束(全系统)

- 每轮最多修改 5 个 Major/P0/P1 问题;最多 5 轮。
- 无 Critical/Major 即停止自动修改。
- 剩余问题需要作者决策、新增实验或真实数据时停止。
- Editor 禁止创造实验结果、数据、引用、系统功能;不确定处用 `TODO(需作者确认)` 标注。
