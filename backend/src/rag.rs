use std::{
    collections::{HashMap, HashSet},
    time::Duration,
};

use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{FromRow, PgPool, Postgres, Transaction};

use crate::{
    error::ApiError,
    models::{RagCitationAuditRead, RagGraphContextRead, RagSourceRead},
    ocr::{extract_text, OcrSource},
    AppState,
};

#[derive(Clone, Debug, FromRow)]
pub struct RagFileRecord {
    pub id: i32,
    pub project_id: i32,
    pub original_filename: String,
    pub storage_path: String,
    pub file_hash: String,
    pub file_category: String,
    pub status: String,
    pub knowledge_sync_status: String,
}

#[derive(Debug, FromRow)]
struct ChunkRow {
    id: i32,
    file_id: i32,
    filename: String,
    content: String,
}

#[derive(Debug, FromRow)]
struct VectorCandidateRow {
    id: i32,
    vector_score: f64,
}

const ACTIVE_CHUNKS_SQL: &str = r#"
    SELECT c.id, c.file_id, f.original_filename AS filename, c.content
    FROM rag_document_chunks c
    JOIN files f ON f.id = c.file_id
    WHERE c.project_id = $1
      AND f.status = 'APPROVED'::filestatus
      AND f.file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
      AND f.knowledge_sync_status = 'synced'
    ORDER BY c.id
"#;

const VECTOR_CANDIDATE_SQL: &str = r#"
    SELECT c.id,
           GREATEST(0.0, 1.0 - (c.embedding <=> $2::vector)) AS vector_score
    FROM rag_document_chunks c
    JOIN files f ON f.id = c.file_id
    WHERE c.project_id = $1
      AND f.status = 'APPROVED'::filestatus
      AND f.file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
      AND f.knowledge_sync_status = 'synced'
    ORDER BY c.embedding <=> $2::vector
    LIMIT $3
"#;

const VECTOR_SCORES_SQL: &str = r#"
    SELECT c.id,
           GREATEST(0.0, 1.0 - (c.embedding <=> $2::vector)) AS vector_score
    FROM rag_document_chunks c
    WHERE c.project_id = $1 AND c.id = ANY($3)
"#;

#[derive(Debug, FromRow)]
struct GraphRow {
    relation_id: i32,
    relation_type: String,
    source_entity_id: i32,
    source_label: String,
    source_entity_type: String,
    target_entity_id: i32,
    target_label: String,
    target_entity_type: String,
    confidence: f64,
    properties: Value,
}

#[derive(Clone, Debug)]
pub struct GenerationResult {
    pub answer: String,
    pub request_id: Option<String>,
    pub model: String,
    pub usage: Value,
}

#[derive(Debug)]
pub enum GenerationError {
    Configuration(String),
    Request(String),
}

pub async fn fetch_rag_file(pool: &PgPool, file_id: i32) -> Result<RagFileRecord, ApiError> {
    sqlx::query_as(
        r#"
        SELECT id, project_id, original_filename, storage_path, file_hash,
               lower(file_category::text) AS file_category,
               lower(status::text) AS status, knowledge_sync_status
        FROM files WHERE id = $1
        "#,
    )
    .bind(file_id)
    .fetch_optional(pool)
    .await?
    .ok_or_else(|| ApiError::new(axum::http::StatusCode::NOT_FOUND, "File not found"))
}

