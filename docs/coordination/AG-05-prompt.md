> status: historical
> owner: 历史协作记录（T160仅补状态头，正文保持）

# AG-05 · 预警阈值单位 UX 根修 + 建议采纳/忽略按钮接线（前端第四轮续）

> 唯一写者：Antigravity（前端线）。派工依据：用户 2026-09-11 授权"修 bug + 整理验收清单"，由 ZCode（证据线）代写本工单。
> 状态：待接单。
> 口径基线：三贡献（①动态图谱建模更新 ②图谱/证据约束的科研辅助工作流含预警 ③导师监督的语义可视化反馈）。
> 边界：只改 `frontend/src/`；不改后端、不改论文主稿、不改他人报告；完成后跑 `npm run lint` + `npm run typecheck` + `npm run build` 三连并写入本文件验收节。

---

## 1. 背景一句话

后端已在写入端拒绝占比类指标的百分数阈值（Q-11 根修，ZC-06），但前端输入框仍在"裸数字"状态，用户看到 80% 的读数却要填 0.8，这正是当初 80/95 被录进库的根因。

## 2. 任务 A：预警阈值输入单位 UX（P1）

文件：`frontend/src/components/project-alerts.tsx`（`ThresholdRow` 组件 + `METRIC_UNIT`）。

要求：
1. **占比类指标**（`return_rate`、`progress_deviation`）输入框标注"%"或"0-1 小数"，占位符用小数示例（如 `0.7`）；
2. 保存前校验：占比类指标值必须 `0 ≤ x ≤ 1`，超界禁用保存按钮并给出行内提示（文案参考后端："占比阈值口径为 0-1 小数，如 0.8 表示 80%"）；
3. 展示侧读数已是百分号显示（`formatValue`），保持一致即可，不要改显示逻辑；
4. 非占比指标（小时/天）不加 0-1 上限。

注意：后端已加硬校验，前端错误提交会收到 400（`detail` 字段含中文说明），`getErrorMessage` 已能透出——但 UX 目标是让用户根本走不到 400。

## 3. 任务 B：建议采纳/忽略按钮接线（Q-12，B2 后端已就绪）

后端端点已上线（commit 8494edc，运行栈已部署）：
- `POST /projects/{id}/agent/next-step-suggestion/feedback`，body：`{ suggestion_key, status: "accepted"|"ignored", mode, related_labels: string[], summary }`；同一 `(project, suggestion_key)` 幂等覆盖。
- `GET /projects/{id}/agent/next-step-suggestion/feedback` 返回留痕列表。
- 请求结构与校验规则见 `backend/src/api/agent_suggestion.rs` 的 `SuggestionFeedbackRequest`（先跑 `npm run generate:api` 同步 `api-schema.d.ts`，若有生成差异一并提交）。

改法建议（可按实际代码调整）：
1. `frontend/src/lib/api.ts` 新增 `recordSuggestionFeedback` / `listSuggestionFeedback` 两个函数；
2. `frontend/src/app/(dashboard)/projects/[id]/ai/page.tsx` 建议卡片（约 205-245 行）每条建议加"采纳 / 忽略"两个小按钮：
   - `suggestion_key`：用建议内容哈希（title+rationale 稳定串，后端注释即此口径，1-120 字符）；
   - `mode` 直接透传 `suggestion.mode`（`llm` / `rule_based`）；
   - 点击后本地置状态（已采纳/已忽略），重复点击可改主意（幂等覆盖）；
3. 不要为按钮单独调 LLM 或改建议生成逻辑，纯留痕。

## 4. 验收标准（Codex 按此勾）

- [ ] 占比阈值输入 80 会被前端拦截（不发出请求），输入 0.8 可保存成功
- [ ] 建议卡片出现采纳/忽略按钮，点击后刷新页面状态可见（后端 GET 可查到留痕行）
- [ ] `npm run lint` / `typecheck` / `build` 三绿
- [ ] openapi 生成类型同步（如无 diff 说明即可）

## 5. 交付与登记

- 完成后在本文件追加"## 6. 交付记录"（改动文件清单 + 三连输出摘要）；
- 台账登记：在 `docs/任务台账.md` 新增一行（ID 接现有编号顺延，执行方=AG）；
- 提交只 add `frontend/src/` 与本文件，commit message 标 `[前端线]`。
