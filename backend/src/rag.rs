use std::{
    collections::{HashMap, HashSet},
    sync::OnceLock,
    time::Duration,
};

use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{FromRow, PgPool, Postgres, QueryBuilder, Transaction};

use crate::{
    error::ApiError,
    models::{RagCitationAuditRead, RagGraphContextRead, RagSourceRead},
    ocr::{extract_text, OcrSource},
    AppState,
};

const MAX_GRAPH_CONTEXT_CHARS: usize = 6_000;
const RAG_INSERT_BATCH_SIZE: usize = 64;

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
    ORDER BY c.embedding <=> $2::vector, c.id
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
    if embeddings.len() != chunks.len() {
        return Err(format!(
            "Embedding backend returned {} vectors for {} chunks; expected {} dimensions",
            embeddings.len(),
            chunks.len(),
            settings.embedding_dimension
        ));
    }
    for embedding in &embeddings {
        validate_embedding_dimensions(embedding, settings.embedding_dimension)?;
    }
    sqlx::query("DELETE FROM rag_document_chunks WHERE file_id = $1")
        .bind(file.id)
        .execute(&mut **transaction)
        .await
        .map_err(|error| error.to_string())?;
    let metadata = json!({"filename": file.original_filename});
    for range in rag_insert_batch_ranges(chunks.len()) {
        let mut query = QueryBuilder::<Postgres>::new(
            "INSERT INTO rag_document_chunks (\
                project_id, file_id, chunk_index, content, content_hash,\
                character_count, embedding, metadata_json, created_at\
            ) ",
        );
        query.push_values(range, |mut row, index| {
            let content = &chunks[index];
            let embedding = vector_literal(&embeddings[index]);
            let content_hash = format!("{:x}", Sha256::digest(content.as_bytes()));
            row.push_bind(file.project_id)
                .push_bind(file.id)
                .push_bind(index as i32)
                .push_bind(content)
                .push_bind(content_hash)
                .push_bind(content.chars().count() as i32)
                .push_bind(embedding)
                .push("::vector")
                .push_bind(metadata.clone())
                .push("now()");
        });
        query
            .build()
            .execute(&mut **transaction)
            .await
            .map_err(|error| error.to_string())?;
    }
    Ok(chunks.len() as i32)
}

fn rag_insert_batch_ranges(chunk_count: usize) -> Vec<std::ops::Range<usize>> {
    let mut ranges = Vec::new();
    let mut start = 0;
    while start < chunk_count {
        let end = start.saturating_add(RAG_INSERT_BATCH_SIZE).min(chunk_count);
        ranges.push(start..end);
        start = end;
    }
    ranges
}

fn validate_embedding_dimensions(embedding: &[f32], expected: usize) -> Result<(), String> {
    if embedding.len() == expected {
        Ok(())
    } else {
        Err(format!(
            "Embedding vector has {} dimensions; expected {expected}",
            embedding.len()
        ))
    }
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
    let lexical_scores = bm25_scores(&rows, query);

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
        validate_embedding_dimensions(&query_embedding, settings.embedding_dimension)
            .map_err(ApiError::internal)?;
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
            .then_with(|| {
                right
                    .1
                    .vector_score
                    .unwrap_or_default()
                    .partial_cmp(&left.1.vector_score.unwrap_or_default())
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| {
                left.1
                    .chunk_id
                    .unwrap_or_default()
                    .cmp(&right.1.chunk_id.unwrap_or_default())
            })
    });
    let limit = if is_collection_query(query) {
        settings
            .rag_collection_retrieval_top_k
            .max(settings.rag_retrieval_top_k)
            .min(settings.rag_vector_candidate_k)
    } else {
        settings.rag_retrieval_top_k
    };
    Ok(scored
        .into_iter()
        .filter(|(score, _)| {
            include_retrieval_candidate(*score, bm25_only, query_tokens.is_empty())
        })
        .map(|(_, source)| source)
        .take(limit)
        .collect())
}

