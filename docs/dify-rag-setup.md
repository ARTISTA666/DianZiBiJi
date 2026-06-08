# Dify RAG 接入说明

第一版 RAG 只接入完整 ELN 主系统：

- 前端入口：`http://localhost:3000`
- 后端接口：`http://localhost:8001`
- Dify：外部服务

## 环境变量

在 `full-system/.env` 中配置：

```env
DIFY_API_BASE_URL=https://your-dify-host
DIFY_DATASET_API_KEY=replace-with-dify-dataset-api-key
DIFY_CHAT_APP_API_KEY=replace-with-dify-chat-app-api-key
DIFY_DEFAULT_INDEXING_TECHNIQUE=high_quality
```

这些密钥只给后端使用，不要写进前端环境变量。

## 使用流程

1. 登录完整系统。
2. 进入一个项目。
3. 打开“资料库”。
4. 上传资料库文件。
5. 审核人或管理员通过资料审核。
6. 在“AI 知识库”区域点击“初始化知识库”。
7. 对审核通过的资料点击“同步AI”。
8. 在“AI 知识库”输入问题。
9. 查看 AI 回答和来源资料。

## 权限规则

- 有项目读取权限的人可以提问。
- 有项目审核或管理权限的人可以初始化知识库。
- 有项目审核或管理权限的人可以同步资料。
- 未审核、驳回、归档、普通笔记附件不会进入 Dify。

## 验证命令

后端 RAG 测试：

```powershell
cd D:\ELN-MVP\full-system
docker compose build backend
docker compose run --rm -e PYTHONPATH=/app backend pytest tests/test_rag_api.py
```

前端类型检查：

```powershell
cd D:\ELN-MVP\full-system\frontend
npm.cmd run lint
```

前端构建：

```powershell
cd D:\ELN-MVP\full-system\frontend
npm.cmd run build
```

## 回滚

本次 RAG 开发按小步提交。查看提交：

```powershell
git log --oneline
```

回到某个版本：

```powershell
git checkout <commit>
```

如需正式回滚到某个提交，请先确认没有未保存改动。
