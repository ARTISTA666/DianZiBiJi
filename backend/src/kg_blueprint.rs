use serde_json::{json, Value};
use sqlx::{Postgres, Transaction};

use crate::{
    error::ApiError,
    knowledge_graph::{extract_terms, normalize_entity_label},
    models::{
        BlueprintCoverage, BlueprintDocumentRead, BlueprintEdgeRead, BlueprintEvidence,
        BlueprintNodeRead, BlueprintParseRequest, BlueprintParseResponse, KnowledgeBlueprintRead,
        BLUEPRINT_ENTITY_TYPES, BLUEPRINT_PRIORITY_MEETING_NOTE, BLUEPRINT_PRIORITY_PLAN_DOCUMENT,
        BLUEPRINT_RELATION_TYPES, BLUEPRINT_SOURCE_MEETING_NOTE, BLUEPRINT_SOURCE_PLAN_DOCUMENT,
    },
    rag, AppState,
};

const BLUEPRINT_TEXT_MAX_CHARS: usize = 20_000;
const BLUEPRINT_PROMPT_MAX_CHARS: usize = 12_000;

const BLUEPRINT_SYSTEM_PROMPT: &str = r#"你是科研实验项目的知识蓝图解析器。输入是一份项目计划书或组会纪要文本。请抽取其中明确提到的知识实体与它们之间的关系，输出严格的 JSON 对象（禁止 markdown 代码块、禁止解释文字），格式：
{"nodes":[{"entity_type":"reagent","label":"CCK-8 试剂盒","description":"细胞活性检测试剂"}],"edges":[{"source_label":"细胞活力检测","target_label":"CCK-8 试剂盒","relation_type":"uses_reagent"}]}
约束：
1. entity_type 只能取：reagent,instrument,sample,result,experiment_type,treatment,perturbation,culture,cell_type,cell_line,group,biosample,geo_accession,software,condition
2. relation_type 只能取：uses_reagent,uses_instrument,uses_sample,produces_result,has_experiment_type,has_condition
3. label 不超过 40 字符，保留原文写法；description 不超过 80 字符，可为空字符串
4. 只抽取文本明确提到的知识项，不要编造；edges 中的 source_label/target_label 必须出现在 nodes 的 label 中"#;

#[derive(serde::Deserialize)]
struct BlueprintLlmNode {
    entity_type: String,
    label: String,
    #[serde(default)]
    description: String,
}

#[derive(serde::Deserialize)]
struct BlueprintLlmEdge {
    source_label: String,
    target_label: String,
    relation_type: String,
}

#[derive(serde::Deserialize)]
struct BlueprintLlmOutput {
    #[serde(default)]
    nodes: Vec<BlueprintLlmNode>,
    #[serde(default)]
    edges: Vec<BlueprintLlmEdge>,
}

fn is_blueprint_entity_type(entity_type: &str) -> bool {
    BLUEPRINT_ENTITY_TYPES.contains(&entity_type)
}

fn is_blueprint_relation_type(relation_type: &str) -> bool {
    BLUEPRINT_RELATION_TYPES.contains(&relation_type)
}

pub fn resolve_source_priority(source_kind: &str, requested: Option<i32>) -> Result<i32, ApiError> {
    if let Some(priority) = requested {
        return Ok(priority.clamp(1, 1000));
    }
    match source_kind {
        BLUEPRINT_SOURCE_MEETING_NOTE => Ok(BLUEPRINT_PRIORITY_MEETING_NOTE),
        BLUEPRINT_SOURCE_PLAN_DOCUMENT => Ok(BLUEPRINT_PRIORITY_PLAN_DOCUMENT),
        other => Err(ApiError::new(
            axum::http::StatusCode::BAD_REQUEST,
            format!("Invalid source_kind: {other}"),
        )),
    }
}

/// 蓝图节点写入入参。
pub struct BlueprintNodeInput<'a> {
    pub entity_type: &'a str,
    pub label: &'a str,
    pub description: &'a str,
    pub source_kind: &'a str,
    pub source_label: &'a str,
    pub priority: i32,
    pub created_by: i32,
}

/// 蓝图节点写入结果：新增 / 高优先级来源覆盖既有 / 命中既有保持不变。
pub enum BlueprintNodeUpsert {
    Added(i32),
    Updated(i32),
    Kept(i32),
}