fn include_retrieval_candidate(score: f64, bm25_only: bool, query_tokens_empty: bool) -> bool {
    score > 0.0 || (!bm25_only && query_tokens_empty)
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
    min_score: f64,
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
        let overlap = exact_token_overlap(&query_tokens, &haystack) as f64;
        let role_bonus = row
            .properties
            .get("roles")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(Value::as_str)
            .filter(|role| {
                tokens(role)
                    .iter()
                    .any(|role_token| query_tokens.contains(role_token))
            })
            .count() as f64;
        let score = overlap
            + role_bonus * 2.0
            + if hints.contains(row.relation_type.as_str()) {
                3.0
            } else {
                0.0
            };
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

fn meets_graph_threshold(score: f64, min_score: f64) -> bool {
    score > 0.0 && score >= min_score
}

pub fn format_sources(sources: &[RagSourceRead]) -> String {
    const MAX_CONTEXT_CHARS: usize = 9_000;
    let prefix = "项目资料检索结果：";
    let per_source_budget =
        MAX_CONTEXT_CHARS.saturating_sub(prefix.chars().count()) / sources.len().max(1);
    let mut output = prefix.to_owned();
    for (index, source) in sources.iter().enumerate() {
        let header = format!(
            "\n\n[S{}] 文件={}; 块={}; 相关度={:.3}\n",
            index + 1,
            source.filename.as_deref().unwrap_or("未知"),
            source.chunk_id.unwrap_or_default(),
            source.retrieval_score.unwrap_or_default()
        );
        let header = if header.chars().count() > per_source_budget {
            let mut capped: String = header
                .chars()
                .take(per_source_budget.saturating_sub(1))
                .collect();
            if per_source_budget > 0 {
                capped.push('…');
            }
            capped
        } else {
            header
        };
        let snippet = source.snippet.as_deref().unwrap_or_default();
        let snippet_limit = per_source_budget.saturating_sub(header.chars().count());
        let snippet_chars = snippet.chars().count();
        let truncated_limit = snippet_limit.saturating_sub(1);
        let content_limit = if snippet_chars > snippet_limit {
            truncated_limit
        } else {
            snippet_limit
        };
        output.push_str(&header);
        output.extend(snippet.chars().take(content_limit));
        if snippet_chars > content_limit
            && header.chars().count() + content_limit < per_source_budget
        {
            output.push('…');
        }
    }
    output
}

pub fn format_graph_context(context: &[RagGraphContextRead]) -> String {
    if context.is_empty() {
        return String::new();
    }
    let visible = graph_context_budget(context);
    let mut output = String::from("实验知识图谱上下文：\n");
    for (index, item) in context.iter().take(visible).enumerate() {
        output.push_str(&graph_context_line(index, item));
    }
    if visible < context.len() {
        output.push_str(&graph_context_truncation_suffix());
    }
    output
}

pub fn graph_context_budget(context: &[RagGraphContextRead]) -> usize {
    let available =
        MAX_GRAPH_CONTEXT_CHARS.saturating_sub(graph_context_truncation_suffix().chars().count());
    let mut used = "实验知识图谱上下文：\n".chars().count();
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

fn graph_context_line(index: usize, item: &RagGraphContextRead) -> String {
    format!(
        "[G{}] {}（{}） {} {}（{}）\n",
        index + 1,
        item.source_label,
        item.source_entity_type_label,
        item.relation_label,
        item.target_label,
        item.target_entity_type_label
    )
}

fn graph_context_truncation_suffix() -> String {
    format!("\n[图谱上下文已截断至 {MAX_GRAPH_CONTEXT_CHARS} 个字符；未展示的细节不得据此推断。]")
}

pub async fn generate(
    state: &AppState,
    system_prompt: &str,
    user_prompt: &str,
    temperature: f64,
) -> Result<GenerationResult, GenerationError> {
    generate_with_max_tokens(state, system_prompt, user_prompt, temperature, 1800).await
}

pub async fn generate_with_max_tokens(
    state: &AppState,
    system_prompt: &str,
    user_prompt: &str,
    temperature: f64,
    max_tokens: u32,
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
        "max_tokens": max_tokens,
        "stream": false,
        "thinking": {"type": "disabled"}
    });
    let mut last_error = String::new();
    for attempt in 0..3 {
        let generation_permit = state.generation_limiter.acquire().await.map_err(|_| {
            GenerationError::Configuration(
                "Generation concurrency limiter is unavailable".to_owned(),
            )
        })?;
        let response = state
            .client
            .post(&url)
            .bearer_auth(api_key)
            .timeout(Duration::from_secs(180))
            .json(&payload)
            .send()
            .await;
        let should_retry = match response {
            Ok(response) if response.status().is_success() => {
                match parse_generation_response(response, model, attempt).await {
                    Ok(result) => return Ok(result),
                    Err(error) => {
                        last_error = error;
                        true
                    }
                }
            }
            Ok(response) => {
                let status = response.status();
                let detail = response.text().await.unwrap_or_default();
                last_error = format!(
                    "DeepSeek request failed: {status} {}",
                    truncate_error_detail(&detail, 1000)
                );
                should_retry_generation_status(status)
            }
            Err(error) => {
                last_error = format!("DeepSeek request failed: {error}");
                true
            }
        };
        drop(generation_permit);
        if !should_retry {
            break;
        }
        if attempt < 2 {
            tokio::time::sleep(Duration::from_secs(1 << attempt)).await;
        }
    }
    Err(GenerationError::Request(last_error))
}

