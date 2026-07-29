# RAG 实验 5 冻结清单核查

核查日期：2026-07-12

## 核查结果

旧清单 `rag-experiment-5-freeze-manifest.json` 中记录的预注册文件大小为 3974 字节，SHA-256 为：

`99fbf3fbe209910003e315f4c15306fbfba57d8c10f95d55dc2d5e37cb7d9f5c`

当前预注册文件的大小和 SHA-256 与该值一致，说明这份文件本身没有发生内容漂移。

旧清单仍不能作为正式实验 5 的完整冻结证据，原因如下：

1. 清单只包含预注册说明，没有包含语料快照、问题、标准要点、参数、提示版本和盲评模板。
2. 文件路径是 `D:\new\...` 形式的旧 Windows 绝对路径，换到当前环境后不能直接校验。
3. 预注册状态仍是“待执行”，真实人工评分也尚未开始。

## 处理方式

- 保留旧清单，不删除、不改写，作为历史记录。
- 正式实验前补齐全部材料，生成新的 v2 清单。
- 新清单使用仓库相对路径，并且默认禁止覆盖。
- 运行实验前和人工评价完成后各校验一次。

新清单示例：

```bash
python scripts/freeze_preregistration.py \
  docs/experiments/rag-experiment-5-preregistration.md \
  data/real/experiment-5/corpus-manifest.json \
  data/real/experiment-5/questions.json \
  data/real/experiment-5/gold-facts.json \
  data/real/experiment-5/run-config.json \
  docs/experiments/rag-experiment-5-blind-review-template.csv \
  --root . \
  --output docs/experiments/rag-experiment-5-freeze-manifest-v2.json
```

校验命令：

```bash
python scripts/freeze_preregistration.py \
  --verify docs/experiments/rag-experiment-5-freeze-manifest-v2.json \
  --root .
```

## 2026-07-13 进展

已准备：

- 五方法 `run-config.json`，包含重复次数、随机种子、生成参数和提示版本。
- 方法隐藏盲评模板，仅保留问题、回答、证据和评分字段。
- 纯 LLM、BM25 RAG、混合 RAG、直接结构化查询和图谱增强 RAG 的统一实验入口。

仍缺少且不会由程序代填：

- `data/real/experiment-5/corpus-manifest.json`
- `data/real/experiment-5/questions.json`
- `data/real/experiment-5/gold-facts.json`

当前运行 v2 冻结命令会因这三份文件缺失而失败，因此尚未生成正式冻结清单，也尚未产生实验 5 的确认性结果。
