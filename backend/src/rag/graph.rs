// 知识图谱检索与格式化：图谱关系打分、聚焦实体、上下文均衡与文本渲染。

use std::collections::HashSet;
use std::sync::OnceLock;

use regex::Regex;
use serde_json::Value;
use sqlx::{FromRow, PgConnection, PgPool, Postgres, Transaction};

use super::{
    bm25::{token_regex, tokens},
    round6,
};
use crate::{error::ApiError, models::RagGraphContextRead};

const MAX_GRAPH_CONTEXT_CHARS: usize = 6_000;

/// Shared graph visibility predicate.  Retrieval and evidence snapshots must
/// never silently diverge on whether a note-derived relation is approved.
pub const GRAPH_RELATIONS_SCOPE_FILTER: &str = r#"
    (
        r.source_type NOT IN ('note', 'note_extraction')
        OR r.source_type IS NULL
        OR r.source_id IN (
            SELECT id FROM experiment_notes
            WHERE project_id = $1 AND status = 'APPROVED'::notestatus
        )
    )
"#;

#[derive(Debug, FromRow)]
struct GraphRow {
    relation_id: i32,
    relation_type: String,
    source_type: Option<String>,
    source_entity_id: i32,
    source_label: String,
    source_normalized_label: String,
    source_natural_key: String,
    source_entity_type: String,
    target_entity_id: i32,
    target_label: String,
    target_normalized_label: String,
    target_natural_key: String,
    target_entity_type: String,
    confidence: f64,
    properties: Value,
}

pub(crate) fn scoped_graph_relations_sql(select_clause: &str) -> String {
    format!(
        r#"
    SELECT {select_clause}
    FROM kg_relations r
    JOIN kg_entities s ON s.id = r.source_entity_id
    JOIN kg_entities t ON t.id = r.target_entity_id
    WHERE r.project_id = $1 AND {GRAPH_RELATIONS_SCOPE_FILTER}
    ORDER BY r.id
    LIMIT 5000
"#
    )
}

pub async fn relevant_graph_context(
    pool: &PgPool,
    project_id: i32,
    query: &str,
    limit: usize,
    min_score: f64,
) -> Result<Vec<RagGraphContextRead>, ApiError> {
    let mut connection = pool.acquire().await?;
    relevant_graph_context_with_connection(&mut connection, project_id, query, limit, min_score)
        .await
}

pub async fn relevant_graph_context_in_transaction(
    project_id: i32,
    query: &str,
    limit: usize,
    min_score: f64,
    transaction: &mut Transaction<'_, Postgres>,
) -> Result<Vec<RagGraphContextRead>, ApiError> {
    relevant_graph_context_with_connection(transaction, project_id, query, limit, min_score).await
}

