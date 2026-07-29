# 系统备份与恢复

## 覆盖范围

`scripts/backup-system.sh` 生成一个不可覆盖的备份目录，其中包含：

- `database.dump`：PostgreSQL custom-format dump；
- `storage.tar.gz`：`SYSTEM_STORAGE_PATH` 指向的上传文件目录；
- `manifest.txt`：格式版本、UTC 时间、应用版本和两个文件的 SHA-256。

嵌入模型缓存不进入备份，可以重新下载。备份脚本会短暂停止正在运行的 backend/frontend，再依次导出数据库和文件，避免业务写入跨越两个快照。

## 创建备份

先确认 `.env` 与当前部署一致、数据库健康且备份目标磁盘空间充足：

```bash
scripts/backup-system.sh
```

也可以指定一个尚不存在的目标目录：

```bash
scripts/backup-system.sh /secure/path/eln-20260716T120000Z
```

脚本不会覆盖已有目录。完成后应将整个目录加密复制到另一台设备或受控对象存储；仓库内的 `backups/` 已忽略，但它仍只是本机副本。

## 恢复

恢复会替换当前数据库和上传文件，只接受显式确认：

```bash
scripts/restore-system.sh /secure/path/eln-20260716T120000Z --confirm-replace
```

脚本按以下顺序执行：

1. 检查必需文件、清单版本和 SHA-256；
2. 用当前 PostgreSQL 的 `pg_restore --list` 验证 dump 可读；
3. 解压文件到同一文件系统的临时目录；
4. 自动创建 `backups/pre-restore-<UTC>` 回滚包；
5. 停止应用，重建业务数据库并恢复 dump；
6. 原子替换配置的持久存储目录；
7. 启动后端并等待 `/ready`，成功后再启动前端。

如果替换开始后失败，应用保持停止，错误信息会给出恢复前回滚包。排查原因后用该包再次执行恢复，不要在部分恢复的数据上继续写入。

## 非破坏性 smoke 与隔离恢复演练

成熟门禁不会在当前业务库上执行完整恢复，因为那会替换正在使用的数据。当前自动证据采用非破坏性 smoke：

```bash
scripts/backup-system.sh /private/tmp/eln-maturity-backup-$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_DIR=$(ls -td /private/tmp/eln-maturity-backup-* | head -1)
backend/.venv/bin/python scripts/restore_drill.py "$BACKUP_DIR" \
  --output docs/system-evidence/restore-drill-latest.json

backend/.venv/bin/python scripts/export_validation_evidence.py \
  --backup-dir "$BACKUP_DIR" \
  --verify-backup-dump \
  --restore-drill-report docs/system-evidence/restore-drill-latest.json \
  --load-smoke-report docs/system-evidence/load-smoke-latest.json \
  --restart-recovery-report output/playwright/restart-recovery.json
```

该检查会验证 `manifest.txt` 中的 SHA-256，用当前 PostgreSQL 容器执行 `pg_restore --list` 读取 `database.dump`，并通过 `scripts/restore_drill.py` 在临时 PostgreSQL 容器中恢复 dump、解压上传文件归档、记录 public table 数量和 storage 文件数。它不替换当前业务库，适合纳入成熟门禁。

该隔离演练仍不等于完整生产灾备：它不测量大数据量 RTO/RPO，不覆盖对象存储/异地复制，不验证反向代理/TLS，也不模拟宿主机整体损坏。完整恢复仍应在预生产环境定期执行。

## 生产灾备策略

上线前必须把本机备份升级为受控灾备流程：

1. 每次 `scripts/backup-system.sh` 产物生成后，先校验 `manifest.txt` 中的 SHA-256，再加密上传到受控对象存储或另一台独立设备；加密密钥不得与数据库、应用密钥放在同一主机。
2. 至少保留最近 7 个每日备份、4 个每周备份和 6 个每月备份；清理旧备份前先确认最近一次 `scripts/restore_drill.py` 通过。
3. 生产目标暂定 RPO ≤ 24 小时、RTO ≤ 4 小时；如果数据量增长导致恢复超过目标，先扩容或分层备份，再允许继续扩大正式数据集。
4. 每周抽取最新备份执行一次 `scripts/restore_drill.py` 隔离恢复演练；每月在预生产环境执行一次完整替换恢复，记录数据库表数、storage 文件数、耗时和操作者。
5. 对象存储访问使用最小权限账号；人员离开项目、密钥泄漏或设备丢失时，立即撤销旧访问凭据并重新加密最近一份可用备份。
6. 异地副本必须与生产宿主机、数据库 volume 和本机 `backups/` 不在同一故障域；仅有本机副本时不得声称生产灾备成熟。

## 2026-07-16 隔离往返记录

在独立 Compose 项目和独立 PostgreSQL volume 中完成了以下验证：

- 生产前端镜像构建成功并由 `next start` 提供页面；
- `/ready` 返回数据库和持久存储均正常；
- 写入唯一数据库表记录和 `SYSTEM_STORAGE_PATH` 文件；
- 创建一致性备份后删除表与文件；
- 执行带恢复前回滚包的完整恢复；
- 数据库值与文件内容均恢复为 `backup-restore-roundtrip-2026-07-16`；
- 恢复后的后端重新通过 `/ready`。
- 当前可复跑的标准脚本是 `scripts/restore_drill.py`；最新自动证据写入 `docs/system-evidence/restore-drill-latest.json`，并由成熟门禁校验。

这证明脚本的基本往返可用，不代表生产灾备已经完成。未完成项仍包括：大数据量恢复时间与磁盘水位测量、备份加密、异地复制、自动保留清理、定期恢复抽检，以及宿主机整体损坏演练。
