# Night Backlog

> 只记录基于真实代码和证据发现的问题。优先级按协议公式：`Paper Value × 2 + User Value + Stability Value + Demo Value + Test Value - Risk × 2 - Scope Cost`。

| ID | Problem | Severity | Paper Value | User Value | Stability Value | Demo Value | Test Value | Risk | Scope Cost | Priority | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| N-001 | 需要把初始化审计、真实流程、测试入口和外部阻塞集中成可追溯夜间上下文 | P2 | 5 | 3 | 4 | 4 | 5 | 0 | 1 | 25 | READY / 本轮文档任务 |
| N-002 | 现有巨大未提交改动使局部回归范围和归属难以判断，需要建立不覆盖用户工作的基线说明 | P1 | 4 | 4 | 5 | 3 | 4 | 0 | 1 | 23 | DONE by NIGHT_CONTEXT |
| N-003 | Rust 生产运行时与历史 Python 测试共存，测试入口容易误判为生产覆盖；需要在不改业务的前提下补充运行时验证记录 | P2 | 5 | 3 | 4 | 3 | 5 | 1 | 2 | 20 | DONE by NIGHT_CONTEXT + Iteration 1 |
| N-004 | Agent 自动质量报告已明确 human review pending，无法把自动分数当作最终科研结论 | P1 | 5 | 3 | 4 | 4 | 1 | 1 | 2 | 20 | NEEDS_OWNER_DECISION |
| N-005 | 最终 maturity gate 仍受生产配置、4 小时 soak、TLS、异地备份和人工冻结等外部条件阻塞 | P1 | 5 | 2 | 4 | 4 | 4 | 0 | 3 | 17 | NEEDS_OWNER_DECISION |
| N-006 | 当前高风险代码面被用户既有修改覆盖，继续改业务实现可能混淆归属和引入回归 | P1 | 4 | 2 | 5 | 2 | 3 | 4 | 4 | 10 | BLOCKED for night |
| N-007 | 开发环境前端/API 使用 `127.0.0.1` 与 `localhost` 的 host 别名不一致时，HttpOnly cookie 不随跨站请求发送，浏览器登录后无法恢复会话 | P2 | 3 | 3 | 3 | 3 | 4 | 2 | 2 | 12 | MITIGATED / 健康检查已提前拦截，策略仍需 Owner 确认 |
| N-008 | 浏览器冒烟记录 `/favicon.ico` 404 与密码输入缺少 `autocomplete` 建议 | P3 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 5 | DONE / icon.svg 与认证表单语义已补齐 |
| N-009 | CSV 实验/盲评导出绕过主 API 请求封装，认证失效时不会统一跳转登录或解析 request-id | P2 | 4 | 3 | 4 | 4 | 4 | 1 | 1 | 21 | DONE / 统一复用 apiFetch Blob 解析 |

## Candidate Selection Notes

- N-001/N-002 属于协议要求的初始化工作，范围仅为新增记录文件，已执行。
- 下一项只从“未覆盖既有改动、可局部验证、论文价值清晰”的任务中选择；若只能修改重叠业务代码，则暂停并记录 `NEEDS_OWNER_DECISION`。
- 不把缺失真实人工评审、生产配置或长期 soak 伪装成可由本地夜间代码修改解决的问题。
- N-007 在 README 推荐的 `localhost` 入口下不复现；若要支持任意 loopback host，需要由项目所有者决定统一 host、反向代理同源 API 或调整 cookie 策略，不能在夜间擅改安全边界。
- N-007 本轮新增了前端/API host 一致性健康检查；只提前报告配置错误，不改变认证或 cookie 策略。
- N-008 本轮以 Next 的 `src/app/icon.svg` 提供应用图标，并为登录、改密和创建账号表单补齐密码管理器语义；当前源码构建已验证生成图标链接。
- N-009 本轮仅将两个 CSV 下载调用统一到 `apiFetch`，保留 Blob 返回类型；lint、typecheck 和 build 均通过。
