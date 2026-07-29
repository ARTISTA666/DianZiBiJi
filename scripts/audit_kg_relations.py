"""Build a reproducible gold-set audit for knowledge-graph relations."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "docs" / "experiments"
PROJECT_NAME = "论文演示项目：KG-RAG 实验流程"

EXPECTED: dict[str, dict[str, list[str]]] = {
    "PCR 条件优化实验": {
        "has_note": ["PCR 条件优化实验"],
        "created_by": ["系统管理员"],
        "has_experiment_type": ["PCR"],
        "uses_reagent": ["Taq DNA Polymerase", "dNTP", "MgCl2", "模板 DNA"],
        "uses_instrument": ["PCR Thermal Cycler"],
        "uses_sample": ["样本 A", "样本 B"],
        "produces_result": [
            "退火温度 58℃ 时扩增条带最清晰，非特异性条带减少。",
            "58℃ 条件下条带清晰。",
        ],
    },
    "细胞活力检测实验": {
        "has_note": ["细胞活力检测实验"],
        "created_by": ["系统管理员"],
        "has_experiment_type": ["细胞培养"],
        "uses_reagent": ["CCK-8", "PBS", "DMEM 培养基"],
        "uses_instrument": ["酶标仪", "CO2 培养箱"],
        "uses_sample": ["处理组细胞", "对照组细胞"],
        "produces_result": [
            "处理组细胞活力较对照组下降约 18%，重复孔结果稳定。",
            "细胞活力下降约 18%。",
        ],
    },
    "Western Blot 蛋白表达验证": {
        "has_note": ["Western Blot 蛋白表达验证"],
        "created_by": ["系统管理员"],
        "has_experiment_type": ["Western Blot"],
        "uses_reagent": ["RIPA 裂解液", "BCA 试剂盒", "一抗", "二抗"],
        "uses_instrument": ["电泳仪", "转膜仪", "凝胶成像系统"],
        "uses_sample": ["蛋白样本 P1", "蛋白样本 P2"],
        "produces_result": [
            "目标蛋白在处理组表达降低，内参条带稳定。",
            "处理组目标蛋白表达降低。",
        ],
    },
    "qPCR 定量验证实验": {
        "has_note": ["qPCR 定量验证实验"],
        "created_by": ["系统管理员"],
        "has_experiment_type": ["PCR"],
        "uses_reagent": ["SYBR Green Master Mix", "cDNA 模板", "引物对", "无酶水"],
        "uses_instrument": ["荧光定量 PCR 仪", "微量分光光度计"],
        "uses_sample": ["cDNA 样本 1", "cDNA 样本 2", "阴性对照"],
        "produces_result": [
            "目标基因在样本 1 中表达量约为样本 2 的 2.3 倍，融解曲线单一峰。",
            "目标基因差异表达约 2.3 倍。",
        ],
    },
}


def query_json(sql: str) -> list[dict]:
    command = [
        "docker",
        "compose",
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        "eln_user",
        "-d",
        "eln",
        "-t",
        "-A",
        "-c",
        sql,
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout.strip())


def load_relations() -> list[dict]:
    project_name = PROJECT_NAME.replace("'", "''")
    titles = ",".join(f"'{title.replace(chr(39), chr(39) * 2)}'" for title in EXPECTED)
    sql = f"""
    SELECT COALESCE(json_agg(row_to_json(x)), '[]'::json)
    FROM (
      SELECT r.id, n.id AS note_id, n.title AS note_title, r.relation_type, r.confidence,
             r.source_type, se.label AS source_label, te.label AS target_label
      FROM kg_relations r
      JOIN kg_entities se ON se.id = r.source_entity_id
      JOIN kg_entities te ON te.id = r.target_entity_id
      JOIN experiment_notes n ON n.id = r.source_id
      JOIN projects p ON p.id = r.project_id
      WHERE p.name = '{project_name}' AND n.title IN ({titles})
      ORDER BY r.id
    ) x;
    """
    return query_json(sql)


def expected_pairs() -> set[tuple[str, str, str]]:
    return {
        (note_title, relation_type, target)
        for note_title, relations in EXPECTED.items()
        for relation_type, targets in relations.items()
        for target in targets
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    relations = load_relations()
    expected = expected_pairs()
    actual = {
        (str(row["note_title"]), str(row["relation_type"]), str(row["target_label"]))
        for row in relations
    }
    true_positive = len(actual & expected)
    false_positive = len(actual - expected)
    false_negative = len(expected - actual)
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    f1 = 2 * precision * recall / (precision + recall)

    audit_path = OUTPUT_DIR / "kg-relation-gold-audit-after-fix.csv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "relation_id",
                "note_id",
                "note_title",
                "source_label",
                "relation_type",
                "target_label",
                "confidence",
                "source_type",
                "gold_verdict",
                "gold_basis",
                "author_signoff",
            ],
        )
        writer.writeheader()
        for row in relations:
            key = (str(row["note_title"]), str(row["relation_type"]), str(row["target_label"]))
            writer.writerow(
                {
                    "relation_id": row["id"],
                    "note_id": row["note_id"],
                    "note_title": row["note_title"],
                    "source_label": row["source_label"],
                    "relation_type": row["relation_type"],
                    "target_label": row["target_label"],
                    "confidence": row["confidence"],
                    "source_type": row["source_type"],
                    "gold_verdict": "TP" if key in expected else "FP",
                    "gold_basis": "对应已审核笔记的结构化字段、正文或基础元数据",
                    "author_signoff": "",
                }
            )

    missing_path = OUTPUT_DIR / "kg-relation-gold-missing-after-fix.json"
    missing_path.write_text(
        json.dumps(
            [
                {"note_title": note_title, "relation_type": relation_type, "target_label": target}
                for note_title, relation_type, target in sorted(expected - actual)
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    relation_counts: dict[str, int] = defaultdict(int)
    for row in relations:
        relation_counts[str(row["relation_type"])] += 1
    summary_path = OUTPUT_DIR / "kg-relation-gold-audit-after-fix-summary.md"
    gold_hash = hashlib.sha256(
        json.dumps(EXPECTED, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    finding = (
        "本次核验未发现错误关系。修复后的分隔规则已将正文“cDNA 样本 1、2”正确解析为“cDNA 样本 1”和“cDNA 样本 2”。"
        if false_positive == 0 and false_negative == 0
        else "仍存在错误或漏检关系，具体条目见 CSV 和缺失关系 JSON。"
    )
    lines = [
        "# 知识图谱关系金标准核验",
        "",
        f"核验对象为“{PROJECT_NAME}”中的四条固定演示笔记。源数据由 `backend/app/services/seed.py` 固定生成；它们不是用户提供的真实实验数据。",
        "",
        f"金标准 SHA-256：`{gold_hash}`。金标准依据固定笔记的结构化字段、正文和基础元数据预先定义，不以本次抽取结果反推答案。",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 实际关系数 | {len(actual)} |",
        f"| 金标准关系数 | {len(expected)} |",
        f"| 正确关系(TP) | {true_positive} |",
        f"| 错误关系(FP) | {false_positive} |",
        f"| 漏检关系(FN) | {false_negative} |",
        f"| 精确率 | {precision:.2%} |",
        f"| 召回率 | {recall:.2%} |",
        f"| F1 | {f1:.2%} |",
        "",
        finding,
        "",
        "关系类型分布:",
        "",
    ]
    for relation_type, count in sorted(relation_counts.items()):
        lines.append(f"- `{relation_type}`: {count}")
    lines.extend(
        [
            "",
            f"边界说明: 该金标准覆盖四条规范化演示笔记和 {len(actual)} 条实际关系,只用于验证当前固定样例上的抽取一致性,不能替代真实实验笔记、跨领域长文本和隐含关系评测。CSV 中保留作者签核列,正式提交前应由研究者复核。",
            "",
        ]
    )
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Audit CSV saved: {audit_path}")
    print(f"Summary saved: {summary_path}")
    print(f"Missing relation list saved: {missing_path}")


if __name__ == "__main__":
    main()