async fn parse_generation_response(
    response: reqwest::Response,
    fallback_model: &str,
    attempt: usize,
) -> Result<GenerationResult, String> {
    let request_id = response
        .headers()
        .get("x-request-id")
        .and_then(|value| value.to_str().ok())
        .map(str::to_owned);
    let body: Value = response
        .json()
        .await
        .map_err(|error| format!("DeepSeek returned invalid JSON: {error}"))?;
    let answer = body["choices"][0]["message"]["content"]
        .as_str()
        .unwrap_or_default()
        .trim()
        .to_owned();
    if answer.is_empty() {
        return Err("DeepSeek returned an empty completion".to_owned());
    }
    let provider_usage = body.get("usage").cloned().unwrap_or_else(|| json!({}));
    let usage = if let Some(mut fields) = provider_usage.as_object().cloned() {
        fields.insert("generation_attempts".to_owned(), json!(attempt + 1));
        Value::Object(fields)
    } else {
        json!({
            "provider_usage": provider_usage,
            "generation_attempts": attempt + 1
        })
    };
    Ok(GenerationResult {
        answer,
        request_id: request_id.or_else(|| body["id"].as_str().map(str::to_owned)),
        model: body["model"].as_str().unwrap_or(fallback_model).to_owned(),
        usage,
    })
}

fn truncate_error_detail(detail: &str, max_bytes: usize) -> &str {
    let mut end = detail.len().min(max_bytes);
    while !detail.is_char_boundary(end) {
        end -= 1;
    }
    &detail[..end]
}

fn should_retry_generation_status(status: reqwest::StatusCode) -> bool {
    matches!(status.as_u16(), 408 | 425 | 429 | 500..=599)
}

