# 最终成熟门禁证据

`scripts/final_maturity_gate.py` 用于判断是否可以启动论文确认性人工评审。它比 `scripts/release_maturity_gate.py` 更严格：release gate 证明内部工程候选版健康，final gate 证明外部评审和生产运行前置条件已经真实满足。

当前 final gate 要求以下证据全部通过：

1. `docs/experiments/main-maturity-gate-latest.json` 中的内部门禁 `passed=true`。
2. `docs/system-evidence/production-config-latest.json` 与 `docs/system-evidence/validation-results.json` 内嵌的 `production_config` 均为 `status=passed`，不能是 `skipped_non_production`；两处还必须包含相同的 `env_file_sha256`、相同关键项清单和全部通过的结构化 `checks`，证明实际检查过同一份生产 env 文件，且汇总证据不是陈旧快照。
3. `docs/experiments/confirmatory-human-review-freeze.json` 通过 `scripts/validate_human_review_freeze.py`，至少包含 3 个项目、60 道问题、每项目至少 10 题、题号唯一、`question_index` 唯一、逐题冻结题干文本与 `gold_facts`、五方法集合、`model`、`prompt_version`、`random_seed`、两名独立评价人、评价人的真实 `user_id`、评价人仅具备 `can_evaluate=true`（其余项目内容、写入、审核和管理权限均为 `false`），以及 hash 校验文件。
4. `docs/system-evidence/long-soak-latest.json` 证明长时 soak 通过，当前最低要求是 4 小时和 1000 次请求。
5. `docs/system-evidence/tls-deployment-latest.json` 证明真实 HTTPS 入口、证书和 HSTS 已验证。
6. `docs/system-evidence/offsite-backup-latest.json` 证明异地加密备份、保留策略和最新恢复抽检已通过。
7. `docs/experiments/final-maturity-evidence-manifest.json` 必须验证通过，证明上述最终证据文件（包括独立 `production-config-latest.json`）在启动确认性人工评审前已经 SHA-256 冻结，未被后续替换。manifest 只接受 `--root` 内相对路径；绝对路径、Windows 绝对路径或 `..` 指向 root 外文件都不算有效证据。

## production-config-latest.json

正式证据必须来自生产配置文件，不能使用开发 `.env`：

```bash
backend/.venv/bin/python scripts/check_production_config.py \
  --env-file /secure/path/production.env \
  --output docs/system-evidence/production-config-latest.json
```

随后重新运行 `scripts/export_validation_evidence.py`、`scripts/freeze_final_maturity_evidence.py --replace` 和 `scripts/final_maturity_gate.py`。若独立报告或 `validation-results.json` 内嵌快照仍是 `skipped_non_production`，缺少 `env_file_sha256` / `checked_keys` / `checks`，任一生产检查未通过，或两处 SHA-256 / 关键项清单 / 结构化检查不一致，说明输入不是同一份可追溯生产配置，不能进入确认性人工评审。

## confirmatory-human-review-freeze.json

冻结包必须由未参与系统开发和回答生成的人整理，并通过：

```bash
backend/.venv/bin/python scripts/validate_human_review_freeze.py \
  docs/experiments/confirmatory-human-review-freeze.json \
  --root .
```

该校验会拒绝单项目开发题集、少于 60 题、项目分布过薄、重复题号、缺少或重复 `question_index`、缺少题干文本、缺少 `gold_facts`、未冻结完整五方法集合（`pure_llm`、`bm25_rag`、`project_rag`、`structured_query`、`kg_enhanced_rag`）、未冻结 `model` / `prompt_version` / `random_seed`、评价人缺少真实 `user_id`、评价人参与开发、评价人具有 `can_read/can_write/can_review/can_manage` 任一权限或缺少唯一允许的 `can_evaluate=true`，以及任何 hash 不匹配的冻结文件。

## long-soak-latest.json

可以继续使用 `scripts/soak_smoke.py` 生成更长时间的报告，但正式证据应在接近生产数据量、真实部署参数和目标并发下运行。当前最低要求是 4 小时、1000 次请求、无错误且 p95 ≤ 2000 ms。报告必须保留逐轮 `cycles` 明细；校验器会要求 summary 中的 cycle 数、请求数、成功数和错误列表与逐轮记录完全一致，避免只手写一个汇总 JSON 冒充长时稳定性证据。

