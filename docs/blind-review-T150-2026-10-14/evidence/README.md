> status: current
> owner: T150 evidence line / ai-engineer

# T150 盲审整改证据核验索引（2026-10-14）

本次补交导师报告 R3、R5、R9 所需的本地核验材料。已完成文件哈希核验、三个 Git 仓及六个提交的身份登记、选定原始记录的离线复算。**导师或未参与开发的第三方尚未独立验收，R3/R5/R9 均不能整体标为已解决。** 保存的 AI 评价可复算，不代表人类金标准已建立。

导师交付目录：`/Users/yusong/Desktop/盲审整改-T150-2026-10-14/导师核验材料/`；可移交的资料位于其中 `核验包/`。三个完整可达历史 bundle 位于本仓 `agent-work/t150-2026-10-14/evidence/history-private/`，未放入核验包。全历史可能含旧身份信息或历史敏感材料，其对外发布审查仍待完成。这里是导师内部核验材料，不能直接作为匿名盲审附件。

## 核验材料

| 相对路径 | 用途及边界 |
| --- | --- |
| `repository-identities.json` | main、T139、T141 三仓 HEAD、分支/引用、远程地址及带时间的 tracked dirty 状态；远程地址仅本地观察，未联网确认。 |
| `commit-map.json` | 报告中的六个短提交号对应完整 SHA、所在仓、源码档案完整 SHA256。 |
| `bundle-verification.json` | 三个全部引用加 HEAD 的历史 bundle 完整 SHA256、字节数、原仓及空仓 `git bundle verify` 退出码。范围为可达历史，不包含 reflog、不可达对象或未提交工作区。 |
| `current-source-snapshot.json` | 当前 Rust/Next.js 源码、锁文件、Compose、Dockerfile、迁移、测试、脚本的 408 文件快照。主仓为 dirty，该清单的整体哈希不是新 Git commit，也不是新测试/部署证据。 |
| `source-path-map.json` | 原路径 → 包内相对路径；每项完整 SHA256。脱敏派生文件同时登记原 SHA 和派生 SHA，明确不满足原件哈希。 |
| `historical-manifest-verification.json` | T114/T136/T139/T141/T148 历史清单逐项核验；16 个旧冻结源码与当前树不同但对应 b6 提交原 blob 一致，不能把后续修改误作历史材料损坏。 |
| `batch-code-map.json` | 各实验批次、运行时、冻结输入、代码身份和结果映射；历史 `unversioned` 批次继续保留缺口。 |
| `model-identities.json` | 336 条 DeepSeek 本地原始响应的请求/返回模型名、响应 ID、日期、usage；184 条 GPT 评价的 model 字段为 null，不能猜填。 |
| `excluded-files.json` | 含 JWT/Bearer 的早期失败日志及带凭据 URL 文件的未打包说明；模式筛查边界、受控核验要求。 |
| `reviewed-fixture-patterns.json` | 已核对的测试固定向量与隔离测试数据库字面量说明，防止把测试夹具误认为真实会话。 |
| `missing-items.json` | 14 个未完成或部分处理项目，以独立验收、原始历史、模型快照、人类复核等缺口逐项登记。 |
| `offline-computation-verification.json` | 本次离线复算结果和可重复入口；没有新模型调用或新生产测试。 |
| `delivery-receipt.json` | 最终包、相对路径文件清单和 ZIP 完整 SHA256及文件数。 |

包内原始资料保持 `docs/…`、`agent-work/…`、`data/real/GSE111619/…` 相对目录；生产源码位于 `current-source/`，六个历史源码筛选档案位于 `code-snapshots/`，本次核验元数据和脚本位于 `_T150/`。没有复制整个 agent-work，没有读取真实 `.env` 或密钥文件，没有将依赖、缓存或论文 Word/PDF 装入包。

## 可复算入口

使用 Python 3.12 或以上和可用的 `httpx` 依赖，在解压后的核验包中执行；输出目录必须是一个尚不存在的新路径：

```bash
python3 _T150/recompute_offline.py --package . --output /tmp/T150-offline-check-new
```

脚本仅检查包内原件哈希、历史源码档案和已保存的 JSON/JSONL；运行过程中禁止网络连接，并在新输出目录写入复算结果。T148 的旧脚本绝对路径读取被映射到包内相同哈希文件；不重新生成问题、标注、答案或生产测试结果。首次准备 Python 依赖可按环境通常方式安装 `httpx`，不需要模型密钥。

已复算：T114 的 40 条补充交叉评价及 144 条语义评价；T136 的 102 个冻结输入和 28 个条件样例原始图谱（12 正文、12 正确字段、4 旧样例）；T148 的 13 个冻结输入、48 条词法覆盖结果、200 条混合请求和 350 条短时请求明细。正文 F1=0，正确字段 F1=0.9733333333333334；两组新明细 p95=9.501708031166345 ms / 7.0653329603374 ms，与各自原汇总一致。

以上是**计算一致性**。T148 语义主要结局仍未计算；AI 参考关系和语义判分仍未经过独立人类复核；较新的 200/350 条明细不能补回旧 600 条请求日志。缺失的历史精确代码/数据库版本、GPT 精确型号、服务方不可变模型快照、服务端版本、后台账单和完整匿名化数据库 dump 均未伪造或回填。详见 `missing-items.json`。

## 导师随机核验建议

1. 校验 ZIP 外部 SHA256；解压后按 `SHA256SUMS.txt` 逐项检查。该清单不含自身，清单完整 SHA 记录在外部 `delivery-receipt.json`。
2. 任意抽取一个响应 ID、一个输入样例和一个图谱错误案例，从原记录追到提示词、上下文、冻结清单、代码身份和复算输出。
3. 在新 Python 环境运行上述离线入口，并记录执行人、时间、输出完整 SHA和验收意见。新环境成功仍不替代模型后台记录核对或人类专家标注。
4. 在受控本机检查三个完整 Git bundle；对外提供前逐项审查历史隐私。敏感日志原件未进入可移交 ZIP，不应以派生文件冒充原件。

本证据收集子任务未修改业务代码、历史证据、论文 Word 或旧实验文件；主线程另存匿名整改副本。是否达到送审要求，应由导师按缺失项和独立验收结果决定。