pub async fn index_file(
    transaction: &mut Transaction<'_, Postgres>,
    state: &AppState,
    file: &RagFileRecord,
) -> Result<i32, String> {
    let settings = &state.settings;
    let extension = std::path::Path::new(&file.storage_path)
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_lowercase();
    let text = if matches!(
        extension.as_str(),
        "png" | "jpg" | "jpeg" | "gif" | "bmp" | "tif" | "tiff" | "webp"
    ) {
        let result: Option<(String, String)> = sqlx::query_as(
            r#"
            SELECT corrected_text, file_hash FROM file_ocr_results
            WHERE file_id = $1 AND review_status = 'confirmed'
            ORDER BY id DESC LIMIT 1
            "#,
        )
        .bind(file.id)
        .fetch_optional(&mut **transaction)
        .await
        .map_err(|error| error.to_string())?;
        let Some((text, hash)) = result else {
            return Err("Image OCR must be reviewed and confirmed before indexing".to_owned());
        };
        if hash != file.file_hash {
            return Err("Confirmed OCR does not match the current file".to_owned());
        }
        text
    } else {
        extract_text(
            settings,
            &OcrSource {
                file_id: file.id,
                original_filename: file.original_filename.clone(),
                storage_path: file.storage_path.clone(),
            },
        )
        .await
        .map_err(|error| error.to_string())?
        .text
    };
    let chunks = chunk_text(&text, settings.rag_chunk_size, settings.rag_chunk_overlap);
    if chunks.is_empty() {
        return Err("No extractable text was found in the document".to_owned());
    }
    let embeddings = state
        .embeddings
        .embed(&chunks)
        .await
        .map_err(|error| error.to_string())?;
    sqlx::query("DELETE FROM rag_document_chunks WHERE file_id = $1")
        .bind(file.id)
        .execute(&mut **transaction)
        .await
        .map_err(|error| error.to_string())?;
    for (index, (content, embedding)) in chunks.iter().zip(embeddings).enumerate() {
        let embedding = vector_literal(&embedding);
        let content_hash = format!("{:x}", Sha256::digest(content.as_bytes()));
        sqlx::query(
            r#"
            INSERT INTO rag_document_chunks (
                project_id, file_id, chunk_index, content, content_hash,
                character_count, embedding, metadata_json, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8, now())
            "#,
        )
        .bind(file.project_id)
        .bind(file.id)
        .bind(index as i32)
        .bind(content)
        .bind(content_hash)
        .bind(content.chars().count() as i32)
        .bind(embedding)
        .bind(json!({"filename": file.original_filename}))
        .execute(&mut **transaction)
        .await
        .map_err(|error| error.to_string())?;
    }
    Ok(chunks.len() as i32)
}

