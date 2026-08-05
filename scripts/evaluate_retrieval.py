#!/usr/bin/env python3
"""Evaluate BM25, vector, hybrid, and graph-enhanced evidence retrieval."""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.metadata
import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ir_measures
import numpy as np
from ir_measures import R, RR, nDCG


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

DEFAULT_PROJECT = "GSE111619 KG-RAG 原始语料盲测项目"
DEFAULT_QUESTIONS = ROOT / "data" / "real" / "GSE111619" / "gse111619_questions.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "real" / "GSE111619" / "retrieval-evaluation"
MODES = ("bm25", "vector", "hybrid_rag", "graph_enhanced_rag")
ABLATION_MODES = (
    "full",
    "without_graph",
    "without_bm25",
    "without_vector",
    "without_collection_graph_expansion",
)
MEASURES = (R @ 1, R @ 3, R @ 5, R @ 10, RR, nDCG @ 10)
MEASURE_NAMES = {
    str(R @ 1): "Recall@1",
    str(R @ 3): "Recall@3",
    str(R @ 5): "Recall@5",
    str(R @ 10): "Recall@10",
    str(RR): "MRR",
    str(nDCG @ 10): "nDCG@10",
}


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    evidence_type: str
    text: str
    source: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").lower().replace("μ", "µ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fffµ><=]+", "", normalized)


def load_questions(path: Path) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("Question file must contain a non-empty JSON list")
    seen: set[str] = set()
    for record in records:
        question_id = str(record.get("id", "")).strip()
        question = str(record.get("question", "")).strip()
        facts = record.get("facts")
        if not question_id or question_id in seen or not question or not isinstance(facts, list) or not facts:
            raise ValueError(f"Invalid question record: {record!r}")
        seen.add(question_id)
        for fact in facts:
            aliases = fact.get("aliases")
            if not fact.get("label") or not isinstance(aliases, list) or not aliases:
                raise ValueError(f"Question {question_id} has an invalid fact: {fact!r}")
    return records


def fact_ids(question: dict[str, Any]) -> list[str]:
    return [f"{question['id']}:F{index:02d}" for index, _ in enumerate(question["facts"], start=1)]


def matching_fact_ids(text: str, question: dict[str, Any]) -> list[str]:
    haystack = normalize_match_text(text)
    matches: list[str] = []
    for fact_id, fact in zip(fact_ids(question), question["facts"], strict=True):
        if any(normalize_match_text(str(alias)) in haystack for alias in fact["aliases"]):
            matches.append(fact_id)
    return matches


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    rank_constant: int = 60,
) -> tuple[list[str], dict[str, float]]:
    scores: defaultdict[str, float] = defaultdict(float)
    best_rank: dict[str, int] = {}
    for ranking in rankings:
        for rank, evidence_id in enumerate(ranking, start=1):
            scores[evidence_id] += 1.0 / (rank_constant + rank)
            best_rank[evidence_id] = min(rank, best_rank.get(evidence_id, rank))
    ordered = sorted(scores, key=lambda item: (-scores[item], best_rank[item], item))
    return ordered, dict(scores)


