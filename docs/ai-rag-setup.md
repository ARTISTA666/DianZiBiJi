# 本地 RAG 与 DeepSeek 配置及实验复现

## 1. 组件

系统使用以下开源组件：

- `BAAI/bge-small-zh-v1.5`：中文文本嵌入模型
- FastEmbed：ONNX/CPU 嵌入推理
- PostgreSQL + pgvector：向量存储和余弦距离检索
- pypdf：PDF 文本提取

DeepSeek 仅承担基于检索上下文的答案和固定任务草稿生成。

## 2. 环境变量

```env
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your-official-api-key
DEEPSEEK_MODEL=deepseek-v4-flash

EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
EMBEDDING_DIMENSION=512
RAG_CHUNK_SIZE=700
RAG_CHUNK_OVERLAP=120
RAG_RETRIEVAL_TOP_K=6
RAG_VECTOR_CANDIDATE_K=30
RAG_GRAPH_TOP_K=10
RAG_GRAPH_MIN_SCORE=1.0
```

修改嵌入模型或向量维度后必须重新创建向量表或执行正式数据库迁移，并重新索引全部资料。

## 3. 数据进入条件

- 只有 `knowledge_document` 类型资料可进入 RAG。
- 只有审核状态为 `approved` 的资料可索引。
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