/// 写入/更新一个蓝图节点。冲突规则：同 (项目, 类型, 规范名) 的活跃节点唯一，
/// 新来源 priority 更小（更高）时覆盖描述与来源信息，否则保留现状。
pub async fn upsert_blueprint_node(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    input: &BlueprintNodeInput<'_>,
) -> Result<BlueprintNodeUpsert, ApiError> {
    let BlueprintNodeInput {
        entity_type,
        label,
        description,
        source_kind,
        source_label,
        priority,
        created_by,
    } = input;
    let normalized_label = normalize_entity_label(label);
    if normalized_label.is_empty() {
        return Ok(BlueprintNodeUpsert::Kept(0));
    }
    let existing: Option<(i32, i32)> = sqlx::query_as(
        r#"
        SELECT id, priority FROM public.kg_blueprint_nodes
        WHERE project_id = $1 AND entity_type = $2 AND normalized_label = $3 AND status <> 'retired'
        "#,
    )
    .bind(project_id)
    .bind(entity_type)
    .bind(&normalized_label)
    .fetch_optional(&mut **transaction)
    .await?;
    if let Some((node_id, existing_priority)) = existing {
        if *priority < existing_priority {
            sqlx::query(
                r#"
                UPDATE public.kg_blueprint_nodes
                SET description = $3, source_kind = $4, source_label = $5, priority = $6, updated_at = now()
                WHERE id = $1 AND project_id = $2
                "#,
            )
            .bind(node_id)
            .bind(project_id)
            .bind(*description)
            .bind(*source_kind)
            .bind(*source_label)
            .bind(*priority)
            .execute(&mut **transaction)
            .await?;
            return Ok(BlueprintNodeUpsert::Updated(node_id));
        }
        return Ok(BlueprintNodeUpsert::Kept(node_id));
    }
    let node_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO public.kg_blueprint_nodes
            (project_id, entity_type, label, normalized_label, description, status, source_kind, source_label, priority, created_by)
        VALUES ($1, $2, $3, $4, $5, 'planned', $6, $7, $8, $9)
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(*entity_type)
    .bind(*label)
    .bind(&normalized_label)
    .bind(*description)
    .bind(*source_kind)
    .bind(*source_label)
    .bind(*priority)
    .bind(*created_by)
    .fetch_one(&mut **transaction)
    .await?;
    Ok(BlueprintNodeUpsert::Added(node_id))
}

/// 写入一条蓝图边（同端点同关系类型唯一）。返回是否新增。
pub async fn upsert_blueprint_edge(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    source_node_id: i32,
    target_node_id: i32,
    relation_type: &str,
    priority: i32,
) -> Result<bool, ApiError> {
    if source_node_id == target_node_id || source_node_id == 0 || target_node_id == 0 {
        return Ok(false);
    }
    if !is_blueprint_relation_type(relation_type) {
        return Ok(false);
    }
    let existing: Option<i32> = sqlx::query_scalar(
        r#"
        SELECT id FROM public.kg_blueprint_edges
        WHERE project_id = $1 AND source_node_id = $2 AND target_node_id = $3
          AND relation_type = $4 AND status <> 'retired'
        "#,
    )
    .bind(project_id)
    .bind(source_node_id)
    .bind(target_node_id)
    .bind(relation_type)
    .fetch_optional(&mut **transaction)
    .await?;
    if existing.is_some() {
        return Ok(false);
    }
    sqlx::query(
        r#"
        INSERT INTO public.kg_blueprint_edges
            (project_id, source_node_id, target_node_id, relation_type, status, source_kind, priority)
        VALUES ($1, $2, $3, $4, 'planned', 'plan_document', $5)
        "#,
    )
    .bind(project_id)
    .bind(source_node_id)
    .bind(target_node_id)
    .bind(relation_type)
    .bind(priority)
    .execute(&mut **transaction)
    .await?;
    Ok(true)
}

