# 方法隐藏人工评价验证记录

> 2026-07-28 安全加固说明：下文保留 2026-07-12 的历史验收事实；当前独立评价账号已收紧为 `can_read=false, can_evaluate=true`，不得据此文旧权限重新配置账号。

验证日期：2026-07-12

## 运行接口验证

使用项目 3 的独立评价账号进行只读验收：

| 检查项 | 结果 |
| --- | ---: |
| 访问原始问答日志 | HTTP 403 |
| 访问模式统计 | HTTP 403 |
| 访问实验列表 | HTTP 403 |
| 尝试运行问答 | HTTP 403 |
| 访问匿名批次 | HTTP 200 |
| 访问匿名回答 | HTTP 200 |
| 管理者访问匿名批次 | HTTP 403 |
| 管理者访问原始日志 | HTTP 200 |

独立评价账号权限为：`can_read=true`、`can_evaluate=true`，其余写入、审核和管理权限均为 `false`，并且不是项目负责人。项目中共有 3 个匿名批次、34 条待评价回答。本次抽取一个含 2 条回答的批次检查返回结构。

匿名批次只返回 `batch_id`、`total_items` 和 `completed_items`。匿名回答只返回 `blind_id`、`question`、`answer`、`evidence` 和当前评价人自己的 `evaluation`。

对返回 JSON 检查以下显式泄露项，结果均未命中：

- `rag_mode`
- `query_log_id`
- `model_name`
- `relation_id`
- `[G1]`
- “图谱关系”

评价协议字段已加入运行 API。独立页面提交时保存为 `method_masked`；管理视图提交时保存为 `unblinded`。项目管理者不能调用方法隐藏接口。

## 自动测试

- 严格盲评权限、字段隐藏和中性证据编号已加入 API 测试。
- 两名评价者独立保存、不相互覆盖及 Cohen’s kappa 计算已加入 API 测试。
- 评价记录保存 `method_masked` 或 `unblinded` 协议；管理者不能提交方法隐藏评分。
- 系统导出汇总脚本会拒绝混入的非盲评分。
- 后端全量测试：`125 passed`。
- 实验脚本测试：`25 passed`。
- 前端 TypeScript 检查：通过。

## 数据库验收

运行数据库结构检查结果为 `ok: true`：

- `file_ocr_results` 表存在且字段齐全；
- 人工评价表包含 `review_protocol`；
- `(query_log_id, evaluator_user_id)` 联合唯一约束存在；
- 旧的单评价者唯一约束不存在。

## 评分数量

本次验收是只读操作。验收前人工评价为 0 条，验收后仍为 0 条，没有自动提交或伪造任何评分。

机器可读运行报告：`blind-review-runtime-2026-07-12.json`。SHA-256 为：

`791908fae563ce6dd1ba5026a5aeefa469893b1224896bc832c35777ee012ae7`

## 当前边界

本记录证明方法隐藏接口、多评价者数据结构、评价协议留痕和运行数据库迁移可用，不代表真实人工评分已完成。确认性结果仍需两名真实评价者独立完成同一批回答。

当前数据库只有 1 个独立评价账号，实验 4 有 24 条待评回答，评分数仍为 0。实际执行步骤见 `human-review-current-status-2026-07-12.md`。

可使用以下命令重复检查运行数据库：

```bash
docker compose exec backend python scripts/verify_runtime_schema.py
```
