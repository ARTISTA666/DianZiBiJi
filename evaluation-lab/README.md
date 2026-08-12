# ELN 评测实验室

这是与主业务系统分离的论文性能验证系统。它不修改主项目页面，负责：

- 查看冻结的 GSE111619 检索与回答基线；
- 对比纯 LLM、BM25 RAG、普通 RAG、结构化查询和图谱增强 RAG；
- 查看 Recall、MRR、nDCG、事实覆盖、精确率、F1、精确案例率和响应耗时；
- 调用原系统 RAG 接口运行新的对照实验；
- 通过单题探针观察回答、来源数量、图谱命中和延迟。

## 启动

主系统运行在本机 `8001` 端口时：

```bash
node evaluation-lab/server.mjs
```

然后打开 <http://localhost:4100>。

也可以使用独立容器：

```bash
docker compose -f docker-compose.evaluation.yml up -d --build
```

评测实验室只保存短期内存会话；实验数据仍由主系统的 RAG 实验接口记录，冻结论文基线来自 `data/real/GSE111619`。
