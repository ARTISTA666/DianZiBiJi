"""Knowledge-graph constants and shared utility helpers.

This module is the single source of truth for all KG-related constants,
label maps, query hints, and small pure utility functions used by both
the extraction and retrieval sub-modules.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.models.knowledge_graph import (
    KnowledgeEntityType,
    KnowledgeRelationType,
)

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

GRAPH_SCHEMA_VERSION = "kg-v3-numbered-list-expansion"

# ---------------------------------------------------------------------------
# Structured-field mapping
# ---------------------------------------------------------------------------

STRUCTURED_FIELD_ROLES = {
    "cell_line": "cell_line",
    "cell_type": "cell_type",
    "condition": "group",
    "shrna_construct": "perturbation",
    "treatment": "treatment",
    "culture_condition": "culture",
    "replicate_label": "replicate",
    "alignment_method": "alignment_software",
    "count_method": "count_software",
    "processing_software": "processing_software",
    "source_accession": "geo_accession",
    "sra_accession": "sra_accession",
    "biosample_accession": "biosample_accession",
    "count_column": "count_column",
    "genome_build": "reference_genome",
}

STRUCTURED_FIELD_TYPES = {
    "cell_line": KnowledgeEntityType.BIOLOGICAL_SOURCE,
    "cell_type": KnowledgeEntityType.BIOLOGICAL_SOURCE,
    "condition": KnowledgeEntityType.CONDITION,
    "shrna_construct": KnowledgeEntityType.CONDITION,
    "treatment": KnowledgeEntityType.CONDITION,
    "culture_condition": KnowledgeEntityType.CONDITION,
    "replicate_label": KnowledgeEntityType.CONDITION,
    "alignment_method": KnowledgeEntityType.SOFTWARE,
    "count_method": KnowledgeEntityType.SOFTWARE,
    "processing_software": KnowledgeEntityType.SOFTWARE,
    "source_accession": KnowledgeEntityType.IDENTIFIER,
    "sra_accession": KnowledgeEntityType.IDENTIFIER,
    "biosample_accession": KnowledgeEntityType.IDENTIFIER,
    "count_column": KnowledgeEntityType.IDENTIFIER,
    "genome_build": KnowledgeEntityType.IDENTIFIER,
}

# ---------------------------------------------------------------------------
# Query / role hints
# ---------------------------------------------------------------------------

ROLE_QUERY_HINTS = {
    "cell_line": ("细胞系", "cell line"),
    "cell_type": ("细胞类型", "cell type"),
    "group": ("组", "分组", "组别", "对照", "敲低", "group", "condition"),
    "perturbation": ("shrna", "靶向", "敲低", "construct"),
    "treatment": ("处理", "剂量", "treatment", "dose"),
    "culture": ("培养", "温度", "co2", "时长", "culture"),
    "replicate": ("重复", "replicate"),
    "alignment_software": ("比对软件", "比对", "aligner", "alignment"),
    "count_software": ("计数软件", "基因计数", "count software"),
    "processing_software": ("处理软件", "软件链", "流程", "pipeline"),
    "geo_accession": ("geo", "gsm", "样本号"),
    "sra_accession": ("sra", "srx", "实验号"),
    "biosample_accession": ("biosample", "samn"),
    "count_column": ("列名", "矩阵列", "column"),
    "reference_genome": ("参考基因组", "基因组", "genome", "hg19", "grch"),
    "total_count": ("总基因计数", "总计数", "total count", "total_count"),
    "detected_gene_rows": ("非零基因", "检测到", "行数", "detected_gene_rows"),
    "count_matrix_gene_rows": ("基因条目", "计数矩阵", "count_matrix_gene_rows", "gene rows"),
    "data_boundary": ("层级", "不能", "不得", "不是", "fastq", "差异表达", "significance"),
    "quality_result": ("质量", "rin", "quality"),
}

ROLE_LABELS = {
    "cell_line": "细胞系",
    "cell_type": "细胞类型",
    "group": "处理组",
    "perturbation": "干预方式",
    "treatment": "处理条件",
    "culture": "培养条件",
    "replicate": "生物学重复",
    "alignment_software": "比对软件",
    "count_software": "计数软件",
    "processing_software": "处理软件",
    "geo_accession": "GEO样本号",
    "sra_accession": "SRA实验号",
    "biosample_accession": "BioSample号",
    "count_column": "计数矩阵列名",
    "reference_genome": "参考基因组",
    "total_count": "总基因计数",
    "detected_gene_rows": "非零基因行数",
    "count_matrix_gene_rows": "计数矩阵基因条目数",
    "data_boundary": "数据边界",
    "quality_result": "质量指标",
}

FOCUS_SYNONYMS = {
    "control": ("对照", "非靶向", "shcontrol", "nontargeting"),
    "p63_knockdown": ("p63敲低", "p63靶向", "shp63", "p63kd"),
}

# ---------------------------------------------------------------------------
# Alias / text patterns
# ---------------------------------------------------------------------------

STRUCTURED_ALIASES: dict[KnowledgeEntityType, tuple[str, ...]] = {
    KnowledgeEntityType.REAGENT: ("reagent", "reagents", "试剂", "材料", "药品"),
    KnowledgeEntityType.INSTRUMENT: ("instrument", "instruments", "仪器", "设备"),
    KnowledgeEntityType.SAMPLE: ("sample", "samples", "样本", "样品"),
    KnowledgeEntityType.RESULT: ("result", "results", "结果", "观察", "结论"),
    KnowledgeEntityType.BIOLOGICAL_SOURCE: (
        "cell_line",
        "cell line",
        "cell_type",
        "cell type",
        "细胞系",
        "细胞类型",
    ),
    KnowledgeEntityType.CONDITION: (
        "condition",
        "shrna_construct",
        "treatment",
        "culture_condition",
        "replicate_label",
        "处理",
        "培养条件",
        "分组",
    ),
    KnowledgeEntityType.SOFTWARE: (
        "software",
        "count_method",
        "alignment_method",
        "计数方法",
        "处理软件",
        "比对软件",
    ),
    KnowledgeEntityType.IDENTIFIER: (
        "source_accession",
        "sra_accession",
        "biosample_accession",
        "count_column",
        "genome_build",
        "登录号",
        "参考基因组",
        "列名",
    ),
}

TEXT_PATTERNS: dict[KnowledgeEntityType, tuple[str, ...]] = {
    KnowledgeEntityType.REAGENT: (r"(?:reagents?|试剂|材料|药品)[:：]\s*([^\n。；;]+)",),
    KnowledgeEntityType.INSTRUMENT: (r"(?:instruments?|仪器|设备)[:：]\s*([^\n。；;]+)",),
    KnowledgeEntityType.SAMPLE: (r"(?:samples?|样本|样品)[:：]\s*([^\n。；;]+)",),
    KnowledgeEntityType.RESULT: (
        r"(?:results?|结果|观察|结论)[:：]\s*([^\n]+)",
        r"(count_matrix_gene_rows=\d+)",
        r"(基因级 HTSeq 计数矩阵；不是原始 FASTQ；不据此进行差异表达显著性推断)",
    ),
}

# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

RELATION_LABELS = {
    KnowledgeRelationType.HAS_NOTE.value: "包含笔记",
    KnowledgeRelationType.CREATED_BY.value: "创建者",
    KnowledgeRelationType.HAS_ATTACHMENT.value: "关联附件",
    KnowledgeRelationType.HAS_EXPERIMENT_TYPE.value: "实验类型",
    KnowledgeRelationType.USES_REAGENT.value: "使用试剂",
    KnowledgeRelationType.USES_INSTRUMENT.value: "使用仪器",
    KnowledgeRelationType.USES_SAMPLE.value: "使用样本",
    KnowledgeRelationType.PRODUCES_RESULT.value: "产生结果",
    KnowledgeRelationType.HAS_BIOLOGICAL_SOURCE.value: "生物来源",
    KnowledgeRelationType.HAS_CONDITION.value: "实验条件",
    KnowledgeRelationType.USES_SOFTWARE.value: "使用软件",
    KnowledgeRelationType.HAS_IDENTIFIER.value: "关联标识符",
}

ENTITY_LABELS = {
    KnowledgeEntityType.PROJECT.value: "项目",
    KnowledgeEntityType.NOTE.value: "实验笔记",
    KnowledgeEntityType.USER.value: "人员",
    KnowledgeEntityType.FILE.value: "附件资料",
    KnowledgeEntityType.EXPERIMENT_TYPE.value: "实验类型",
    KnowledgeEntityType.REAGENT.value: "试剂",
    KnowledgeEntityType.INSTRUMENT.value: "仪器",
    KnowledgeEntityType.SAMPLE.value: "样本",
    KnowledgeEntityType.RESULT.value: "实验结果",
    KnowledgeEntityType.BIOLOGICAL_SOURCE.value: "生物来源",
    KnowledgeEntityType.CONDITION.value: "实验条件",
    KnowledgeEntityType.SOFTWARE.value: "分析软件",
    KnowledgeEntityType.IDENTIFIER.value: "数据标识符",
}

# ---------------------------------------------------------------------------
# Query relation hints & collection keywords
# ---------------------------------------------------------------------------

QUERY_RELATION_HINTS = {
    KnowledgeRelationType.HAS_NOTE.value: ("笔记", "记录", "已审核", "note", "notes"),
    KnowledgeRelationType.USES_REAGENT.value: ("试剂", "材料", "药品", "reagent", "reagents"),
    KnowledgeRelationType.USES_INSTRUMENT.value: ("仪器", "设备", "instrument", "instruments"),
    KnowledgeRelationType.USES_SAMPLE.value: ("样本", "样品", "sample", "samples"),
    KnowledgeRelationType.PRODUCES_RESULT.value: (
        "结果",
        "观察",
        "结论",
        "计数",
        "行数",
        "条目",
        "最高",
        "最低",
        "相差",
        "层级",
        "不能",
        "不得",
        "差异表达",
        "result",
        "results",
        "total",
        "detected",
        "fastq",
        "significance",
    ),
    KnowledgeRelationType.HAS_ATTACHMENT.value: ("附件", "资料", "文件", "attachment", "file"),
    KnowledgeRelationType.CREATED_BY.value: ("谁", "人员", "创建", "负责人", "user", "creator"),
    KnowledgeRelationType.HAS_EXPERIMENT_TYPE.value: ("类型", "实验类型", "type"),
    KnowledgeRelationType.HAS_BIOLOGICAL_SOURCE.value: (
        "细胞",
        "细胞系",
        "细胞类型",
        "来源",
        "cell",
        "source",
    ),
    KnowledgeRelationType.HAS_CONDITION.value: (
        "分组",
        "组别",
        "条件",
        "处理",
        "培养",
        "重复",
        "对照",
        "敲低",
        "condition",
        "treatment",
        "replicate",
        "control",
        "knockdown",
    ),
    KnowledgeRelationType.USES_SOFTWARE.value: (
        "软件",
        "比对",
        "计数软件",
        "处理流程",
        "software",
        "aligner",
    ),
    KnowledgeRelationType.HAS_IDENTIFIER.value: (
        "标识符",
        "登录号",
        "样本号",
        "列名",
        "参考基因组",
        "geo",
        "sra",
        "biosample",
        "accession",
        "genome",
    ),
}

COLLECTION_QUERY_KEYWORDS = (
    "哪些",
    "全部",
    "所有",
    "列出",
    "多少",
    "分别",
    "归纳",
    "汇总",
    "清单",
    "完整",
    "各自",
    "数量",
    "四个",
    "两个",
    "最高",
    "最低",
    "相差",
    "list",
    "all",
    "count",
)


# ---------------------------------------------------------------------------
# Shared utility functions (used by both extraction and retrieval)
# ---------------------------------------------------------------------------


def clean_label(label: str) -> str:
    """Collapse whitespace and strip leading/trailing blanks."""
    return re.sub(r"\s+", " ", str(label)).strip()


def normalize_text(label: str) -> str:
    """Lower-case + whitespace-normalised form for comparisons."""
    return clean_label(label).lower()


def normalize_entity_label(label: str) -> str:
    """NFKC-normalise, strip punctuation, lower-case."""
    normalized = unicodedata.normalize("NFKC", clean_label(label)).lower()
    without_punctuation = "".join(
        " " if unicodedata.category(character).startswith("P") else character
        for character in normalized
    )
    return re.sub(r"\s+", " ", without_punctuation).strip()


def source_natural_key(
    entity_type: KnowledgeEntityType,
    source_type: str | None,
    source_id: int | None,
) -> str:
    """Build the natural key for source-backed entities."""
    return f"{entity_type.value}:{source_type}:{source_id}"


def split_terms(value: object, keep_sentence: bool = False) -> list[str]:
    """Split a value into a flat list of term strings."""
    if isinstance(value, list):
        terms: list[str] = []
        for item in value:
            terms.extend(split_terms(item, keep_sentence=keep_sentence))
        return terms
    if not isinstance(value, str):
        return [str(value).strip()] if value is not None and str(value).strip() else []
    text = value.strip()
    if not text:
        return []
    if keep_sentence:
        return [item.strip(" -\t") for item in re.split(r"[\n；;]+", text) if item.strip(" -\t")]
    terms = [item.strip(" -\t") for item in re.split(r"[,，、；;\n]+", text) if item.strip(" -\t")]
    if not terms:
        return []
    shared_number_prefix = ""
    expanded: list[str] = []
    for term in terms:
        match = re.fullmatch(r"(.+?\D\s*)(\d+)", term)
        if match:
            shared_number_prefix = match.group(1)
        elif shared_number_prefix and term.isdigit():
            term = f"{shared_number_prefix}{term}"
        else:
            shared_number_prefix = ""
        expanded.append(term)
    return expanded


def flatten_text(values: Iterable[object]) -> list[str]:
    """Recursively flatten nested dicts/lists into a list of strings."""
    texts: list[str] = []
    for value in values:
        if isinstance(value, str):
            if value.strip():
                texts.append(value.strip())
        elif isinstance(value, dict):
            for key, item in value.items():
                texts.extend(flatten_text([str(key), item]))
        elif isinstance(value, list):
            texts.extend(flatten_text(value))
        elif value is not None:
            texts.append(str(value))
    return texts


def dedupe_labels(labels: list[str]) -> list[str]:
    """De-duplicate labels by their normalised form."""
    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        clean = clean_label(label)
        key = normalize_entity_label(clean)
        if clean and key not in seen:
            seen.add(key)
            deduped.append(clean)
    return deduped