pub fn audit_citations(
    answer: &str,
    source_count: usize,
    graph_count: usize,
) -> RagCitationAuditRead {
    let regex = Regex::new(r"(?i)\[([SG])([^\]]*)\]").unwrap();
    let citations: Vec<(String, Option<usize>, String)> = regex
        .captures_iter(answer)
        .map(|capture| {
            let kind = capture[1].to_uppercase();
            let raw_index = capture[2].to_owned();
            let index = raw_index
                .chars()
                .all(|character| character.is_ascii_digit())
                .then(|| raw_index.parse::<usize>().ok())
                .flatten();
            let marker = format!("[{kind}{raw_index}]");
            (kind, index, marker)
        })
        .collect();
    let invalid_citations: Vec<String> = citations
        .iter()
        .filter_map(|(kind, index, marker)| {
            let limit = if kind == "S" {
                source_count
            } else {
                graph_count
            };
            (!index.is_some_and(|index| (1..=limit).contains(&index))).then(|| marker.clone())
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
    token_frequencies(text).into_keys().collect()
}

fn exact_token_overlap(query_tokens: &HashSet<String>, text: &str) -> usize {
    let text_tokens = tokens(text);
    query_tokens.intersection(&text_tokens).count()
}

fn token_regex() -> &'static Regex {
    static TOKEN_REGEX: OnceLock<Regex> = OnceLock::new();
    TOKEN_REGEX.get_or_init(|| Regex::new(r"(?i)[a-z0-9_µ><=./-]+|[\p{Han}]+").unwrap())
}

fn token_frequencies(text: &str) -> HashMap<String, usize> {
    let mut frequencies = HashMap::new();
    for matched in token_regex().find_iter(text) {
        let token = matched.as_str().to_lowercase();
        *frequencies.entry(token.clone()).or_insert(0) += 1;
        if token
            .chars()
            .all(|character| ('\u{4e00}'..='\u{9fff}').contains(&character))
        {
            let chars: Vec<char> = token.chars().collect();
            for window in chars.windows(2) {
                *frequencies.entry(window.iter().collect()).or_insert(0) += 1;
            }
        }
    }
    frequencies
}

fn bm25_scores(rows: &[ChunkRow], query: &str) -> HashMap<i32, f64> {
    if rows.is_empty() {
        return HashMap::new();
    }
    let query_terms = token_frequencies(query);
    if query_terms.is_empty() {
        return rows.iter().map(|row| (row.id, 0.0)).collect();
    }
    let documents: Vec<HashMap<String, usize>> = rows
        .iter()
        .map(|row| token_frequencies(&row.content))
        .collect();
    let mut document_frequency = HashMap::<String, usize>::new();
    for document in &documents {
        for term in document.keys() {
            *document_frequency.entry(term.clone()).or_insert(0) += 1;
        }
    }
    let average_document_length = documents
        .iter()
        .map(|document| document.values().sum::<usize>() as f64)
        .sum::<f64>()
        / documents.len() as f64;
    let document_count = rows.len() as f64;
    let scores = rows.iter().zip(documents).map(|(row, document)| {
        let document_length = document.values().sum::<usize>() as f64;
        let raw_score = query_terms.keys().fold(0.0, |score, term| {
            let Some(&term_frequency) = document.get(term) else {
                return score;
            };
            let document_frequency = document_frequency.get(term).copied().unwrap_or_default();
            let idf = ((document_count - document_frequency as f64 + 0.5)
                / (document_frequency as f64 + 0.5)
                + 1.0)
                .ln();
            let normalized_length = document_length / average_document_length.max(1.0);
            let denominator = term_frequency as f64 + 1.2 * (1.0 - 0.75 + 0.75 * normalized_length);
            score + idf * (term_frequency as f64 * 2.2) / denominator
        });
        (row.id, raw_score / (raw_score + 1.0))
    });
    scores.collect()
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

pub fn is_collection_query(query: &str) -> bool {
    let normalized = query.to_lowercase();
    [
        "哪些",
        "有哪些",
        "全部",
        "所有",
        "列出",
        "列举",
        "多少",
        "分别",
        "完整",
        "汇总",
        "归纳",
        "清单",
        "一览",
    ]
    .iter()
    .any(|keyword| normalized.contains(keyword))
        || tokens(query)
            .iter()
            .any(|token| matches!(token.as_str(), "all" | "list" | "enumerate"))
}

fn relation_hints(query: &str) -> HashSet<&'static str> {
    let mut hints = HashSet::new();
    let query_tokens = tokens(query);
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

fn hint_tokens_match(left: &str, right: &str) -> bool {
    left == right
        || (left.len() > 3 && left.strip_suffix('s') == Some(right))
        || (right.len() > 3 && right.strip_suffix('s') == Some(left))
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

    use axum::{
        extract::State, http::StatusCode, response::IntoResponse, routing::post, Json, Router,
    };
    use serde_json::{json, Value};
    use sqlx::postgres::PgPoolOptions;
    use uuid::Uuid;

    use super::{
        audit_citations, bm25_scores, chunk_text, exact_token_overlap, fetch_vector_candidates,
        format_graph_context, format_sources, generate, generate_with_max_tokens,
        graph_context_budget, include_retrieval_candidate, is_collection_query,
        meets_graph_threshold, rag_insert_batch_ranges, relation_hints, retrieve,
        should_retry_generation_status, tokens, truncate_error_detail,
        validate_embedding_dimensions, vector_literal, ChunkRow, ACTIVE_CHUNKS_SQL,
        MAX_GRAPH_CONTEXT_CHARS, VECTOR_CANDIDATE_SQL,
    };
    use crate::{
        config::Settings,
        db::{connect_database, initialize_database},
        embedding::hash_embedding,
        models::{RagGraphContextRead, RagSourceRead},
        AppState,
    };

    #[derive(Clone, Default)]
    struct ConcurrencyProbe {
        active: Arc<AtomicUsize>,
        maximum: Arc<AtomicUsize>,
        max_tokens: Arc<AtomicUsize>,
    }

    #[derive(Clone)]
    struct RetryPermitProbe {
        requests: Arc<AtomicUsize>,
        first_failure: Arc<tokio::sync::Notify>,
    }

    impl Default for RetryPermitProbe {
        fn default() -> Self {
            Self {
                requests: Arc::new(AtomicUsize::new(0)),
                first_failure: Arc::new(tokio::sync::Notify::new()),
            }
        }
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
    fn test_citation_audit_rejects_overflowing_source_numbers() {
        let audit = audit_citations("Valid [S1], malformed [S999999999999999999999]", 1, 0);

        assert!(!audit.passed);
        assert_eq!(audit.invalid_citations, ["[S999999999999999999999]"]);
    }

    #[test]
    fn test_citation_audit_rejects_malformed_markers() {
        let audit = audit_citations("Valid [S1], malformed [S系统], [S1-S2] and [S+1]", 1, 0);

        assert!(!audit.passed);
        assert_eq!(audit.citation_count, 4);
        assert_eq!(audit.invalid_citations, ["[S系统]", "[S1-S2]", "[S+1]"]);
    }

    #[test]
    fn test_rag_insert_batch_ranges_cover_chunks_without_oversized_batches() {
        let ranges = rag_insert_batch_ranges(129);

        assert_eq!(ranges, vec![0..64, 64..128, 128..129]);
    }

    #[test]
    fn test_validate_embedding_dimensions_rejects_mismatched_query_vector() {
        assert!(validate_embedding_dimensions(&[0.0; 512], 512).is_ok());
        assert_eq!(
            validate_embedding_dimensions(&[0.0; 128], 512).unwrap_err(),
            "Embedding vector has 128 dimensions; expected 512"
        );
    }

    #[test]
    fn test_bm25_prioritizes_rare_terms_over_common_term_frequency() {
        let rows = vec![
            ChunkRow {
                id: 1,
                file_id: 1,
                filename: "common.txt".to_owned(),
                content: "common ".repeat(12),
            },
            ChunkRow {
                id: 2,
                file_id: 2,
                filename: "rare.txt".to_owned(),
                content: "common raremarker".to_owned(),
            },
        ];

        let scores = bm25_scores(&rows, "common raremarker");

        assert!(scores[&2] > scores[&1]);
        assert!(scores[&2] <= 1.0);
    }

    #[test]
    fn test_collection_query_detection_handles_chinese_and_english_without_substring_false_hits() {
        assert!(is_collection_query("汇总所有样本清单"));
        assert!(is_collection_query("Please list all samples"));
        assert!(!is_collection_query("small molecule protocol"));
    }

    #[test]
    fn test_graph_matching_uses_exact_tokens() {
        assert_eq!(exact_token_overlap(&tokens("cell"), "cellular culture"), 0);
        assert_eq!(exact_token_overlap(&tokens("cell"), "cell culture"), 1);
    }

    #[test]
    fn test_relation_hints_do_not_match_substrings() {
        assert!(!relation_hints("user").contains("uses_reagent"));
        assert!(relation_hints("Which reagents were used?").contains("uses_reagent"));
    }

    #[test]
    fn test_graph_threshold_rejects_below_threshold_and_zero_scores() {
        assert!(meets_graph_threshold(1.0, 1.0));
        assert!(meets_graph_threshold(1.0, 0.0));
        assert!(!meets_graph_threshold(0.9, 1.0));
        assert!(!meets_graph_threshold(0.0, 0.0));
    }

    #[test]
    fn test_source_context_keeps_all_source_markers_with_long_snippets() {
        let sources = (1..=3)
            .map(|index| RagSourceRead {
                chunk_id: Some(index),
                file_id: Some(index),
                filename: Some(format!("source-{index}.txt")),
                dify_document_id: None,
                snippet: Some("evidence ".repeat(2_000)),
                vector_score: Some(0.9),
                lexical_score: Some(0.8),
                retrieval_score: Some(0.85),
            })
            .collect::<Vec<_>>();

        let formatted = format_sources(&sources);

        assert!(formatted.chars().count() <= 9_000);
        for marker in ["[S1]", "[S2]", "[S3]"] {
            assert!(
                formatted.contains(marker),
                "missing source marker: {marker}"
            );
        }
    }

    #[test]
    fn test_source_context_caps_oversized_source_headers() {
        let formatted = format_sources(&[RagSourceRead {
            chunk_id: Some(1),
            file_id: Some(1),
            filename: Some("x".repeat(20_000)),
            dify_document_id: None,
            snippet: Some("evidence".to_owned()),
            vector_score: Some(0.9),
            lexical_score: Some(0.8),
            retrieval_score: Some(0.85),
        }]);

        assert!(formatted.chars().count() <= 9_000);
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
                source_entity_type: "note".to_owned(),
                source_entity_type_label: "实验笔记".to_owned(),
                target_entity_id: index + 100,
                target_label: "target ".to_owned() + &"y".repeat(1_000),
                target_entity_type: "reagent".to_owned(),
                target_entity_type_label: "试剂".to_owned(),
                confidence: 0.8,
                retrieval_score: 1.0,
            })
            .collect::<Vec<_>>();

        let formatted = format_graph_context(&context);

        assert!(formatted.chars().count() <= MAX_GRAPH_CONTEXT_CHARS);
        assert_eq!(graph_context_budget(&context), 2);
        assert!(formatted.contains("[G1]"));
        assert!(formatted.contains("[G2]"));
        assert!(!formatted.contains("[G30]"));
        assert!(formatted.contains("图谱上下文已截断"));
    }

    #[test]
    fn test_truncate_error_detail_preserves_utf8_boundaries() {
        let detail = format!("{}中", "a".repeat(999));

        assert_eq!(truncate_error_detail(&detail, 1000), "a".repeat(999));
    }

    #[test]
    fn test_generation_retry_policy_covers_transient_http_statuses() {
        for status in [
            reqwest::StatusCode::REQUEST_TIMEOUT,
            reqwest::StatusCode::TOO_EARLY,
            reqwest::StatusCode::TOO_MANY_REQUESTS,
            reqwest::StatusCode::INTERNAL_SERVER_ERROR,
            reqwest::StatusCode::BAD_GATEWAY,
        ] {
            assert!(should_retry_generation_status(status));
        }
        for status in [
            reqwest::StatusCode::BAD_REQUEST,
            reqwest::StatusCode::UNAUTHORIZED,
            reqwest::StatusCode::FORBIDDEN,
            reqwest::StatusCode::NOT_FOUND,
        ] {
            assert!(!should_retry_generation_status(status));
        }
    }

    #[test]
    fn test_empty_bm25_queries_do_not_return_zero_score_documents() {
        assert!(!include_retrieval_candidate(0.0, true, true));
        assert!(include_retrieval_candidate(0.7, true, true));
        assert!(include_retrieval_candidate(0.0, false, true));
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
            ("RAG_VECTOR_CANDIDATE_K".to_owned(), "2".to_owned()),
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
        for index in 1..=4 {
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
        let orthogonal_index = query_embedding
            .iter()
            .position(|value| value.abs() < f32::EPSILON)
            .unwrap();
        let query_index = query_embedding
            .iter()
            .position(|value| value.abs() >= f32::EPSILON)
            .unwrap();
        let mut near_embedding = vec![0.0_f32; 512];
        near_embedding[query_index] = 0.99;
        near_embedding[orthogonal_index] = 0.1;
        let mut medium_embedding = vec![0.0_f32; 512];
        medium_embedding[query_index] = 0.95;
        medium_embedding[orthogonal_index] = 0.31;
        let mut orthogonal_embedding = vec![0.0_f32; 512];
        orthogonal_embedding[orthogonal_index] = 1.0;
        let contents = [
            "unrelated vector-nearest content",
            "another vector-nearest document",
            "raremarker exact lexical evidence",
            "another unrelated document",
        ];
        let embeddings = [
            vector_literal(&query_embedding),
            vector_literal(&near_embedding),
            vector_literal(&orthogonal_embedding),
            vector_literal(&medium_embedding),
        ];
        let mut chunk_ids = Vec::new();
        for index in 0..4 {
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
            fetch_vector_candidates(&pool, project_id, &vector_literal(&query_embedding), 2)
                .await
                .unwrap();
        assert_eq!(vector_candidates.len(), 2);
        assert_eq!(vector_candidates[0].id, chunk_ids[0]);
        assert!(!vector_candidates
            .iter()
            .any(|candidate| candidate.id == chunk_ids[2]));

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
        async fn completion(
            State(probe): State<ConcurrencyProbe>,
            Json(payload): Json<Value>,
        ) -> Json<Value> {
            probe.max_tokens.store(
                payload["max_tokens"].as_u64().unwrap_or_default() as usize,
                Ordering::SeqCst,
            );
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
        assert_eq!(probe.max_tokens.load(Ordering::SeqCst), 1800);

        generate_with_max_tokens(&state, "system", "user", 0.0, 2200)
            .await
            .unwrap();
        assert_eq!(probe.max_tokens.load(Ordering::SeqCst), 2200);
    }

    #[tokio::test]
    async fn test_generation_releases_provider_permit_during_retry_backoff() {
        async fn completion(State(probe): State<RetryPermitProbe>) -> axum::response::Response {
            if probe.requests.fetch_add(1, Ordering::SeqCst) == 0 {
                probe.first_failure.notify_one();
                return (StatusCode::INTERNAL_SERVER_ERROR, "retry").into_response();
            }
            Json(json!({
                "id": "retry-probe",
                "model": "deepseek-test",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 1}
            }))
            .into_response()
        }

        let probe = RetryPermitProbe::default();
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
            ("DEEPSEEK_MAX_CONCURRENCY".to_owned(), "1".to_owned()),
        ]))
        .unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();
        let state = AppState::new(pool, settings).unwrap();
        let first_state = state.clone();
        let first =
            tokio::spawn(async move { generate(&first_state, "system", "user", 0.0).await });
        probe.first_failure.notified().await;

        let second_state = state.clone();
        let second = tokio::time::timeout(
            Duration::from_millis(500),
            generate(&second_state, "system", "user", 0.0),
        )
        .await
        .expect("retry backoff must not hold provider permit")
        .unwrap();

        assert_eq!(second.answer, "ok");
        assert_eq!(second.usage["generation_attempts"], 1);
        let first = first.await.unwrap().unwrap();
        assert_eq!(first.answer, "ok");
        assert_eq!(first.usage["generation_attempts"], 2);
    }

    #[tokio::test]
    async fn test_generation_retries_invalid_success_response() {
        async fn completion(State(requests): State<Arc<AtomicUsize>>) -> axum::response::Response {
            if requests.fetch_add(1, Ordering::SeqCst) == 0 {
                return (StatusCode::OK, "not-json").into_response();
            }
            Json(json!({
                "id": "invalid-json-probe",
                "model": "deepseek-test",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"total_tokens": 1}
            }))
            .into_response()
        }

        let requests = Arc::new(AtomicUsize::new(0));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let server_requests = requests.clone();
        tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new()
                    .route("/chat/completions", post(completion))
                    .with_state(server_requests),
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
            ("DEEPSEEK_MAX_CONCURRENCY".to_owned(), "1".to_owned()),
        ]))
        .unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();
        let state = AppState::new(pool, settings).unwrap();

        let result = generate(&state, "system", "user", 0.0).await.unwrap();

        assert_eq!(result.answer, "ok");
        assert_eq!(result.usage["generation_attempts"], 2);
    }
}
