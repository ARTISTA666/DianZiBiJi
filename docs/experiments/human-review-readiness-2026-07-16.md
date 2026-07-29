# 人工评审启动门槛（2026-07-16）

## 结论

当前 **可以准备受控内部试评，但不启动论文确认性人工评审**。评审页面已具备技术可用性，且 `docs/experiments/main-maturity-gate-latest.md` 中的内部自动成熟门禁已经通过；但这仍是开发方内部自动证据，不等于外部冻结语料、独立评价人和长时间生产 soak 已完成。更严格的 `scripts/final_maturity_gate.py` 已把这些条件固化为最终门禁，当前结果为 FAIL。

正式确认性评审的阻塞项包括两类：一是目前只有短并发、非破坏性备份 smoke 和隔离恢复证据，尚未完成数小时至数天的长时间、大语料、多进程和接近生产容量的运行验证；二是正式证据包尚未齐全，现有回答来自开发者整理的单项目内部题集，外部冻结的多项目问题、标准事实以及两名真实评价人仍未落实。

最新最终成熟门禁见 `docs/experiments/final-maturity-gate-latest.md`。该门禁当前明确阻塞：生产配置尚未在 `APP_ENV=production` 下通过、`confirmatory-human-review-freeze.json` 缺失、经 `scripts/check_long_soak_report.py` 校验的长时 soak 证据缺失、经 `scripts/check_tls_deployment.py` 生成的真实 TLS 部署证据缺失、经 `scripts/check_offsite_backup_evidence.py` 校验的异地加密备份证据缺失。
这些证据文件的最小结构见 `docs/operations/final-maturity-evidence.md`。

## 已达到的技术条件

- 独立评价账号只进入专用工作区，不显示方法、模型、运行顺序和管理日志。
- 页面按单条展示问题、匿名回答和中性证据，支持进度、前后导航和提交后自动继续；盲评入口已显式提示“正式评审前必须冻结题集、语料和评分规则”，并区分无批次、无待评记录和批次完成状态。
- 两名评价人的记录互不覆盖；提交后不能修改；负面判断必须说明原因。
- RAG 回答保存引用审计，能识别缺失引用和不存在的 `[S]`、`[G]` 编号。
- 固定任务 Agent 会检查 `[N]`、`[F]`、`[R]` 引用，失败时自动修订一次并再次复核。
- 混合检索使用向量候选与 BM25 候选并集，不再只是向量候选内的词法重排。
- 归档资料会清除向量块和同步记录，检索端同时过滤非审核/非同步资料；归档或作废笔记会退出图谱和搜索索引。
- Agent 引用复核仍失败时状态为 `needs_review`，不再显示为已完成。
- 实验请求先持久化执行计划并返回 `202 queued`，后台逐条结算进度；重复领取同一批次由条件更新拒绝，页面可离开后继续轮询。
- 非预期实验执行异常会把运行标记为 `failed`，记录未执行用例，不再永久停在 `running`；未执行记录导出为 `not_executed`，不再误报为模型失败。
- 单进程后端在启动时会把进程中断遗留的 `running` 实验结算为 `interrupted`，且只允许用户显式续跑。隔离环境中已实际在模型调用期间向后端发送 `SIGKILL`，重启后识别中断并续跑至 1/1 完成。
- DeepSeek 客户端会对 429、5xx 和传输异常作有限重试，尊重有上限的 `Retry-After`，并明确处理空回答和无效 JSON；对应故障分支已有自动测试。
- 真实 DeepSeek 微型回归 3/3 通过，覆盖精确指令、无证据拒答和单来源引用；只记录答案哈希、字符数、token、请求 ID 与延迟，不落盘提示词或答案。该结果仅证明最小链路可用，不代表 RAG/Agent 效果成熟。
- 所有 HTTP 响应返回可追踪的 `X-Request-ID`，前端错误提示包含请求号；请求日志不记录请求正文或密钥。
- 后端提供 `/metrics` 运行指标端点，暴露请求总数、状态码分组、in-flight、平均/最大/p95 延迟和版本；系统证据导出和成熟门禁会校验该端点可用。
- `scripts/check_monitoring_alerts.py` 已提供可 cron/CI 调用的告警探针，当前阈值检查 `/ready`、错误率、in-flight 和 p95 延迟；最新证据显示 178 个请求、错误率 0。
- 已提供 `deploy/nginx.conf.template` 和 `scripts/check_reverse_proxy_config.py`，覆盖 HTTP→HTTPS、TLS 证书占位符、HSTS、上传体积限制、反代超时、`X-Forwarded-*` 和 `X-Request-ID`；成熟门禁会校验该模板。
- 生产配置拒绝默认密钥、默认初始密码和演示数据；退出和改密会撤销旧令牌。
- 已新增 `docs/operations/secret-rotation.md` 和 `scripts/check_secret_rotation_runbook.py`，覆盖 `SECRET_KEY`、管理员/用户密码、`POSTGRES_PASSWORD`、`DEEPSEEK_API_KEY` 的备份、变更、验证、回滚和旧凭据撤销；成熟门禁会校验该 runbook。
- `docs/operations/backup-restore.md` 已补充生产灾备策略，覆盖加密副本、异地复制、保留周期、RPO/RTO、每周/每月恢复抽检和旧访问凭据撤销；`scripts/check_backup_policy.py` 与成熟门禁会校验该策略存在。
- `/ready` 同时检查 PostgreSQL 与上传文件持久目录；前端只在后端真正就绪后启动。
- 前端使用生产构建与 `next start`，不再通过源码挂载和开发服务器伪装部署状态。
- PostgreSQL 与上传文件的一致性备份、哈希校验、恢复前回滚包和恢复后就绪检查已实现；`scripts/restore_drill.py` 可在临时 PostgreSQL 容器和临时 storage 目录中执行非破坏性隔离恢复演练。
- 前端生产依赖审计为 0 个已知漏洞（2026-07-16 npm 官方审计结果）。
- 隔离浏览器验收 3/3 通过，覆盖审批、OCR 校对入库、RAG 问答、五方法实验和盲评提交。
- `scripts/run-system-e2e.sh` 已在 2026-07-16 重新通过完整链路：重建隔离 Compose 环境、浏览器 3/3、模型调用期间强杀后端并显式续跑至 completed、90 次并发读探针 90/90 成功，p95 28 ms。
- 主系统完成 90 次、并发度 10 的短读探针，90/90 成功，p95 43 ms、最大 51 ms；这是冒烟验证，不是容量结论。
- 已新增 `scripts/soak_smoke.py`，可按固定时长重复执行读探针并落盘每轮结果；当前成熟门禁只要求短 soak smoke，不代表数小时至数天稳定性已经完成。
- 主系统非破坏性备份 smoke 通过，`database.dump` 与 `storage.tar.gz` 的 SHA-256 和清单一致，并通过当前 PostgreSQL 容器的 `pg_restore --list` 可读性检查；隔离恢复演练已恢复 26 张 public 表和 28 个 storage 文件。
- 内部自动成熟门禁已汇总 RAG/Agent、运行态、Playwright、load smoke、备份 smoke、灾备策略和 KG 核验，当前结果为 PASS、0 failures；门禁输入证据已由 `docs/system-evidence/maturity-evidence-manifest.json` 冻结 15 个文件的 SHA-256，并在门禁中重新校验。

