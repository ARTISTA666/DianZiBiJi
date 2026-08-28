# 去人工化 RAG 回答质量评价标准调研报告

- 日期：2026-08-26（核实工作于 2026-08-25/26 完成）
- 用途：为硕士论文《ELN 图谱增强 RAG 问答系统》补充一个学术界公认、可去人工化的回答质量评价标准，替代被质疑为"事后规则"的机械字符串匹配，并绕开作者身份不独立导致的人工盲评不可行问题。
- 核实方法：所有 venue、年份、star 数、指标定义均通过 WebFetch 抓取 arXiv 页面、ACL Anthology、GitHub API、PyPI、OpenAlex API 与官方文档核实，正文附链接。抓取不到的一律标注**未核实**。
- 说明：Semantic Scholar API 在调研期间持续限流（HTTP 429），引用数改用 OpenAlex API 核实（OpenAlex 计数通常低于 Google Scholar，但可复现核查）。GitHub star 数为抓取时刻数值，论文写作时应注明"截至 YYYY-MM"。

---

## 结论速览

| 角色 | 选择 | 一句话理由 |
| --- | --- | --- |
| **主标准** | **RAGAS**（faithfulness + response relevancy 无参考指标；context precision/recall 以既有参考答案作 reference） | 唯一同时满足"正式发表 + 大规模工业采用 + 官方维护活跃 + 支持任意 OpenAI 兼容 judge（DeepSeek 可直连）+ 官方多语言适配流程"的标准 |
| **归因专项补充** | **ALCE 的 citation precision / citation recall 协议** | 与本文 [S]/[G] 证据编号引用协议天然同构：逐声明判"是否有证据支持"、逐引用判"是否真的支持该声明"，直接映射论文的"可追溯性"维度 |
| 方法学引用支撑 | MT-Bench/LLM-as-judge（Zheng et al.）+ G-Eval（Liu et al.） | 为"用 LLM 当裁判"提供权威一致率数据（85% vs 人-人 81%）与偏差缓解依据 |
| 备选/交叉验证 | DeepEval（第二实现交叉验证）、Prometheus 2 或本地 Qwen/GLM（第二家族 judge，规避自我偏好） | 工程冗余 |

---

## 1. 候选标准总表

适配度评分：★ 数越多越适合本文（中文回答、生物医学 ELN、[S]/[G] 引用协议、180+40 条已生成回答离线评测、可用 DeepSeek API 作 judge）。