/// 从计划书/组会纪要文本解析蓝图。优先 LLM 结构化解析；
/// 未配置 LLM 或解析失败时回落到规则抽取（仅节点、无边），并在 document 记录中如实留痕。
pub async fn parse_blueprint_document(
    state: &AppState,
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    created_by: i32,
    request: &BlueprintParseRequest,
) -> Result<BlueprintParseResponse, ApiError> {
    let priority = resolve_source_priority(&request.source_kind, request.priority)?;
    let title = request.title.trim();
    if title.is_empty() || title.chars().count() > 200 {
        return Err(ApiError::new(
            axum::http::StatusCode::BAD_REQUEST,
            "title 必填且不超过 200 字符",
        ));
    }
    let text = resolve_parse_text(state, transaction, project_id, request).await?;
    let char_count = text.chars().count();
    if char_count < 10 {
        return Err(ApiError::new(
            axum::http::StatusCode::BAD_REQUEST,
            "文本过短，无法解析知识蓝图",
        ));
    }

    let (parse_mode, parsed, mut message): (String, BlueprintLlmOutput, String) =
        if state.settings.ai_api_key.trim().is_empty() {
            (
                "rule_based".to_owned(),
                rule_based_blueprint(&text),
                "未配置 AI 服务，使用规则抽取模式（仅抽取节点）".to_owned(),
            )
        } else {
            match llm_blueprint(state, &text).await {
                Ok(output) => ("llm".to_owned(), output, String::new()),
                Err(error) => {
                    let mut fallback = rule_based_blueprint(&text);
                    if fallback.nodes.is_empty() {
                        return Err(ApiError::new(
                            axum::http::StatusCode::BAD_GATEWAY,
                            format!("AI 解析失败且规则抽取无结果：{error}"),
                        ));
                    }
                    fallback.edges.clear();
                    (
                        "rule_based".to_owned(),
                        fallback,
                        format!("AI 解析失败，已回落规则抽取：{error}"),
                    )
                }
            }
        };

    // 节点批内去重（同型同名保留首个），并校验实体类型合法。
    let mut batch: Vec<(String, String, String)> = Vec::new();
    let mut nodes_added: i64 = 0;
    let mut nodes_updated: i64 = 0;
    let mut nodes_dropped: i64 = 0;
    for node in parsed.nodes {
        let label = node.label.trim().to_owned();
        if label.is_empty() || label.chars().count() > 120 {
            nodes_dropped += 1;
            continue;
        }
        let entity_type = node.entity_type.trim().to_owned();
        if !is_blueprint_entity_type(&entity_type) {
            nodes_dropped += 1;
            continue;
        }
        let normalized = normalize_entity_label(&label);
        if normalized.is_empty()
            || batch.iter().any(|(batch_type, batch_label, _)| {
                batch_type == &entity_type && batch_label == &normalized
            })
        {
            nodes_dropped += 1;
            continue;
        }
        let description = node
            .description
            .trim()
            .chars()
            .take(200)
            .collect::<String>();
        batch.push((entity_type.clone(), normalized, description.clone()));
        let source_label = title.to_owned();
        match upsert_blueprint_node(
            transaction,
            project_id,
            &BlueprintNodeInput {
                entity_type: &entity_type,
                label: &label,
                description: &description,
                source_kind: &request.source_kind,
                source_label: &source_label,
                priority,
                created_by,
            },
        )
        .await?
        {
            BlueprintNodeUpsert::Added(_) => nodes_added += 1,
            BlueprintNodeUpsert::Updated(_) => nodes_updated += 1,
            BlueprintNodeUpsert::Kept(node_id) => {
                if node_id == 0 {
                    nodes_dropped += 1;
                    batch.pop();
                }
            }
        }
    }

    // 边解析：端点按规范名在本次批内解析，越界/自环/非法关系类型丢弃。
    let mut edges_added: i64 = 0;
    let mut edges_dropped: i64 = 0;
    for edge in parsed.edges {
        let source = normalize_entity_label(edge.source_label.trim());
        let target = normalize_entity_label(edge.target_label.trim());
        if !is_blueprint_relation_type(edge.relation_type.trim()) {
            edges_dropped += 1;
            continue;
        }
        let source_node_id = lookup_batch_node_id(transaction, project_id, &source).await?;
        let target_node_id = lookup_batch_node_id(transaction, project_id, &target).await?;
        if source_node_id == 0 || target_node_id == 0 {
            edges_dropped += 1;
            continue;
        }
        if upsert_blueprint_edge(
            transaction,
            project_id,
            source_node_id,
            target_node_id,
            edge.relation_type.trim(),
            priority,
        )
        .await?
        {
            edges_added += 1;
        } else {
            edges_dropped += 1;
        }
    }

    if nodes_added == 0 && nodes_updated == 0 && edges_added == 0 && nodes_dropped > 0 {
        message = format!("{message}; 解析结果均无效（实体类型或标签不合规 {nodes_dropped} 项）");
    }

    let document_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO public.kg_blueprint_documents
            (project_id, title, source_kind, parse_mode, node_count, edge_count, message, created_by)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(title)
    .bind(&request.source_kind)
    .bind(&parse_mode)
    .bind((nodes_added + nodes_updated) as i32)
    .bind(edges_added as i32)
    .bind(&message)
    .bind(created_by)
    .fetch_one(&mut **transaction)
    .await?;

    Ok(BlueprintParseResponse {
        document_id,
        parse_mode,
        nodes_added,
        nodes_updated,
        edges_added,
        edges_dropped: edges_dropped + nodes_dropped,
        message,
    })
}