async fn relevant_graph_context_with_connection(
    connection: &mut PgConnection,
    project_id: i32,
    query: &str,
    limit: usize,
    min_score: f64,
) -> Result<Vec<RagGraphContextRead>, ApiError> {
    let graph_sql = scoped_graph_relations_sql(
        r#"
        r.id AS relation_id, r.relation_type, r.source_type,
        s.id AS source_entity_id, s.label AS source_label,
        s.normalized_label AS source_normalized_label,
        s.natural_key AS source_natural_key,
        s.entity_type AS source_entity_type,
        t.id AS target_entity_id, t.label AS target_label,
        t.normalized_label AS target_normalized_label,
        t.natural_key AS target_natural_key,
        t.entity_type AS target_entity_type,
        r.confidence, r.properties
        "#,
    );
    let rows = sqlx::query_as::<_, GraphRow>(&graph_sql)
        .bind(project_id)
        .fetch_all(&mut *connection)
        .await?;
    let normalized_query = query.to_lowercase();
    let query_tokens = tokens(query);
    let hints = relation_hints(&normalized_query);
    let focus_ids = focused_graph_entity_ids(&rows, query);
    let mut scored = Vec::new();
    for row in rows {
        if !hints.is_empty() && !hints.contains(row.relation_type.as_str()) {
            continue;
        }
        if let Some(focus_ids) = &focus_ids {
            if !focus_ids.contains(&row.source_entity_id)
                && !focus_ids.contains(&row.target_entity_id)
            {
                continue;
            }
        }
        let score = graph_relation_score(&row, &query_tokens, &normalized_query, &hints);
        if !meets_graph_threshold(score, min_score) {
            continue;
        }
        scored.push((
            score,
            RagGraphContextRead {
                relation_id: row.relation_id,
                relation_label: relation_label(&row.relation_type).to_owned(),
                relation_type: row.relation_type,
                source_entity_id: row.source_entity_id,
                source_label: row.source_label,
                source_normalized_label: row.source_normalized_label,
                source_natural_key: row.source_natural_key,
                source_entity_type_label: entity_type_label(&row.source_entity_type).to_owned(),
                source_entity_type: row.source_entity_type,
                target_entity_id: row.target_entity_id,
                target_label: row.target_label,
                target_normalized_label: row.target_normalized_label,
                target_natural_key: row.target_natural_key,
                target_entity_type_label: entity_type_label(&row.target_entity_type).to_owned(),
                target_entity_type: row.target_entity_type,
                confidence: row.confidence,
                retrieval_score: round6(score),
                relation_roles: row
                    .properties
                    .get("roles")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect(),
                relation_properties: row.properties.clone(),
            },
        ));
    }
    scored.sort_by(|left, right| {
        right
            .0
            .partial_cmp(&left.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| {
                right
                    .1
                    .confidence
                    .partial_cmp(&left.1.confidence)
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| right.1.relation_id.cmp(&left.1.relation_id))
    });
    Ok(balance_graph_context(scored, limit, query)
        .into_iter()
        .map(|(_, context)| context)
        .collect())
}

fn meets_graph_threshold(score: f64, min_score: f64) -> bool {
    score > 0.0 && score >= min_score
}

fn balance_graph_context(
    scored: Vec<(f64, RagGraphContextRead)>,
    limit: usize,
    query: &str,
) -> Vec<(f64, RagGraphContextRead)> {
    if limit == 0 {
        return Vec::new();
    }
    let normalized_query = query.to_lowercase();
    let mut selected = Vec::with_capacity(limit);
    let mut selected_ids = HashSet::new();
    let mut seen_groups = HashSet::new();
    for (score, context) in &scored {
        let matching_role = context
            .relation_roles
            .iter()
            .find(|role| role_query_matches(role, &normalized_query))
            .map(String::as_str)
            .unwrap_or_default();
        let wants_distinct_targets =
            matches!(matching_role, "processing_software" | "data_boundary")
                && [
                    "完整",
                    "全部",
                    "所有",
                    "软件链",
                    "流程",
                    "层级",
                    "不能",
                    "不得",
                    "不是",
                    "pipeline",
                    "fastq",
                ]
                .iter()
                .any(|keyword| normalized_query.contains(keyword));
        let group = (
            if wants_distinct_targets {
                0
            } else {
                context.source_entity_id
            },
            context.relation_type.clone(),
            matching_role.to_owned(),
            if wants_distinct_targets {
                context.target_entity_id
            } else {
                0
            },
        );
        if context.source_entity_type == "note" && seen_groups.insert(group) {
            selected_ids.insert(context.relation_id);
            selected.push((*score, context.clone()));
            if selected.len() == limit {
                return selected;
            }
        }
    }
    for (score, context) in scored {
        if selected_ids.insert(context.relation_id) {
            selected.push((score, context));
            if selected.len() == limit {
                break;
            }
        }
    }
    selected
}

pub fn format_graph_context(context: &[RagGraphContextRead], query: &str) -> String {
    if context.is_empty() {
        return String::new();
    }
    let visible = graph_context_budget(context, query);
    let mut output = String::from("实验知识图谱上下文：\n");
    for line in numeric_summary_lines(context, query) {
        output.push_str(&line);
        output.push('\n');
    }
    for (index, item) in context.iter().take(visible).enumerate() {
        output.push_str(&graph_context_line(index, item));
    }
    if visible < context.len() {
        output.push_str(&graph_context_truncation_suffix());
    }
    output
}

pub fn graph_context_budget(context: &[RagGraphContextRead], query: &str) -> usize {
    let available =
        MAX_GRAPH_CONTEXT_CHARS.saturating_sub(graph_context_truncation_suffix().chars().count());
    let mut used = "实验知识图谱上下文：\n".chars().count();
    used += numeric_summary_lines(context, query)
        .iter()
        .map(|line| line.chars().count() + 1)
        .sum::<usize>();
    let mut visible = 0;
    for (index, item) in context.iter().enumerate() {
        let line_length = graph_context_line(index, item).chars().count();
        if used + line_length > available {
            break;
        }
        used += line_length;
        visible += 1;
    }
    visible
}

fn numeric_summary_lines(context: &[RagGraphContextRead], query: &str) -> Vec<String> {
    let normalized_query = query.to_lowercase();
    if !["计数", "行数", "total", "detected"]
        .iter()
        .any(|keyword| normalized_query.contains(keyword))
    {
        return Vec::new();
    }
    static SUMMARY_PATTERN: OnceLock<Regex> = OnceLock::new();
    let pattern = SUMMARY_PATTERN.get_or_init(|| {
        Regex::new(r"(?i)(GSM\d+).*?total_count=(\d+).*?detected_gene_rows=(\d+)").unwrap()
    });
    let mut records = context
        .iter()
        .filter_map(|item| {
            let captures = pattern.captures(&item.target_label)?;
            Some((
                captures.get(1)?.as_str().to_owned(),
                captures.get(2)?.as_str().parse::<i64>().ok()?,
                captures.get(3)?.as_str().parse::<i64>().ok()?,
            ))
        })
        .collect::<Vec<_>>();
    if records.is_empty() {
        return Vec::new();
    }
    records.sort_by(|left, right| left.0.cmp(&right.0));
    let use_detected = ["非零", "行数", "detected"]
        .iter()
        .any(|keyword| normalized_query.contains(keyword));
    let metric = if use_detected {
        "detected_gene_rows"
    } else {
        "total_count"
    };
    let value = |record: &(String, i64, i64)| if use_detected { record.2 } else { record.1 };
    let mut lines = vec!["结构化数值汇总（系统直接计算）：".to_owned()];
    lines.extend(
        records
            .iter()
            .map(|record| format!("- {}: {metric}={}", record.0, value(record))),
    );
    if ["最高", "最大", "highest", "maximum"]
        .iter()
        .any(|keyword| normalized_query.contains(keyword))
    {
        if let Some(record) = records.iter().max_by_key(|record| value(record)) {
            lines.push(format!(
                "- 比较结果：最高为 {}，{metric}={}。",
                record.0,
                value(record)
            ));
        }
    }
    if ["最低", "最小", "lowest", "minimum"]
        .iter()
        .any(|keyword| normalized_query.contains(keyword))
    {
        if let Some(record) = records.iter().min_by_key(|record| value(record)) {
            lines.push(format!(
                "- 比较结果：最低为 {}，{metric}={}。",
                record.0,
                value(record)
            ));
        }
    }
    if ["相差", "差值", "difference"]
        .iter()
        .any(|keyword| normalized_query.contains(keyword))
        && records.len() == 2
    {
        lines.push(format!(
            "- 差值：{}。",
            (value(&records[0]) - value(&records[1])).abs()
        ));
    }
    lines
}

fn graph_context_line(index: usize, item: &RagGraphContextRead) -> String {
    let role_text = if item.relation_roles.is_empty() {
        String::new()
    } else {
        format!(
            "；用途：{}",
            item.relation_roles
                .iter()
                .map(|role| inline_text(role_label(role)))
                .collect::<Vec<_>>()
                .join("、")
        )
    };
    format!(
        "[G{}] {}（{}） {} {}（{}） (置信度 {:.2}{role_text})\n",
        index + 1,
        inline_text(&item.source_label),
        inline_text(&item.source_entity_type_label),
        inline_text(&item.relation_label),
        inline_text(&item.target_label),
        inline_text(&item.target_entity_type_label),
        item.confidence
    )
}

fn inline_text(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn role_label(value: &str) -> &str {
    match value {
        "cell_line" => "细胞系",
        "cell_type" => "细胞类型",
        "group" => "处理组",
        "perturbation" => "干预方式",
        "treatment" => "处理条件",
        "culture" => "培养条件",
        "replicate" => "生物学重复",
        "alignment_software" => "比对软件",
        "count_software" => "计数软件",
        "processing_software" => "处理软件",
        "geo_accession" => "GEO样本号",
        "sra_accession" => "SRA实验号",
        "biosample_accession" => "BioSample号",
        "count_column" => "计数矩阵列名",
        "reference_genome" => "参考基因组",
        "total_count" => "总基因计数",
        "detected_gene_rows" => "非零基因行数",
        "count_matrix_gene_rows" => "计数矩阵基因条目数",
        "data_boundary" => "数据边界",
        "quality_result" => "质量指标",
        _ => value,
    }
}

fn graph_context_truncation_suffix() -> String {
    format!("\n[图谱上下文已截断至 {MAX_GRAPH_CONTEXT_CHARS} 个字符；未展示的细节不得据此推断。]")
}

fn graph_relation_score(
    row: &GraphRow,
    query_tokens: &HashSet<String>,
    normalized_query: &str,
    hints: &HashSet<&'static str>,
) -> f64 {
    let mut score = if hints.contains(row.relation_type.as_str()) {
        3.0
    } else {
        0.0
    };
    let haystacks = [
        inline_text(&row.source_label).to_lowercase(),
        inline_text(&row.target_label).to_lowercase(),
        row.source_entity_type.to_lowercase(),
        row.target_entity_type.to_lowercase(),
        row.relation_type.to_lowercase(),
        relation_label(&row.relation_type).to_lowercase(),
    ];
    for token in query_tokens {
        for haystack in &haystacks {
            if token == haystack {
                score += 3.0;
            } else if haystack.contains(token) || token.contains(haystack) {
                score += 1.0;
            }
        }
    }
    if row.source_entity_type == "note" {
        score += 0.2;
    }
    if row.source_type.as_deref() == Some("note_extraction") {
        score += 0.3;
    }
    if let Some(roles) = row.properties.get("roles").and_then(Value::as_array) {
        score += roles
            .iter()
            .filter_map(Value::as_str)
            .filter(|role| role_query_matches(role, normalized_query))
            .count() as f64
            * 4.0;
    }
    score
}

#[cfg(test)]
fn graph_relation_haystack(row: &GraphRow) -> String {
    format!(
        "{} {} {} {} {} {}",
        row.source_label,
        row.target_label,
        row.source_entity_type,
        row.target_entity_type,
        row.relation_type,
        relation_label(&row.relation_type),
    )
    .to_lowercase()
}

fn relation_hints(query: &str) -> HashSet<&'static str> {
    let mut hints = HashSet::new();
    let query_tokens = tokens(query);
    for (relation, words) in [
        (
            "has_note",
            &["笔记", "记录", "已审核", "note", "notes"] as &[&str],
        ),
        (
            "uses_reagent",
            &["试剂", "材料", "药品", "reagent", "reagents"],
        ),
        (
            "uses_instrument",
            &["仪器", "设备", "instrument", "instruments"],
        ),
        ("uses_sample", &["样本", "样品", "sample", "samples"]),
        (
            "produces_result",
            &[
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
            ],
        ),
        (
            "has_attachment",
            &["附件", "资料", "文件", "attachment", "file"],
        ),
        (
            "created_by",
            &["谁", "人员", "创建", "负责人", "user", "creator"],
        ),
        ("has_experiment_type", &["类型", "实验类型", "type"]),
        (
            "has_biological_source",
            &["细胞", "细胞系", "细胞类型", "来源", "cell", "source"],
        ),
        (
            "has_condition",
            &[
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
            ],
        ),
        (
            "uses_software",
            &[
                "软件",
                "比对",
                "计数软件",
                "处理流程",
                "software",
                "aligner",
            ],
        ),
        (
            "has_identifier",
            &[
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
            ],
        ),
    ] {
        if words.iter().any(|word| {
            tokens(word).iter().any(|hint_token| {
                query_tokens
                    .iter()
                    .any(|query_token| hint_tokens_match(query_token, hint_token))
            })
        }) {
            hints.insert(relation);
        }
    }
    hints
}

fn role_query_matches(role: &str, normalized_query: &str) -> bool {
    let keywords: &[&str] = match role {
        "cell_line" => &["细胞系", "cell line"],
        "cell_type" => &["细胞类型", "cell type"],
        "group" => &["组", "分组", "组别", "对照", "敲低", "group", "condition"],
        "perturbation" => &["shrna", "靶向", "敲低", "construct"],
        "treatment" => &["处理", "剂量", "treatment", "dose"],
        "culture" => &["培养", "温度", "co2", "时长", "culture"],
        "replicate" => &["重复", "replicate"],
        "alignment_software" => &["比对软件", "比对", "aligner", "alignment"],
        "count_software" => &["计数软件", "基因计数", "count software"],
        "processing_software" => &["处理软件", "软件链", "流程", "pipeline"],
        "geo_accession" => &["geo", "gsm", "样本号"],
        "sra_accession" => &["sra", "srx", "实验号"],
        "biosample_accession" => &["biosample", "samn"],
        "count_column" => &["列名", "矩阵列", "column"],
        "reference_genome" => &["参考基因组", "基因组", "genome", "hg19", "grch"],
        "total_count" => &["总基因计数", "总计数", "total count", "total_count"],
        "detected_gene_rows" => &["非零基因", "检测到", "行数", "detected_gene_rows"],
        "count_matrix_gene_rows" => &[
            "基因条目",
            "计数矩阵",
            "count_matrix_gene_rows",
            "gene rows",
        ],
        "data_boundary" => &[
            "层级",
            "不能",
            "不得",
            "不是",
            "fastq",
            "差异表达",
            "significance",
        ],
        "quality_result" => &["质量", "rin", "quality"],
        _ => &[],
    };
    keywords
        .iter()
        .any(|keyword| normalized_query.contains(keyword))
}

fn focused_graph_entity_ids(rows: &[GraphRow], query: &str) -> Option<HashSet<i32>> {
    let normalized_query = query.to_lowercase();
    let focus_tokens = token_regex()
        .find_iter(query)
        .map(|matched| matched.as_str().to_lowercase())
        .filter(|token| token.chars().count() >= 2 && !is_generic_graph_token(token))
        .collect::<HashSet<_>>();
    let mut matched = HashSet::new();
    for row in rows {
        for (entity_id, label) in [
            (row.source_entity_id, row.source_label.as_str()),
            (row.target_entity_id, row.target_label.as_str()),
        ] {
            let normalized_label = label.to_lowercase();
            let token_match = focus_tokens.iter().any(|token| {
                normalized_label == *token
                    || normalized_label.contains(token)
                    || token.contains(&normalized_label)
            });
            let synonym_match = [
                (
                    "control",
                    &["对照", "非靶向", "shcontrol", "nontargeting"] as &[&str],
                ),
                ("p63_knockdown", &["p63敲低", "p63靶向", "shp63", "p63kd"]),
            ]
            .iter()
            .any(|(canonical, aliases)| {
                normalized_label.contains(canonical)
                    && aliases.iter().any(|alias| normalized_query.contains(alias))
            });
            if token_match || synonym_match {
                matched.insert(entity_id);
            }
        }
    }
    if matched.is_empty() {
        return None;
    }
    let mut focused = matched.clone();
    for row in rows {
        if matched.contains(&row.source_entity_id) && row.target_entity_type == "note" {
            focused.insert(row.target_entity_id);
        }
        if matched.contains(&row.target_entity_id) && row.source_entity_type == "note" {
            focused.insert(row.source_entity_id);
        }
    }
    Some(focused)
}

fn is_generic_graph_token(token: &str) -> bool {
    matches!(
        token,
        "笔记"
            | "记录"
            | "已审核"
            | "note"
            | "notes"
            | "试剂"
            | "材料"
            | "药品"
            | "reagent"
            | "reagents"
            | "use"
            | "仪器"
            | "设备"
            | "instrument"
            | "instruments"
            | "样本"
            | "样品"
            | "sample"
            | "samples"
            | "结果"
            | "观察"
            | "结论"
            | "result"
            | "count"
            | "计数"
            | "行数"
            | "条目"
            | "total"
            | "detected"
            | "fastq"
            | "significance"
            | "附件"
            | "资料"
            | "文件"
            | "file"
            | "谁"
            | "人员"
            | "创建"
            | "creator"
            | "user"
            | "负责人"
            | "类型"
            | "实验类型"
            | "type"
            | "细胞"
            | "细胞系"
            | "细胞类型"
            | "来源"
            | "cell"
            | "条件"
            | "分组"
            | "组别"
            | "处理"
            | "培养"
            | "重复"
            | "对照"
            | "敲低"
            | "condition"
            | "treatment"
            | "replicate"
            | "control"
            | "knockdown"
            | "软件"
            | "比对"
            | "计数软件"
            | "处理流程"
            | "software"
            | "aligner"
            | "登录号"
            | "标识符"
            | "标识"
            | "样本号"
            | "列名"
            | "参考基因组"
            | "accession"
            | "geo"
            | "sra"
            | "biosample"
            | "genome"
            | "哪些"
            | "有哪些"
            | "全部"
            | "所有"
            | "列出"
            | "列举"
            | "多少"
            | "分别"
            | "完整"
            | "汇总"
            | "归纳"
            | "清单"
            | "一览"
            | "各自"
            | "数量"
            | "四个"
            | "两个"
            | "最高"
            | "最低"
            | "相差"
            | "all"
            | "list"
            | "enumerate"
    )
}

fn hint_tokens_match(left: &str, right: &str) -> bool {
    left == right
        || (left.len() > 3 && left.strip_suffix('s') == Some(right))
        || (right.len() > 3 && right.strip_suffix('s') == Some(left))
}

pub(crate) fn relation_label(value: &str) -> &str {
    match value {
        "has_note" => "包含笔记",
        "created_by" => "创建者",
        "has_attachment" => "关联附件",
        "has_experiment_type" => "实验类型",
        "uses_reagent" => "使用试剂",
        "uses_instrument" => "使用仪器",
        "uses_sample" => "使用样本",
        "produces_result" => "产生结果",
        "has_biological_source" => "生物来源",
        "has_condition" => "实验条件",
        "uses_software" => "使用软件",
        "has_identifier" => "关联标识符",
        _ => value,
    }
}

pub(crate) fn entity_type_label(value: &str) -> &str {
    match value {
        "project" => "项目",
        "note" => "实验笔记",
        "user" => "人员",
        "file" => "附件资料",
        "experiment_type" => "实验类型",
        "reagent" => "试剂",
        "instrument" => "仪器",
        "sample" => "样本",
        "result" => "实验结果",
        "biological_source" => "生物来源",
        "condition" => "实验条件",
        "software" => "分析软件",
        "identifier" => "数据标识符",
        _ => value,
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{
        balance_graph_context, focused_graph_entity_ids, format_graph_context,
        graph_context_budget, graph_relation_haystack, graph_relation_score, meets_graph_threshold,
        relation_hints, role_query_matches, GraphRow, MAX_GRAPH_CONTEXT_CHARS,
    };
    use crate::models::RagGraphContextRead;
    use crate::rag::bm25::{exact_token_overlap, tokens};

    #[test]
    fn test_graph_relation_score_keeps_python_ranking_components() {
        let row = GraphRow {
            relation_id: 1,
            relation_type: "uses_reagent".to_owned(),
            source_type: Some("note_extraction".to_owned()),
            source_entity_id: 10,
            source_label: "PCR experiment".to_owned(),
            source_normalized_label: "pcr experiment".to_owned(),
            source_natural_key: "pcr-10".to_owned(),
            source_entity_type: "note".to_owned(),
            target_entity_id: 11,
            target_label: "PBS buffer solution".to_owned(),
            target_normalized_label: "pbs buffer solution".to_owned(),
            target_natural_key: "pbs-11".to_owned(),
            target_entity_type: "reagent".to_owned(),
            confidence: 0.9,
            properties: json!({"roles": ["group"]}),
        };
        let query = "PBS reagent";
        let score = graph_relation_score(&row, &tokens(query), query, &relation_hints(query));

        assert!(score >= 4.5);
    }

    #[test]
    fn test_graph_matching_includes_human_relation_labels() {
        let row = GraphRow {
            relation_id: 1,
            relation_type: "uses_reagent".to_owned(),
            source_type: Some("note_extraction".to_owned()),
            source_entity_id: 10,
            source_label: "PCR experiment".to_owned(),
            source_normalized_label: "pcr experiment".to_owned(),
            source_natural_key: "pcr-10".to_owned(),
            source_entity_type: "note".to_owned(),
            target_entity_id: 11,
            target_label: "Taq".to_owned(),
            target_normalized_label: "taq".to_owned(),
            target_natural_key: "taq-11".to_owned(),
            target_entity_type: "reagent".to_owned(),
            confidence: 0.9,
            properties: json!({}),
        };

        assert!(exact_token_overlap(&tokens("使用试剂"), &graph_relation_haystack(&row)) > 0);
    }

    #[test]
    fn test_relation_hints_do_not_match_substrings() {
        assert!(!relation_hints("user").contains("uses_reagent"));
        assert!(relation_hints("Which reagents were used?").contains("uses_reagent"));
        assert!(relation_hints("列出所有资料").contains("has_attachment"));
        assert!(relation_hints("总计数和检测行数").contains("produces_result"));
        assert!(relation_hints("负责人是谁").contains("created_by"));
        assert!(relation_hints("count software").contains("uses_software"));
    }

    #[test]
    fn test_graph_role_aliases_match_human_queries() {
        assert!(role_query_matches("alignment_software", "比对软件"));
        assert!(role_query_matches("count_software", "count software"));
        assert!(!role_query_matches("alignment_software", "实验结果"));
    }

    #[test]
    fn test_graph_focus_keeps_requested_note_and_disables_for_collection_queries() {
        let rows = vec![
            GraphRow {
                relation_id: 1,
                relation_type: "uses_reagent".to_owned(),
                source_type: Some("note_extraction".to_owned()),
                source_entity_id: 10,
                source_label: "PCR condition experiment".to_owned(),
                source_normalized_label: "pcr condition experiment".to_owned(),
                source_natural_key: "pcr-10".to_owned(),
                source_entity_type: "note".to_owned(),
                target_entity_id: 11,
                target_label: "Taq DNA Polymerase".to_owned(),
                target_normalized_label: "taq dna polymerase".to_owned(),
                target_natural_key: "taq-11".to_owned(),
                target_entity_type: "reagent".to_owned(),
                confidence: 0.9,
                properties: json!({}),
            },
            GraphRow {
                relation_id: 2,
                relation_type: "uses_reagent".to_owned(),
                source_type: Some("note_extraction".to_owned()),
                source_entity_id: 20,
                source_label: "Western blot experiment".to_owned(),
                source_normalized_label: "western blot experiment".to_owned(),
                source_natural_key: "western-20".to_owned(),
                source_entity_type: "note".to_owned(),
                target_entity_id: 21,
                target_label: "RIPA buffer".to_owned(),
                target_normalized_label: "ripa buffer".to_owned(),
                target_natural_key: "ripa-21".to_owned(),
                target_entity_type: "reagent".to_owned(),
                confidence: 0.9,
                properties: json!({}),
            },
        ];

        let focused = focused_graph_entity_ids(&rows, "PCR 实验用了哪些试剂？").unwrap();
        assert!(focused.contains(&10));
        assert!(!focused.contains(&20));
        assert!(focused_graph_entity_ids(&rows, "列出所有试剂").is_none());

        let material_rows = vec![GraphRow {
            relation_id: 3,
            relation_type: "has_attachment".to_owned(),
            source_type: Some("project".to_owned()),
            source_entity_id: 30,
            source_label: "资料库".to_owned(),
            source_normalized_label: "资料库".to_owned(),
            source_natural_key: "project-30".to_owned(),
            source_entity_type: "project".to_owned(),
            target_entity_id: 31,
            target_label: "protocol.pdf".to_owned(),
            target_normalized_label: "protocol.pdf".to_owned(),
            target_natural_key: "protocol-31".to_owned(),
            target_entity_type: "file".to_owned(),
            confidence: 0.9,
            properties: json!({}),
        }];
        assert!(focused_graph_entity_ids(&material_rows, "列出所有资料").is_none());
    }

    #[test]
    fn test_graph_context_balances_note_sources() {
        let context = |relation_id: i32,
                       source_entity_id: i32,
                       target_entity_id: i32,
                       retrieval_score: f64| RagGraphContextRead {
            relation_id,
            relation_type: "uses_reagent".to_owned(),
            relation_label: "使用试剂".to_owned(),
            source_entity_id,
            source_label: format!("note-{source_entity_id}"),
            source_normalized_label: format!("note-{source_entity_id}"),
            source_natural_key: format!("note-{source_entity_id}"),
            source_entity_type: "note".to_owned(),
            source_entity_type_label: "实验笔记".to_owned(),
            target_entity_id,
            target_label: format!("reagent-{target_entity_id}"),
            target_normalized_label: format!("reagent-{target_entity_id}"),
            target_natural_key: format!("reagent-{target_entity_id}"),
            target_entity_type: "reagent".to_owned(),
            target_entity_type_label: "试剂".to_owned(),
            confidence: 0.9,
            retrieval_score,
            relation_roles: vec![],
            relation_properties: json!({}),
        };
        let selected = balance_graph_context(
            vec![
                (3.0, context(1, 10, 11, 3.0)),
                (2.0, context(2, 10, 12, 2.0)),
                (1.0, context(3, 20, 21, 1.0)),
            ],
            2,
            "列出所有试剂",
        );

        let relation_ids = selected
            .into_iter()
            .map(|(_, context)| context.relation_id)
            .collect::<Vec<_>>();
        assert_eq!(relation_ids, [1, 3]);
    }

    #[test]
    fn test_graph_threshold_rejects_below_threshold_and_zero_scores() {
        assert!(meets_graph_threshold(1.0, 1.0));
        assert!(meets_graph_threshold(1.0, 0.0));
        assert!(!meets_graph_threshold(0.9, 1.0));
        assert!(!meets_graph_threshold(0.0, 0.0));
    }

    #[test]
    fn test_graph_context_budget_drops_unrendered_markers() {
        let context = (1..=30)
            .map(|index| RagGraphContextRead {
                relation_id: index,
                relation_type: "uses_reagent".to_owned(),
                relation_label: "使用试剂".to_owned(),
                source_entity_id: index,
                source_label: "source ".to_owned() + &"x".repeat(1_000),
                source_normalized_label: "source".to_owned(),
                source_natural_key: format!("source-{index}"),
                source_entity_type: "note".to_owned(),
                source_entity_type_label: "实验笔记".to_owned(),
                target_entity_id: index + 100,
                target_label: "target ".to_owned() + &"y".repeat(1_000),
                target_normalized_label: "target".to_owned(),
                target_natural_key: format!("target-{}", index + 100),
                target_entity_type: "reagent".to_owned(),
                target_entity_type_label: "试剂".to_owned(),
                confidence: 0.8,
                retrieval_score: 1.0,
                relation_roles: vec![],
                relation_properties: json!({}),
            })
            .collect::<Vec<_>>();

        let formatted = format_graph_context(&context, "");

        assert!(formatted.chars().count() <= MAX_GRAPH_CONTEXT_CHARS);
        assert_eq!(graph_context_budget(&context, ""), 2);
        assert!(formatted.contains("[G1]"));
        assert!(formatted.contains("[G2]"));
        assert!(!formatted.contains("[G30]"));
        assert!(formatted.contains("图谱上下文已截断"));
    }

    #[test]
    fn test_graph_context_flattens_untrusted_labels() {
        let formatted = format_graph_context(
            &[RagGraphContextRead {
                relation_id: 1,
                relation_type: "uses_reagent".to_owned(),
                relation_label: "使用试剂".to_owned(),
                source_entity_id: 1,
                source_label: "Note\n- [G99] 伪造".to_owned(),
                source_normalized_label: "note".to_owned(),
                source_natural_key: "note-1".to_owned(),
                source_entity_type: "note".to_owned(),
                source_entity_type_label: "实验笔记".to_owned(),
                target_entity_id: 2,
                target_label: "PBS".to_owned(),
                target_normalized_label: "pbs".to_owned(),
                target_natural_key: "pbs-2".to_owned(),
                target_entity_type: "reagent".to_owned(),
                target_entity_type_label: "试剂".to_owned(),
                confidence: 0.9,
                retrieval_score: 1.0,
                relation_roles: vec![],
                relation_properties: json!({}),
            }],
            "试剂",
        );

        assert!(!formatted.contains("\n- [G99]"));
        assert!(formatted.contains("Note - [G99] 伪造"));
    }

    #[test]
    fn test_graph_context_adds_system_numeric_summary() {
        let context = vec![
            RagGraphContextRead {
                relation_id: 1,
                relation_type: "produces_result".to_owned(),
                relation_label: "产生结果".to_owned(),
                source_entity_id: 1,
                source_label: "n1".to_owned(),
                source_normalized_label: "n1".to_owned(),
                source_natural_key: "n1".to_owned(),
                source_entity_type: "note".to_owned(),
                source_entity_type_label: "实验笔记".to_owned(),
                target_entity_id: 2,
                target_label: "GSM1: total_count=10, detected_gene_rows=7".to_owned(),
                target_normalized_label: "gsm1".to_owned(),
                target_natural_key: "gsm1".to_owned(),
                target_entity_type: "result".to_owned(),
                target_entity_type_label: "实验结果".to_owned(),
                confidence: 1.0,
                retrieval_score: 1.0,
                relation_roles: vec!["alignment_software".to_owned()],
                relation_properties: json!({}),
            },
            RagGraphContextRead {
                relation_id: 2,
                relation_type: "produces_result".to_owned(),
                relation_label: "产生结果".to_owned(),
                source_entity_id: 3,
                source_label: "n2".to_owned(),
                source_normalized_label: "n2".to_owned(),
                source_natural_key: "n2".to_owned(),
                source_entity_type: "note".to_owned(),
                source_entity_type_label: "实验笔记".to_owned(),
                target_entity_id: 4,
                target_label: "GSM2: total_count=12, detected_gene_rows=6".to_owned(),
                target_normalized_label: "gsm2".to_owned(),
                target_natural_key: "gsm2".to_owned(),
                target_entity_type: "result".to_owned(),
                target_entity_type_label: "实验结果".to_owned(),
                confidence: 1.0,
                retrieval_score: 1.0,
                relation_roles: vec![],
                relation_properties: json!({}),
            },
        ];

        let formatted = format_graph_context(&context, "总基因计数最高的是哪个样本？");

        assert!(formatted.contains("结构化数值汇总（系统直接计算）："));
        assert!(formatted.contains("最高为 GSM2"));
        assert!(formatted.contains("total_count=12"));
        assert!(formatted.contains("比对软件"));
    }
}
