# -*- coding: utf-8 -*-
"""式(5-3) 评分系数消融 v2(离线,无 LLM)。

输入:docs/experiments/rag-experiment-4.csv 中 kg_enhanced_rag 20 题真实注入的
top-10 图谱上下文(graph_context_json,含 relation_id/retrieval_score/label/type/conf)。
方法:对每题候选池按各档位系数重新打分——词元匹配/关系提示/来源加成可由 CSV 字段
+ legacy kg_constants 常量完整重建;roles 属性在 CSV 缺失,以当前库 project 1 的
同名关系 properties 补齐(仅 data_boundary 一条非空,影响 Q12 软件链题)。
输出:每档位与实验4原始得分的排序一致性、阈值 1.0 幸存集变化、[G] 引用所指关系位移。
口径:实验4 relation_id 空间与当前库不同代,按 (relation_type, source_label,
target_label) 三元组对齐补 roles;对不上的关系 role 项计 0(与实验4运行时
roles 全空的事实一致——论文 5.1.4:项目1 roles 常为空)。
"""
import csv, json, re, sys, unicodedata
sys.path.insert(0, "/work/backend")
# --- 自包含常量(自 backend/app/services/kg_constants.py ast 提取,枚举键按 .value 展开) ---
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

QUERY_RELATION_HINTS = {
    "has_note": ("笔记", "记录", "已审核", "note", "notes"),
    "uses_reagent": ("试剂", "材料", "药品", "reagent", "reagents"),
    "uses_instrument": ("仪器", "设备", "instrument", "instruments"),
    "uses_sample": ("样本", "样品", "sample", "samples"),
    "produces_result": (
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
    "has_attachment": ("附件", "资料", "文件", "attachment", "file"),
    "created_by": ("谁", "人员", "创建", "负责人", "user", "creator"),
    "has_experiment_type": ("类型", "实验类型", "type"),
    "has_biological_source": (
        "细胞",
        "细胞系",
        "细胞类型",
        "来源",
        "cell",
        "source",
    ),
    "has_condition": (
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
    "uses_software": (
        "软件",
        "比对",
        "计数软件",
        "处理流程",
        "software",
        "aligner",
    ),
    "has_identifier": (
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
    "有哪些",
    "全部",
    "所有",
    "列出",
    "列举",
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
    "一览",
    "list",
    "all",
    "enumerate",
    "count",
)

def _query_tokens(query):
    raw = re.findall(r"[A-Za-z0-9_\-]+|[\u4e00-\u9fff]{2,}", query.lower())
    toks = {norm(t) for t in raw if len(norm(t)) >= 2}
    nq = norm(query)
    if nq:
        toks.add(nq)
    return toks

BASE = "/work"
VARIANTS = {
    "baseline": dict(hint=3.0, exact=3.0, partial=1.0, note_e=0.2, note_x=0.3, role=4.0),
    "role=2.0": dict(hint=3.0, exact=3.0, partial=1.0, note_e=0.2, note_x=0.3, role=2.0),
    "role=1.0": dict(hint=3.0, exact=3.0, partial=1.0, note_e=0.2, note_x=0.3, role=1.0),
    "role=0.0": dict(hint=3.0, exact=3.0, partial=1.0, note_e=0.2, note_x=0.3, role=0.0),
    "exact=2.0": dict(hint=3.0, exact=2.0, partial=1.0, note_e=0.2, note_x=0.3, role=4.0),
    "partial=2.0": dict(hint=3.0, exact=3.0, partial=2.0, note_e=0.2, note_x=0.3, role=4.0),
    "hint=1.0": dict(hint=1.0, exact=3.0, partial=1.0, note_e=0.2, note_x=0.3, role=4.0),
    "bonuses=0": dict(hint=3.0, exact=3.0, partial=1.0, note_e=0.0, note_x=0.0, role=4.0),
}

def norm(v):
    v = unicodedata.normalize("NFKC", v or "").lower().replace("μ", "µ")
    return re.sub(r"[^a-z0-9\u4e00-\u9fffµ><=]+", "", v)

def relation_hints(query, tokens):
    q = norm(query)
    hints = set()
    for rt, kws in QUERY_RELATION_HINTS.items():
        if any(k.lower() in q or k.lower() in tokens for k in kws):
            hints.add(rt)
    return hints

def rescore(item, tokens, hints, qnorm, W, roles):
    score = 0.0
    if item["relation_type"] in hints:
        score += W["hint"]
    hay = [item["source_label"], item["target_label"], item["source_entity_type"],
           item["target_entity_type"], item["relation_type"], item["relation_label"]]
    for tok in tokens:
        for h in hay:
            n = norm(h)
            if tok and tok == n:
                score += W["exact"]
            elif tok and (tok in n or n in tok):
                score += W["partial"]
    if item["source_entity_type"] == "note":
        score += W["note_e"]
    # source_type 实验四全部为 note_extraction(笔记抽取关系)→ note_x 对抽取关系恒加
    score += W["note_x"]
    for role in roles:
        if any(k in qnorm for k in ROLE_QUERY_HINTS.get(role, ())):
            score += W["role"]
    return score

def main():
    rows = list(csv.DictReader(open(f"{BASE}/docs/experiments/rag-experiment-4.csv", encoding="utf-8")))
    kg = [r for r in rows if r["mode"] == "kg_enhanced_rag"]
    # roles 补齐:从当前库 project1 读 (rtype, slabel, tlabel) -> roles
    roles_map = {}
    try:
        import psycopg
        conn = psycopg.connect("postgresql://eln_user:eln_password@eln-db-1:5432/eln", connect_timeout=5)
        with conn.cursor() as cur:
            cur.execute("select relation_type, properties from kg_relations where project_id=1")
            for rt, props in cur.fetchall():
                for role in (props or {}).get("roles", []):
                    roles_map.setdefault(rt, set()).add(role)
        conn.close()
    except Exception as e:  # DB 不可达时 roles 全空(实验4运行时同样为空)
        print("# db unreachable, roles empty:", e, file=sys.stderr)
    out = {"meta": {
        "input": "docs/experiments/rag-experiment-4.csv kg_enhanced_rag graph_context_json (20 题 x 实验四真实 top-10 候选池)",
        "method": "对每题候选池按档位系数重打分重排;比较与实验4原始分序的一致性与阈值1.0幸存集",
        "roles_source": "当前库 project1 kg_relations.properties 按关系类型聚合(实验4 CSV 不含 roles;运行时项目1 roles 实际全空)",
        "variants": list(VARIANTS),
    }, "per_question": [], "summary": {}}
    agg = {k: {"tau_pairs": 0, "tau_discord": 0, "surv_base": 0, "surv_var": 0,
               "ref_moves": 0, "refs": 0, "set_overlap": []} for k in VARIANTS if k != "baseline"}
    for qi, r in enumerate(kg, 1):
        q = r["question"]
        cand = json.loads(r["graph_context_json"])
        if not cand:
            continue
        tokens = _query_tokens(q)
        hints = relation_hints(q, tokens)
        qnorm = norm(q)
        base_scores = [c["retrieval_score"] for c in cand]
        base_order = sorted(range(len(cand)), key=lambda i: (-base_scores[i], i))
        refs = sorted({int(m) for m in re.findall(r"\[G(\d+)\]", r["answer"] or "")})
        rec = {"question_index": qi, "n_cand": len(cand)}
        for name, W in VARIANTS.items():
            scores = []
            for c in cand:
                roles = sorted(roles_map.get(c["relation_type"], []))
                scores.append(rescore(c, tokens, hints, qnorm, W, roles))
            order = sorted(range(len(cand)), key=lambda i: (-scores[i], i))
            if name == "baseline":
                rec["baseline_survivors"] = sum(1 for s in scores if s >= 1.0)
                rec["baseline_top"] = [cand[i]["relation_id"] for i in order[:10]]
                continue
            a = base_order; b = order
            discord = sum(1 for x in range(len(a)) for y in range(x+1, len(a))
                          if (a.index(x) < a.index(y)) != (b.index(x) < b.index(y)))
            pairs = len(a)*(len(a)-1)//2
            surv = sum(1 for s in scores if s >= 1.0)
            # [G] 引用位移:原引用位所指关系在新排序中的位次差
            moves = []
            for g in refs:
                old_pos = g - 1
                if 0 <= old_pos < len(cand):
                    rel_id = base_order[old_pos]
                    new_pos = order.index(rel_id) if rel_id in order else -1
                    moves.append(abs((new_pos + 1) - g))
            agg[name]["tau_pairs"] += pairs
            agg[name]["tau_discord"] += discord
            agg[name]["surv_base"] += rec["baseline_survivors"]
            agg[name]["surv_var"] += surv
            agg[name]["refs"] += len(refs)
            agg[name]["ref_moves"] += sum(moves)
            agg[name]["set_overlap"].append(len(set(order[:10]) & set(base_order[:10])) / 10)
            rec[name] = {"survivors": surv, "top_changed": [cand[i]["relation_id"] for i in order[:10]] != rec.get("baseline_top", [])}
        out["per_question"].append(rec)
    for name, a in agg.items():
        n_q = len(out["per_question"])
        out["summary"][name] = {
            "kendall_tau_consistency": round(1 - a["tau_discord"] / a["tau_pairs"], 4) if a["tau_pairs"] else 1.0,
            "survivors_min_score>=1.0": {"baseline": a["surv_base"], "variant": a["surv_var"]},
            "mean_top10_set_overlap": round(sum(a["set_overlap"]) / len(a["set_overlap"]), 4),
            "citation_position_shift_mean": round(a["ref_moves"] / a["refs"], 2) if a["refs"] else 0.0,
            "citation_refs_total": a["refs"],
        }
    print(json.dumps(out, ensure_ascii=False, indent=1))

main()
