# 智能体安全性质测试证据(创新点三)

- 证据等级:`INTERNAL_DEVELOPMENT / ENGINEERING_TEST`,仅证明机制性质成立,不产生任何方法优越性或质量结论。
- 日期:2026-08-28。基线 commit:`bbe72eb`(工作区含未提交改动,新增测试位于 `backend/src/api/agent_runtime.rs` 测试模块)。
- 运行环境:macOS arm64,Rust 1.88.0(`rust-toolchain.toml` 固定),隔离测试库 pgvector/pg16(`docker-compose.test-db.yml`,项目 `eln-rust-test-db`)。

## 新增测试(3 项,Rust 集成测试)

| 测试函数 | 验证性质 |
| --- | --- |
| `high_risk_tool_waits_for_confirmation_and_rejection_blocks_execution` | 高风险工具 `review_note` 经 MCP 调用时进入确认队列(`confirmation_required`)而不执行;拒绝后动作关闭,再确认返回 409;执行键从未落库 |
| `confirmed_action_executes_once_and_same_key_replays_cached_result` | 确认后真实执行(笔记 DRAFT→APPROVED)且执行键仅落库一次;同 key 重复调用返回同一已完成动作(创建去重,唯一约束);对已完成动作再确认返回 409;执行键已存在且参数哈希不同则确认被拒(防同键异参复用) |
| `expired_or_consumed_pending_actions_cannot_be_confirmed` | 过期待确认动作的 approve/reject 均返回 409;已完成(completed)动作不可再次确认 |

即幂等防重放由三层共同保证:①创建去重(`agent_pending_actions` 唯一约束 `(user_id, tool_name, idempotency_key)`,去重不过滤状态);②确认时执行键缓存与参数哈希校验;③`tool_execution_keys` 主键约束拒绝同键二次写入。

## 运行记录(摘录)

```
$ TEST_DATABASE_URL=... cargo test --locked --all-targets --no-default-features \
    agent_runtime::tests -- --test-threads=1
running 8 tests
test api::agent_runtime::tests::confirmed_action_executes_once_and_same_key_replays_cached_result ... ok
test api::agent_runtime::tests::expired_or_consumed_pending_actions_cannot_be_confirmed ... ok
test api::agent_runtime::tests::high_risk_tool_waits_for_confirmation_and_rejection_blocks_execution ... ok
...(模块内 5 项既有单元测试)...
test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 254 filtered out
```

- 全量套件:`scripts/run-rust-db-tests.sh` 通过(隔离库,lib 目标 264 项 + bin 目标 2 项,含上述 3 项新测试);`cargo fmt --all --check` 与 `cargo clippy --locked --all-targets --all-features -- -D warnings` 通过。
- legacy Python 套件(同一提交,SQLite 模式):`backend/.venv/bin/python -m pytest tests -q` → **346 passed, 11 skipped**(10.43s)。

## 论文口径映射

- 7.2 节安全边界测试:可新增"确认队列与幂等防重放"条目引用本证据。
- 7.2 节"共 105 个用例"的过期数字:Python 实际 346 通过/11 跳过;Rust 264 项(含本 3 项)。
- 1.5/8.2 创新点三的验证表述:确认队列与幂等防重放不再缺专项测试。