pub async fn retrieve(
    state: &AppState,
    project_id: i32,
    query: &str,
    bm25_only: bool,
) -> Result<Vec<RagSourceRead>, ApiError> {
    let pool = &state.pool;
    let settings = &state.settings;
    let rows = sqlx::query_as::<_, ChunkRow>(ACTIVE_CHUNKS_SQL)
        .bind(project_id)
        .fetch_all(pool)
        .await?;
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let query_tokens = tokens(query);
    let lexical_scores = rows
        .iter()
        .map(|row| {
            let document_tokens = tokens(&row.content);
            let matched = query_tokens.intersection(&document_tokens).count();
            let lexical_score = if query_tokens.is_empty() {
                0.0
            } else {
                matched as f64 / query_tokens.len() as f64
            };
            (row.id, lexical_score)
        })
        .collect::<HashMap<_, _>>();

    let (candidate_ids, vector_scores) = if bm25_only {
        (
            rows.iter().map(|row| row.id).collect::<Vec<_>>(),
            HashMap::new(),
        )
    } else {
        let query_embedding = state
            .embeddings
            .embed(&[query.to_owned()])
            .await
            .map_err(ApiError::internal)?
            .into_iter()
            .next()
            .ok_or_else(|| ApiError::internal("Embedding returned no query vector"))?;
        let query_vector = vector_literal(&query_embedding);
        let vector_candidates = fetch_vector_candidates(
            pool,
            project_id,
            &query_vector,
            settings.rag_vector_candidate_k,
        )
        .await?;
        let mut vector_scores = vector_candidates
            .iter()
            .map(|candidate| (candidate.id, candidate.vector_score))
            .collect::<HashMap<_, _>>();
        let mut candidate_ids = vector_candidates
            .into_iter()
            .map(|candidate| candidate.id)
            .collect::<Vec<_>>();
        let mut seen = candidate_ids.iter().copied().collect::<HashSet<_>>();

        let mut lexical_candidates = lexical_scores
            .iter()
            .filter(|(_, score)| **score > 0.0)
            .map(|(id, score)| (*id, *score))
            .collect::<Vec<_>>();
        lexical_candidates.sort_by(|left, right| {
            right
                .1
                .partial_cmp(&left.1)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| left.0.cmp(&right.0))
        });
        lexical_candidates.truncate(settings.rag_vector_candidate_k);
        for (id, _) in lexical_candidates {
            if seen.insert(id) {
                candidate_ids.push(id);
            }
        }

        let missing_vector_scores = candidate_ids
            .iter()
            .copied()
            .filter(|id| !vector_scores.contains_key(id))
            .collect::<Vec<_>>();
        if !missing_vector_scores.is_empty() {
            for candidate in
                fetch_vector_scores(pool, project_id, &query_vector, &missing_vector_scores).await?
            {
                vector_scores.insert(candidate.id, candidate.vector_score);
            }
        }
        (candidate_ids, vector_scores)
    };

    let rows_by_id = rows
        .into_iter()
        .map(|row| (row.id, row))
        .collect::<HashMap<_, _>>();
    let mut scored = Vec::new();
    for chunk_id in candidate_ids {
        let Some(row) = rows_by_id.get(&chunk_id) else {
            continue;
        };
        let vector_score = if bm25_only {
            0.0
        } else {
            vector_scores.get(&row.id).copied().unwrap_or_default()
        };
        let lexical_score = lexical_scores.get(&row.id).copied().unwrap_or_default();
        let retrieval_score = if bm25_only {
            lexical_score
        } else {
            0.7 * vector_score + 0.3 * lexical_score
        };
        scored.push((
            retrieval_score,
            RagSourceRead {
                chunk_id: Some(row.id),
                file_id: Some(row.file_id),
                filename: Some(row.filename.clone()),
                dify_document_id: None,
                snippet: Some(row.content.clone()),
                vector_score: Some(round6(vector_score)),
                lexical_score: Some(round6(lexical_score)),
                retrieval_score: Some(round6(retrieval_score)),
            },
        ));
    }
    scored.sort_by(|left, right| {
        right
            .0
            .partial_cmp(&left.0)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    let collection = [
        "哪些", "全部", "所有", "列出", "多少", "分别", "完整", "all", "list",
    ]
    .iter()
    .any(|keyword| query.to_lowercase().contains(keyword));
    let limit = if collection {
        settings
            .rag_collection_retrieval_top_k
            .max(settings.rag_retrieval_top_k)
            .min(settings.rag_vector_candidate_k)
    } else {
        settings.rag_retrieval_top_k
    };
    Ok(scored
        .into_iter()
        .filter(|(score, _)| *score > 0.0 || query_tokens.is_empty())
        .map(|(_, source)| source)
        .take(limit)
        .collect())
}

async fn fetch_vector_candidates(
    pool: &PgPool,
    project_id: i32,
    query_vector: &str,
    candidate_k: usize,
) -> Result<Vec<VectorCandidateRow>, sqlx::Error> {
    sqlx::query_as(VECTOR_CANDIDATE_SQL)
        .bind(project_id)
        .bind(query_vector)
        .bind(i64::try_from(candidate_k).unwrap_or(i64::MAX))
        .fetch_all(pool)
        .await
}

async fn fetch_vector_scores(
    pool: &PgPool,
    project_id: i32,
    query_vector: &str,
    chunk_ids: &[i32],
) -> Result<Vec<VectorCandidateRow>, sqlx::Error> {
    sqlx::query_as(VECTOR_SCORES_SQL)
        .bind(project_id)
        .bind(query_vector)
        .bind(chunk_ids)
        .fetch_all(pool)
        .await
}

pub async fn relevant_graph_context(
    pool: &PgPool,
    project_id: i32,
    query: &str,
    limit: usize,
) -> Result<Vec<RagGraphContextRead>, ApiError> {
    let rows = sqlx::query_as::<_, GraphRow>(
        r#"
        SELECT r.id AS relation_id, r.relation_type,
               s.id AS source_entity_id, s.label AS source_label,
               s.entity_type AS source_entity_type,
               t.id AS target_entity_id, t.label AS target_label,
               t.entity_type AS target_entity_type,
               r.confidence, r.properties
        FROM kg_relations r
        JOIN kg_entities s ON s.id = r.source_entity_id
        JOIN kg_entities t ON t.id = r.target_entity_id
        WHERE r.project_id = $1
          AND (
              r.source_type NOT IN ('note', 'note_extraction')
              OR r.source_type IS NULL
              OR r.source_id IN (
                  SELECT id FROM experiment_notes
                  WHERE project_id = $1 AND status = 'APPROVED'::notestatus
              )
          )
        ORDER BY r.id
        "#,
    )
    .bind(project_id)
    .fetch_all(pool)
    .await?;
    let normalized_query = query.to_lowercase();
    let query_tokens = tokens(query);
    let hints = relation_hints(&normalized_query);
    let mut scored = Vec::new();
    for row in rows {
        if !hints.is_empty() && !hints.contains(row.relation_type.as_str()) {
            continue;
        }
        let haystack = format!(
            "{} {} {} {} {}",
            row.source_label,
            row.target_label,
            row.source_entity_type,
            row.target_entity_type,
            row.relation_type
        )
        .to_lowercase();
        let overlap = query_tokens
            .iter()
            .filter(|token| haystack.contains(token.as_str()))
            .count() as f64;
        let role_bonus = row
            .properties
            .get("roles")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .filter(|role| normalized_query.contains(*role))
            .count() as f64;
        let score = overlap
            + role_bonus * 2.0
            + if hints.contains(row.relation_type.as_str()) {
                3.0
            } else {
                0.0
            };
        if score <= 0.0 {
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
                source_entity_type_label: entity_type_label(&row.source_entity_type).to_owned(),
                source_entity_type: row.source_entity_type,
                target_entity_id: row.target_entity_id,
                target_label: row.target_label,
                target_entity_type_label: entity_type_label(&row.target_entity_type).to_owned(),
                target_entity_type: row.target_entity_type,
                confidence: row.confidence,
                retrieval_score: round6(score),
            },
        ));
    }
    scored.sort_by(|left, right| {
        right
            .0
            .partial_cmp(&left.0)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    Ok(scored
        .into_iter()
        .map(|(_, context)| context)
        .take(limit)
        .collect())
}

pub fn format_sources(sources: &[RagSourceRead]) -> String {
    let mut output = String::from("项目资料检索结果：");
    for (index, source) in sources.iter().enumerate() {
        output.push_str(&format!(
            "\n\n[S{}] 文件={}; 块={}; 相关度={:.3}\n{}",
            index + 1,
            source.filename.as_deref().unwrap_or("未知"),
            source.chunk_id.unwrap_or_default(),
            source.retrieval_score.unwrap_or_default(),
            source.snippet.as_deref().unwrap_or_default()
        ));
    }
    output.chars().take(9000).collect()
}

pub fn format_graph_context(context: &[RagGraphContextRead]) -> String {
    if context.is_empty() {
        return String::new();
    }
    let mut output = String::from("实验知识图谱上下文：");
    for (index, item) in context.iter().enumerate() {
        output.push_str(&format!(
            "\n[G{}] {}（{}） {} {}（{}）",
            index + 1,
            item.source_label,
            item.source_entity_type_label,
            item.relation_label,
            item.target_label,
            item.target_entity_type_label
        ));
    }
    output
}

pub async fn generate(
    state: &AppState,
    system_prompt: &str,
    user_prompt: &str,
    temperature: f64,
) -> Result<GenerationResult, GenerationError> {
    let api_key = state.settings.deepseek_api_key.trim();
    if api_key.is_empty() {
        return Err(GenerationError::Configuration(
            "DEEPSEEK_API_KEY is not configured".to_owned(),
        ));
    }
    let model = state.settings.normalized_deepseek_model();
    if model.is_empty() {
        return Err(GenerationError::Configuration(
            "DEEPSEEK_MODEL is not configured".to_owned(),
        ));
    }
    let _generation_permit = state.generation_limiter.acquire().await.map_err(|_| {
        GenerationError::Configuration("Generation concurrency limiter is unavailable".to_owned())
    })?;
    let url = format!(
        "{}/chat/completions",
        state.settings.deepseek_api_base_url.trim_end_matches('/')
    );
    let payload = json!({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": 1800,
        "stream": false,
        "thinking": {"type": "disabled"}
    });
    let mut last_error = String::new();
    for attempt in 0..3 {
        let response = state
            .client
            .post(&url)
            .bearer_auth(api_key)
            .timeout(Duration::from_secs(180))
            .json(&payload)
            .send()
            .await;
        match response {
            Ok(response) if response.status().is_success() => {
                let request_id = response
                    .headers()
                    .get("x-request-id")
                    .and_then(|value| value.to_str().ok())
                    .map(str::to_owned);
                let body: Value = response.json().await.map_err(|error| {
                    GenerationError::Request(format!("DeepSeek returned invalid JSON: {error}"))
                })?;
                let answer = body["choices"][0]["message"]["content"]
                    .as_str()
                    .unwrap_or_default()
                    .trim()
                    .to_owned();
                if answer.is_empty() {
                    return Err(GenerationError::Request(
                        "DeepSeek returned an empty completion".to_owned(),
                    ));
                }
                return Ok(GenerationResult {
                    answer,
                    request_id: request_id.or_else(|| body["id"].as_str().map(str::to_owned)),
                    model: body["model"].as_str().unwrap_or(model).to_owned(),
                    usage: body.get("usage").cloned().unwrap_or_else(|| json!({})),
                });
            }
            Ok(response) => {
                let status = response.status();
                let detail = response.text().await.unwrap_or_default();
                last_error = format!(
                    "DeepSeek request failed: {status} {}",
                    truncate_error_detail(&detail, 1000)
                );
                if status.as_u16() < 500 && status.as_u16() != 429 {
                    break;
                }
            }
            Err(error) => last_error = format!("DeepSeek request failed: {error}"),
        }
        if attempt < 2 {
            tokio::time::sleep(Duration::from_secs(1 << attempt)).await;
        }
    }
    Err(GenerationError::Request(last_error))
}

fn truncate_error_detail(detail: &str, max_bytes: usize) -> &str {
    let mut end = detail.len().min(max_bytes);
    while !detail.is_char_boundary(end) {
        end -= 1;
    }
    &detail[..end]
}

pub fn audit_citations(
    answer: &str,
    source_count: usize,
    graph_count: usize,
) -> RagCitationAuditRead {
    let regex = Regex::new(r"(?i)\[([SG])(\d+)\]").unwrap();
    let citations: Vec<(String, usize)> = regex
        .captures_iter(answer)
        .filter_map(|capture| Some((capture[1].to_uppercase(), capture[2].parse::<usize>().ok()?)))
        .collect();
    let invalid_citations: Vec<String> = citations
        .iter()
        .filter_map(|(kind, index)| {
            let limit = if kind == "S" {
                source_count
            } else {
                graph_count
            };
            (*index < 1 || *index > limit).then(|| format!("[{kind}{index}]"))
        })
        .collect();
    let has_evidence = source_count > 0 || graph_count > 0;
    let passed = invalid_citations.is_empty() && (!citations.is_empty() || !has_evidence);
    let message = if !invalid_citations.is_empty() {
        format!(
            "发现 {} 个不存在的证据编号：{}。",
            invalid_citations.len(),
            invalid_citations.join("、")
        )
    } else if has_evidence && citations.is_empty() {
        "回答没有引用任何已检索证据，需要人工复核。".to_owned()
    } else if !citations.is_empty() {
        format!("引用校验通过，共核对 {} 个证据编号。", citations.len())
    } else {
        "该回答没有可引用的项目证据。".to_owned()
    };
    RagCitationAuditRead {
        passed,
        citation_count: citations.len(),
        invalid_citations,
        has_evidence,
        message,
    }
}

fn chunk_text(text: &str, chunk_size: usize, overlap: usize) -> Vec<String> {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    let chars: Vec<char> = normalized.trim().chars().collect();
    if chars.is_empty() {
        return Vec::new();
    }
    let size = chunk_size.max(200);
    let overlap = overlap.min(size / 2);
    let mut chunks = Vec::new();
    let mut start = 0;
    while start < chars.len() {
        let end = (start + size).min(chars.len());
        let chunk: String = chars[start..end]
            .iter()
            .collect::<String>()
            .trim()
            .to_owned();
        if !chunk.is_empty() {
            chunks.push(chunk);
        }
        if end == chars.len() {
            break;
        }
        start = end.saturating_sub(overlap);
    }
    chunks
}

fn tokens(text: &str) -> HashSet<String> {
    let mut output = HashSet::new();
    let regex = Regex::new(r"(?i)[a-z0-9_µ><=./-]+|[\p{Han}]+").unwrap();
    for matched in regex.find_iter(text) {
        let token = matched.as_str().to_lowercase();
        output.insert(token.clone());
        if token
            .chars()
            .all(|character| ('\u{4e00}'..='\u{9fff}').contains(&character))
        {
            let chars: Vec<char> = token.chars().collect();
            for window in chars.windows(2) {
                output.insert(window.iter().collect());
            }
        }
    }
    output
}

fn vector_literal(vector: &[f32]) -> String {
    format!(
        "[{}]",
        vector
            .iter()
            .map(|value| format!("{value:.9}"))
            .collect::<Vec<_>>()
            .join(",")
    )
}

fn round6(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

fn relation_hints(query: &str) -> HashSet<&'static str> {
    let mut hints = HashSet::new();
    for (relation, words) in [
        ("has_note", &["笔记", "记录", "note"] as &[&str]),
        ("uses_reagent", &["试剂", "材料", "reagent", "use"]),
        ("uses_instrument", &["仪器", "设备", "instrument"]),
        ("uses_sample", &["样本", "样品", "sample"]),
        ("produces_result", &["结果", "结论", "result", "count"]),
        ("has_attachment", &["附件", "文件", "file"]),
        ("created_by", &["谁", "创建", "creator"]),
        ("has_experiment_type", &["实验类型", "type"]),
        ("has_biological_source", &["细胞", "来源", "cell"]),
        ("has_condition", &["条件", "处理", "对照", "condition"]),
        ("uses_software", &["软件", "比对", "software"]),
        ("has_identifier", &["登录号", "标识", "accession"]),
    ] {
        if words.iter().any(|word| query.contains(word)) {
            hints.insert(relation);
        }
    }
    hints
}

fn relation_label(value: &str) -> &str {
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

fn entity_type_label(value: &str) -> &str {
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

pub fn merge_usage(values: &[Value]) -> Value {
    let mut output: HashMap<String, Value> = HashMap::new();
    for value in values {
        if let Some(fields) = value.as_object() {
            for (key, value) in fields {
                if let Some(number) = value.as_i64() {
                    let total = output.get(key).and_then(Value::as_i64).unwrap_or(0) + number;
                    output.insert(key.clone(), json!(total));
                } else {
                    output.entry(key.clone()).or_insert_with(|| value.clone());
                }
            }
        }
    }
    json!(output)
}

#[cfg(test)]
mod tests {
    use std::{
        collections::HashMap,
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        },
        time::Duration,
    };

    use axum::{extract::State, routing::post, Json, Router};
    use serde_json::{json, Value};
    use sqlx::postgres::PgPoolOptions;
    use uuid::Uuid;

    use super::{
        audit_citations, chunk_text, fetch_vector_candidates, generate, retrieve,
        truncate_error_detail, vector_literal, ACTIVE_CHUNKS_SQL, VECTOR_CANDIDATE_SQL,
    };
    use crate::{
        config::Settings,
        db::{connect_database, initialize_database},
        embedding::hash_embedding,
        AppState,
    };

    #[derive(Clone, Default)]
    struct ConcurrencyProbe {
        active: Arc<AtomicUsize>,
        maximum: Arc<AtomicUsize>,
    }

    #[test]
    fn test_chunk_embedding_and_citation_contract() {
        let chunks = chunk_text(&"a".repeat(500), 200, 20);
        assert_eq!(chunks.len(), 3);
        assert_eq!(hash_embedding("PCR Taq", 512).len(), 512);
        let audit = audit_citations("Result [S1], bad [G2]", 1, 1);
        assert!(!audit.passed);
        assert_eq!(audit.invalid_citations, ["[G2]"]);
    }

    #[test]
    fn test_truncate_error_detail_preserves_utf8_boundaries() {
        let detail = format!("{}中", "a".repeat(999));

        assert_eq!(truncate_error_detail(&detail, 1000), "a".repeat(999));
    }

    #[test]
    fn test_vector_candidate_sql_is_hnsw_bounded_without_returning_embeddings() {
        let active_sql = ACTIVE_CHUNKS_SQL
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");
        let vector_sql = VECTOR_CANDIDATE_SQL
            .split_whitespace()
            .collect::<Vec<_>>()
            .join(" ");

        assert!(!active_sql.contains("embedding"));
        assert!(vector_sql.contains("ORDER BY c.embedding <=> $2::vector"));
        assert!(vector_sql.contains("LIMIT $3"));
        assert!(!vector_sql.contains("embedding::text"));
    }

    #[tokio::test]
    async fn test_hybrid_retrieval_uses_hnsw_candidates_and_rescues_lexical_match() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let username = format!("rag_candidates_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), username.clone()),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustCandidates123!".to_owned(),
            ),
            ("EMBEDDING_BACKEND".to_owned(), "hash".to_owned()),
            ("RAG_VECTOR_CANDIDATE_K".to_owned(), "1".to_owned()),
            ("RAG_RETRIEVAL_TOP_K".to_owned(), "2".to_owned()),
            ("RAG_COLLECTION_RETRIEVAL_TOP_K".to_owned(), "2".to_owned()),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let state = AppState::new(pool.clone(), settings).unwrap();
        let user_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username = $1")
            .bind(&username)
            .fetch_one(&pool)
            .await
            .unwrap();
        let project_id: i32 = sqlx::query_scalar(
            r#"
            INSERT INTO projects (
                name, description, is_sensitive, status, approval_enabled, owner_user_id
            ) VALUES ($1, NULL, false, 'ACTIVE'::projectstatus, false, $2)
            RETURNING id
            "#,
        )
        .bind(format!("RAG candidate project {suffix}"))
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();

        let mut file_ids = Vec::new();
        for index in 1..=3 {
            let file_id: i32 = sqlx::query_scalar(
                r#"
                INSERT INTO files (
                    project_id, uploaded_by, file_category, original_filename,
                    storage_path, file_size, file_hash, status, knowledge_sync_status
                ) VALUES (
                    $1, $2, 'KNOWLEDGE_DOCUMENT'::filecategory, $3, $4, 1, $5,
                    'APPROVED'::filestatus, 'synced'
                )
                RETURNING id
                "#,
            )
            .bind(project_id)
            .bind(user_id)
            .bind(format!("candidate-{suffix}-{index}.txt"))
            .bind(format!("/tmp/candidate-{suffix}-{index}.txt"))
            .bind(format!("candidate-{suffix}-{index}"))
            .fetch_one(&pool)
            .await
            .unwrap();
            file_ids.push(file_id);
        }

        let query_embedding = hash_embedding("raremarker", 512);
        let mut orthogonal_embedding = vec![0.0_f32; 512];
        let orthogonal_index = query_embedding
            .iter()
            .position(|value| value.abs() < f32::EPSILON)
            .unwrap();
        orthogonal_embedding[orthogonal_index] = 1.0;
        let contents = [
            "unrelated vector-nearest content",
            "raremarker exact lexical evidence",
            "another unrelated document",
        ];
        let embeddings = [
            vector_literal(&query_embedding),
            vector_literal(&orthogonal_embedding),
            vector_literal(&orthogonal_embedding),
        ];
        let mut chunk_ids = Vec::new();
        for index in 0..3 {
            let chunk_id: i32 = sqlx::query_scalar(
                r#"
                INSERT INTO rag_document_chunks (
                    project_id, file_id, chunk_index, content, content_hash,
                    character_count, embedding, metadata_json
                ) VALUES ($1, $2, 0, $3, $4, $5, $6::vector, '{}'::json)
                RETURNING id
                "#,
            )
            .bind(project_id)
            .bind(file_ids[index])
            .bind(contents[index])
            .bind(format!("candidate-chunk-{suffix}-{index}"))
            .bind(contents[index].chars().count() as i32)
            .bind(&embeddings[index])
            .fetch_one(&pool)
            .await
            .unwrap();
            chunk_ids.push(chunk_id);
        }

        let vector_candidates =
            fetch_vector_candidates(&pool, project_id, &vector_literal(&query_embedding), 1)
                .await
                .unwrap();
        assert_eq!(vector_candidates.len(), 1);
        assert_eq!(vector_candidates[0].id, chunk_ids[0]);

        let mut explain = pool.begin().await.unwrap();
        sqlx::raw_sql(
            "SET LOCAL enable_seqscan = off; SET LOCAL enable_bitmapscan = off; SET LOCAL enable_sort = off",
        )
        .execute(&mut *explain)
        .await
        .unwrap();
        let plan: Value =
            sqlx::query_scalar(&format!("EXPLAIN (FORMAT JSON) {VECTOR_CANDIDATE_SQL}"))
                .bind(project_id)
                .bind(vector_literal(&query_embedding))
                .bind(1_i64)
                .fetch_one(&mut *explain)
                .await
                .unwrap();
        explain.rollback().await.unwrap();
        assert!(plan.to_string().contains("ix_rag_chunks_embedding_hnsw"));

        let results = retrieve(&state, project_id, "raremarker", false)
            .await
            .unwrap();
        assert_eq!(results.len(), 2);
        assert!(results
            .iter()
            .any(|source| source.file_id == Some(file_ids[0])));
        assert!(results
            .iter()
            .any(|source| source.file_id == Some(file_ids[1])));
    }

    #[tokio::test]
    async fn test_generation_honors_provider_concurrency_limit() {
        async fn completion(State(probe): State<ConcurrencyProbe>) -> Json<Value> {
            let active = probe.active.fetch_add(1, Ordering::SeqCst) + 1;
            probe.maximum.fetch_max(active, Ordering::SeqCst);
            tokio::time::sleep(Duration::from_millis(40)).await;
            probe.active.fetch_sub(1, Ordering::SeqCst);
            Json(json!({
                "id": "concurrency-probe",
                "model": "deepseek-test",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 1}
            }))
        }

        let probe = ConcurrencyProbe::default();
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server_probe = probe.clone();
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new()
                    .route("/chat/completions", post(completion))
                    .with_state(server_probe),
            )
            .await
            .unwrap();
        });
        let settings = Settings::from_map(&HashMap::from([
            (
                "DEEPSEEK_API_BASE_URL".to_owned(),
                format!("http://{address}"),
            ),
            ("DEEPSEEK_API_KEY".to_owned(), "test-key".to_owned()),
            ("DEEPSEEK_MODEL".to_owned(), "deepseek-test".to_owned()),
            ("DEEPSEEK_MAX_CONCURRENCY".to_owned(), "2".to_owned()),
        ]))
        .unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();
        let state = AppState::new(pool, settings).unwrap();
        let mut tasks = tokio::task::JoinSet::new();
        for _ in 0..6 {
            let state = state.clone();
            tasks.spawn(async move { generate(&state, "system", "user", 0.0).await });
        }
        while let Some(result) = tasks.join_next().await {
            result.unwrap().unwrap();
        }

        assert!(probe.maximum.load(Ordering::SeqCst) <= 2);
    }
}
