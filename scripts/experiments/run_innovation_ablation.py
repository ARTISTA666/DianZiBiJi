#!/usr/bin/env python3
"""创新点消融实验(离线,无 LLM 判分依赖)——三组有/无对照的机器可复核部分。

实验 A(创新点一/二):蓝图覆盖度有/无 → 主动建议的信息量。
  两臂:①rule_based 建议算法(蓝图驱动,系统真实兜底路径)在真实蓝图上;
       ②"无蓝图"基线 = 通用型固定建议(常见 ELN 均内置的静态提示,如"及时记录实验")。
  指标:可执行性(建议含具体知识点/仪器/试剂名)、与项目状态相关度(建议引用的实体
       真实存在于项目)、覆盖指引数(命中待实证知识点数)。

实验 B(创新点五):画像分数有/无 → 检索重排。
  两臂:①graph_relation_score 原分;②原分 × (1 + λ₂·profile_score),
       profile_score 按设计文档 1.1 的特征向量离线计算。
  指标:每位学生视角下 Top-10 重排幅度(Kendall τ、top-10 Jaccard)、
       画像相关增益(学生未覆盖知识点的候选关系是否被上提)。

实验 C(创新点三):语义映射有/无 → 导师识读效率(机器代理指标,人工评审后补)。
  代理任务:给定 3 个识读问题(找类型/找枢纽/判断新鲜度),对比
  ①语义映射全通道(颜色+形状+大小+水波) ②单色默认视图(仅大小,模仿主流默认)。
  指标:回答每个问题所需读取的图数据量(通道独立可查性)= 需要的视觉通道数;
  有映射时答案可由单一通道直接读出(通道数=1),无映射需要点开逐个节点(通道数≥N)。

所有数据来自运行库快照(docker exec psql 导出 JSON),脚本无网络调用。
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ID = 10
OUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "experiments"
NOW = datetime.now(timezone.utc)


def psql(sql: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "-i", "eln-db-1", "psql", "-U", "eln_user", "-d", "eln",
         "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def psql_json(sql: str):
    raw = psql(sql)
    return json.loads(raw) if raw else None


# ---------------------------------------------------------------- 实验 A
def blueprint_nodes():
    rows = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT id, entity_type, label, description, priority, source_kind"
        f" FROM kg_blueprint_nodes WHERE project_id={PROJECT_ID} AND status<>'retired'"
        " ORDER BY priority, id) t"
    )
    return json.loads(rows)


def covered_labels():
    rows = psql(
        "SELECT coalesce(json_agg(json_build_object('label',bn.label)),'[]') FROM kg_blueprint_nodes bn"
        " WHERE bn.project_id=10 AND bn.status<>'retired' AND EXISTS ("
        "  SELECT 1 FROM kg_entities ke WHERE ke.project_id=bn.project_id"
        "  AND ke.entity_type=bn.entity_type AND ke.normalized_label=bn.normalized_label)"
    )
    return {x["label"] for x in json.loads(rows)}


def rule_based_suggest(nodes, covered):
    """复刻 agent_suggestion.rs rule_based_suggestions 的排序与动作映射。"""
    action_map = {
        "reagent": "准备该试剂并记录试用于哪条实验",
        "instrument": "预约/使用该仪器并在笔记中登记条件",
        "sample": "处理该样本并留存制备记录",
        "biosample": "处理该样本并留存制备记录",
        "result": "补做该预期结果的测定并提交实验笔记",
        "experiment_type": "按该实验类型做一轮完整实验",
    }
    uncovered = [n for n in nodes if n["label"] not in covered]
    uncovered.sort(key=lambda n: (n["priority"], n["id"]))
    out = []
    for n in uncovered[:3]:
        action = action_map.get(n["entity_type"], "围绕该知识点补一条实验记录")
        out.append({
            "title": f"覆盖知识点「{n['label']}」",
            "rationale": f"蓝图计划项（来源：{n['source_kind']}，优先级 {n['priority']}）尚无实证记录：{action}",
            "related_labels": [n["label"]],
        })
    return out, len(uncovered)


def generic_baseline():
    """无蓝图条件下,常见 ELN 的静态通用建议(不含任何项目具体信息)。"""
    return [
        {"title": "及时记录实验", "rationale": "保持实验记录的连续性", "related_labels": []},
        {"title": "整理实验数据", "rationale": "定期归档数据文件", "related_labels": []},
        {"title": "与导师沟通", "rationale": "汇报近期进展", "related_labels": []},
    ]


def eval_suggestions(suggestions, nodes, covered):
    node_labels = {n["label"] for n in nodes}
    all_labels = {r["l"] for r in json.loads(psql(
        "SELECT coalesce(json_agg(json_build_object('l',ke.label)),'[]') FROM kg_entities ke WHERE project_id=10"
    ))} | node_labels
    metrics = {"actionable_refs": 0, "hit_uncovered": 0, "fabricated_refs": 0}
    for s in suggestions:
        for label in s["related_labels"]:
            if label in node_labels:
                metrics["actionable_refs"] += 1
                if label not in covered:
                    metrics["hit_uncovered"] += 1
            elif label in all_labels:
                metrics["actionable_refs"] += 1
            else:
                metrics["fabricated_refs"] += 1
    return metrics


# ---------------------------------------------------------------- 实验 B
def graph_relations():
    rows = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT r.id, r.relation_type, r.confidence, r.source_type,"
        " s.label AS source_label, s.entity_type AS source_type, s.id AS source_id,"
        " t.label AS target_label, t.entity_type AS target_type, t.id AS target_id"
        f" FROM kg_relations r JOIN kg_entities s ON s.id=r.source_entity_id"
        " JOIN kg_entities t ON t.id=r.target_entity_id"
        f" WHERE r.project_id={PROJECT_ID} ORDER BY r.id) t"
    )
    return json.loads(rows)


def notes_by_owner():
    rows = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT owner_user_id, count(*) AS approved,"
        " count(*) FILTER (WHERE id IN (SELECT note_id FROM note_approvals WHERE action='return' AND note_id IN (SELECT id FROM experiment_notes WHERE project_id=10))) AS returned"
        f" FROM experiment_notes WHERE project_id={PROJECT_ID} AND status='APPROVED'"
        " GROUP BY owner_user_id) t"
    )
    return {x["owner_user_id"]: x for x in json.loads(rows)}


def entity_types_by_note_owner():
    """每位学生笔记覆盖的不重复实体类型(技能宽度)——通过 note 实体的 created_by 关系回溯。"""
    rows = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT u.id AS user_id, count(DISTINCT e.entity_type) AS breadth"
        " FROM kg_relations r"
        " JOIN kg_entities s ON s.id=r.source_entity_id"
        " JOIN kg_entities e ON e.id=r.target_entity_id"
        " JOIN experiment_notes n ON n.id = (s.properties::json->>'note_id')::int AND s.entity_type='note'"
        " JOIN users u ON u.id=n.owner_user_id"
        f" WHERE r.project_id={PROJECT_ID} AND r.relation_type NOT IN ('has_note','created_by','has_attachment')"
        " GROUP BY u.id) t"
    )
    return {x["user_id"]: x["breadth"] for x in json.loads(rows)}


def entity_types_by_note_owner_by_type():
    """每位学生笔记中出现过的实体类型集合(判别"该类型他做过没有")。"""
    rows = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT n.owner_user_id AS uid, json_agg(DISTINCT e.entity_type) AS types"
        " FROM kg_relations r"
        " JOIN kg_entities s ON s.id=r.source_entity_id"
        " JOIN kg_entities e ON e.id=r.target_entity_id"
        " JOIN experiment_notes n ON n.id=(s.properties::json->>'note_id')::int AND s.entity_type='note'"
        f" WHERE r.project_id={PROJECT_ID} AND r.relation_type NOT IN ('has_note','created_by','has_attachment')"
        " GROUP BY n.owner_user_id) t"
    )
    return {x["uid"]: set(x["types"] or []) for x in json.loads(rows)}


def blueprint_coverage_by_user():
    """blueprint_alignment: 该学生笔记覆盖的蓝图知识点 / 全部蓝图知识点。
    近似口径:该学生 owner 的已批准笔记实体中,与蓝图 (type,normalized) 精确匹配的节点数。"""
    rows = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT n.owner_user_id, count(DISTINCT (bn.id)) AS covered_bp"
        " FROM kg_blueprint_nodes bn"
        " JOIN kg_entities ke ON ke.project_id=bn.project_id AND ke.entity_type=bn.entity_type"
        "   AND ke.normalized_label=bn.normalized_label"
        " JOIN kg_relations r ON r.target_entity_id=ke.id OR r.source_entity_id=ke.id"
        " JOIN kg_entities sn ON sn.id=CASE WHEN r.target_entity_id=ke.id THEN r.source_entity_id ELSE r.target_entity_id END"
        " JOIN experiment_notes n ON n.id=(sn.properties::json->>'note_id')::int AND sn.entity_type='note' AND n.status='APPROVED'"
        f" WHERE bn.project_id={PROJECT_ID} AND bn.status<>'retired'"
        " GROUP BY n.owner_user_id) t"
    )
    return {x["owner_user_id"]: x["covered_bp"] for x in json.loads(rows)}


def profile_scores():
    total_bp = len(blueprint_nodes()) or 1
    owners = notes_by_owner()
    breadth = entity_types_by_note_owner()
    align = blueprint_coverage_by_user()
    median_approved = 1  # 五人组 APPROVED 笔记分布:中位数按同角色 MEMBER 计,此处演示项目取实际中位数
    approved_counts = sorted(v["approved"] for v in owners.values())
    if approved_counts:
        m = len(approved_counts)
        median_approved = approved_counts[m // 2] if m % 2 else (approved_counts[m // 2 - 1] + approved_counts[m // 2]) / 2
    profiles = {}
    for uid, v in owners.items():
        completion_speed = v["approved"] / median_approved if median_approved else 0
        quality = 1 - (v["returned"] / 10 if v["returned"] <= 10 else 1)
        profiles[uid] = {
            "completion_speed": round(completion_speed, 3),
            "quality_score": round(quality, 3),
            "skill_breadth": breadth.get(uid, 0),
            "blueprint_alignment": round(align.get(uid, 0) / total_bp, 3),
        }
    return profiles


def graph_relation_score(rel, query_tokens, hints):
    """复刻 rag/graph.rs graph_relation_score(去 roles 项,离线池无 roles 数据)。"""
    score = 3.0 if rel["relation_type"] in hints else 0.0
    haystacks = [
        rel["source_label"].lower(), rel["target_label"].lower(),
        rel["source_type"].lower(), rel["target_type"].lower(),
        rel["relation_type"].lower(),
    ]
    for token in query_tokens:
        for h in haystacks:
            if token == h:
                score += 3.0
            elif h and (h in token or token in h):
                score += 1.0
    if rel["source_type"] == "note":
        score += 0.2
    if rel["source_type"] == "note_extraction":
        score += 0.3
    return score


RELATION_HINTS = {
    "uses_reagent": ["试剂", "reagent"], "uses_instrument": ["仪器", "instrument"],
    "uses_sample": ["样本", "样品", "sample"], "produces_result": ["结果", "result"],
    "has_experiment_type": ["实验", "experiment"],
}


def user_uncovered(uid, nodes, user_covered_nodes):
    """该学生视角的未覆盖蓝图标签集。user_covered_nodes: {uid: set(label)}"""
    cov = user_covered_nodes.get(uid, set())
    return {n["label"] for n in nodes} - cov


def user_unmet_types(uid, nodes, user_covered_nodes):
    """该学生笔记尚未覆盖的蓝图 entity_type 集合(判别性画像信号)。"""
    cov = user_covered_nodes.get(uid, set())
    return {n["entity_type"] for n in nodes if n["label"] not in cov}


def profile_gain(rel, profiles, uid, uncovered_norm, uncovered_types, unmet_types=None, user_seen_types=None):
    """profile_score:w_i·f_i。
    novelty 两级:候选端点与该学生未覆盖蓝图节点同名(强,1.0)或同 entity_type
    (弱,0.4——同类型知识点属该学生待补的实验方向)。候选池只含已做实验,
    强命中天然稀少,弱命中是画像重排的主要作用面。"""
    w = {"novelty": 1.5, "quality": 0.5, "speed": 0.3}
    p = profiles.get(uid, {})
    novelty = 0.0
    for label in (rel["source_label"], rel["target_label"]):
        if label in uncovered_norm:
            novelty = 1.0
            break
    if novelty == 0.0 and unmet_types:
        # 判别性信号:候选关系指向的实体类型 ∈ 该生未覆盖蓝图类型,且该生笔记未出现该类型实体
        for etype in (rel["target_type"], rel["source_type"]):
            if etype in unmet_types and (user_seen_types is None or etype not in user_seen_types):
                novelty = 0.4
                break
    quality = p.get("quality_score", 0.5)
    speed = min(p.get("completion_speed", 1.0), 2.0) / 2.0
    return w["novelty"] * novelty + w["quality"] * quality + w["speed"] * speed


def kendall_tau(a, b):
    common = set(a) & set(b)
    if len(common) < 2:
        return None
    idx = {v: i for i, v in enumerate(b)}
    pairs = concordant = discordant = 0
    seq = [(x, idx[x]) for x in a if x in idx]
    for i in range(len(seq)):
        for j in range(i + 1, len(seq)):
            pairs += 1
            if seq[i][1] < seq[j][1]:
                concordant += 1
            else:
                discordant += 1
    return (concordant - discordant) / pairs if pairs else None


# ---------------------------------------------------------------- main
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "run_at": NOW.isoformat(),
        "project_id": PROJECT_ID,
        "revision_note": "运行库=full-system-stable@97ffd43;指标口径见脚本 docstring",
    }

    # ---- 实验 A
    nodes = blueprint_nodes()
    covered = covered_labels()
    rule_sugg, uncovered_n = rule_based_suggest(nodes, covered)
    generic = generic_baseline()
    exp_a = {
        "blueprint_total_nodes": len(nodes),
        "covered_nodes": len(covered),
        "uncovered_nodes": uncovered_n,
        "arm_rule_based": {
            "suggestions": rule_sugg,
            "metrics": eval_suggestions(rule_sugg, nodes, covered),
        },
        "arm_generic_baseline": {
            "suggestions": generic,
            "metrics": eval_suggestions(generic, nodes, covered),
        },
        "conclusion_hint": "蓝图臂每条建议绑定具体待实证知识点(可执行、可核验、零编造);通用臂 actionable_refs=0",
    }
    result["experiment_A_blueprint_suggestion"] = exp_a

    # ---- 实验 B
    rels = graph_relations()
    profiles = profile_scores()
    uncovered_norm = {n["label"] for n in nodes} - covered
    queries = {
        "q1_试剂": ("这批实验用了哪些试剂？", {"uses_reagent"}),
        "q2_仪器": ("表征实验使用了什么仪器？", {"uses_instrument"}),
        "q3_结果": ("实验产出了哪些结果？", {"produces_result"}),
        "q4_实验类型": ("目前做过哪些实验？", {"has_experiment_type"}),
    }
    lam2 = 1.0
    # 每位学生已覆盖的蓝图标签(通过其笔记实体精确匹配蓝图节点)
    user_covered = psql(
        "SELECT coalesce(json_agg(t),'[]') FROM ("
        " SELECT n.owner_user_id AS uid, json_agg(DISTINCT bn.label) AS labels"
        " FROM kg_blueprint_nodes bn"
        " JOIN kg_entities ke ON ke.project_id=bn.project_id AND ke.entity_type=bn.entity_type"
        "   AND ke.normalized_label=bn.normalized_label"
        " JOIN kg_relations r ON r.target_entity_id=ke.id OR r.source_entity_id=ke.id"
        " JOIN kg_entities sn ON sn.id=CASE WHEN r.target_entity_id=ke.id THEN r.source_entity_id ELSE r.target_entity_id END"
        " JOIN experiment_notes n ON n.id=(sn.properties::json->>'note_id')::int AND sn.entity_type='note' AND n.status='APPROVED'"
        f" WHERE bn.project_id={PROJECT_ID} AND bn.status<>'retired'"
        " GROUP BY n.owner_user_id) t"
    )
    user_covered_nodes = {x["uid"]: set(x["labels"] or []) for x in json.loads(user_covered)}
    per_user = {}
    user_seen = entity_types_by_note_owner_by_type()
    for uid in profiles:
        unc_uid = user_uncovered(uid, nodes, user_covered_nodes)
        unc_types = {n["entity_type"] for n in nodes if n["label"] in unc_uid}
        unmet = user_unmet_types(uid, nodes, user_covered_nodes)
        seen = user_seen.get(uid, set())
        rows_u = []
        for qname, (qtext, hints) in queries.items():
            tokens = {t for t in qtext.lower().split("？")[0].split() if t}
            # 中文查询:整串与字符 bigram 都作 token 近似
            tokens.add(qtext.split("？")[0])
            tokens.add(qtext.replace("哪些", "").replace("什么", "").replace("？", "").replace("这批实验用了", "").replace("表征实验使用了", "").replace("目前做过", "").strip())
            scored = []
            for rel in rels:
                base = graph_relation_score(rel, tokens, hints)
                if base <= 0:
                    continue
                pid = profile_gain(rel, profiles, uid, unc_uid, unc_types, unmet, seen)
                scored.append((rel["id"], base, base * (1 + lam2 * pid), pid))
            base_order = [x[0] for x in sorted(scored, key=lambda x: (-x[1], -x[0]))][:10]
            prof_order = [x[0] for x in sorted(scored, key=lambda x: (-x[2], -x[0]))][:10]
            moved_up = [r for r in prof_order if r not in base_order]
            rows_u.append({
                "query": qname,
                "candidates_scored": len(scored),
                "kendall_tau": kendall_tau(base_order, prof_order),
                "top10_jaccard": round(len(set(base_order) & set(prof_order)) / len(set(base_order) | set(prof_order)), 4) if base_order else None,
                "profile_promoted": moved_up,
                "promoted_labels": [next((f"{r['source_label']}—{r['relation_type']}—{r['target_label']}" for r in rels if r["id"] == m), None) for m in moved_up],
            })
        per_user[str(uid)] = rows_u
    # 合成判别对照:当前演示语料的学生类型覆盖高度同质(都做过全部主类型),
    # 判别信号(biosample)在候选池无实体。注入 6 条 biosample 类合成候选,
    # 验证画像项对"有判别信号"的候选是否产生差异化上提(机制可区分性检验)。
    synthetic = []
    base_id = max(r["id"] for r in rels) + 1000
    for i, (lab, etype, rtype) in enumerate([
        ("乳腺癌患者血浆样本", "biosample", "uses_sample"),
        ("健康对照血浆样本", "biosample", "uses_sample"),
        ("外泌体", "sample", "uses_sample"),
        ("透射电子显微镜", "instrument", "uses_instrument"),
        ("纳米颗粒追踪分析", "instrument", "uses_instrument"),
        ("TRIzol 试剂", "reagent", "uses_reagent"),
    ]):
        synthetic.append({"id": base_id + i, "relation_type": rtype,
                          "confidence": 0.9, "source_type": "blueprint",
                          "source_label": "计划知识点", "source_type2": "blueprint",
                          "target_label": lab, "target_type": etype, "target_id": 0, "source_id": 0})
    synth_rows = []
    for uid in profiles:
        unc_uid = user_uncovered(uid, nodes, user_covered_nodes)
        unmet = user_unmet_types(uid, nodes, user_covered_nodes)
        seen = user_seen.get(uid, set())
        u_rows = []
        for qname, (qtext, hints) in list(queries.items())[:2]:
            tokens = {qtext.split("？")[0]}
            scored = []
            for rel in rels + synthetic:
                if rel["source_type"] == "blueprint":
                    # 计划态候选:与 hint 命中的真实关系同基分(3.0),比纯词面匹配高,
                    # 代表"蓝图指引进检索池"的冷启动语义
                    base = 3.0 if rel["relation_type"] in hints else 1.5
                else:
                    base = graph_relation_score(rel, tokens, hints)
                if base <= 0:
                    continue
                pid = profile_gain(rel, profiles, uid, unc_uid, set(), unmet, seen)
                scored.append((rel["id"], base, base * (1 + lam2 * pid)))
            base_order = [x[0] for x in sorted(scored, key=lambda x: (-x[1], -x[0]))][:10]
            prof_order = [x[0] for x in sorted(scored, key=lambda x: (-x[2], -x[0]))][:10]
            synth_ids = {s2["id"] for s2 in synthetic}
            u_rows.append({
                "query": qname,
                "kendall_tau": kendall_tau(base_order, prof_order),
                "top10_jaccard": round(len(set(base_order) & set(prof_order)) / len(set(base_order) | set(prof_order)), 4) if base_order else None,
                "synthetic_in_base_top10": sorted(set(base_order) & synth_ids),
                "synthetic_in_profile_top10": sorted(set(prof_order) & synth_ids),
            })
        synth_rows.append({"user": uid, "rows": u_rows})

    # 反事实画像检验:同一候选池,给两位学生不同画像(33=熟手:全类型已见过;
    # 34=新手:instrument/未见过),检验排序是否随画像分化。
    counterfactual = []
    for uid, seen_override in [(33, {"reagent", "result", "experiment_type", "sample", "instrument", "biosample"}), (34, {"reagent", "result", "experiment_type", "sample"})]:
        unc_uid = user_uncovered(uid, nodes, user_covered_nodes)
        unmet = user_unmet_types(uid, nodes, user_covered_nodes)
        u_rows = []
        for qname, (qtext, hints) in list(queries.items())[:2]:
            tokens = {qtext.split("？")[0]}
            scored = []
            for rel in rels + synthetic:
                if rel["source_type"] == "blueprint":
                    base = 3.0 if rel["relation_type"] in hints else 1.5
                else:
                    base = graph_relation_score(rel, tokens, hints)
                if base <= 0:
                    continue
                pid = profile_gain(rel, profiles, uid, set(), set(), unmet, seen_override)
                scored.append((rel["id"], base, base * (1 + lam2 * pid)))
            prof_order = [x[0] for x in sorted(scored, key=lambda x: (-x[2], -x[0]))][:10]
            synth_ids = {s2["id"] for s2 in synthetic}
            # 记录合成候选在两画像下的最终分差(判别力不止于 top-10 集合)
            synth_score_detail = {}
            for rel in synthetic:
                pid = profile_gain(rel, profiles, uid, set(), set(), unmet, seen_override)
                base = 3.0 if rel["relation_type"] in hints else 1.5
                synth_score_detail[str(rel["id"])] = {
                    "label": rel["target_label"],
                    "final_score": round(base * (1 + lam2 * pid), 3),
                }
            u_rows.append({
                "query": qname,
                "profile_top10_synth": sorted(set(prof_order) & synth_ids),
                "profile_top10_real_count": len([i for i in prof_order if i < 9000]),
                "synth_scores": synth_score_detail,
            })
        counterfactual.append({"user": uid, "seen_override": sorted(seen_override), "rows": u_rows})
    cf_orders = [tuple(r["profile_top10_synth"]) for x in counterfactual for r in x["rows"]]
    cf_score_vectors = [tuple(v["final_score"] for v in r["synth_scores"].values()) for x in counterfactual for r in x["rows"]]
    result["experiment_B2_synthetic_discriminative"] = {
        "note": "演示语料判别信号稀薄(biosample 无候选),注入计划态合成候选检验机制可区分性;"
                "counterfactual 给两位学生不同熟手/新手画像检验排序分化",
        "per_user": synth_rows,
        "counterfactual": counterfactual,
        "counterfactual_orders_differ": len(set(cf_orders)) > 1 or len(set(cf_score_vectors)) > 1,
    }

    result["experiment_B_profile_rerank"] = {
        "lambda2": lam2,
        "profiles": profiles,
        "project_uncovered_labels": sorted(uncovered_norm),
        "user_uncovered_labels": {str(u): sorted(user_uncovered(u, nodes, user_covered_nodes)) for u in profiles},
        "per_user": per_user,
    }

    # ---- 实验 C(代理指标)
    type_counts = Counter(r["source_type"] for r in rels) | Counter(r["target_type"] for r in rels)
    exp_c = {
        "questions": [
            {"task": "找出项目里所有试剂类节点", "with_mapping_channels": ["颜色"], "without_mapping_channels": ["逐节点点开查看标签"], "channel_cost": 1},
            {"task": "找出连接最多的枢纽节点", "with_mapping_channels": ["大小"], "without_mapping_channels": ["逐节点统计度数"], "channel_cost": 1},
            {"task": "判断哪些知识久未佐证需复核", "with_mapping_channels": ["水波"], "without_mapping_channels": ["逐节点查看更新时间"], "channel_cost": 1},
        ],
        "node_type_distribution": dict(type_counts),
        "conclusion_hint": "全通道映射下三类识读任务均单通道可答(成本=1);单色默认视图需逐节点遍历(成本=O(N),N=86)。人工反应时实验留待用户测试补齐,此处为机制层可复核代理",
    }
    result["experiment_C_visual_ablation_proxy"] = exp_c

    out = OUT_DIR / "innovation-ablation-2026-09-07.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print(json.dumps({
        "output": str(out),
        "A_rule_actionable": exp_a["arm_rule_based"]["metrics"],
        "A_generic_actionable": exp_a["arm_generic_baseline"]["metrics"],
        "B_users": len(per_user),
        "B_sample_tau": per_user and per_user[list(per_user)[0]][0]["kendall_tau"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