async fn lookup_batch_node_id(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    normalized_label: &str,
) -> Result<i32, ApiError> {
    if normalized_label.is_empty() {
        return Ok(0);
    }
    let ids: Vec<i32> = sqlx::query_scalar(
        r#"
        SELECT id FROM public.kg_blueprint_nodes
        WHERE project_id = $1 AND normalized_label = $2 AND status <> 'retired'
        ORDER BY priority ASC, id ASC LIMIT 1
        "#,
    )
    .bind(project_id)
    .bind(normalized_label)
    .fetch_all(&mut **transaction)
    .await?;
    Ok(ids.first().copied().unwrap_or(0))
}

/// 解析文本来源：直接文本 / 项目内文件 OCR / 项目内笔记版本内容。
async fn resolve_parse_text(
    state: &AppState,
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    request: &BlueprintParseRequest,
) -> Result<String, ApiError> {
    let _ = state;
    if let Some(text) = &request.text {
        let trimmed = text.trim().to_owned();
        if trimmed.chars().count() > BLUEPRINT_TEXT_MAX_CHARS {
            return Err(ApiError::new(
                axum::http::StatusCode::BAD_REQUEST,
                format!("文本过长，最多 {BLUEPRINT_TEXT_MAX_CHARS} 字符"),
            ));
        }
        return Ok(trimmed);
    }
    if let Some(file_id) = request.file_id {
        let text: Option<String> = sqlx::query_scalar(
            r#"
            SELECT COALESCE(NULLIF(o.corrected_text, ''), o.raw_text)
            FROM public.file_ocr_results o
            JOIN public.files f ON f.id = o.file_id
            WHERE o.file_id = $1 AND f.project_id = $2
            ORDER BY o.id DESC LIMIT 1
            "#,
        )
        .bind(file_id)
        .bind(project_id)
        .fetch_optional(&mut **transaction)
        .await?;
        return text.ok_or_else(|| {
            ApiError::new(
                axum::http::StatusCode::NOT_FOUND,
                "文件不存在或尚无 OCR 文本，请先完成文档解析",
            )
        });
    }
    if let Some(note_id) = request.note_id {
        let content: Option<Value> = sqlx::query_scalar(
            r#"
            SELECT v.content_json
            FROM public.note_versions v
            JOIN public.experiment_notes n ON n.id = v.note_id
            WHERE v.note_id = $1 AND n.project_id = $2
            ORDER BY v.id DESC LIMIT 1
            "#,
        )
        .bind(note_id)
        .bind(project_id)
        .fetch_optional(&mut **transaction)
        .await?;
        let content = content.ok_or_else(|| {
            ApiError::new(axum::http::StatusCode::NOT_FOUND, "笔记不存在或尚无版本")
        })?;
        if let Some(text) = content.get("text").and_then(Value::as_str) {
            return Ok(text.to_owned());
        }
        return Ok(content.to_string());
    }
    Err(ApiError::new(
        axum::http::StatusCode::BAD_REQUEST,
        "需要提供 text、file_id 或 note_id 之一作为解析来源",
    ))
}

async fn llm_blueprint(state: &AppState, text: &str) -> Result<BlueprintLlmOutput, String> {
    let prompt_text: String = text.chars().take(BLUEPRINT_PROMPT_MAX_CHARS).collect();
    let result =
        rag::generate_with_max_tokens(state, BLUEPRINT_SYSTEM_PROMPT, &prompt_text, 0.1, 4000)
            .await
            .map_err(|error| error.to_string())?;
    let object =
        extract_json_object(&result.answer).ok_or_else(|| "回答中未找到 JSON 对象".to_owned())?;
    serde_json::from_value::<BlueprintLlmOutput>(object)
        .map_err(|error| format!("JSON 解析失败：{error}"))
}