| 名称 | 论文 / venue（已核） | 工具成熟度 | judge 要求 | 中文支持 | 参考答案需求 | 适配度 |
| --- | --- | --- | --- | --- | --- | --- |
| **RAGAS** | EACL 2024 System Demonstrations, pp.150–158（[Anthology](https://aclanthology.org/2024.eacl-demo.16/)）；arXiv:2309.15217 | 仓库 [vibrantlabsai/ragas](https://github.com/explodinggradients/ragas) 15,478★、Apache-2.0、最新版 v0.4.3（2026-01-13，[PyPI](https://pypi.org/project/ragas/)），持续发版 | LLM judge，`llm_factory` 支持 OpenAI 兼容客户端直连，或经 LiteLLM 接 100+ 提供商 → DeepSeek 可用 | 默认英文 prompt，但官方文档提供 `adapt()` 多语言适配流程（翻译 few-shot 示例，可选连指令一起翻） | faithfulness / response relevancy **无参考**；context precision / recall **需参考答案** | ★★★★★ |
| **ARES** | NAACL 2024（[arXiv Comments 已核](https://arxiv.org/abs/2311.09476)） | [stanford-futuredata/ARES](https://github.com/stanford-futuredata/ARES) 732★，最后 push 2025-03，维护放缓 | 需用 GPT 系合成数据微调轻量 DeBERTa judge；PPI 置信区间需少量人工标注（论文报告八个任务合计仅几百条） | 英文为主；中文需自建合成训练集重训 judge | 判决器本身无参考即可打分，但 PPI 需人工标注校准 | ★★☆ |
| **TruLens RAG Triad** | 无单一正式论文（工程框架） | [truera/trulens](https://github.com/truera/trulens) 3,524★、MIT，2026-08 仍在推送（活跃） | LLM feedback function，可接自定义模型 | 默认英文 prompt，可自定义 | 三项（groundedness / context relevance / answer relevance）均无参考 | ★★★ |
| **G-Eval** | EMNLP 2023 主会 pp.2511–2522（[Anthology](https://aclanthology.org/2023.emnlp-main.153/)）；arXiv:2303.16634 | 有官方代码（star 未核实）；更多作为方法被 DeepEval 等框架内置 | 强 LLM + CoT prompt，评估维度可自定义 → 中文可行 | prompt 自定义即中文可行（无官方中文声明） | 无参考（按维度直接打分） | ★★★★（作为方法学引用而非工具） |
| **MT-Bench / LLM-as-judge** | NeurIPS 2023 Datasets & Benchmarks Track（[arXiv Comments 已核](https://arxiv.org/abs/2306.05685)） | MT-Bench 题集随 [lm-sys/FastChat](https://github.com/lm-sys/FastChat) 发布（39,524★） | 强 LLM judge；论文给出位置/冗长/自我增强三类偏差及缓解 | 题集英文；方法本身语言无关 | 无参考（成对/单答打分） | ★★★★（方法学依据） |
| **ALCE 引用协议** | EMNLP 2023（[arXiv Comments 已核](https://arxiv.org/abs/2305.14627)） | [princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE) 526★、最后 push 2024-10（研究代码，协议简单可自行实现） | 原文用 NLI 模型 TRUE(T5-11B)；中文场景可直接换成 LLM judge 做蕴含二判 | NLI 模型英文；换 LLM judge 后中文可行 | 不需要参考答案，只需回答中的引用编号 + 对应证据片段 | ★★★★★（归因专项） |
| **KILT R-precision** | **NAACL 2021**（[arXiv Comments 已核](https://arxiv.org/abs/2009.02252)，常被误引为 EMNLP 2020） | [facebookresearch/KILT](https://github.com/facebookresearch/KILT) 978★，停更于 2022-03 | 无需 judge（对照金标准 provenance 计算） | 语言无关 | **需要金标准证据切分（gold provenance）**，本文没有 | ★★ |
| **DeepEval** | 无单篇旗舰论文（内置 G-Eval 等已发表指标） | [confident-ai/deepeval](https://github.com/confident-ai/deepeval) 17,869★、Apache-2.0、PyPI 4.2.0（2026-08-24），极活跃 | 明确支持"任意自选 LLM"（custom LLM 类） | prompt 自定义可行 | 同 RAGAS 分层：faithfulness / answer relevancy 无参考，contextual precision / recall 有参考 | ★★★★（备选实现） |
| **RGB** | AAAI 2024（[arXiv Comments 已核](https://arxiv.org/abs/2309.01431)） | [chen700564/RGB](https://api.github.com/repos/chen700564/RGB) 373★，最后 push 2024-05 | 是中英双语诊断基准（噪声鲁棒/负拒绝/信息集成/反事实鲁棒四能力），需构造扰动测试集，不是评分协议 | 中英双语（对中文友好） | 需按其规范构造测试集 | ★★ |
| **Prometheus 2** | EMNLP 2024 主会（[arXiv Comments 已核](https://arxiv.org/abs/2405.01535)） | [prometheus-eval/prometheus-eval](https://github.com/prometheus-eval/prometheus-eval) 1,107★，最后 push 2025-04 | 本地开源 judge（7B/8x7B），支持自定义 rubric 打分与成对比较 | 基座为 Mistral/Zephyr 系，中文能力弱于 GPT-4 级闭源模型 | 无参考（rubric 自定义） | ★★★（本地第二 judge 备选） |
| TRACe | **未核实** | 多轮 arXiv API 检索（标题含 "TRACe"+"attribution"、摘要含 "TRACe"+"centrality" 等）均未命中同名归因评测基准；Semantic Scholar API 限流未能交叉验证 | — | — | — | 建议论文暂不引用 |

---

## 2. 分项要点与证据

### 2.1 RAGAS（推荐主标准）

1. 论文与 venue：Es, James, Espinosa-Anke, Schockaert, *RAGAS: Automated Evaluation of Retrieval Augmented Generation*，正式发表于 **EACL 2024 System Demonstrations**（pp.150–158，DOI `10.18653/v1/2024.eacl-demo.16`，[ACL Anthology 页面已核实](https://aclanthology.org/2024.eacl-demo.16/)）；arXiv 版 [2309.15217](https://arxiv.org/abs/2309.15217)（v1 2023-09-26，v2 2025-04-28）。核心卖点与本文需求完全一致：**无需人工标注参考答案即可评测 RAG**（摘要原文明确 "without having to rely on ground truth human annotations"）。
2. 工具成熟度：GitHub 仓库现位于 [vibrantlabsai/ragas](https://github.com/explodinggradients/ragas)（原 explodinggradients/ragas，API 显示已迁移，旧链接重定向有效），**15,478 stars / 1,656 forks，Apache-2.0**（GitHub API 抓取）；最新 release **v0.4.3（2026-01-13）**，与 [PyPI ragas 0.4.3](https://pypi.org/project/ragas/) 上传时间一致——版本化发版规律、社区体量为同类最大。OpenAlex 收录该 demo 论文被引 **404 次**（OpenAlex 计数偏低，仅作下界参考）。
3. 指标与去人工化分层（[官方指标文档](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/) 及各指标子页已核实）：**Faithfulness = 被检索上下文支持的声明数 / 回答总声明数**（先做 claim 分解再逐条判定，官方公式页：[faithfulness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/)），**不需要参考答案**；Response Relevancy 同样无参考。**Context Recall 明确"always requires a reference"**（将参考答案拆成声明、逐条归因到检索上下文，[context_recall 子页](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_recall/)）——本文预注册批次的 SQL 金标准结果和 20 题成对实验的要点恰好可以充当该 reference，属于"仅需少量既有金标准、无需新人工标注"。
4. Judge 要求：v0.4 文档 [customize_models 页](https://docs.ragas.io/en/stable/howtos/customizations/customize_models/) 核实：通过 `llm_factory` 传入 OpenAI 兼容 client 即可，OpenAI/Anthropic/Google 直连，其余端点经 LiteLLM（100+ 提供商）。DeepSeek API 为 OpenAI 兼容端点，直接可用。
5. 中文支持：官方文档专设多语言适配页（[metrics_language_adaptation](https://docs.ragas.io/en/stable/howtos/customizations/metrics/metrics_language_adaptation/)）：对每个指标的 prompt 属性调用 `adapt(target_language=..., llm=...)` 自动翻译 few-shot 示例，`adapt_instruction=True` 可连指令一起翻译；文档并提醒多 prompt 指标（如 Faithfulness 的声明分解 + NLI 两段 prompt）都要适配。这是所有候选中唯一有**官方多语言适配流程**的。

### 2.2 ARES（不推荐为主标准，理由见下）

1. 论文与 venue：Saad-Falcon, Khattab, Potts, Zaharia, *ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems*，[arXiv:2311.09476](https://arxiv.org/abs/2311.09476) Comments 字段明确 **NAACL 2024**；沿 context relevance / answer faithfulness / answer relevance 三轴评测。
2. 方法：用 GPT 系模型生成合成训练数据，微调轻量 DeBERTa 判决器；再用 **PPI（prediction-powered inference）**以"一小撮人工标注"给出统计置信区间——论文报告在 KILT/SuperGLUE/AIS 八个知识密集任务上总共只需几百条人工标注。
3. 成熟度：[stanford-futuredata/ARES](https://github.com/stanford-futuredata/ARES) 732★，最后 push 2025-03-28，明显进入低维护状态；OpenAlex 被引 110 次，学术认可度尚可。
4. 不推荐原因：(a) 判决器需针对本文生物医学 ELN 语域重新合成数据并微调，工程量远超 RAGAS；(b) PPI 置信区间需要人工标注，而作者身份不独立使这批标注仍需外部人员完成；(c) 中文判决器需要全新合成语料，官方未提供；(d) 维护放缓。其价值在于：若答辩委员要求"评价结果带置信区间"，可在小规模人工盲评子集上借 PPI 思路报告误差棒。

### 2.3 TruLens RAG Triad

1. 组成（[官方 RAG Triad 文档页已核实](https://www.trulens.org/getting_started/core_concepts/rag_triad/)）：context relevance（检索块是否切题）、groundedness（把回答拆成独立声明、逐条找证据支持）、answer relevance（最终回答对用户输入的相关性）；三项全过则认为应用在其知识库范围内无幻觉。
2. 维护与采用：[truera/trulens](https://github.com/truera/trulens) 3,524★、MIT，2026-08-25 仍有推送（GitHub API 抓取），工业界使用较多。
3. 局限：**没有一篇对应的正式发表论文**（RAG Triad 是 TruEra 公司提出的工程概念），在硕士论文中作为"学术公认成熟标准"引用说服力弱于 RAGAS；指标语义与 RAGAS 高度重叠。可作为工程备选。

### 2.4 G-Eval（LLM-judge 方法学引用）

1. Liu et al., *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment*，**EMNLP 2023 主会 pp.2511–2522**（[ACL Anthology 已核实](https://aclanthology.org/2023.emnlp-main.153/)；[arXiv:2303.16634](https://arxiv.org/abs/2303.16634)）。注意精确表述：摘要给出的是 **Spearman 相关 0.514**（summarization 任务，GPT-4 骨干），并非 Pearson。
2. 贡献：用 LLM 按 CoT 生成评估步骤再按"表单填写"范式打分，当时大幅超越已有零样本评估法；摘要同时首次点名了"LLM 评审偏爱 LLM 生成的文本"这一自偏好隐患——论文写局限时可直接引用。
3. 定位：本文不必直接跑 G-Eval 官方代码，而是把它作为"LLM-as-judge + CoT + 自定义评估维度"的方法学出处之一；DeepEval 已将其产品化为内置指标（见 2.8），OpenAlex 被引 708 次。

### 2.5 MT-Bench / Chatbot Arena（LLM-as-judge 权威一致性数据）

1. Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*，**NeurIPS 2023 Datasets and Benchmarks Track**（arXiv [2306.05685](https://arxiv.org/abs/2306.05685) Comments 字段已核）。
2. 关键数字（本次从全文 HTML 逐条核实，比常见转述更精确）：MT-Bench 成对比较中 **GPT-4 与人类专家一致率 85%（S2 设定、剔除平局），高于人与人之间的 81%（第一轮）/82%（第二轮）**；Chatbot Arena 上 GPT-4-人一致率 87%。摘要层面则保守表述为 ">80%"。
3. 已知局限（同文核实）：**位置偏差**——交换答案顺序后 GPT-4 仅 65% 判断一致（few-shot 示例可提升到 77.5%；GPT-3.5 只有 46.2%）；另有 verbosity bias、self-enhancement bias 与推理能力上限。这些是本文"局限"一节必须引用的内容，也是缓解措施的出处（交换位置取均值/多数、控制长度差、judge 与被评系统不同源）。
4. 资产：MT-Bench 题集与 3.3K 专家投票随 [lm-sys/FastChat](https://github.com/lm-sys/FastChat)（39,524★）发布。OpenAlex 记录约 579 次（存在重复记录）。

### 2.6 ALCE（推荐归因专项补充）

1. Gao, Yen, Yu, Chen, *Enabling Large Language Models to Generate Text with Citations*，**EMNLP 2023**（arXiv [2305.14627](https://arxiv.org/abs/2305.14627) Comments 字段 "Accepted by EMNLP 2023" 已核；仓库描述同样标注 EMNLP 2023）。
2. 指标定义（从全文核实，可直接搬进论文）：**citation recall**——把回答拆成 statement，每条若"至少有一个引用且被引段落拼接后能蕴含该 statement"记 1，对所有 statement 取平均；**citation precision**——对每个引用单独判 0/1（若该引用自身不足以支持对应 statement、且删掉它其余引用仍完整支持，则记为无关引用），对所有引用取平均。原文自动评测用 **TRUE（T5-11B 多 NLI 数据集微调）**做蕴含判定。
3. 与本文协议的映射：本文回答里的 `[S]/[G]` 编号就是 citation，编号指向的证据切片就是被引段落——**把蕴含判定器从 TRUE 换成 DeepSeek judge 即得到中文版的 citation precision/recall**，分别度量"该引的引了没"与"引的是否真支持"，正交地补上 RAGAS 不覆盖的可追溯性维度。
4. 成熟度：[princeton-nlp/ALCE](https://github.com/princeton-nlp/ALCE) 526★、MIT，最后 push 2024-10；属研究代码，但其指标是逐条 0/1 取平均的简单协议，本文自实现约百行脚本即可，不依赖其代码库。数据集为 ASQA/QAMPARI/ELI5 等（全文核实版本）。OpenAlex 被引 177 次。

### 2.7 KILT R-precision（不适配，说明理由）

1. Petroni et al., *KILT: a Benchmark for Knowledge Intensive Language Tasks*，**NAACL 2021**（[arXiv:2009.02252](https://arxiv.org/abs/2009.02252) Comments 字段 "accepted at NAACL 2021" 已核——若参考文献里写成 EMNLP 2020 请修正）。摘要确认其对下游性能之外还评 **provenance**（证据溯源）能力，R-precision 即其 provenance 指标族代表（R-precision 逐字定义在正文/排行榜，本次未逐句核实，引用时以论文原文为准）。
2. 不适配原因：R-precision 需要**金标准证据切分（gold provenance）**来对照，而本文 180+40 条回答并没有逐条人工圈定的 gold 证据 span；构造它的成本正是本文想避免的人工标注。仓库 978★ 但 2022 年后停止更新。[facebookresearch/KILT](https://api.github.com/repos/facebookresearch/KILT)

### 2.8 DeepEval（备选实现/交叉验证）

1. [confident-ai/deepeval](https://github.com/confident-ai/deepeval)：**17,869★、Apache-2.0，2026-08-26 当天仍有 push**，PyPI 最新版 4.2.0（2026-08-24）——四个候选框架中迭代最活跃。
2. 能力（PyPI 长描述核实）：内置 G-Eval、Faithfulness、Answer Relevancy、Contextual Precision / Recall 等指标，语义与 RAGAS 指标族一一对应；明确宣传"powered by ANY LLM of your choice"，提供 custom LLM 接入文档。
3. 用途建议：不是替代而是冗余——同一批数据用 RAGAS 与 DeepEval 各跑一遍 faithfulness，两套独立实现的分数相关性本身就是稳健性检查，可写入论文附录。

### 2.9 RGB（中文诊断基准，非评分协议）

1. Chen, Lin, Han, Sun, *Benchmarking Large Language Models in Retrieval-Augmented Generation*，**AAAI 2024**（arXiv [2309.01431](https://arxiv.org/abs/2309.01431) Comments 字段已核）。构建了**中英双语**语料，测四项能力：噪声鲁棒、负拒绝、信息集成、反事实鲁棒。
2. 定位差异：RGB 是"造测试集考系统"的诊断型 benchmark，不是对已有回答打分的协议；本文 180+40 条回答已经生成完毕，无法回头套用其测试集构造。其价值有二：证明"中文 RAG 评测有顶会先例"；其负拒绝/反事实设计可解释本文四臂消融中直接 SQL 臂的行为。

### 2.10 Prometheus 2（本地第二 judge 备选）

1. Kim et al., *Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models*，**EMNLP 2024 主会**（[arXiv:2405.01535](https://arxiv.org/abs/2405.01535) Comments 字段已核）。开源 evaluator LM，同时支持绝对打分（自定义 rubric）与成对比较，在 4 个 DA + 4 个成对基准上取得开源模型中最优的人机相关。
2. 仓库：[prometheus-eval/prometheus-eval](https://github.com/prometheus-eval/prometheus-eval) 1,107★（v2 代码所在；同 org 下 prometheus/prometheus 324★ 为 v1，已停更）。
3. 用途：当 judge 必须与 DeepSeek 不同源时，Prometheus 2 是可本地跑的选择；但其基座中文能力一般，若本地资源允许，用较新的中文强开源模型（Qwen/GLM 系）加 G-Eval 式 prompt 做第二 judge 更实际。

### 2.11 TRACe —— 未核实

多轮 arXiv 官方 API 检索（`ti:"TRACe" AND abs:"attribution"`、`all:"TRACe" AND abs:"centrality"` 等）均未命中名为 TRACe 的归因评测基准（命中项皆为无关的编码理论/物理/作者归属论文）；Semantic Scholar API 调研期间持续 HTTP 429，无法交叉验证。**结论：该名称的存在性与出处未能核实，建议论文暂不引用；如确需引用请到 ACL Anthology 人工确认后再加。**

### 2.12 LLM judge 自我偏好偏差（局限一节必引）

Panickssery, Bowman, Feng, *LLM Evaluators Recognize and Favor Their Own Generations*，[arXiv:2404.13076](https://arxiv.org/abs/2404.13076)（提交于 2024-04-15，经 arXiv API 核实标题/作者/日期；正式 venue **未核实**，引用前建议查证）。核心发现：GPT-4、Llama-2 等能识别自己生成的文本，且自我识别能力与自偏好强度呈线性关系。**对本文的含义：若 ELN 系统的生成端也用 DeepSeek 家族模型，则用 DeepSeek 作 judge 存在系统性自偏好风险，必须换家族 judge 或至少双 judge 对照并在局限中披露。**

---

## 3. 推荐结论

**主标准：RAGAS（faithfulness + response relevancy + context precision/recall 四指标组合）；归因专项补充：ALCE 的 citation precision/recall 协议。**

推荐理由：

1. **成熟度与学术地位可写进论文**：RAGAS 有正式发表 venue（EACL 2024 System Demonstrations）、15k+ stars 的持续维护工具链（v0.4.3，2026-01 发版）、OpenAlex 可查的数百次引用；"学术界公认的自动化 RAG 评测标准"这一表述有据可依。相比之下 ARES 维护放缓且要训 judge，TruLens 无正式论文，KILT 需金标准溯源。
2. **精准回应两个痛点**：
   - 作者身份不独立 → faithfulness 与 response relevancy 是**全程无人参与**的无参考指标，机器全量跑完 220 条，作者只读报表不打分；
   - 机械匹配是"事后规则" → RAGAS faithfulness 是**自底向上的 claim 分解 + 逐条蕴含判定**，规则由通用协议而非作者事后拟定；同时可报告新指标与原机械匹配分数的 Spearman 相关，把机械匹配降格为" sanity check"而非主证据。
3. **与本文数据的适配成本低**：DeepSeek API 是 OpenAI 兼容端点，RAGAS `llm_factory` 直连即可；中文有官方 `adapt()` 适配流程；context recall 所需的 reference 可复用本文已有的 SQL 金标准与 20 题要点，不需新增人工标注。
4. **ALCE 补上可追溯性**：RAGAS 不评"回答是否正确挂了证据编号"，而这恰是 [S]/[G] 协议的核心贡献点。ALCE 协议（逐 statement 判引用覆盖 × 逐 citation 判真实支持）与 [S]/[G] 结构同构，实现只是"解析编号 → judge 蕴含二判 → 取平均"，并把论文的评价维度显式映射为"准确性 ← context 指标 + 金标准对照；可追溯性 ← citation precision/recall；忠实性 ← faithfulness"。

---

## 4. 落地路径（在本文 180 + 40 条回答上运行）

### 4.1 Judge 选择

| 角色 | 模型 | 接入方式 | 备注 |
| --- | --- | --- | --- |
| 主 judge | DeepSeek API（deepseek-v4-flash） | RAGAS `llm_factory` 传入指向 `api.deepseek.com` 的 OpenAI 兼容 client；温度 0，固定版本号 | 便宜、快，够做 claim 分解与蕴含二判这类判别式任务 |
| 第二 judge（强烈建议） | 不同家族模型：本地 Qwen/GLM 系，或 Prometheus 2 | DeepEval custom LLM 类或裸脚本 | 规避自我偏好（arXiv:2404.13076）；报告两 judge 的分数相关与分歧样本量 |

前提披露：若生成端也是 DeepSeek 家族，必须在论文局限中说明并展示第二 judge 结果方向一致。

### 4.2 步骤

1. **导出统一 JSONL**（每行一条）：`{qid, method, user_input, response, retrieved_contexts: [...], reference, citations: [{marker:"[S1]", evidence_id}], evidence_text: {evidence_id: text}}`。180 条预注册批次 + 40 条消融/成对批次共用此格式。
2. **中文适配**：按官方 [metrics_language_adaptation](https://docs.ragas.io/en/stable/howtos/customizations/metrics/metrics_language_adaptation/) 流程，对 Faithfulness（注意它是 claim 分解 + NLI 双 prompt，两个都要 `adapt()`）与 AnswerRelevancy 调用 `adapt(target_language="chinese", llm=..., adapt_instruction=True)`；适配后的 prompt 全文放入论文附录保证可复现。先抽 20 条试跑人工目检分解质量。
3. **跑四指标**：
   - 无参考：`faithfulness`（忠实性）、`response_relevancy`（相关性）；
   - 有参考（reference=SQL 金标准答案/20 题要点）：`context_precision`、`context_recall`（检索质量，映射"准确性"的检索侧）；
   - 准确性的生成侧继续用既有的 SQL 金标准对照（执行结果等价性），LLM 指标与其互补而非替代。
4. **实现 ALCE 协议脚本**（约百余行）：正则解析回答中的 [S]/[G] 标记 → 取对应证据文本 → 对每个 statement 问 judge："证据是否蕴含该声明（yes/no）"→ 计算 citation recall（statement 粒度平均）与 citation precision（citation 粒度平均）；无任何引用的回答记 recall=0。
5. **稳健性三件套**：位置/顺序不变（本文是单答打分，天然回避位置偏差）；同一输入跑 2–3 次报方差；RAGAS 与 DeepEval 双实现对跑 faithfulness 报相关系数。
6. **小规模外部锚定**（可选但加分）：请导师/同学（非作者）对随机 30–50 条做盲评（好/中/差或 1–5 分），计算人-judge 一致率，对照 MT-Bench 的人-人 81%、GPT-4-人 85% 锚点讨论；这一步把"作者不能自评"转化为"他人抽查校准机器"。

### 4.3 工作量与成本预估

- 工程：JSONL 导出脚本 0.5 天 + RAGAS 适配与试跑 1 天 + ALCE 脚本 0.5–1 天 ≈ **2–3 个工作日**。
- 计算：220 条 × 4 指标 × 每指标 2–4 次 LLM 调用 ≈ 2,000–3,500 次调用、每次数千 token 上下文；flash 级单价下预计为个位数到十几美元量级（先用 20 条试跑实测单价再全量）。
- 写作：新增"自动化评价指标"小节 + 附录（prompt 全文、judge 版本、温度、代码链接）≈ 1 天。

### 4.4 局限（论文中应如实陈述）

1. **LLM judge 三类偏差**：position bias（本文单答打分影响小）、verbosity bias、self-enhancement/self-preference bias（Zheng et al. 2023；Panickssery et al. 2024）——以不同家族第二 judge 缓解并披露。
2. **claim 分解的中文敏感性**：长难句拆分可能漏拆/错拆，需抽样目检并报告失败模式。
3. **faithfulness ≠ 事实正确**：它只保证"说法能在检索上下文里找到支持"，上下文本身错了它照样给高分——这正是必须保留 SQL 金标准对照与 context 指标的原因，三者互补构成"准确性"。
4. **可复现性**：judge 是非确定组件，须固定模型版本、温度 0、prompt 全文公开；换 judge/换版本可能改变绝对分数，故结论应基于相对比较（普通 RAG vs 图谱增强）而非绝对值。
5. **引用数口径**：OpenAlex 计数低于 Google Scholar，论文中引用数建议写"截至 2026-08，OpenAlex 收录 X 次"或干脆只写 venue+star 数这类硬事实。

---

## 5. 参考文献条目（可直接并入论文参考文献）

1. Es S, James J, Espinosa-Anke L, et al. RAGAS: Automated evaluation of retrieval augmented generation[C]//Proceedings of the 18th Conference of the European Chapter of the Association for Computational Linguistics: System Demonstrations. St. Julians, Malta: Association for Computational Linguistics, 2024: 150-158. DOI: 10.18653/v1/2024.eacl-demo.16. arXiv:2309.15217.
2. Liu Y, Iter D, Xu Y, et al. G-Eval: NLG evaluation using GPT-4 with better human alignment[C]//Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing. Singapore: Association for Computational Linguistics, 2023: 2511-2522. arXiv:2303.16634.
3. Zheng L, Chiang W L, Sheng Y, et al. Judging LLM-as-a-judge with MT-Bench and Chatbot Arena[C]//Advances in Neural Information Processing Systems 36 (NeurIPS 2023) Datasets and Benchmarks Track. 2023. arXiv:2306.05685.
4. Gao T, Yen H, Yu J, et al. Enabling large language models to generate text with citations[C]//Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing. Singapore: Association for Computational Linguistics, 2023. arXiv:2305.14627.
5. Saad-Falcon J, Khattab O, Potts C, et al. ARES: An automated evaluation framework for retrieval-augmented generation systems[C]//Proceedings of the 2024 Conference of the North American Chapter of the Association for Computational Linguistics (NAACL). 2024. arXiv:2311.09476.

（可选增补：Panickssery A, Bowman S R, Feng S. LLM evaluators recognize and favor their own generations. arXiv:2404.13076, 2024. —— venue 未核实，引用前确认。）

---

## 附：核实状态清单（抓取时间 2026-08-25/26）

| 声明 | 证据来源 | 状态 |
| --- | --- | --- |
| RAGAS = EACL 2024 Demo, pp.150–158 | aclanthology.org/2024.eacl-demo.16/ | 已核实 |
| ragas 仓库 15,478★ / Apache-2.0 / v0.4.3 (2026-01-13) | api.github.com/repos/vibrantlabsai/ragas + releases/latest + pypi.org/project/ragas | 已核实 |
| RAGAS faithfulness 公式与无参考性；context recall 需 reference | docs.ragas.io 两个指标子页 | 已核实（原文摘录） |
| RAGAS 自定义 LLM（llm_factory/LiteLLM）与多语言 adapt() | docs.ragas.io customize_models 与 metrics_language_adaptation | 已核实 |
| ARES = NAACL 2024；DeBERTa 合成微调 + PPI 几百条标注 | arxiv.org/abs/2311.09476（Comments + 摘要） | 已核实 |
| ARES 仓库 732★、push 2025-03 | api.github.com/repos/stanford-futuredata/ARES | 已核实 |
| TruLens RAG Triad 三反馈定义；3,524★、2026-08 仍活跃 | trulens.org rag_triad 页 + api.github.com/repos/truera/trulens | 已核实 |
| G-Eval = EMNLP 2023 主会；Spearman 0.514 | aclanthology.org/2023.emnlp-main.153/ + arxiv.org/abs/2303.16634 | 已核实 |
| MT-Bench = NeurIPS 2023 D&B；85%/81%/87%；位置一致性 65%→77.5% | arxiv.org/abs/2306.05685 + 全文 HTML（ar5iv） | 已核实 |
| ALCE = EMNLP 2023；citation recall/precision 定义与 TRUE(NLI)；526★ | arxiv.org/abs/2305.14627 + ar5iv 全文 + api.github.com/repos/princeton-nlp/ALCE | 已核实 |
| KILT = NAACL 2021（非 EMNLP 2020）；需 gold provenance；978★、2022 停更 | arxiv.org/abs/2009.02252 + api.github.com/repos/facebookresearch/KILT | 已核实（R-precision 逐字定义未逐句核对） |
| DeepEval 17,869★、v4.2.0(2026-08-24)、任意 LLM | api.github.com/repos/confident-ai/deepeval + pypi.org/project/deepeval | 已核实 |
| RGB = AAAI 2024；双语四能力；373★ | arxiv.org/abs/2309.01431 + api.github.com/repos/chen700564/RGB | 已核实 |
| Prometheus 2 = EMNLP 2024 主会；prometheus-eval org 1,107★ | arxiv.org/abs/2405.01535 + api.github.com search | 已核实 |
| 自偏好偏差论文 = arXiv:2404.13076（Panickssery et al.） | export.arxiv.org API（标题+作者+日期） | 已核实（venue 未核实） |
| TRACe 归因评测基准 | arXiv API 多检索式 + Semantic Scholar（限流） | **未核实** |
| 各论文 Google Scholar 精确被引数 | Semantic Scholar 持续 429 | **未核实**（改用 OpenAlex：G-Eval 708 / RAGAS 404 / MT-Bench ~579 / ARES 110 / ALCE 177） |
