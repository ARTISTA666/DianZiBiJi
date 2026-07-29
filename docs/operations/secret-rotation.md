# 密钥与凭据轮换手册

本手册用于生产环境的计划轮换和疑似泄漏应急轮换。轮换前必须明确维护窗口、负责人、回滚人和验证人；不要在聊天、截图或日志中粘贴真实密钥。

## 覆盖对象

- `SECRET_KEY`：JWT 签名密钥。轮换后所有旧访问令牌都会失效，所有用户需要重新登录。
- `BOOTSTRAP_ADMIN_PASSWORD`：仅用于首次创建管理员；已存在管理员应通过系统用户管理或 `/users/me/password` 改密。
- 用户密码：管理员重置或用户自助改密会增加 `auth_version`，旧 token 立即失效。
- `POSTGRES_PASSWORD`：数据库账号密码，必须与 `.env`、数据库角色和后端容器同步变更。
- `DEEPSEEK_API_KEY`：外部模型 API key，只注入后端，不写入前端构建产物。

## 通用前置步骤

1. 创建当前一致性备份，并保存到离机位置：

   ```bash
   scripts/backup-system.sh /secure/backups/eln-before-secret-rotation-$(date -u +%Y%m%dT%H%M%SZ)
   ```

2. 运行当前成熟证据链中的健康检查，确认不是带故障轮换：

   ```bash
   backend/.venv/bin/python scripts/check_monitoring_alerts.py --api-base https://ELN_DOMAIN/api
   backend/.venv/bin/python scripts/check_secret_hygiene.py --output docs/system-evidence/secret-hygiene-latest.json
   ```

3. 准备新 secret，长度和来源必须满足生产预检；不要复用旧值。

## `SECRET_KEY` 轮换

1. 生成至少 32 字符的新随机值，写入生产 secret store 或 `.env`。
2. 重启后端容器：

   ```bash
   docker compose up -d --no-deps backend
   ```

3. 验证 `/ready`、`/metrics` 和登录流程。
4. 预期影响：所有旧 JWT token 失效，用户需要重新登录。
5. 回滚：若新密钥导致登录不可用，恢复轮换前备份的 `SECRET_KEY` 并重启后端；确认旧 token 行为后再重新安排轮换。

## 管理员和用户密码轮换

1. 管理员为用户重置密码，或用户使用“修改密码”自助改密。
2. 系统会增加该用户的 `auth_version`，旧 token 失效。
3. 验证：旧 token 访问 `/auth/me` 失败，新密码登录成功。
4. 回滚：不恢复旧密码；如新密码丢失，由管理员再次重置。

## `POSTGRES_PASSWORD` 轮换

1. 确认已有可恢复备份，并记录维护窗口。
2. 在数据库内修改业务用户密码：

   ```bash
   docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -c "ALTER USER \"$POSTGRES_USER\" WITH PASSWORD 'NEW_STRONG_PASSWORD';"
   ```

3. 同步更新生产 secret store 或 `.env` 中的 `POSTGRES_PASSWORD`。
4. 重启后端并验证 `/ready`、迁移状态和登录。
5. 回滚：用旧密码再次执行 `ALTER USER`，恢复 `.env`，重启后端。

## `DEEPSEEK_API_KEY` 轮换

1. 在 DeepSeek 控制台创建新 key，不删除旧 key。
2. 写入生产 secret store 或 `.env`，重启后端。
3. 运行最小真实模型回归：

   ```bash
   backend/.venv/bin/python scripts/validate_real_llm.py
   ```

4. 验证 RAG 问答和 Agent 探针。
5. 确认新 key 正常后，在 DeepSeek 控制台撤销旧 key。
6. 回滚：若新 key 失败，恢复旧 key 并重启后端；修复原因后重新轮换。

## 轮换后必须执行

```bash
backend/.venv/bin/python scripts/check_production_config.py --output docs/system-evidence/production-config-latest.json
backend/.venv/bin/python scripts/check_secret_hygiene.py --output docs/system-evidence/secret-hygiene-latest.json
backend/.venv/bin/python scripts/check_monitoring_alerts.py --api-base https://ELN_DOMAIN/api --output docs/system-evidence/monitoring-alerts-latest.json
```

通过后记录轮换时间、操作者、验证人、涉及 secret 名称、是否回滚、旧凭据撤销时间。不要记录 secret 值本身。
