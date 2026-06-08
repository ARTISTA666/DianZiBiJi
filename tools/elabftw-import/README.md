# eLabFTW 导入工具

将现有的 eLabFTW 实例中的数据导入到本 ELN 系统。

## 目录结构

```
adapter_base.py        — 抽象适配器接口
adapter_elabftw.py     — eLabFTW HTTP API 适配器
verify_elabftw_connection.py — 验证 eLabFTW 连接
```

## 使用方式

```powershell
# 1. 配置环境变量
$env:ELABFTW_BASE_URL="https://eln.example.com"
$env:ELABFTW_API_KEY="your-api-key"

# 2. 验证连接
python verify_elabftw_connection.py

# 3. 导出数据快照
python verify_elabftw_connection.py --require-core-data --output ../snapshot.json
```
