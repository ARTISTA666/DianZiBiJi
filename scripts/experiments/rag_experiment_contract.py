"""Shared, stable field contracts for the paper evidence pipeline."""

from __future__ import annotations


MODES = ("pure_llm", "bm25_rag", "project_rag", "structured_query", "kg_enhanced_rag")

PAPER_BLOCKER_ARCHIVE_MAPPING = (
    (
        "report_scope_is_internal_only",
        "范围声明（不属于八项最低清单）",
        "明确区分内部开发证据与确认性证据",
    ),
    ("app_revision_is_bound", "8. 版本归档", "代码 revision 与运行时版本可复核"),
    ("external_freeze_inputs_present", "1. 数据绑定", "语料快照、文件清单与哈希齐备"),
    ("multi_project_question_set_ready", "2. 问题集绑定", "至少 3 个项目、至少 60 题"),
    ("independent_human_review_present", "6. 人工评价", "双人盲评、签核与一致性统计齐备"),
    ("confirmatory_evidence_package_present", "4. 逐案例证据", "同批次 v1 证据包与逐案例证据齐备"),
)

RETRIEVAL_SNAPSHOT_FIELDS = {
    "pure_llm": (),
    "bm25_rag": (
        "corpus_snapshot_hash",
        "retrieval_top_k",
        "collection_retrieval_top_k",
        "chunk_size",
        "chunk_overlap",
    ),
    "project_rag": (
        "embedding_model",
        "corpus_snapshot_hash",
        "retrieval_top_k",
        "collection_retrieval_top_k",
        "vector_candidate_k",
        "chunk_size",
        "chunk_overlap",
    ),
    "structured_query": ("graph_schema_version", "graph_top_k", "graph_min_score"),
    "kg_enhanced_rag": (
        "embedding_model",
        "corpus_snapshot_hash",
        "retrieval_top_k",
        "collection_retrieval_top_k",
        "vector_candidate_k",
        "graph_top_k",
        "chunk_size",
        "chunk_overlap",
        "graph_min_score",
    ),
}
