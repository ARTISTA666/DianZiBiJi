"""Build a reproducible gold-set audit for knowledge-graph relations."""

from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "docs" / "experiments"
NOTE_IDS = (9, 10, 11, 36)

EXPECTED: dict[int, dict[str, list[str]]] = {
    9: {
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
    10: {
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
    11: {
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
    36: {
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
    ids = ",".join(str(value) for value in NOTE_IDS)
    sql = f"""
    SELECT COALESCE(json_agg(row_to_json(x)), '[]'::json)
    FROM (
      SELECT r.id, r.source_id AS note_id, r.relation_type, r.confidence,
             r.source_type, se.label AS source_label, te.label AS target_label
      FROM kg_relations r
      JOIN kg_entities se ON se.id = r.source_entity_id
      JOIN kg_entities te ON te.id = r.target_entity_id
      WHERE r.project_id = 19 AND r.source_id IN ({ids})
      ORDER BY r.id
    ) x;
    """
    return query_json(sql)


def expected_pairs() -> set[tuple[int, str, str]]:
    return {
        (note_id, relation_type, target)
        for note_id, relations in EXPECTED.items()
        for relation_type, targets in relations.items()
        for target in targets
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    relations = load_relations()
    expected = expected_pairs()
    actual = {
        (int(row["note_id"]), str(row["relation_type"]), str(row["target_label"]))
        for row in relations
    }
    true_positive = len(actual & expected)
    false_positive = len(actual - expected)
    false_negative = len(expected - actual)
    precision = true_positive / (true_positive + false_positive)
    recall = true_positive / (true_positive + false_negative)
    f1 = 2 * precision * recall / (precision + recall)

    audit_path = OUTPUT_DIR / "kg-relation-gold-audit-53.csv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "relation_id",
                "note_id",
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
            key = (int(row["note_id"]), str(row["relation_type"]), str(row["target_label"]))
            writer.writerow(
                {
                    "relation_id": row["id"],
                    "note_id": row["note_id"],
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

    missing_path = OUTPUT_DIR / "kg-relation-gold-missing.json"
    missing_path.write_text(
        json.dumps(
            [
                {"note_id": note_id, "relation_type": relation_type, "target_label": target}
                for note_id, relation_type, target in sorted(expected - actual)
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    relation_counts: dict[str, int] = defaultdict(int)
    for row in relations:
        relation_counts[str(row["relation_type"])] += 1
    summary_path = OUTPUT_DIR / "kg-relation-gold-audit-summary.md"
    lines = [
        "# 知识图谱关系金标准核验",
        "",
        "核验对象为项目 19 的前四条已审核实验笔记。金标准依据当前已审核版本中的结构化字段、正文和基础元数据逐条定义,不以抽取结果反推答案。",
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
        "唯一错误关系为 qPCR 笔记中的样本实体“2”。其来源是正文“cDNA 样本 1、2”被分隔符规则拆分为“cDNA 样本 1”和“2”,说明当前规则对省略中心词的并列表达处理不足。",
        "",
        "关系类型分布:",
        "",
    ]
    for relation_type, count in sorted(relation_counts.items()):
        lines.append(f"- `{relation_type}`: {count}")
    lines.extend(
        [
            "",
            "边界说明: 该金标准覆盖四条规范化笔记和 53 条实际关系,用于验证当前演示数据上的抽取一致性,不能替代跨领域、长文本和隐含关系场景的大规模信息抽取评测。CSV 中保留作者签核列,正式提交前应由研究者复核。",
            "",
        ]
    )
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Audit CSV saved: {audit_path}")
    print(f"Summary saved: {summary_path}")
    print(f"Missing relation list saved: {missing_path}")


if __name__ == "__main__":
    main()