## 正式确认性评审仍未达到的门槛

1. 使用真实 DeepSeek、实际嵌入模型和外部冻结的多项目语料执行完整回归集，覆盖正常、无证据、无效引用、Agent 修订、模型超时与限流。当前自动门禁主要证明单项目内部题集和系统链路健康。
2. 对大语料、多用户并发和长批次实验做数小时至数天持续运行验证，并保存 `scripts/soak_smoke.py` 或更强负载工具的完整报告。当前队列和全局容量限制只适用于一个后端进程；多进程部署前必须引入跨进程持久任务队列或数据库租约。
3. 在接近生产的数据量上重复迁移和恢复演练，并实际落地备份加密、异地复制、保留期限与周期性恢复抽检；当前只是策略和脚本门禁已补齐。
4. 补齐真实证书部署、错误聚合、容量阈值和反向代理上线操作手册。
5. 解决确认性评测自身的外部冻结题集、评价人和预注册问题。

## 正式评审必须全部满足

0. `backend/.venv/bin/python scripts/final_maturity_gate.py` 必须 PASS；若该门禁失败，不得启动确认性人工评审。
1. 由未参与系统开发和回答生成的人员冻结至少 3 个项目、60 道问题及逐题标准事实。
2. 保存语料、问题、标准事实、模型、提示词和随机种子的冻结清单与哈希；生成回答后不得改题或删题。
3. 五种方法按同一问题、同一重复次数随机执行，运行失败必须保留并说明，不能静默剔除。
4. 确定两名真实评价人并创建两个独立账号，只授予 `can_evaluate=true`；`can_read/can_write/can_review/can_manage` 均保持 `false`。
5. 先用不属于正式批次的 5～10 条训练样例校准评分规则，再分别完成正式批次全部回答。
6. 两人完成前不解盲、不讨论具体答案；分歧由第三人复核，但保留原始两份评分。
7. 仅在两名评价人均完成后导出 CSV，并运行 `scripts/summarize_system_reviews.py`；完整性检查失败时不得生成正式结论。
8. 正式冻结包必须先通过 `scripts/validate_human_review_freeze.py`：至少 3 个项目、60 道问题、每项目至少 10 题、题号唯一、`question_index` 唯一、逐题 `gold_facts`、完整五方法集合、`model`、`prompt_version`、`random_seed`、两名独立评价人、评价人的真实 `user_id`、评价人仅具备 `can_evaluate=true` 且无项目内容读取权，以及所有语料/规则文件的 SHA-256。
9. 正式评审完成后，`backend/.venv/bin/python scripts/confirmatory_review_completion_gate.py` 必须 PASS，才能报告人工准确率、可追溯率或质量分。

## 当前推进顺序

1. 可先启动不计入论文结论的 5～10 条受控内部试评，用于验证评分说明、页面交互和导出流程。
2. 同步组织外部人员冻结多项目问题与标准事实。
3. 补真实 TLS 证书部署、异地灾备和长时 soak。
4. 外部冻结包通过 `scripts/validate_human_review_freeze.py`、长时运行和灾备证据全部通过后，再启动两名独立评价人的正式盲评。
5. 两名评价人完成且 `scripts/confirmatory_review_completion_gate.py` PASS 前，不解盲、不报告人工准确率、可追溯率或主观质量分。

在正式盲评完成前，论文只能写“人工评价工具和流程已实现，且内部自动成熟门禁和浏览器验收通过”，不能写“确认性人工评价已经证明某方法更优”。