def evidence_ranking_to_fact_run(
    mode: str,
    question: dict[str, Any],
    ranking: list[str],
    evidence_by_id: dict[str, Evidence],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    emitted: list[str] = []
    seen_facts: set[str] = set()
    trace: list[dict[str, Any]] = []
    for evidence_rank, evidence_id in enumerate(ranking, start=1):
        evidence = evidence_by_id[evidence_id]
        new_matches = [
            fact_id
            for fact_id in matching_fact_ids(evidence.text, question)
            if fact_id not in seen_facts
        ]
        if new_matches:
            for fact_id in new_matches:
                seen_facts.add(fact_id)
                emitted.append(fact_id)
                trace.append(
                    {
                        "mode": mode,
                        "question_id": question["id"],
                        "fact_id": fact_id,
                        "evidence_rank": evidence_rank,
                        "fact_rank": len(emitted),
                        "evidence_id": evidence_id,
                        "evidence_type": evidence.evidence_type,
                        "source": evidence.source,
                    }
                )
        else:
            emitted.append(f"{question['id']}:I:{mode}:{evidence_rank:05d}")
    total = len(emitted)
    return {document_id: float(total - rank + 1) for rank, document_id in enumerate(emitted, start=1)}, trace


def metric_name(measure: object) -> str:
    return MEASURE_NAMES.get(str(measure), str(measure))


def calculate_metrics(
    qrels: dict[str, dict[str, int]],
    runs: dict[str, dict[str, dict[str, float]]],
    modes: tuple[str, ...] = MODES,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    aggregate_rows: list[dict[str, Any]] = []
    per_query_rows: list[dict[str, Any]] = []
    for mode in modes:
        aggregate = ir_measures.calc_aggregate(MEASURES, qrels, runs[mode])
        aggregate_rows.append(
            {"mode": mode, **{metric_name(measure): round(float(value), 6) for measure, value in aggregate.items()}}
        )
        for result in ir_measures.iter_calc(MEASURES, qrels, runs[mode]):
            per_query_rows.append(
                {
                    "mode": mode,
                    "question_id": result.query_id,
                    "metric": metric_name(result.measure),
                    "value": round(float(result.value), 6),
                }
            )
    return aggregate_rows, per_query_rows


def format_per_query_rows(
    metric_rows: list[dict[str, Any]],
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    question_by_id = {record["id"]: record for record in questions}
    grouped: defaultdict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in metric_rows:
        grouped[(row["mode"], row["question_id"])][row["metric"]] = row["value"]
    return [
        {
            "mode": mode,
            "question_id": question_id,
            "category": question_by_id[question_id].get("category", ""),
            "question": question_by_id[question_id]["question"],
            "fact_count": len(question_by_id[question_id]["facts"]),
            **values,
        }
        for (mode, question_id), values in sorted(grouped.items())
    ]


def ablation_delta_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    full = next(row for row in rows if row["mode"] == "full")
    metrics = ("Recall@1", "Recall@3", "Recall@5", "Recall@10", "MRR", "nDCG@10")
    return [
        {
            **row,
            **{f"delta_{metric}": round(row[metric] - full[metric], 6) for metric in metrics},
        }
        for row in rows
    ]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def package_versions() -> dict[str, str]:
    names = (
        "fastembed",
        "ir-measures",
        "numpy",
        "pytrec-eval-terrier",
        "scipy",
        "sqlalchemy",
    )
    return {name: importlib.metadata.version(name) for name in names}


def evidence_id_for_chunk(filename: str, chunk_index: int, content_hash: str) -> str:
    return f"chunk:{filename}:{chunk_index}:{content_hash[:12]}"


def evidence_id_for_graph(item: dict[str, Any]) -> str:
    identity = {
        "source": item["source_label"],
        "relation": item["relation_type"],
        "target": item["target_label"],
    }
    return f"graph:{sha256_json(identity)[:16]}"


def graph_evidence(item: dict[str, Any]) -> Evidence:
    evidence_id = evidence_id_for_graph(item)
    text = " ".join(
        [
            item["source_label"],
            item["relation_type"],
            item["relation_label"],
            item["target_label"],
            " ".join(item.get("relation_roles") or []),
        ]
    )
    return Evidence(evidence_id, "graph_relation", text, f"{item['source_label']} -> {item['target_label']}")


def cosine_scores(query_vector: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_norm = np.linalg.norm(query_vector)
    row_norms = np.linalg.norm(matrix, axis=1)
    denominator = np.maximum(row_norms * query_norm, 1e-12)
    return matrix @ query_vector / denominator


def ranked_ids(ids: list[str], scores: np.ndarray | list[float]) -> list[str]:
    return [
        evidence_id
        for _, evidence_id in sorted(
            zip((float(score) for score in scores), ids, strict=True),
            key=lambda item: (-item[0], item[1]),
        )
    ]


def build_report(
    report: dict[str, Any],
    aggregate_rows: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# 自动检索评价报告",
        "",
        "> 本报告只评价是否检索到预设证据事实，不评价答案文风，也不调用生成模型。题目和金标准由项目开发方整理，因此属于内部自动评价，不是独立第三方结论。",
        "",
        "## 固定输入",
        "",
        f"- 项目：{report['project']['name']}（ID={report['project']['id']}）",
        f"- 问题数：{report['question_count']}；预设事实数：{report['fact_count']}",
        f"- 文档块数：{report['corpus']['chunk_count']}；图谱关系数：{report['corpus']['relation_count']}",
        f"- 题集 SHA-256：`{report['questions_sha256']}`",
        f"- 语料 SHA-256：`{report['corpus']['sha256']}`",
        "",
        "## 汇总结果",
        "",
        "| 模式 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | nDCG@10 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in aggregate_rows:
        lines.append(
            f"| {row['mode']} | {row['Recall@1']:.4f} | {row['Recall@3']:.4f} | "
            f"{row['Recall@5']:.4f} | {row['Recall@10']:.4f} | {row['MRR']:.4f} | {row['nDCG@10']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 消融结果",
            "",
            f"- 集合型问题：{report['configuration']['collection_query_count']} 个（{'、'.join(report['configuration']['collection_question_ids'])}）。",
            "- 变化值相对完整方案计算；关闭组件后指标上升，表示该组件在当前数据上未证明有稳定正收益。",
            "",
            "| 条件 | Recall@10 | 变化 | MRR | 变化 | nDCG@10 | 变化 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in ablation_rows:
        lines.append(
            f"| {row['mode']} | {row['Recall@10']:.4f} | {row['delta_Recall@10']:+.4f} | "
            f"{row['MRR']:.4f} | {row['delta_MRR']:+.4f} | "
            f"{row['nDCG@10']:.4f} | {row['delta_nDCG@10']:+.4f} |"
        )
    lines.extend(
        [
            "",
            "## 计算口径",
            "",
            "- BM25 使用系统运行时同款 Rust/Python 兼容实现（k1=1.2、b=0.75）。",
            "- 向量检索使用系统现有 FastEmbed 模型和数据库中的文档向量。",
            "- 混合 RAG 使用 RRF 合并 BM25 与向量排名，RRF 常数为 60。",
            "- 图谱增强 RAG 再用 RRF 合并混合检索排名与图谱关系排名。",
            f"- BM25 和向量检索各取前 {report['configuration']['candidate_k']} 条候选后进行融合。",
            f"- 集合型问题关闭扩展时，只将其图谱候选从 {report['configuration']['graph_limit']} 条改为 {report['configuration']['collection_base_graph_limit']} 条；其他条件不变。",
            "- 每个预设事实作为一个评价单元；证据首次支持该事实时记为命中，无关证据保留为未命中位置。指标由 `ir-measures` 计算。",
            f"- 结果 SHA-256：`{report['result_sha256']}`",
            f"- 重复运行校验：{'通过' if report['reproducibility_verified'] else '未执行'}。",
            "",
            "## 边界",
            "",
            "该题集来自同一 GSE111619 项目，且已经用于项目内部开发。结果可以检查四条检索路径是否真实运行及其相对表现，不能直接外推到其他实验类型，也不能替代新的独立题集或人工盲评。",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    from app.core.database import SessionLocal
    from app.models.file import StoredFile
    from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
    from app.models.project import Project
    from app.models.rag import RagDocumentChunk
    from app.services.embedding import EmbeddingClient
    from app.services.local_rag import LocalRagService
    from app.services.knowledge_graph import (
        GRAPH_SCHEMA_VERSION,
        KnowledgeGraphService,
        is_collection_query,
    )

    questions_path = args.questions.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    questions = load_questions(questions_path)
    collection_question_ids = [
        record["id"]
        for record in questions
        if is_collection_query(record["question"])
    ]
    collection_question_id_set = set(collection_question_ids)

    with SessionLocal() as db:
        project = db.query(Project).filter(Project.name == args.project).one_or_none()
        if project is None:
            raise ValueError(f"Project not found: {args.project}")
        chunks = (
            db.query(RagDocumentChunk)
            .filter(RagDocumentChunk.project_id == project.id)
            .order_by(RagDocumentChunk.id)
            .all()
        )
        if not chunks:
            raise ValueError(f"Project {project.id} has no indexed document chunks")
        files = {
            record.id: record
            for record in db.query(StoredFile).filter(StoredFile.project_id == project.id).all()
        }
        entities = (
            db.query(KnowledgeEntity)
            .filter(KnowledgeEntity.project_id == project.id)
            .order_by(KnowledgeEntity.id)
            .all()
        )
        relations = (
            db.query(KnowledgeRelation)
            .filter(KnowledgeRelation.project_id == project.id)
            .order_by(KnowledgeRelation.id)
            .all()
        )
        entity_by_id = {entity.id: entity for entity in entities}
        relation_rows = [
            {
                "id": relation.id,
                "source": {
                    "id": relation.source_entity_id,
                    "type": entity_by_id[relation.source_entity_id].entity_type,
                    "label": entity_by_id[relation.source_entity_id].label,
                    "properties": entity_by_id[relation.source_entity_id].properties or {},
                },
                "relation": relation.relation_type,
                "target": {
                    "id": relation.target_entity_id,
                    "type": entity_by_id[relation.target_entity_id].entity_type,
                    "label": entity_by_id[relation.target_entity_id].label,
                    "properties": entity_by_id[relation.target_entity_id].properties or {},
                },
                "confidence": relation.confidence,
                "properties": relation.properties or {},
            }
            for relation in relations
        ]

        evidence_by_id: dict[str, Evidence] = {}
        chunk_ids: list[str] = []
        chunk_texts: list[str] = []
        embeddings: list[list[float]] = []
        corpus_rows: list[dict[str, Any]] = []
        for chunk in chunks:
            filename = files[chunk.file_id].original_filename
            evidence_id = evidence_id_for_chunk(filename, chunk.chunk_index, chunk.content_hash)
            evidence_by_id[evidence_id] = Evidence(evidence_id, "document_chunk", chunk.content, filename)
            chunk_ids.append(evidence_id)
            chunk_texts.append(chunk.content)
            embeddings.append(chunk.embedding or [])
            corpus_rows.append(
                {
                    "evidence_id": evidence_id,
                    "filename": filename,
                    "chunk_index": chunk.chunk_index,
                    "content_hash": chunk.content_hash,
                    "embedding_sha256": sha256_json(chunk.embedding or []),
                }
            )
        embedding_matrix = np.asarray(embeddings, dtype=np.float64)
        if embedding_matrix.ndim != 2 or embedding_matrix.shape[0] != len(chunks):
            raise ValueError("Stored embeddings are missing or inconsistent")

        embedding_client = EmbeddingClient()
        query_vectors = asyncio.run(
            embedding_client.embed_documents([record["question"] for record in questions])
        )
        graph_service = KnowledgeGraphService()

        qrels = {question["id"]: {fact_id: 1 for fact_id in fact_ids(question)} for question in questions}
        runs: dict[str, dict[str, dict[str, float]]] = {mode: {} for mode in MODES}
        ablation_runs: dict[str, dict[str, dict[str, float]]] = {
            mode: {} for mode in ABLATION_MODES
        }
        trace_rows: list[dict[str, Any]] = []
        evidence_rows: list[dict[str, Any]] = []
        score_rows: list[dict[str, Any]] = []

        for question, query_vector in zip(questions, query_vectors, strict=True):
            bm25_scores = LocalRagService._bm25_scores(question["question"], chunk_texts)
            vector_scores = cosine_scores(np.asarray(query_vector, dtype=np.float64), embedding_matrix)
            bm25_ranking = ranked_ids(chunk_ids, bm25_scores)[: args.candidate_k]
            vector_ranking = ranked_ids(chunk_ids, vector_scores)[: args.candidate_k]
            hybrid_ranking, hybrid_scores = reciprocal_rank_fusion([bm25_ranking, vector_ranking])

            graph_items = graph_service.find_relevant_context(
                db,
                project.id,
                question["question"],
                limit=args.graph_limit,
            )
            graph_ranking: list[str] = []
            for item in graph_items:
                evidence = graph_evidence(item)
                evidence_by_id[evidence.evidence_id] = evidence
                graph_ranking.append(evidence.evidence_id)
            graph_enhanced_ranking, graph_enhanced_scores = reciprocal_rank_fusion(
                [hybrid_ranking[: args.candidate_k], graph_ranking]
            )
            without_bm25_ranking, _ = reciprocal_rank_fusion([vector_ranking, graph_ranking])
            without_vector_ranking, _ = reciprocal_rank_fusion([bm25_ranking, graph_ranking])
            is_collection_query = question["id"] in collection_question_id_set
            limited_graph_ranking = (
                graph_ranking[: args.collection_base_graph_limit]
                if is_collection_query
                else graph_ranking
            )
            without_collection_expansion_ranking, _ = reciprocal_rank_fusion(
                [hybrid_ranking[: args.candidate_k], limited_graph_ranking]
            )

            rankings = {
                "bm25": bm25_ranking,
                "vector": vector_ranking,
                "hybrid_rag": hybrid_ranking,
                "graph_enhanced_rag": graph_enhanced_ranking,
            }
            score_maps = {
                "bm25": dict(zip(chunk_ids, (float(value) for value in bm25_scores), strict=True)),
                "vector": dict(zip(chunk_ids, (float(value) for value in vector_scores), strict=True)),
                "hybrid_rag": hybrid_scores,
                "graph_enhanced_rag": graph_enhanced_scores,
            }
            for mode, ranking in rankings.items():
                runs[mode][question["id"]], trace = evidence_ranking_to_fact_run(
                    mode,
                    question,
                    ranking,
                    evidence_by_id,
                )
                trace_rows.extend(trace)
                for rank, evidence_id in enumerate(ranking[: args.trace_top_k], start=1):
                    evidence = evidence_by_id[evidence_id]
                    matches = matching_fact_ids(evidence.text, question)
                    evidence_rows.append(
                        {
                            "mode": mode,
                            "question_id": question["id"],
                            "rank": rank,
                            "evidence_id": evidence_id,
                            "evidence_type": evidence.evidence_type,
                            "source": evidence.source,
                            "matched_fact_ids": json.dumps(matches, ensure_ascii=False),
                            "text": evidence.text[:500].replace("\n", " "),
                        }
                    )
                    score_rows.append(
                        {
                            "mode": mode,
                            "question_id": question["id"],
                            "evidence_id": evidence_id,
                            "score": round(score_maps[mode].get(evidence_id, 0.0), 10),
                        }
                    )

            ablation_rankings = {
                "full": graph_enhanced_ranking,
                "without_graph": hybrid_ranking,
                "without_bm25": without_bm25_ranking,
                "without_vector": without_vector_ranking,
                "without_collection_graph_expansion": without_collection_expansion_ranking,
            }
            for mode, ranking in ablation_rankings.items():
                ablation_runs[mode][question["id"]], _ = evidence_ranking_to_fact_run(
                    mode,
                    question,
                    ranking,
                    evidence_by_id,
                )

    aggregate_rows, per_query_metric_rows = calculate_metrics(qrels, runs)
    per_query_rows = format_per_query_rows(per_query_metric_rows, questions)
    ablation_aggregate, ablation_per_query_metrics = calculate_metrics(
        qrels,
        ablation_runs,
        ABLATION_MODES,
    )
    ablation_rows = ablation_delta_rows(ablation_aggregate)
    ablation_per_query_rows = format_per_query_rows(ablation_per_query_metrics, questions)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": {"id": project.id, "name": project.name},
        "output_dir": str(output_dir),
        "questions_file": questions_path.name,
        "questions_sha256": sha256_file(questions_path),
        "question_count": len(questions),
        "fact_count": sum(len(record["facts"]) for record in questions),
        "corpus": {
            "chunk_count": len(corpus_rows),
            "entity_count": len(entities),
            "relation_count": len(relations),
            "sha256": sha256_json({"chunks": corpus_rows, "relations": relation_rows}),
        },
        "configuration": {
            "modes": list(MODES),
            "rrf_rank_constant": 60,
            "candidate_k": args.candidate_k,
            "graph_limit": args.graph_limit,
            "collection_base_graph_limit": args.collection_base_graph_limit,
            "collection_query_count": len(collection_question_ids),
            "collection_question_ids": collection_question_ids,
            "trace_top_k": args.trace_top_k,
            "graph_schema_version": GRAPH_SCHEMA_VERSION,
            "embedding_model": embedding_client.model,
            "embedding_dimension": embedding_client.dimensions,
            "generation_model_used": False,
            "metric_implementation": "ir-measures",
        },
        "package_versions": package_versions(),
        "aggregate": aggregate_rows,
        "ablation": ablation_rows,
        "expected_result_sha256": args.expected_result_sha256 or None,
    }
    report["result_sha256"] = sha256_json(
        {
            "project": report["project"],
            "questions_sha256": report["questions_sha256"],
            "corpus": report["corpus"],
            "configuration": report["configuration"],
            "package_versions": report["package_versions"],
            "aggregate": aggregate_rows,
            "ablation": ablation_rows,
            "per_query": per_query_rows,
            "ablation_per_query": ablation_per_query_rows,
            "evidence_trace": trace_rows,
        }
    )
    report["reproducibility_verified"] = bool(
        args.expected_result_sha256 and args.expected_result_sha256 == report["result_sha256"]
    )
    if args.expected_result_sha256 and args.expected_result_sha256 != report["result_sha256"]:
        raise AssertionError(
            f"Result hash mismatch: expected {args.expected_result_sha256}, got {report['result_sha256']}"
        )

    write_csv(
        output_dir / "aggregate.csv",
        aggregate_rows,
        ["mode", "Recall@1", "Recall@3", "Recall@5", "Recall@10", "MRR", "nDCG@10"],
    )
    write_csv(
        output_dir / "per-query.csv",
        per_query_rows,
        ["mode", "question_id", "category", "question", "fact_count", "Recall@1", "Recall@3", "Recall@5", "Recall@10", "MRR", "nDCG@10"],
    )
    ablation_fields = [
        "mode",
        "Recall@1",
        "Recall@3",
        "Recall@5",
        "Recall@10",
        "MRR",
        "nDCG@10",
        "delta_Recall@1",
        "delta_Recall@3",
        "delta_Recall@5",
        "delta_Recall@10",
        "delta_MRR",
        "delta_nDCG@10",
    ]
    write_csv(output_dir / "ablation.csv", ablation_rows, ablation_fields)
    write_csv(
        output_dir / "ablation-per-query.csv",
        ablation_per_query_rows,
        ["mode", "question_id", "category", "question", "fact_count", "Recall@1", "Recall@3", "Recall@5", "Recall@10", "MRR", "nDCG@10"],
    )
    write_csv(
        output_dir / "evidence-trace.csv",
        trace_rows,
        ["mode", "question_id", "fact_id", "evidence_rank", "fact_rank", "evidence_id", "evidence_type", "source"],
    )
    write_csv(
        output_dir / "top-evidence.csv",
        evidence_rows,
        ["mode", "question_id", "rank", "evidence_id", "evidence_type", "source", "matched_fact_ids", "text"],
    )
    write_csv(
        output_dir / "scores.csv",
        score_rows,
        ["mode", "question_id", "evidence_id", "score"],
    )
    (output_dir / "qrels.json").write_text(
        json.dumps(qrels, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    fact_catalog_rows = [
        {
            "question_id": question["id"],
            "fact_id": fact_id,
            "label": fact["label"],
            "aliases": json.dumps(fact["aliases"], ensure_ascii=False),
        }
        for question in questions
        for fact_id, fact in zip(fact_ids(question), question["facts"], strict=True)
    ]
    write_csv(
        output_dir / "fact-catalog.csv",
        fact_catalog_rows,
        ["question_id", "fact_id", "label", "aliases"],
    )
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        build_report(report, aggregate_rows, ablation_rows),
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--candidate-k", type=int, default=30)
    parser.add_argument("--graph-limit", type=int, default=30)
    parser.add_argument("--collection-base-graph-limit", type=int, default=10)
    parser.add_argument("--trace-top-k", type=int, default=20)
    parser.add_argument("--expected-result-sha256", default="")
    args = parser.parse_args()
    if (
        args.candidate_k < 1
        or args.graph_limit < 1
        or args.collection_base_graph_limit < 1
        or args.trace_top_k < 1
    ):
        parser.error("limits must be positive")
    if args.collection_base_graph_limit > args.graph_limit:
        parser.error("collection base graph limit cannot exceed graph limit")
    return args


if __name__ == "__main__":
    result = run(parse_args())
    print(
        json.dumps(
            {"output": result["output_dir"], "result_sha256": result["result_sha256"]},
            ensure_ascii=False,
        )
    )
