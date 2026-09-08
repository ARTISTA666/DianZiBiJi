# HANDOFF — 三端协调交接（持久化，唯一写者：ZCode 证据线）

> 建立时间：2026-09-07 21:58（本机，Asia/Shanghai）；**ZC-03 更正：2026-09-07 22:16（实际时钟）**。本文件为**持久交接锚点**：任何会话中断/换人接手，以本文件为起点。
> 状态基准：round-2 各报告**均待 Codex 总协调验收**（完成 ≠ 审核通过）。不等待其他 agent 完成，状态后更新。

## 1. 三项贡献（统一表述，Codex 指定）

1. **动态图谱建模更新**（原创新点一：知识蓝图 + 实证图谱抽取）
2. **图谱/证据约束的科研辅助工作流（含预警）**（原创新点二：建议/思维链 + 创新点四：预警闭环）
3. **导师监督的语义可视化反馈**（原创新点三：图谱语义映射；**形状/水波通道已在当前 HEAD 裁撤**，口径以 AG-02 后的映射文档 v1.1 为准）

**画像（原创新点五）= 三贡献之外的前瞻项（outlook）**：设计文档 + 离线原型验证，不占贡献条目，无任何真实收益主张。

## 2. 会话名 / 绝对路径 / 分工范围

| 端 | 会话名（准确名） | 绝对路径 | 本轮范围 | 状态 |
| --- | --- | --- | --- | --- |
| Codex | 总协调（经用户转达） | 工作区根：`/Users/yusong/Downloads/new/full-system/` | 派活/审核/裁决；不直接写三端文件 | — |
| ZCode（本会话） | 「运行项目测试新功能并录制验证视频」 | 仓库同上；stable 检出：`/Users/yusong/Downloads/full-system-stable/` | `docs/coordination/` 下 ZC 系列与 HANDOFF/README；消融勘误 `docs/experiments/innovation-ablation-2026-09-07.md`；创新点总览映射修正 | ZC-01/ZC-02 已交，**ZC-03 已完成，均待验收** |
| Antigravity | 「前端图谱样式优化」 | 仓库同上 | `docs/coordination/AG-01.md`、`AG-02.md`；`docs/innovation/图谱可视化语义映射-v1.md`（v1.1）。**第三轮已派工（AG-03-prompt.md，2026-09-07 在库）：自身文档残留结论修正 + 贡献三论文素材 + 识读实验设计草案** | AG-01/AG-02 待验收；AG-03 进行中 |
| DeepSeek | 研究线 Harness（「桌面有一个“创新点讨论”的」） | 仓库同上 + `~/Desktop/创新点讨论-*.html` | `docs/coordination/DS-01.md`；**已获准：备份修正桌面报告、核实六来源、归档至 `agent-work/research/DS-02`——目前仍在运行，勿打扰** | DS-01 已提交待验收；DS-02 进行中 |
| 文字线（隔离） | GPT 论文线 | `docs/毕业论文重构稿.md` | **三端均不得触碰**；单写者窗口规则见 AGENTS.md | 未参与 round-2/3 |

**【ZC-03 事实更正】Antigravity 未留下任何源码修改**（`git diff HEAD -- frontend/src` 为空；HEAD 的 `ENTITY_COLORS` 实体键仍为 17 类，无 sample/experiment_type 键）。此前记录的"kg-visualization.tsx 颜色补齐""AG-02 正在改源码"为错误记录，已删除。AG-02 对 `图谱可视化语义映射-v1.md` 的 v1.1 文档改动真实存在（工作区 M 状态，125 行 diff），文档主张与源码的差异以 AG 第三轮文档修正为准。

**共享边界**：`docs/experiments/innovation-ablation-2026-09-07.{md,json}`、`scripts/run_innovation_ablation.py` 归 ZCode；JSON 与脚本冻结不改。其他 agent 报告互不修改。

## 3. 版本不确定项（ZC-04 更新 2026-09-08）

- 主工作区 HEAD `cc4eb8a`；**运行栈 /ready revision 已于 2026-09-08 重建为 `cc4eb8a`**（此前"运行行为 97ffd43、revision 标签 4606189"历史快照作废）。部署用 `--allow-dirty`（development 模式，tracked 源码 clean、仅 docs M 状态）。
- **工作副本源码级一致 ≠ 部署镜像内容已证**的保留原则不变，但本轮 revision 标签与 HEAD 一致，版本归因风险已消除。
- 桌面旧演示视频（09-05 录制）对应版本仍未核实；**新演示材料以 `docs/innovation/创新点试用展示-2026-09-08.md` 及其 screenshots/ 为准**。