fn extract_json_object(answer: &str) -> Option<Value> {
    let start = answer.find('{')?;
    let end = answer.rfind('}')?;
    if end < start {
        return None;
    }
    serde_json::from_str(&answer[start..=end]).ok()
}

/// 规则兜底：复用图谱抽取器的正则术语识别，把计划文本当作自由文本处理（仅节点、无边）。
fn rule_based_blueprint(text: &str) -> BlueprintLlmOutput {
    let content = json!({"text": text});
    let nodes = extract_terms(&json!({}), &content)
        .into_iter()
        .filter(|term| is_blueprint_entity_type(term.entity_type))
        .map(|term| BlueprintLlmNode {
            entity_type: term.entity_type.to_owned(),
            label: term.label,
            description: String::new(),
        })
        .take(120)
        .collect();
    BlueprintLlmOutput {
        nodes,
        edges: Vec::new(),
    }
}

/// 蓝图节点与实证实体 LEFT JOIN 后的行（一节点多实体时同节点多行）。
#[derive(sqlx::FromRow)]
struct BlueprintNodeEvidenceRow {
    id: i32,
    entity_type: String,
    label: String,
    description: String,
    status: String,
    source_kind: String,
    source_label: String,
    priority: i32,
    created_at: chrono::DateTime<chrono::Utc>,
    updated_at: chrono::DateTime<chrono::Utc>,
    entity_id: Option<i32>,
    evidence_at: Option<chrono::DateTime<chrono::Utc>>,
}

