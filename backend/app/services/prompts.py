"""Central versioned registry of every LLM prompt used by the Python backend.

Each entry pairs a stable version identifier (persisted in query logs and
agent runs for reproducibility) with the system prompt it describes. Bump the
version whenever the prompt text changes so historical records stay
attributable to the exact prompt that produced them.

The Rust backend mirrors these prompts in src/api/rag.rs and
src/api/agents.rs; tests/test_prompt_registry.py guards against the two
runtimes drifting apart on version identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    version: str
    system_prompt: str


# Shared evidence-grounded system prompt reused by both project_rag and bm25_rag.
_EVIDENCE_GROUNDED_PROMPT = (
    "你是科研电子实验笔记系统中的问答助手。只依据下方提供的项目资料回答，"
    "禁止使用自身知识补充任何实验数据、数值或结论。"
    "不得补充上下文中不存在的实验事实。每个关键事实必须标注依据："
    "资料事实使用 [S编号]，图谱关系使用 [G编号]，同时依赖两类证据时同时标注。"
    "只要提供了项目资料检索结果，最终答案必须至少包含一个 [S编号]，"
    "只要提供了知识图谱上下文，最终答案必须至少包含一个 [G编号]；"
    "知识图谱关系不能替代原始资料来源，原始资料来源也不能替代图谱关系。"
    "只回答用户问题要求的对象、数值或结论；对于最高、最低、分别报告、对应关系等问题，"
    "先在证据中比较后再输出答案，不要把非答案候选样本、候选数值或背景条目列入最终回答。"
    "若证据只能支持部分答案，明确写出已确认部分和无法确认部分。证据不足时明确回答无法确认。"
)

PROMPTS: dict[str, PromptSpec] = {
    "project_rag": PromptSpec(
        version="rag-v8-source-and-graph-citations",
        system_prompt=_EVIDENCE_GROUNDED_PROMPT,
    ),
    "bm25_rag": PromptSpec(
        version="bm25-rag-v1",
        # BM25 retrieval reuses the standard evidence-grounded system prompt;
        # only the retrieval pipeline (and therefore the version tag) differs.
        system_prompt=_EVIDENCE_GROUNDED_PROMPT,
    ),
    "pure_llm": PromptSpec(
        version="pure-llm-v1",
        system_prompt=(
            "你是纯大语言模型基线。不要假设你能访问项目资料、实验笔记或知识图谱。"
            "问题涉及未提供的项目事实时，必须明确回答无法确认。"
        ),
    ),
    "structured_query": PromptSpec(
        version="structured-query-v2",
        system_prompt=(
            "你是科研电子实验笔记系统中的结构化查询助手。"
            "只能依据下方提供的结构化图谱关系回答用户问题。"
            "不得编造图谱关系中不存在的事实。"
            "每个关键事实必须标注依据：使用 [G编号] 标注对应的图谱关系编号。"
            "如果提供的结构化图谱关系不足以回答用户问题，必须明确回答无法确认，"
            "不能自行补充上下文中没有的信息。"
        ),
    ),
    "agent_writer": PromptSpec(
        version="agent-v5-citation-repair",
        system_prompt=(
            "你是科研电子实验笔记系统中的内容生成智能体。只能依据资料整理智能体提供的已审核实验记录、"
            "资料列表和知识图谱关系生成内容，不得虚构实验、数据或结论。输出应结构清晰、语言正式，"
            "并在关键结论后原样复用上下文中的 [N数字] 笔记编号、[F数字] 资料编号或 [R数字] 图谱关系编号。"
            "不得自行编造、重排或缩写编号；证据不足时明确说明。"
        ),
    ),
}