## 4. 账号配额对账锚（共享账号，无精确 token 换算）

- 最新快照（ZC-03 轮，2026-09-07 22:15 前后）：**五小时余 31%，周余 11%**。此前轮读数（52%/14%）为历史快照，不追溯修改。
- 重置（北京时间）：五小时窗 **09-08 02:19**；周窗 **09-11 21:23**。
- 停新任务阈值：五小时余 <20% 或 周余 <10%（本轮 31%/11% 已接近，周余仅高 1 个百分点）。
- **两张重置券：未获授权，不得使用。**

## 5. 复制即用的用户恢复提示词（完整中文，2026-09-07 22:16 更新）

> 继续三端协调。先读 `/Users/yusong/Downloads/new/full-system/docs/coordination/HANDOFF.md` 与 `README.md` 恢复上下文。三项贡献统一表述：①动态图谱建模更新；②图谱与证据约束的科研辅助工作流（含预警）；③导师监督的语义可视化反馈；学生画像只作展望。当前状态：ZCode 已交 ZC-01/ZC-02/ZC-03（消融口径勘误、三贡献映射修正、最小补证方案表），Antigravity 已交 AG-01/AG-02 并负责第三轮自身文档残留结论修正与贡献三论文素材，DeepSeek Harness 已交 DS-01、获准备份修正桌面报告并归档六来源核验到 agent-work/research/DS-02（仍在运行，勿打扰）。全部产物待 Codex 验收。约束：不改数据、代码、脚本、主论文、他人报告；不部署、不提交、不推送；没有证据就标未核实；共享账号配额低于五小时 20% 或周 10% 即停新任务，重置券未授权。

## 6. 产物清单与状态（全部待 Codex 验收；完成 ≠ 审核通过）

| 文件 | 写者 | 状态 |
| --- | --- | --- |
| ZC-01.md（含 ZC-02 更正） | ZCode | 已交，待验收 |
| 消融 md 日期勘误 | ZCode | 已交，待验收 |
| 创新点总览映射修正 | ZCode | 已交，待验收 |
| ZC-02.md | ZCode | 已交，待验收 |
| [ZC-03.md](ZC-03.md)（最小补证方案表） | ZCode | 已交，待验收 |
| **ZC-04.md（走查+试用展示+前端评估+DS对齐）** | ZCode | **2026-09-08 新建，待验收** |
| **ZC-05.md（零调用补证轮）+ `docs/experiments/innovation-supplement-2026-09-08.md`** | ZCode | **2026-09-08 新建，待验收**（D1 重算 4/4 一致、C1 追溯 1/15 vs 3/15、①-A 留痕降级、①-B B4 不可行；含阈值单位缺陷发现，详见 ZC-05 §3） |
| `docs/innovation/创新点试用展示-2026-09-08.md` + screenshots/ | ZCode | 新建，待验收 |
| `docs/innovation/创新点前端可用性评估-v1.md` | ZCode | 新建，可转派 AG 第四轮，待验收 |
| AG-01.md / AG-02.md | Antigravity | 已提交，待验收；第三轮文档修正进行中 |
| DS-01.md | DeepSeek | 已提交，待验收 |
| DS-02（agent-work/research/DS-02） | DeepSeek | 进行中，勿打扰 |
| README.md 索引 | ZCode | 随 ZC-03 同步更新，待验收 |

## 7. 目录重构补记（2026-09-08；本节由 DeepSeek Harness 代记，第 1-6 节仍为 ZCode 原文）

- 用户授权文档整理轮：仓库目录已重构 —— `scripts/` 按功能域分 7 子目录（gates/freeze/experiments/data/render/ops/audit），`backend/app` 重命名为 `backend/legacy/app`。
- 第 2 节提到的 `scripts/run_innovation_ablation.py` 现位于 `scripts/experiments/`（内容 0 改动，纯 rename）；2026-09-08 前的旧扁平路径一律按 `docs/README.md` 第三节《路径迁移对照表》解析。
- 原顶层 `CONVERSATION_MIGRATIONS/` 已移至本目录 `handoff/` 子目录。
- 任务历史与后续任务登记统一走 `docs/任务台账.md`（T-020/T-021/T-022 已记录本轮）。