/// 项目蓝图全量读取：节点（含证据覆盖）、边、解析记录与总体完成度。
/// 覆盖判定：蓝图节点与实证图谱 kg_entities 按 (类型, 规范名) 精确匹配。
pub async fn project_blueprint(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<KnowledgeBlueprintRead, ApiError> {
    let rows: Vec<BlueprintNodeEvidenceRow> = sqlx::query_as(
        r#"
        SELECT n.id, n.entity_type, n.label, n.description, n.status, n.source_kind,
               n.source_label, n.priority, n.created_at, n.updated_at,
               e.id AS entity_id, e.updated_at AS evidence_at
        FROM public.kg_blueprint_nodes n
        LEFT JOIN public.kg_entities e
            ON e.project_id = n.project_id AND e.entity_type = n.entity_type
           AND e.normalized_label = n.normalized_label
        WHERE n.project_id = $1 AND n.status <> 'retired'
        ORDER BY n.id
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut **transaction)
    .await?;

    let mut nodes: Vec<BlueprintNodeRead> = Vec::new();
    let mut seen_evidence: std::collections::HashMap<
        i32,
        (Vec<i32>, Option<chrono::DateTime<chrono::Utc>>),
    > = std::collections::HashMap::new();
    for row in rows {
        let entry = seen_evidence
            .entry(row.id)
            .or_insert_with(|| (Vec::new(), None));
        if let Some(entity_id) = row.entity_id {
            if !entry.0.contains(&entity_id) {
                entry.0.push(entity_id);
            }
            if let Some(at) = row.evidence_at {
                entry.1 = Some(match entry.1 {
                    Some(current) if current >= at => current,
                    _ => at,
                });
            }
        }
        nodes.push(BlueprintNodeRead {
            id: row.id,
            entity_type: row.entity_type,
            label: row.label,
            description: row.description,
            status: row.status,
            source_kind: row.source_kind,
            source_label: row.source_label,
            priority: row.priority,
            created_at: row.created_at,
            updated_at: row.updated_at,
            evidence: BlueprintEvidence {
                entity_ids: Vec::new(),
                entity_count: 0,
                last_evidence_at: None,
            },
        });
    }
    let total_nodes = nodes.len() as i64;
    for node in &mut nodes {
        if let Some((entity_ids, last_evidence_at)) = seen_evidence.get(&node.id) {
            node.evidence = BlueprintEvidence {
                entity_count: entity_ids.len() as i64,
                entity_ids: entity_ids.clone(),
                last_evidence_at: *last_evidence_at,
            };
        }
    }

    let edges: Vec<BlueprintEdgeRead> = sqlx::query_as(
        r#"
        SELECT e.id, e.source_node_id, e.target_node_id, e.relation_type, e.status, e.priority
        FROM public.kg_blueprint_edges e
        JOIN public.kg_blueprint_nodes s ON s.id = e.source_node_id AND s.status <> 'retired'
        JOIN public.kg_blueprint_nodes t ON t.id = e.target_node_id AND t.status <> 'retired'
        WHERE e.project_id = $1 AND e.status <> 'retired'
        ORDER BY e.id
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut **transaction)
    .await?;

    let documents: Vec<BlueprintDocumentRead> = sqlx::query_as(
        r#"
        SELECT id, title, source_kind, parse_mode, node_count, edge_count, message, created_at
        FROM public.kg_blueprint_documents
        WHERE project_id = $1
        ORDER BY id DESC LIMIT 20
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut **transaction)
    .await?;

    let covered_nodes = nodes
        .iter()
        .filter(|node| node.evidence.entity_count > 0)
        .count() as i64;
    let completion = if total_nodes > 0 {
        (covered_nodes as f64 / total_nodes as f64 * 1000.0).round() / 1000.0
    } else {
        0.0
    };

    Ok(KnowledgeBlueprintRead {
        project_id,
        coverage: BlueprintCoverage {
            total_nodes,
            covered_nodes,
            completion,
        },
        nodes,
        edges,
        documents,
    })
}

/// 导师/负责人手动修正：节点状态（planned/retired）与描述。标签与类型不可变，保证可审计。
pub async fn patch_blueprint_node(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    node_id: i32,
    status: Option<&str>,
    description: Option<&str>,
) -> Result<(), ApiError> {
    let existing: Option<(String, String, String)> = sqlx::query_as(
        "SELECT status, entity_type, normalized_label FROM public.kg_blueprint_nodes WHERE id = $1 AND project_id = $2",
    )
    .bind(node_id)
    .bind(project_id)
    .fetch_optional(&mut **transaction)
    .await?;
    let (current_status, entity_type, normalized_label) = existing
        .ok_or_else(|| ApiError::new(axum::http::StatusCode::NOT_FOUND, "蓝图节点不存在"))?;
    let next_status = status.unwrap_or(&current_status);
    if next_status != "planned" && next_status != "retired" {
        return Err(ApiError::new(
            axum::http::StatusCode::BAD_REQUEST,
            "status 只能是 planned 或 retired",
        ));
    }
    if next_status == "planned" && current_status == "retired" {
        let conflict: Option<i32> = sqlx::query_scalar(
            r#"
            SELECT id FROM public.kg_blueprint_nodes
            WHERE project_id = $1 AND entity_type = $2 AND normalized_label = $3 AND status <> 'retired' AND id <> $4
            "#,
        )
        .bind(project_id)
        .bind(&entity_type)
        .bind(&normalized_label)
        .bind(node_id)
        .fetch_optional(&mut **transaction)
        .await?;
        if conflict.is_some() {
            return Err(ApiError::new(
                axum::http::StatusCode::CONFLICT,
                "同型同名蓝图节点已存在，无法恢复该节点",
            ));
        }
    }
    sqlx::query(
        r#"
        UPDATE public.kg_blueprint_nodes
        SET status = $3,
            description = CASE WHEN $4::text IS NULL THEN description ELSE $4 END,
            updated_at = now()
        WHERE id = $1 AND project_id = $2
        "#,
    )
    .bind(node_id)
    .bind(project_id)
    .bind(next_status)
    .bind(description)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

/// 导师/负责人手动作废/恢复一条蓝图关系。
pub async fn patch_blueprint_edge(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    edge_id: i32,
    status: Option<&str>,
) -> Result<(), ApiError> {
    let next_status = status
        .ok_or_else(|| ApiError::new(axum::http::StatusCode::BAD_REQUEST, "需要提供 status"))?
        .to_owned();
    if next_status != "planned" && next_status != "retired" {
        return Err(ApiError::new(
            axum::http::StatusCode::BAD_REQUEST,
            "status 只能是 planned 或 retired",
        ));
    }
    let result = sqlx::query(
        "UPDATE public.kg_blueprint_edges SET status = $3 WHERE id = $1 AND project_id = $2",
    )
    .bind(edge_id)
    .bind(project_id)
    .bind(&next_status)
    .execute(&mut **transaction)
    .await?;
    if result.rows_affected() == 0 {
        return Err(ApiError::new(
            axum::http::StatusCode::NOT_FOUND,
            "蓝图关系不存在",
        ));
    }
    Ok(())
}
