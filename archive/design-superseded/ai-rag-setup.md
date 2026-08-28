# 本地 RAG 与 DeepSeek 配置及实验复现

## 1. 组件

系统使用以下开源组件：

- `BAAI/bge-m3`：生产使用的多语言文本嵌入模型（1024 维）
- OpenAI-compatible embedding endpoint：Rust 后端唯一生产语义向量入口
- `rust-hash-512-v1`：仅 development/test 的确定性测试替身
- PostgreSQL + pgvector：向量存储和余弦距离检索
- pypdf：PDF 文本提取

DeepSeek 仅承担基于检索上下文的答案和固定任务草稿生成。

## 2. 环境变量

```env
AI_PROVIDER=deepseek
AI_BASE_URL=https://api.deepseek.com
AI_API_KEY=your-official-api-key
AI_MODEL=deepseek-v4-flash
# 迁移期仍兼容 DEEPSEEK_API_BASE_URL / DEEPSEEK_API_KEY / DEEPSEEK_MODEL

EMBEDDING_BACKEND=openai_compatible
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_API_URL=https://embedding.example.org/v1/embeddings
EMBEDDING_API_KEY=your-provider-key
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=120
RAG_RETRIEVAL_TOP_K=6
RAG_VECTOR_CANDIDATE_K=30
RAG_RETRIEVAL_STRATEGY=rrf-v1
RAG_INDEX_VERSION=structured-v1
RAG_GRAPH_TOP_K=10
RAG_GRAPH_MIN_SCORE=1.0
```

修改嵌入模型、向量维度或 `RAG_INDEX_VERSION` 后，旧同步记录会标记为 stale，必须显式重建项目索引。生产环境不能使用 `hash` 后端；Rust 的配置检查会直接拒绝该组合。`RAG_RETRIEVAL_STRATEGY=legacy-weighted` 是迁移期检索回滚路径。

## 3. 数据进入条件

- 只有 `knowledge_document` 类型资料可进入 RAG。
- 只有审核状态为 `approved` 的资料可索引。
- 选择实验模板的笔记必须使用启用模板声明的结构化字段；服务端会校验模板、实验类型和字段名，防止结构化数据漂移。
- 草稿笔记不会进入知识图谱。
- 审核通过的笔记会触发图谱抽取。

## 4. 检索与降级

普通 RAG 只使用项目资料块。图谱增强 RAG 同时加入问题相关的图谱关系。

`auto` 模式在图谱相关度未达到阈值时降级为普通 RAG，并记录 `fallback_reason`。强制图谱增强模式未命中关系时直接报错，不会伪造图谱上下文。

## 5. 实验记录

每条问答记录保存：

- 生成模型、提供方和提示词版本
- 嵌入模型、分块和召回参数
- 来源块、向量/词法/综合相关度
- 图谱关系和相关度
- 响应耗时、token 用量和错误
- 人工评分、准确性和可追溯性

每次批量实验额外保存题集、对照模式、语料快照哈希和汇总指标。CSV 导出按题号配对普通 RAG 与图谱增强 RAG。

## 6. 复现建议

1. 冻结 `.env` 中的模型与检索参数。
2. 完成资料审核和全量重新索引。
3. 不再修改资料和知识图谱。
4. 运行固定题集的成对对照实验。
5. 由人工盲评两个模式的答案。
6. 导出 CSV，统计准确率、可追溯率、平均评分和响应时间。

论文中应区分人工评价指标与系统自动采集指标，不应将模拟记录纳入统计。

## 7. 发布证据冻结

正式评测使用部署后的 Rust API；`scripts/evaluate_retrieval.py` 仍是历史 Python/本地实现，只能作为开发对照，不能作为生产效果证据。先运行一次 Rust API 评测取得 `result_sha256`，再用该哈希重复运行确认可复现。`--retrieval-config` 必须同时记录 `embedding_backend`、`embedding_model` 和 `embedding_dimension`；评测脚本会从 Rust `/metrics` 读取实际运行时指纹并逐项比对：

```bash
backend/.venv/bin/python scripts/evaluate_rust_retrieval.py \
  --base-url https://<production-domain>/api \
  --token <review-token> \
  --project-id <project-id> \
  --questions data/real/GSE111619/gse111619_questions.json \
  --retrieval-config output/release-evidence/rag-retrieval-parameters.json \
  --corpus-sha256 <frozen-corpus-sha256> \
  --corpus-chunk-count <frozen-chunk-count> \
  --output output/release-evidence/rag-retrieval-first-run.json
```

第二次运行增加 `--expected-result-sha256`、`--image-digest`、`--git-revision` 和 `--embedding-model-sha256`，输出才会包含可过门禁的 `evidence_bindings`。

评测报告不能直接作为生产效果证据。完成 Rust 部署后的评测必须使用真实镜像 digest、Git revision 和模型文件 SHA-256 冻结：

```bash
backend/.venv/bin/python scripts/freeze_rag_evidence.py \
  --report output/release-evidence/rag-retrieval-second-run.json \
  --report-output output/release-evidence/rag-retrieval-report.json \
  --manifest-output output/release-evidence/rag-runtime-manifest.json \
  --image-digest sha256:<deployed-image-digest> \
  --git-revision <deployed-git-revision> \
  --embedding-model-sha256 <bge-m3-artifact-sha256>
```

该命令会拒绝非 `rust-axum`、非 `openai_compatible`/`BAAI/bge-m3`/1024 维、未复现或哈希格式不正确的报告。发布门禁必须同时传入生成的 `--retrieval-runtime-manifest`；任一绑定（包括后端、模型和维度）不一致都会失败。