```bash
ELN_PASSWORD=... backend/.venv/bin/python scripts/soak_smoke.py \
  --api-base https://eln.example.org \
  --username admin \
  --password "$ELN_PASSWORD" \
  --requests 100 \
  --concurrency 10 \
  --duration-seconds 14400 \
  --interval-seconds 300 \
  --output docs/system-evidence/long-soak-latest.json

backend/.venv/bin/python scripts/check_long_soak_report.py \
  docs/system-evidence/long-soak-latest.json \
  --output docs/system-evidence/long-soak-latest.json
```

校验器输出会保留原始 soak 字段并附加检查结果，因此该文件可直接作为 `scripts/final_maturity_gate.py` 的输入。

## tls-deployment-latest.json

该文件不是 Nginx 模板预检。它必须来自真实域名和真实证书的部署检查：

```bash
backend/.venv/bin/python scripts/check_tls_deployment.py \
  https://eln.example.org \
  --output docs/system-evidence/tls-deployment-latest.json
```

最终门禁会拒绝只手写顶层 `ok` / `certificate_valid` / `hsts_enabled` 的报告；文件必须保留 `scripts/check_tls_deployment.py` 生成的关键 `checks` 记录。HSTS 不能只是出现响应头，`max-age` 至少需要 31536000 秒。

## offsite-backup-latest.json

该文件必须对应真实离机或对象存储副本。只有本机 `backups/` 或 `/private/tmp` 备份时，不得置为通过。证据必须包含远端 URI，并绑定最新恢复演练报告的 SHA-256；`restore_drill_report` 必须是 `--root` 内的相对路径，不能指向 root 外文件。

```json
{
  "ok": true,
  "encrypted": true,
  "offsite": true,
  "target_uri": "s3://eln-backups/2026/07/16/eln.tar.age",
  "retention_policy_configured": true,
  "latest_restore_drill_passed": true,
  "restore_drill_report": "docs/system-evidence/restore-drill-latest.json",
  "restore_drill_sha256": "<sha256>"
}
```

```bash
backend/.venv/bin/python scripts/check_offsite_backup_evidence.py \
  docs/system-evidence/offsite-backup-latest.json \
  --root . \
  --output docs/system-evidence/offsite-backup-latest.json
```

校验器输出会保留原始备份字段并附加检查结果，因此该文件可直接作为 `scripts/final_maturity_gate.py` 的输入。

## 运行

```bash
backend/.venv/bin/python scripts/freeze_final_maturity_evidence.py --replace
backend/.venv/bin/python scripts/freeze_final_maturity_evidence.py \
  --verify docs/experiments/final-maturity-evidence-manifest.json

backend/.venv/bin/python scripts/final_maturity_gate.py
```

只有该命令 PASS 后，才允许启动确认性人工评审；否则只能做内部试评或继续工程硬化。
`scripts/release_maturity_gate.py`、`scripts/final_maturity_gate.py` 和 `scripts/confirmatory_review_completion_gate.py` 对损坏 JSON、非对象 JSON、字段结构异常或损坏的 manifest 都会视为失败证据并写入 FAIL 报告，不能靠工具异常中止绕过成熟判定。

## 评审完成门禁

`scripts/final_maturity_gate.py` 只判断能不能启动确认性人工评审；评审完成后，报告人工评价结论前还必须运行：

```bash
backend/.venv/bin/python scripts/freeze_confirmatory_review_evidence.py --replace
backend/.venv/bin/python scripts/freeze_confirmatory_review_evidence.py \
  --verify docs/experiments/confirmatory-review-evidence-manifest.json

backend/.venv/bin/python scripts/confirmatory_review_completion_gate.py
```

该门禁首先要求 `docs/experiments/final-maturity-gate-latest.json` 已经 PASS。随后它会重新校验冻结包，并检查 `docs/experiments/confirmatory-human-review-export.csv`：每个“问题—方法”必须完成、每项必须有两名评价人的 method-masked 评分、导出 `question_index` 集合和题干文本必须完全等于冻结问题集合、导出方法集合必须完全等于冻结方法集合、导出评价人 ID 必须完全等于冻结评价人的 `user_id`，导出条目数必须等于冻结问题数 × 方法数；正式 CSV 还必须包含一致的 `review_batch_id`（`R` + 12 位大写十六进制）、`export_protocol=confirmatory_human_review_v1` 和匹配当前最终成熟门禁文件的 `final_maturity_gate_sha256`，不能用旧导出或手工拼接 CSV 顶替。最后，`confirmatory-review-evidence-manifest.json` 必须覆盖最终成熟门禁、冻结包和导出 CSV 并验证通过。
