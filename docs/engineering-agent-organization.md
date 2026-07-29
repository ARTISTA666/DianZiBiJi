# 工程 Agent 组织、分类与发布责任制

本项目按大型软件团队常见的“治理层 + 平台职能 + 领域小队 + 独立保障”方式协作。Agent 不是共享同一改动面的匿名执行器；每个 Agent 都有唯一职责、代码所有权、验收证据和升级边界。

## 1. 四层 Agent 分类

| 层级 | 类型 | 决策范围 | 典型 Agent | 是否直接改代码 |
| --- | --- | --- | --- | --- |
| L0 | 治理与集成 | 需求优先级、跨域契约、风险接受、最终集成 | 产品与工程负责人 | 可以，仅处理集成面 |
| L1 | 平台职能 | 公共技术能力和工程基础设施 | 后端平台、前端平台、数据平台、SRE、安全、研发效能 | 可以，仅限所有权范围 |
| L2 | 领域小队 | 面向完整业务价值流交付 | IAM/协作、OCR/知识、RAG/实验、管理/审计 | 可以，遵守平台契约 |
| L3 | 独立保障 | 测试、证据、合规和发布否决 | QA、韧性验证、Release Reviewer | QA 可改测试；Reviewer 只读 |

L0 对最终集成负责，但不能绕过 L3 门禁；L3 可以否决发布，但不能通过降低阈值或修改业务实现来制造“通过”。

## 2. Agent 注册表

| Agent ID | 层级 | 主要责任 | 默认所有权 | 必交证据 |
| --- | --- | --- | --- | --- |
| `eng_lead` | L0 | 需求拆解、优先级、跨层 API/数据契约、冲突仲裁、最终汇总 | 根目录契约、README、组织与发布文档 | 需求—实现—证据矩阵；P0/P1 处置结论 |
| `backend_platform` | L1 | Rust/Axum 公共服务、错误模型、事务边界、OpenAPI | `backend/src/`、`backend/sql/`、`backend/openapi.json` | `fmt`、`clippy -D warnings`、Rust 全量测试 |
| `frontend_platform` | L1 | Next.js 壳层、API 客户端、状态隔离、组件规范、可访问性 | `frontend/src/app/`、`frontend/src/lib/`、`frontend/src/components/ui/` | TypeScript 检查、生产构建、契约生成一致性 |
| `data_platform` | L1 | PostgreSQL schema、索引、迁移、锁顺序和数据生命周期 | `backend/sql/`、`backend/migrations/`、数据库初始化代码 | 新旧库迁移、约束测试、并发/死锁回归 |
| `sre_ha` | L1 | 启动、租约、恢复、备份、观测、容量和运行手册 | Docker、部署模板、健康检查、运行脚本 | 重启恢复、负载/soak、备份恢复、指标探针 |
| `security_engineering` | L1 | 认证防护、秘密管理、输入/导出安全、威胁边界 | 认证中间件、安全配置、导出策略 | 滥用/越权负测、生产配置预检、依赖审计 |
| `developer_productivity` | L1 | CI、可复现工具链、缓存、证据导出和 manifest | `.github/`、构建与验证脚本 | 干净环境 CI、失败可诊断、证据可重放 |
| `iam_collaboration` | L2 | 账号、小组、项目、成员、独立评价人和最小授权 | IAM/项目 API、对应前端页面和测试 | 权限矩阵、管理员不变量、TOCTOU/写偏差回归 |
| `ocr_knowledge` | L2 | 文件、OCR、人工校对、归档、知识图谱 | 文件/OCR/KG API 与页面 | 格式负测、校对确认、抽取质量与溯源证据 |
| `rag_experiment` | L2 | 入库、检索、问答、五方法实验、盲评 | RAG/Agent/实验 API 与页面 | 引用合法性、盲评脱敏、实验恢复与一致性 |
| `admin_audit` | L2 | 系统管理、审计可见性、操作留痕 | 管理端、审计 API 与页面 | 管理闭环 E2E、敏感操作审计、导出安全 |
| `qa_release` | L3 | 测试矩阵、关键路径 E2E、证据新鲜度和发布门禁 | 测试、fixture、证据门禁脚本 | 指定流程逐条通过；报告未过期且哈希可验证 |
| `resilience_validator` | L3 | 并发、故障注入、性能和恢复独立验证 | 只写测试与探针，不改业务实现 | 真实数据库竞态、强杀恢复、负载与恢复结果 |
| `release_reviewer` | L3 | 只读交叉检查、复现 P0/P1、审查证据强度 | 无写权限 | 可复现发现；逐项确认修复；独立发布意见 |

“所有权”表示默认写入边界，不表示知识孤岛。跨域改动必须由 `eng_lead` 指定一个主责 Agent；其他 Agent 通过契约测试或审查参与，避免多人同时修改同一区段。

## 3. 当前实例与逻辑岗位

| 当前实例 | 逻辑岗位 | 本轮职责 |
| --- | --- | --- |
| 主 Agent | `eng_lead` | 拆解、集成、验证矩阵与最终交付 |
| `iam_project_guard` | `iam_collaboration` + IAM 专项 Reviewer | 权限不变量、项目并发和独立评价人边界 |
| `ha_startup` | `sre_ha` + `data_platform` | 启动迁移、实验租约、恢复与备份链路 |
| `release_reviewer` | `release_reviewer` | 与实现隔离的最终 P0/P1 和证据审查 |

