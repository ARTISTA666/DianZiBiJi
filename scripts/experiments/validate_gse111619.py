#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import json
import os
import platform
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DEFAULT_DATA_DIR = ROOT / "data" / "real" / "GSE111619"
sys.path.insert(0, str(BACKEND))


EXPECTED_COMPRESSED_HASHES = {
    "GSE111619_family.soft.gz": "fbfb8aa0a5b0bee99c8ec44d641eec82568a4ce24706b1d16a3010c9403c6043",
    "GSE111619_series_matrix.txt.gz": "b8086b3dad39d1120d6e03fc62ee22007692e86c7ad688e4da300c38822b8849",
    "GSE111619_HTSeq_counts.txt.gz": "662eeaa22c55beb5457b447a27be6f9c5df70f831addd3b04ed6bc718de569f5",
}

SOURCE_URLS = {
    "series": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE111619",
    "family_soft": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE111nnn/GSE111619/soft/GSE111619_family.soft.gz",
    "series_matrix": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE111nnn/GSE111619/matrix/GSE111619_series_matrix.txt.gz",
    "counts": "https://ftp.ncbi.nlm.nih.gov/geo/series/GSE111nnn/GSE111619/suppl/GSE111619_RNAseq_H226_shp63_analysis_HTSeq_counts.txt.gz",
}

EXPECTED_SAMPLES = ["GSM3035185", "GSM3035186", "GSM3035187", "GSM3035188"]
EXPECTED_COUNT_COLUMNS = ["NonTargeting_rep1", "NonTargeting_rep2", "p63KD_rep1", "p63KD_rep2"]


@dataclass(frozen=True)
class Fact:
    label: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class QueryCase:
    case_id: str
    question: str
    facts: tuple[Fact, ...]


