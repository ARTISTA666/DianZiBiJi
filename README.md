# 完整 ELN 系统

这是从 `D:\dianzibiji` 整合进当前仓库的完整电子实验笔记系统。

它和当前 `companion` / `frontend` 验证工作台并行存在：

- 完整系统前端：http://localhost:3000
- 完整系统后端：http://localhost:8001
- Companion 工作台：http://localhost:5173
- Companion API：http://localhost:8000

## 功能范围

完整系统包含：

- 用户登录
- 用户管理
- 小组管理
- 项目管理
- 项目成员与权限
- 实验笔记创建、编辑、提交、审核、退回、归档、作废
- 实验模板
- 附件/资料库上传、审核、下载、归档
- Dify RAG：项目资料同步、AI 知识库问答、来源展示
- 审计日志

## 默认账号

```text
账号：admin
密码：admin123
```

## 启动

在当前目录运行：

```powershell
cd D:\ELN-MVP\full-system
docker compose up -d --build
```

## 本地验证

后端健康检查：

```powershell
Invoke-WebRequest -UseBasicParsing http://localhost:8001/health
```

登录接口：

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8001/auth/login `
  -ContentType 'application/json' `
  -Body '{"username":"admin","password":"admin123"}'
```

前端检查：

```powershell
cd D:\ELN-MVP\full-system\frontend
npm.cmd run lint
npm.cmd run build
```

后端源码编译检查：

```powershell
cd D:\ELN-MVP\full-system\backend
python -m compileall app
```

## Dify RAG

RAG 功能以外部 Dify 为基座。第一版支持：

- 每个项目初始化一个 Dify 知识库
- 审核通过的资料手动同步到 Dify
- 在项目资料库里向 AI 提问
- 回答展示来源资料

配置和测试方法见 [docs/dify-rag-setup.md](docs/dify-rag-setup.md)。