短期专项 Agent（例如认证限流、RAG 一致性）在任务完成后退出；其变更必须由长期所有者接管测试和运行手册，避免“临时 Agent 走后无人负责”。

## 4. 权限与职责边界

1. 实现 Agent 只能在分配范围内写代码；发现跨域问题时先提交最小复现和受影响契约。
2. `release_reviewer` 保持只读，不参与原实现，也不替实现者修复缺陷。
3. 安全边界、数据库不变量和分布式状态必须由服务端或数据库保证；前端隐藏不算权限控制。
4. 生产配置、真实外部服务、长期 soak 和人工评审缺失时必须显示为阻塞，不能用测试桩或内部数据代替。
5. 任何 Agent 不得重置、覆盖或清理无法确认归属的工作树改动。

## 5. 需求到发布的协作流水线

| 阶段 | Accountable | Responsible | Consulted / Reviewer | 退出条件 |
| --- | --- | --- | --- | --- |
| 需求与风险分级 | `eng_lead` | 对应领域小队 | 平台、安全、QA | 验收条件和 P0/P1 定义明确 |
| 契约与数据设计 | `eng_lead` | 平台 + 领域主责 | IAM、安全、SRE | API/schema/锁顺序可验证 |
| RED | 领域主责 | 领域主责或 QA | 独立保障层 | 失败可稳定复现且断言业务结果 |
| GREEN/重构 | 领域主责 | 实现 Agent | 平台所有者 | 目标测试通过，无弱化断言 |
| 跨层集成 | `eng_lead` | 前端/后端/数据所有者 | QA、SRE | 契约、构建、数据库回归通过 |
| 系统验证 | `qa_release` | QA + 韧性验证 | 各领域小队 | E2E、恢复、负载、备份证据齐全 |
| 独立审查 | `release_reviewer` | Reviewer | `eng_lead` 仅答疑 | P0/P1 清零或明确否决 |
| 发布决策 | `eng_lead` | QA/SRE 提供证据 | Security + Reviewer | 自动门禁通过，外部阻塞已解除 |

## 6. 缺陷分级与升级路径

| 等级 | 定义 | 响应规则 |
| --- | --- | --- |
| P0 | 数据破坏、系统不可用、认证绕过、秘密泄露、不可恢复错误 | 立即停止发布；`eng_lead`、安全和所有者共同处理 |
| P1 | 核心流程错误、越权、并发不变量破坏、可靠复现的死锁/恢复失败 | 本轮必须修复并由独立 Reviewer 复验 |
| P2 | 非核心功能退化、可恢复错误、明显可访问性或运维缺陷 | 建立测试和负责人；发布前显式接受或修复 |
| P3 | 文案、低影响体验和开发便利性问题 | 进入正常 backlog，不得伪装成 P0/P1 |

发现者负责提供最小复现、影响范围和证据；代码所有者负责修复；QA 负责回归；Reviewer 负责确认缺陷是否真正关闭。

## 7. 各价值流 RACI

| 价值流 | R | A | C | I |
| --- | --- | --- | --- | --- |
| 登录、账号、小组、项目成员 | `iam_collaboration` | `eng_lead` | Security、Data | QA、Reviewer |
| 笔记审批、资料审核 | `ocr_knowledge` | `eng_lead` | IAM、Frontend | QA |
| OCR、校对、归档、知识图谱 | `ocr_knowledge` | `eng_lead` | Data、RAG | QA、Reviewer |
| 入库、问答、五方法实验、盲评 | `rag_experiment` | `eng_lead` | IAM、Data、Security | QA、Reviewer |
| 系统管理与审计 | `admin_audit` | `eng_lead` | IAM、Security | QA、Reviewer |
| 多副本启动、租约、恢复、备份 | `sre_ha` | `eng_lead` | Data、Backend | QA、Reviewer |
| CI、证据冻结、发布门禁 | `qa_release` | `eng_lead` | Dev Productivity、SRE | 全体 |

R=执行，A=最终负责，C=必须会签，I=需获知结果。每条价值流只有一个 A，避免发布责任悬空。

## 8. 统一完成定义（Definition of Done）

一个功能只有同时满足以下条件才算完成：

1. 需求、失败模式和权限边界均有明确验收项。
2. 缺陷修复遵循 RED → GREEN → REFACTOR，并保留能防回归的断言。
3. 数据库约束、事务锁和服务端授权覆盖并发与绕过路径。
4. 目标单元/集成测试、上层回归、TypeScript/Rust 静态检查均通过。
5. 业务链路具备生产构建下的浏览器证据；控制台结果固化为机器可读产物。
6. 安全、恢复、依赖和负载证据与当前代码版本对应，且未超过新鲜度门限。
7. 独立 Reviewer 未留有未处置 P0/P1；P2/P3 有明确负责人和接受记录。
8. 生产外部条件未满足时保持发布门禁为红，不把“内部可运行”表述为“可生产发布”。

任何角色都不能单方面宣布发布完成；最终判断由 `eng_lead` 汇总独立审查、自动门禁和剩余外部证据后作出。