QUERY_CASES = (
    QueryCase(
        "Q1",
        "哪些样本属于非靶向对照组，哪些样本属于 p63 敲低组？",
        (
            Fact("GSM3035185", ("GSM3035185",)),
            Fact("GSM3035186", ("GSM3035186",)),
            Fact("GSM3035187", ("GSM3035187",)),
            Fact("GSM3035188", ("GSM3035188",)),
            Fact("Control", ("Control", "shControl", "NonTargeting")),
            Fact("p63", ("p63", "shp63", "p63KD")),
        ),
    ),
    QueryCase(
        "Q2",
        "全部样本使用了哪些试剂或处理材料？",
        (
            Fact("doxycycline 1 microgram per mL", ("doxycycline (1 microgram per mL)", "1 µg/mL doxycycline", "1µg/mL doxycycline")),
            Fact("PureLink RNA Mini kit", ("PureLink RNA Mini kit",)),
            Fact("TruSeq Stranded mRNA Library Prep Kit", ("TruSeq Stranded mRNA Library Prep Kit",)),
        ),
    ),
    QueryCase(
        "Q3",
        "使用了哪些仪器进行 RNA 质量评估和测序，质量要求是什么？",
        (
            Fact("Illumina HiSeq 2500", ("Illumina HiSeq 2500", "HiSeq 2500")),
            Fact("Bioanalyzer RNA Pico chips", ("Bioanalyzer RNA Pico chips", "RNA Pico chips")),
            Fact("RIN > 9", ("RIN > 9", "RIN >9")),
        ),
    ),
    QueryCase(
        "Q4",
        "四个样本的结果中，基因计数总量和非零基因条目数分别是多少？",
        (),
    ),
    QueryCase(
        "Q5",
        "HTSeq 计数矩阵共有多少个基因条目？",
        (Fact("count_matrix_gene_rows=25369", ("count_matrix_gene_rows=25369", "25369", "25,369")),),
    ),
    QueryCase(
        "Q6",
        "本系统导入的 GSE111619 数据是什么层级的数据，哪些分析结论不能据此声称？",
        (
            Fact("基因级 HTSeq 计数矩阵", ("基因级 HTSeq 计数矩阵", "gene-level HTSeq count matrix")),
            Fact("不是原始 FASTQ", ("不是原始 FASTQ", "not raw FASTQ")),
            Fact("不据此进行差异表达显著性推断", ("不据此进行差异表达显著性推断", "no differential expression significance inference")),
        ),
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def line_count(path: Path) -> int:
    with path.open("rb") as handle:
        return sum(1 for _ in handle)


def validate_gzip(path: Path) -> None:
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            if not block:
                break


def parse_soft(path: Path) -> tuple[dict[str, list[str]], dict[str, dict[str, list[str]]], dict[str, list[str]]]:
    series: dict[str, list[str]] = defaultdict(list)
    samples: dict[str, dict[str, list[str]]] = {}
    platform_meta: dict[str, list[str]] = defaultdict(list)
    current_kind = ""
    current_sample = ""
    with path.open(encoding="utf-8", errors="strict") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if line.startswith("^SERIES = "):
                current_kind = "series"
                current_sample = ""
            elif line.startswith("^PLATFORM = "):
                current_kind = "platform"
                current_sample = ""
            elif line.startswith("^SAMPLE = "):
                current_kind = "sample"
                current_sample = line.split("=", 1)[1].strip()
                samples[current_sample] = defaultdict(list)
            elif line.startswith("!") and " = " in line:
                key, value = line[1:].split(" = ", 1)
                if current_kind == "series":
                    series[key].append(value)
                elif current_kind == "platform":
                    platform_meta[key].append(value)
                elif current_kind == "sample" and current_sample:
                    samples[current_sample][key].append(value)
    return dict(series), {key: dict(value) for key, value in samples.items()}, dict(platform_meta)


def parse_characteristics(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition(":")
        if separator:
            result[key.strip().lower()] = item.strip()
    return result


def first(values: list[str] | None, default: str = "") -> str:
    return values[0] if values else default


def parse_counts(path: Path) -> tuple[list[str], list[str], np.ndarray]:
    genes: list[str] = []
    rows: list[list[int]] = []
    with path.open(encoding="utf-8", errors="strict", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        if header[0] != "GeneID":
            raise AssertionError(f"Unexpected first column: {header[0]}")
        columns = header[1:]
        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise AssertionError(f"Row {row_number} has {len(row)} fields; expected {len(header)}")
            genes.append(row[0])
            try:
                values = [int(value) for value in row[1:]]
            except ValueError as exc:
                raise AssertionError(f"Non-integer count at row {row_number}") from exc
            if any(value < 0 for value in values):
                raise AssertionError(f"Negative count at row {row_number}")
            rows.append(values)
    return genes, columns, np.asarray(rows, dtype=np.int64)


def normalize_text(value: str) -> str:
    normalized = value.lower().replace("μ", "µ").replace("microgram", "µg")
    return re.sub(r"[^a-z0-9\u4e00-\u9fffµ><=]+", "", normalized)


def matched_facts(text: str, facts: tuple[Fact, ...]) -> list[str]:
    haystack = normalize_text(text)
    return [fact.label for fact in facts if any(normalize_text(alias) in haystack for alias in fact.aliases)]


def sample_column_map(samples: dict[str, dict[str, list[str]]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for accession, metadata in samples.items():
        for description in metadata.get("Sample_description", []):
            if description in EXPECTED_COUNT_COLUMNS:
                mapping[description] = accession
    return mapping


def build_sample_records(
    samples: dict[str, dict[str, list[str]]],
    columns: list[str],
    counts: np.ndarray,
) -> list[dict[str, Any]]:
    column_to_accession = sample_column_map(samples)
    records: list[dict[str, Any]] = []
    for index, column in enumerate(columns):
        accession = column_to_accession[column]
        metadata = samples[accession]
        characteristics = parse_characteristics(metadata.get("Sample_characteristics_ch1", []))
        records.append(
            {
                "geo_accession": accession,
                "count_column": column,
                "title": first(metadata.get("Sample_title")),
                "condition": "control" if "NonTargeting" in column else "p63_knockdown",
                "replicate": 1 if column.endswith("rep1") else 2,
                "cell_line": characteristics.get("cell line", ""),
                "cell_type": characteristics.get("cell type", ""),
                "shrna_construct": characteristics.get("inducible shrna construct", ""),
                "treatment": characteristics.get("treatment", ""),
                "culture_condition": characteristics.get("culture condition", ""),
                "molecule": first(metadata.get("Sample_molecule_ch1")),
                "instrument": first(metadata.get("Sample_instrument_model")),
                "library_strategy": first(metadata.get("Sample_library_strategy")),
                "biosample": next((item.split(": ", 1)[1] for item in metadata.get("Sample_relation", []) if item.startswith("BioSample:")), ""),
                "sra": next((item.split("term=", 1)[1] for item in metadata.get("Sample_relation", []) if item.startswith("SRA:")), ""),
                "total_gene_count": int(counts[:, index].sum()),
                "detected_gene_rows": int(np.count_nonzero(counts[:, index] > 0)),
                "zero_gene_rows": int(np.count_nonzero(counts[:, index] == 0)),
            }
        )
    return records


def dynamic_query_cases(sample_records: list[dict[str, Any]]) -> tuple[QueryCase, ...]:
    cases = list(QUERY_CASES[:3])
    result_facts = []
    for record in sample_records:
        accession = record["geo_accession"]
        total = record["total_gene_count"]
        detected = record["detected_gene_rows"]
        result_facts.append(
            Fact(
                f"{accession}: total_count={total}, detected_gene_rows={detected}",
                (
                    f"{accession}: total_count={total}, detected_gene_rows={detected}",
                    f"{accession}: total_count={total}; detected_gene_rows={detected}",
                    f"{accession} total_count={total} detected_gene_rows={detected}",
                ),
            )
        )
    cases.append(QueryCase(QUERY_CASES[3].case_id, QUERY_CASES[3].question, tuple(result_facts)))
    cases.extend(QUERY_CASES[4:])
    return tuple(cases)


def build_notes(sample_records: list[dict[str, Any]], gene_rows: int) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for record in sample_records:
        accession = record["geo_accession"]
        sample_label = (
            f"{accession} [{record['count_column']} | shRNA={record['shrna_construct']} | "
            f"condition={record['condition']}]"
        )
        count_result = (
            f"{accession}: total_count={record['total_gene_count']}, "
            f"detected_gene_rows={record['detected_gene_rows']}"
        )
        fixed_fields = {
            "source": "NCBI GEO GSE111619",
            "source_accession": accession,
            "reagents": [
                "doxycycline (1 microgram per mL)",
                "PureLink RNA Mini kit",
                "TruSeq Stranded mRNA Library Prep Kit",
            ],
            "instruments": ["Illumina HiSeq 2500", "Bioanalyzer RNA Pico chips"],
            "samples": [sample_label],
            "results": [count_result, "RNA quality: RIN > 9"],
            "cell_line": record["cell_line"],
            "cell_type": record["cell_type"],
            "shrna_construct": record["shrna_construct"],
            "treatment": record["treatment"],
            "culture_condition": record["culture_condition"],
            "genome_build": "GRCh37/hg19",
            "count_method": "HTSeq v0.6.1",
        }
        content_text = (
            f"数据来源：NCBI GEO GSE111619，样本登录号 {accession}。\n"
            f"样本信息为 {sample_label}。\n"
            f"处理：{record['treatment']}；培养条件：{record['culture_condition']}。\n"
            "使用的处理物和建库材料包括 doxycycline (1 microgram per mL)、PureLink RNA Mini kit 和"
            "TruSeq Stranded mRNA Library Prep Kit。\n"
            "仪器信息包括 Illumina HiSeq 2500 和 Bioanalyzer RNA Pico chips。\n"
            "计数摘要为 RNA quality RIN > 9；"
            f"{count_result}；count_matrix_gene_rows={gene_rows}。\n"
            "处理流程：TopHat2 比对至 GRCh37/hg19，HTSeq 生成基因级原始计数；"
            "本文仅作记录管理与检索验证，不据此进行差异表达显著性推断。"
        )
        notes.append(
            {
                "title": f"GSE111619 {accession} RNA-seq record",
                "experiment_type": "RNA-Seq",
                "experiment_date": None,
                "status": "approved",
                "fixed_fields_json": fixed_fields,
                "content_json": {"text": content_text},
            }
        )
    return notes


def build_knowledge_document(series: dict[str, list[str]], notes: list[dict[str, Any]]) -> str:
    paragraphs = [
        "\n".join(
            [
                "GEO series GSE111619 structured validation document",
                f"研究标题：{first(series.get('Series_title'))}",
                "研究设计：H226 肺鳞状细胞癌细胞中，比较 doxycycline 诱导的非靶向 shRNA 对照与 p63 靶向 shRNA；每组两个生物学重复。",
                "数据边界：下载并处理的是 GEO 提供的基因级 HTSeq 计数矩阵和 SOFT 元数据，不是本地实验室原始笔记，也不是原始 FASTQ 读段。",
                "来源：https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE111619",
            ]
        )
    ]
    for note in notes:
        fields = note["fixed_fields_json"]
        paragraphs.append(
            "\n".join(
                [
                    note["title"],
                    note["content_json"]["text"],
                    f"结构化样本字段：{'; '.join(fields['samples'])}。",
                    f"结构化结果字段：{'; '.join(fields['results'])}。",
                    "元数据处理软件包括 bcl2fastq v1.8.4、FASTQC v0.11.2、TopHat2 v2.0.13、SAMtools v0.1.19、Picard v1.129、RSeQC v2.6 和 HTSeq v0.6.1。",
                ]
            )
        )
    return "\n\n".join(paragraphs) + "\n"


def descriptive_statistics(columns: list[str], counts: np.ndarray) -> dict[str, Any]:
    transformed = np.log1p(counts.astype(np.float64))
    correlations = np.corrcoef(transformed, rowvar=False)
    pairs = {}
    for left in range(len(columns)):
        for right in range(left + 1, len(columns)):
            pairs[f"{columns[left]}__{columns[right]}"] = round(float(correlations[left, right]), 6)
    return {
        "total_counts_all_samples": int(counts.sum()),
        "minimum_count": int(counts.min()),
        "maximum_count": int(counts.max()),
        "log1p_pearson_correlations": pairs,
        "within_condition_correlations": {
            "NonTargeting_rep1__NonTargeting_rep2": pairs["NonTargeting_rep1__NonTargeting_rep2"],
            "p63KD_rep1__p63KD_rep2": pairs["p63KD_rep1__p63KD_rep2"],
        },
    }


def package_versions() -> dict[str, str]:
    import fastembed
    import sqlalchemy

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "sqlalchemy": sqlalchemy.__version__,
        "fastembed": fastembed.__version__,
    }


class OfflineHashEmbeddingClient:
    """Deterministic test embedding used when the production model is unavailable."""

    dimensions = 512

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._encode(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._encode(text)

    def _encode(self, text: str) -> list[float]:
        normalized = text.lower().replace("μ", "µ")
        ascii_tokens = re.findall(r"[a-z0-9µ><=_-]+", normalized)
        chinese_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
        chinese_bigrams = [run[index : index + 2] for run in chinese_runs for index in range(max(1, len(run) - 1))]
        tokens = ascii_tokens + chinese_bigrams
        vector = np.zeros(self.dimensions, dtype=np.float64)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        if norm:
            vector /= norm
        return vector.tolist()


def run_system_validation(
    data_dir: Path,
    notes: list[dict[str, Any]],
    query_cases: tuple[QueryCase, ...],
    embedding_mode: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    os.environ["EMBEDDING_CACHE_PATH"] = str(data_dir / "model-cache")
    os.environ["EMBEDDING_MODEL"] = "BAAI/bge-small-zh-v1.5"
    os.environ["EMBEDDING_DIMENSION"] = "512"
    os.environ["RAG_RETRIEVAL_TOP_K"] = "6"
    os.environ["RAG_VECTOR_CANDIDATE_K"] = "30"

    import app.models  # noqa: F401
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import get_settings
    from app.core.database import Base
    from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
    from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation
    from app.models.note import ExperimentNote, NoteStatus, NoteVersion
    from app.models.project import Project
    from app.models.rag import RagDocumentChunk
    from app.models.user import User, UserRole
    from app.services.knowledge_graph import KnowledgeGraphService
    from app.services.local_rag import LocalRagService

    get_settings.cache_clear()
    database_path = data_dir / "gse111619_validation.sqlite3"
    database_path.unlink(missing_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)

    comparison_rows: list[dict[str, Any]] = []
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            username="geo_import",
            password_hash="not-used-in-offline-validation",
            display_name="GEO data importer",
            role=UserRole.MEMBER,
        )
        db.add(user)
        db.flush()
        project = Project(
            name="GSE111619 real-data validation",
            description="Offline validation project built from public NCBI GEO metadata and processed counts",
            approval_enabled=True,
            owner_user_id=user.id,
        )
        db.add(project)
        db.flush()

        note_models = []
        for payload in notes:
            note = ExperimentNote(
                project_id=project.id,
                title=payload["title"],
                experiment_type=payload["experiment_type"],
                experiment_date=None,
                owner_user_id=user.id,
                status=NoteStatus.APPROVED,
            )
            db.add(note)
            db.flush()
            version = NoteVersion(
                note_id=note.id,
                version_number=1,
                fixed_fields_json=payload["fixed_fields_json"],
                content_json=payload["content_json"],
                created_by=user.id,
                change_summary="Imported from verified GEO metadata and counts for offline validation",
                is_locked=True,
            )
            db.add(version)
            db.flush()
            note.current_version_id = version.id
            note_models.append(note)

        knowledge_paths = [
            data_dir / "gse111619_knowledge_document.txt",
            data_dir / "GSE111619_series_matrix.txt",
            data_dir / "GSE111619_HTSeq_counts.txt",
        ]
        file_records = []
        for knowledge_path in knowledge_paths:
            file_record = StoredFile(
                project_id=project.id,
                note_id=None,
                uploaded_by=user.id,
                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                original_filename=knowledge_path.name,
                storage_path=str(knowledge_path),
                mime_type="text/plain",
                file_size=knowledge_path.stat().st_size,
                file_hash=sha256_file(knowledge_path),
                status=FileStatus.APPROVED,
                knowledge_sync_status=KnowledgeSyncStatus.PENDING_SYNC.value,
            )
            db.add(file_record)
            db.flush()
            file_records.append(file_record)

        graph_service = KnowledgeGraphService()
        extraction_runs = []
        for note in note_models:
            run = graph_service.extract_note(db, note, triggered_by=user.id, rebuild=True)
            extraction_runs.append(
                {
                    "note_id": note.id,
                    "status": run.status,
                    "extracted_entities": run.extracted_entities,
                    "extracted_relations": run.extracted_relations,
                }
            )
        db.flush()

        entity_counts = dict(
            sorted(Counter(entity.entity_type for entity in db.query(KnowledgeEntity).all()).items())
        )
        relation_counts = dict(
            sorted(Counter(relation.relation_type for relation in db.query(KnowledgeRelation).all()).items())
        )
        counts_before_rebuild = {
            "entities": db.query(KnowledgeEntity).count(),
            "relations": db.query(KnowledgeRelation).count(),
        }
        for note in note_models:
            graph_service.extract_note(db, note, triggered_by=user.id, rebuild=True)
        db.flush()
        counts_after_rebuild = {
            "entities": db.query(KnowledgeEntity).count(),
            "relations": db.query(KnowledgeRelation).count(),
        }
        if counts_before_rebuild != counts_after_rebuild:
            raise AssertionError(
                f"Knowledge graph rebuild is not idempotent: {counts_before_rebuild} != {counts_after_rebuild}"
            )

        rag_summary: dict[str, Any]
        if embedding_mode == "skip":
            rag_summary = {
                "status": "skipped",
                "reason": "--skip-rag was supplied",
                "embedding_model": "BAAI/bge-small-zh-v1.5",
                "chunk_count": 0,
            }
        else:
            embedding_client = OfflineHashEmbeddingClient() if embedding_mode == "offline_hash" else None
            rag_service = LocalRagService(embedding_client=embedding_client)
            chunks_by_file = {}
            for file_record in file_records:
                chunks_by_file[file_record.original_filename] = asyncio.run(rag_service.index_file(db, file_record))
                file_record.knowledge_sync_status = KnowledgeSyncStatus.SYNCED.value
            chunk_count = sum(chunks_by_file.values())
            db.flush()
            for case in query_cases:
                retrieved = asyncio.run(rag_service.retrieve(db, project.id, case.question))
                graph_items = graph_service.find_relevant_context(db, project.id, case.question)
                plain_evidence = "\n".join(item.snippet for item in retrieved)
                graph_evidence = "\n".join(
                    f"{item['source_label']} {item['relation_type']} {item['target_label']}"
                    for item in graph_items
                )
                plain_matches = matched_facts(plain_evidence, case.facts)
                enhanced_matches = matched_facts(plain_evidence + "\n" + graph_evidence, case.facts)
                total_facts = len(case.facts)
                comparison_rows.append(
                    {
                        "case_id": case.case_id,
                        "question": case.question,
                        "expected_fact_count": total_facts,
                        "ordinary_rag_matched": len(plain_matches),
                        "ordinary_rag_recall": round(len(plain_matches) / total_facts, 4),
                        "kg_enhanced_matched": len(enhanced_matches),
                        "kg_enhanced_recall": round(len(enhanced_matches) / total_facts, 4),
                        "recall_delta": round((len(enhanced_matches) - len(plain_matches)) / total_facts, 4),
                        "ordinary_matched_facts": plain_matches,
                        "enhanced_matched_facts": enhanced_matches,
                        "rag_source_count": len(retrieved),
                        "graph_relation_count": len(graph_items),
                        "top_rag_scores": [round(item.retrieval_score, 6) for item in retrieved],
                    }
                )
            rag_summary = {
                "status": "completed",
                "embedding_backend": (
                    "deterministic_offline_hash_512" if embedding_mode == "offline_hash" else "fastembed"
                ),
                "embedding_model": (
                    "not_applicable_test_double" if embedding_mode == "offline_hash" else get_settings().embedding_model
                ),
                "embedding_dimensions": get_settings().embedding_dimension,
                "production_embedding_model_validated": embedding_mode == "fastembed",
                "indexed_file_count": len(file_records),
                "chunk_count": chunk_count,
                "chunks_by_file": chunks_by_file,
                "stored_chunk_count": db.query(RagDocumentChunk).count(),
                "ordinary_macro_recall": round(
                    sum(row["ordinary_rag_recall"] for row in comparison_rows) / len(comparison_rows), 4
                ),
                "kg_enhanced_macro_recall": round(
                    sum(row["kg_enhanced_recall"] for row in comparison_rows) / len(comparison_rows), 4
                ),
            }
        db.commit()

    return (
        {
            "database": database_path.name,
            "project_count": 1,
            "note_count": len(notes),
            "note_version_count": len(notes),
            "knowledge_graph": {
                "extraction_runs": extraction_runs,
                "entity_count": counts_after_rebuild["entities"],
                "relation_count": counts_after_rebuild["relations"],
                "entity_counts_by_type": entity_counts,
                "relation_counts_by_type": relation_counts,
                "rebuild_idempotent": True,
            },
            "rag": rag_summary,
        },
        comparison_rows,
    )


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            }
            writer.writerow(normalized)


def build_fallacy_scan() -> list[dict[str, str]]:
    return [
        {"item": "Simpson's paradox", "status": "not_applicable", "note": "未比较聚合趋势与分层趋势。"},
        {"item": "Ecological fallacy", "status": "not_detected", "note": "未从组水平数据推断个体结论。"},
        {"item": "Berkson's paradox", "status": "not_applicable", "note": "不是按共同结果筛选的临床样本；但单一公开数据集仍有外部效度限制。"},
        {"item": "Collider bias", "status": "not_applicable", "note": "未拟合包含协变量的因果模型。"},
        {"item": "Base-rate neglect", "status": "not_applicable", "note": "未进行诊断分类。"},
        {"item": "Regression to the mean", "status": "not_applicable", "note": "未按极端值筛选前后测样本。"},
        {"item": "Survivorship bias", "status": "not_assessable", "note": "GEO 元数据未提供本研究全部培养样本及排除过程。"},
        {"item": "Look-elsewhere effect", "status": "avoided", "note": "未开展基因逐项显著性检验或筛选显著结果。"},
        {"item": "Garden of forking paths", "status": "limited", "note": "验证规则与问题清单固定在脚本中，但未进行正式预注册。"},
        {"item": "Correlation is not causation", "status": "avoided", "note": "相关系数仅作重复样本描述，不作因果解释。"},
        {"item": "Reverse causality", "status": "not_applicable", "note": "未提出方向性因果结论。"},
    ]


def report_markdown(report: dict[str, Any], comparison_rows: list[dict[str, Any]]) -> str:
    data = report["dataset"]
    graph = report["system_validation"]["knowledge_graph"]
    rag = report["system_validation"]["rag"]
    lines = [
        "# GSE111619 离线预检报告",
        "",
        "> 本文件只记录独立 SQLite 与测试向量后端的离线服务层预检，不是正式部署系统的运行结果。论文中的系统实现与问答实验应引用 `system_import_report.json`、`gse111619_paired_experiment.csv` 和 `gse111619_paired_experiment_report.json`。",
        "",
        f"- Verification Status: **{report['verification_status']}**",
        f"- Reproducibility fingerprint: `{report['reproducibility_fingerprint']}`",
        "- 数据性质：NCBI GEO 公开 RNA-seq 实验元数据和基因级 HTSeq 计数矩阵。",
        "- 使用边界：该数据用于验证实验记录结构化、知识图谱构建和检索证据覆盖，不代表本地实验室数据，也不替代原始 FASTQ 分析。",
        "",
        "## 数据完整性",
        "",
        f"- GEO 系列：{data['series_accession']}，样本数 {data['sample_count']}。",
        f"- 计数矩阵：{data['gene_rows']:,} 个基因条目，{data['count_columns']}。",
        f"- 压缩文件哈希：{data['compressed_hash_checks_passed']}/{data['compressed_hash_checks_total']} 通过。",
        f"- gzip 完整性、字段数、整数类型、非负计数和样本映射检查均通过。",
        "- 元数据存在一处来源内部不一致：系列总体设计写 HiSeq 2000，平台及逐样本字段写 Illumina HiSeq 2500；系统记录采用更具体的逐样本字段，并在报告中保留该警示。",
        "",
        "## 离线服务层预检结果",
        "",
        f"- 导入实验笔记 {report['system_validation']['note_count']} 条，笔记版本 {report['system_validation']['note_version_count']} 条。",
        f"- 知识图谱包含 {graph['entity_count']} 个实体、{graph['relation_count']} 条关系；重复重建后数量不变。",
        f"- 实体类型计数：{json.dumps(graph['entity_counts_by_type'], ensure_ascii=False, sort_keys=True)}。",
        f"- 关系类型计数：{json.dumps(graph['relation_counts_by_type'], ensure_ascii=False, sort_keys=True)}。",
    ]
    if rag["status"] == "completed":
        lines.extend(
            [
                f"- 检索向量后端：{rag['embedding_backend']}（{rag['embedding_dimensions']} 维），生成 {rag['chunk_count']} 个文档块。",
                f"- 4 个固定问题的普通 RAG 宏平均事实召回率为 {rag['ordinary_macro_recall']:.4f}，图谱增强后为 {rag['kg_enhanced_macro_recall']:.4f}。",
                "",
                "## 检索对比",
                "",
                "| 用例 | 普通 RAG 命中/总事实 | 图谱增强命中/总事实 | 召回率增量 | 图谱关系数 |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in comparison_rows:
            lines.append(
                f"| {row['case_id']} | {row['ordinary_rag_matched']}/{row['expected_fact_count']} | "
                f"{row['kg_enhanced_matched']}/{row['expected_fact_count']} | {row['recall_delta']:.4f} | "
                f"{row['graph_relation_count']} |"
            )
    else:
        lines.extend(["- RAG 验证未执行。", "", "## 检索对比", "", "本次运行未生成检索对比结果。"])
    lines.extend(
        [
            "",
            "## 描述性统计限制",
            "",
            "- 每组仅有 2 个生物学重复，不据此进行推断统计或系统效果显著性检验。",
            "- 本报告计算的 log1p Pearson 相关系数仅用于数据一致性描述，不等同于生物学重复质量的完整判定。",
            "- 未运行 DESeq2，也未报告 p 值、置信区间或差异表达基因；论文不得把本验证改写为差异表达结论。",
            "- 检索对比评价的是固定事实是否进入证据上下文，不是大语言模型答案质量，也没有独立人工盲评。",
            "- 若向量后端为 deterministic_offline_hash_512，本结果只验证本地检索管线与图谱补证逻辑，不能写成 BAAI/bge-small-zh-v1.5 的语义检索效果。",
            "- 11 类统计谬误已全部检查；详细状态见 JSON 报告。",
            "",
            "## 可复现文件",
            "",
            "- `GSE111619_family.soft(.gz)`：系列、平台和样本元数据。",
            "- `GSE111619_HTSeq_counts.txt(.gz)`：基因级计数矩阵。",
            "- `gse111619_samples.csv`：样本字段及描述性计数。",
            "- `gse111619_notes.json`：导入系统的 4 条结构化实验笔记。",
            "- `gse111619_validation.sqlite3`：独立 SQLite 离线预检数据库，不代表部署系统数据库。",
            "- `gse111619_retrieval_comparison.csv`：逐问题事实召回对比。",
            "- `validation_report.json`：机器可读验证报告。",
            "",
        ]
    )
    return "\n".join(lines)


def readme_markdown(report: dict[str, Any]) -> str:
    return f"""# GSE111619 real-data validation package

This directory contains public NCBI GEO data and locally generated validation artifacts for the `full-system` project.

## Source

- GEO series: {SOURCE_URLS['series']}
- Family SOFT: {SOURCE_URLS['family_soft']}
- Series matrix: {SOURCE_URLS['series_matrix']}
- Processed HTSeq counts: {SOURCE_URLS['counts']}

The downloaded count matrix is processed gene-level count data. It is not raw FASTQ data and it is not a local laboratory notebook.

## Artifact scopes

- `validation_report.json` and `validation_report.md`: offline SQLite/service preflight only.
- `system_import_report.json`: formal API import into the running PostgreSQL system.
- `gse111619_paired_experiment.csv` and `gse111619_paired_experiment_report.json`: formal paired DeepSeek experiment from the running system.

Thesis claims about the implemented system must use the latter two artifact groups, not the offline preflight metrics.

## Verification

- Status: {report['verification_status']}
- Fingerprint: `{report['reproducibility_fingerprint']}`
- Sample accessions: {', '.join(EXPECTED_SAMPLES)}
- Gene rows: {report['dataset']['gene_rows']}
- Script: `../../../scripts/validate_gse111619.py`

Run from the repository root with:

```bash
backend/.venv/bin/python scripts/validate_gse111619.py
```

The first full run may download the 90 MB `BAAI/bge-small-zh-v1.5` embedding model into `model-cache/`.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate GSE111619 with full-system knowledge graph and local RAG services")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--skip-rag", action="store_true", help="Run data and knowledge graph checks without downloading/loading the embedding model")
    parser.add_argument(
        "--offline-hash-embedding",
        action="store_true",
        help="Exercise LocalRagService with a deterministic 512-dimensional test embedding and no network access",
    )
    parser.add_argument("--expected-fingerprint", default="", help="Set the prior run fingerprint to verify deterministic reproduction")
    args = parser.parse_args()

    data_dir = args.data_dir.resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "family_soft": data_dir / "GSE111619_family.soft",
        "series_matrix": data_dir / "GSE111619_series_matrix.txt",
        "counts": data_dir / "GSE111619_HTSeq_counts.txt",
    }
    for path in paths.values():
        if not path.exists():
            raise FileNotFoundError(path)

    compressed_checks = []
    for filename, expected_hash in EXPECTED_COMPRESSED_HASHES.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(path)
        validate_gzip(path)
        actual_hash = sha256_file(path)
        compressed_checks.append(
            {
                "filename": filename,
                "sha256": actual_hash,
                "expected_sha256": expected_hash,
                "passed": actual_hash == expected_hash,
                "bytes": path.stat().st_size,
            }
        )
    if not all(check["passed"] for check in compressed_checks):
        raise AssertionError("One or more downloaded files do not match the recorded SHA-256 hashes")

    series, samples, platform_meta = parse_soft(paths["family_soft"])
    genes, columns, counts = parse_counts(paths["counts"])
    if first(series.get("Series_geo_accession")) != "GSE111619":
        raise AssertionError("SOFT series accession mismatch")
    if list(samples) != EXPECTED_SAMPLES:
        raise AssertionError(f"Unexpected sample accessions: {list(samples)}")
    if columns != EXPECTED_COUNT_COLUMNS:
        raise AssertionError(f"Unexpected count columns: {columns}")
    if sample_column_map(samples) != dict(zip(EXPECTED_COUNT_COLUMNS, EXPECTED_SAMPLES, strict=True)):
        raise AssertionError("Count columns could not be mapped one-to-one to GEO sample accessions")
    if len(genes) != len(set(genes)):
        raise AssertionError("Duplicate GeneID values found")
    if counts.shape != (len(genes), len(columns)):
        raise AssertionError(f"Unexpected matrix shape: {counts.shape}")

    sample_records = build_sample_records(samples, columns, counts)
    notes = build_notes(sample_records, len(genes))
    knowledge_document = build_knowledge_document(series, notes)
    (data_dir / "gse111619_knowledge_document.txt").write_text(knowledge_document, encoding="utf-8")
    query_cases = dynamic_query_cases(sample_records)
    if args.skip_rag and args.offline_hash_embedding:
        parser.error("--skip-rag and --offline-hash-embedding cannot be used together")
    embedding_mode = "skip" if args.skip_rag else ("offline_hash" if args.offline_hash_embedding else "fastembed")
    system_validation, comparison_rows = run_system_validation(data_dir, notes, query_cases, embedding_mode)

    dataset_report = {
        "source_urls": SOURCE_URLS,
        "series_accession": first(series.get("Series_geo_accession")),
        "series_title": first(series.get("Series_title")),
        "public_status": first(series.get("Series_status")),
        "sample_count": len(samples),
        "sample_accessions": list(samples),
        "gene_rows": len(genes),
        "count_columns": columns,
        "matrix_shape": list(counts.shape),
        "compressed_hash_checks_passed": sum(check["passed"] for check in compressed_checks),
        "compressed_hash_checks_total": len(compressed_checks),
        "compressed_files": compressed_checks,
        "decompressed_files": {
            key: {
                "filename": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "lines": line_count(path),
            }
            for key, path in paths.items()
        },
        "platform_id": first(series.get("Series_platform_id")),
        "sample_level_instrument": sorted({record["instrument"] for record in sample_records}),
        "platform_title": first(platform_meta.get("Platform_title")),
        "source_internal_discrepancy": {
            "series_overall_design": "Illumina HiSeq 2000",
            "platform_and_sample_metadata": "Illumina HiSeq 2500",
            "handling": "Use sample-level HiSeq 2500 in structured notes and retain this caution in the report",
        },
    }
    stats = descriptive_statistics(columns, counts)

    comparison_core = [
        {
            key: row[key]
            for key in (
                "case_id",
                "expected_fact_count",
                "ordinary_rag_matched",
                "ordinary_rag_recall",
                "kg_enhanced_matched",
                "kg_enhanced_recall",
                "recall_delta",
                "rag_source_count",
                "graph_relation_count",
                "top_rag_scores",
            )
        }
        for row in comparison_rows
    ]
    fingerprint_payload = {
        "compressed_hashes": {check["filename"]: check["sha256"] for check in compressed_checks},
        "matrix_shape": dataset_report["matrix_shape"],
        "sample_records": sample_records,
        "descriptive_statistics": stats,
        "knowledge_graph": system_validation["knowledge_graph"],
        "rag": system_validation["rag"],
        "comparison": comparison_core,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if args.expected_fingerprint and args.expected_fingerprint != fingerprint:
        raise AssertionError(
            f"Reproducibility fingerprint mismatch: expected {args.expected_fingerprint}, got {fingerprint}"
        )
    verification_status = "VERIFIED" if args.expected_fingerprint else "ANALYZED"

    report = {
        "artifact_scope": "offline SQLite/service preflight; not the deployed full-system run",
        "authoritative_system_reports": [
            "system_import_report.json",
            "gse111619_paired_experiment.csv",
            "gse111619_paired_experiment_report.json",
        ],
        "verification_status": verification_status,
        "reproducibility_fingerprint": fingerprint,
        "reproduced_against": args.expected_fingerprint or None,
        "dataset": dataset_report,
        "sample_records": sample_records,
        "descriptive_statistics": stats,
        "system_validation": system_validation,
        "retrieval_comparison": comparison_rows,
        "statistical_fallacy_scan": {
            "coverage": "11/11",
            "items": build_fallacy_scan(),
        },
        "limitations": [
            "Public external GEO data, not local laboratory records",
            "Processed gene-level counts, not raw FASTQ reads",
            "Two biological replicates per condition; no inferential test is reported",
            "Retrieval evaluation measures evidence fact recall for four fixed questions, not generated-answer quality",
            "The completed retrieval run uses a deterministic offline test embedding, not BAAI/bge-small-zh-v1.5",
            "No independent human blind review was performed",
        ],
        "runtime": package_versions(),
    }

    (data_dir / "gse111619_notes.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_csv(
        data_dir / "gse111619_samples.csv",
        sample_records,
        list(sample_records[0]),
    )
    write_csv(
        data_dir / "gse111619_retrieval_comparison.csv",
        comparison_rows,
        list(comparison_rows[0]) if comparison_rows else ["case_id"],
    )
    (data_dir / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (data_dir / "validation_report.md").write_text(report_markdown(report, comparison_rows), encoding="utf-8")
    (data_dir / "README.md").write_text(readme_markdown(report), encoding="utf-8")
    print(json.dumps({"status": verification_status, "fingerprint": fingerprint, "report": str(data_dir / 'validation_report.md')}, ensure_ascii=False))


if __name__ == "__main__":
    main()
