# 智能电子实验笔记系统

面向科研过程管理与论文实验验证的 ELN 系统，包含权限、审批、实验笔记、资料库、知识图谱、本地 RAG、DeepSeek 问答、固定任务智能体和成对对照实验。

## AI 架构

- 文档解析：TXT/Markdown/CSV/JSON/XML/HTML/PDF
- 文本分块：可配置块大小与重叠长度
- 嵌入模型：`BAAI/bge-small-zh-v1.5`
- 推理运行时：FastEmbed + ONNX Runtime（CPU）
- 向量存储：PostgreSQL 16 + pgvector
- 检索：向量相似度与词法相关度混合排序
- 图谱增强：按问题匹配相关实体关系，未命中时显式降级
- 生成模型：DeepSeek 官方 OpenAI 兼容接口
- 实验复现：保存模型、提示词版本、检索参数、语料哈希、耗时和 token 用量

系统不会在 AI 服务失败时生成模拟回答。失败会返回明确错误并写入日志。

## 服务地址

- 前端：http://localhost:3000
- 后端：http://localhost:8001
- 后端健康检查：http://localhost:8001/health

## 默认账号

```text
账号：admin
密码：admin123
```

正式部署后应立即修改默认密码。

## 配置

复制 `.env.example` 为 `.env`，至少配置：

```env
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=your-official-api-key
DEEPSEEK_MODEL=deepseek-v4-flash
```

DeepSeek 密钥只注入后端容器，不会传给前端。

## 启动

```powershell
cd D:\new\full-system
docker compose up -d --build
```

首次启动需要下载约数百 MB 的嵌入模型。模型保存在 Docker volume，后续启动直接复用。

## 论文对照实验

1. 登录系统并进入目标项目的“资料库”。
2. 初始化 AI 知识库。
3. 将审核通过的资料执行“本地向量入库”。
4. 在“论文对照实验”中逐行输入问题。
5. 系统对每个问题分别运行普通 RAG 和知识图谱增强 RAG。
6. 完成后导出 CSV，并对回答进行人工准确性、可追溯性和 1-5 分评价。

模拟数据脚本不再生成 AI 问答、评价或智能体结果，论文统计应只使用真实接口运行产生的数据。

详细配置与复现方法见 [docs/ai-rag-setup.md](docs/ai-rag-setup.md)。

## 验证

```powershell
cd D:\new\full-system\backend
python -m pytest -q
python -m compileall app

cd D:\new\full-system\frontend
npm run lint
```

运行状态：

```powershell
docker compose ps
docker stats --no-stream
```
