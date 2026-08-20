// 混合检索主流程：BM25 与向量候选的融合、相关度打分与多样化选源。

use std::collections::{HashMap, HashSet};

#[cfg(test)]
use sqlx::PgPool;
use sqlx::{FromRow, PgConnection, Postgres, Transaction};

use super::{
    bm25::{bm25_scores, expand_query_for_bm25, tokens},
    index::validate_embedding_dimensions,
    round6, vector_literal,
};
use crate::{error::ApiError, models::RagSourceRead, AppState};
// removed unused import

#[derive(Debug, FromRow)]
pub(crate) struct ChunkRow {
    pub(crate) id: i32,
    pub(crate) file_id: i32,
    pub(crate) filename: String,
    pub(crate) file_hash: String,
    pub(crate) chunk_index: i32,
    pub(crate) content_hash: String,
    pub(crate) content: String,
}

#[derive(Debug, FromRow)]
pub(crate) struct VectorCandidateRow {
    pub(crate) id: i32,
    pub(crate) vector_score: f64,
}

pub const ACTIVE_CHUNKS_SQL: &str = r#"
    SELECT c.id, c.file_id, f.original_filename AS filename, f.file_hash,
           c.chunk_index, c.content_hash, c.content
    FROM rag_document_chunks c
    JOIN files f ON f.id = c.file_id
    WHERE c.project_id = $1
      AND f.status = 'APPROVED'::filestatus
      AND f.file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
      AND f.knowledge_sync_status = 'synced'
      AND c.index_version = $2
    ORDER BY c.id
"#;

const VECTOR_CANDIDATE_SQL: &str = r#"
    SELECT c.id,
           GREATEST(0.0, 1.0 - (c.embedding <=> $3::vector)) AS vector_score
    FROM rag_document_chunks c
    JOIN files f ON f.id = c.file_id
    WHERE c.project_id = $1
      AND f.status = 'APPROVED'::filestatus
      AND f.file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
      AND f.knowledge_sync_status = 'synced'
      AND c.index_version = $2
    ORDER BY c.embedding <=> $3::vector, c.id
    LIMIT $4
"#;

const VECTOR_SCORES_SQL: &str = r#"
    SELECT c.id,
           GREATEST(0.0, 1.0 - (c.embedding <=> $3::vector)) AS vector_score
    FROM rag_document_chunks c
    WHERE c.project_id = $1 AND c.index_version = $2 AND c.id = ANY($4)
"#;

pub async fn retrieve(
    state: &AppState,
    project_id: i32,
    query: &str,
    bm25_only: bool,
) -> Result<Vec<RagSourceRead>, ApiError> {
    let mut connection = state.pool.acquire().await?;
    retrieve_with_connection(state, project_id, query, bm25_only, &mut connection).await
}

pub async fn retrieve_in_transaction(
    state: &AppState,
    project_id: i32,
    query: &str,
    bm25_only: bool,
    transaction: &mut Transaction<'_, Postgres>,
) -> Result<Vec<RagSourceRead>, ApiError> {
    retrieve_with_connection(state, project_id, query, bm25_only, transaction).await
}

async fn retrieve_with_connection(
    state: &AppState,
    project_id: i32,
    query: &str,
    bm25_only: bool,
    connection: &mut PgConnection,
) -> Result<Vec<RagSourceRead>, ApiError> {
    let settings = &state.settings;
    let rows = sqlx::query_as::<_, ChunkRow>(ACTIVE_CHUNKS_SQL)
        .bind(project_id)
        .bind(&settings.rag_index_version)
        .fetch_all(&mut *connection)
        .await?;
    if rows.is_empty() {
        return Ok(Vec::new());
    }
    let query_tokens = tokens(query);
    // 查询扩展：为 BM25 检索添加同义词，提升召回率
    let expanded_query = expand_query_for_bm25(query);
    let lexical_scores = bm25_scores(&rows, &expanded_query);

    let (candidate_ids, vector_scores) = if bm25_only {
        (
            rows.iter().map(|row| row.id).collect::<Vec<_>>(),
            HashMap::new(),
        )
    } else {
        // 尝试从进程缓存中读取已计算的查询向量，若不存在则调用 embedding 服务并写入缓存。
        let query_embedding = {
            // 先锁住缓存进行读写。
            let mut cache = state.embedding_cache.lock().await;
            if let Some(arc_vec) = cache.get(query) {
                (**arc_vec).clone()
            } else {
                let vec = state
                    .embeddings
                    .embed(&[query.to_owned()])
                    .await
                    .map_err(ApiError::internal)?
                    .into_iter()
                    .next()
                    .ok_or_else(|| ApiError::internal("Embedding returned no query vector"))?;
                cache.insert(query.to_string(), std::sync::Arc::new(vec.clone()));
                vec
            }
        };
        validate_embedding_dimensions(&query_embedding, settings.embedding_dimension)
            .map_err(ApiError::internal)?;
        let query_vector = vector_literal(&query_embedding);
        let vector_candidates = fetch_vector_candidates_with_connection(
            connection,
            project_id,
            &settings.rag_index_version,
            &query_vector,
            settings.rag_vector_candidate_k.min(30),
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
        lexical_candidates.truncate(settings.rag_vector_candidate_k.min(30));
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
            for candidate in fetch_vector_scores_with_connection(
                connection,
                project_id,
                &settings.rag_index_version,
                &query_vector,
                &missing_vector_scores,
            )
            .await?
            {
                vector_scores.insert(candidate.id, candidate.vector_score);
            }
        }
        (candidate_ids, vector_scores)
    };

    let lexical_first = query_prefers_lexical_exact_match(query);
    let use_rrf = !bm25_only && settings.rag_retrieval_strategy == "rrf-v1";
    // 词法优先且走 rrf-v1 时，预先为每个块切好 content+filename 词集，
    // 避免在候选评分循环里对每个候选重复分词（结果与原实现逐位一致）。
    let content_token_sets = if use_rrf && lexical_first {
        rows.iter()
            .map(|row| (row.id, tokens(&format!("{} {}", row.content, row.filename))))
            .collect::<HashMap<_, _>>()
    } else {
        HashMap::new()
    };
    let rows_by_id = rows
        .into_iter()
        .map(|row| (row.id, row))
        .collect::<HashMap<_, _>>();
    let mut vector_ranking = candidate_ids.clone();
    vector_ranking.sort_by(|left, right| {
        vector_scores
            .get(right)
            .unwrap_or(&0.0)
            .partial_cmp(vector_scores.get(left).unwrap_or(&0.0))
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| left.cmp(right))
    });
    let mut lexical_ranking = candidate_ids.clone();
    lexical_ranking.sort_by(|left, right| {
        lexical_scores
            .get(right)
            .unwrap_or(&0.0)
            .partial_cmp(lexical_scores.get(left).unwrap_or(&0.0))
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| left.cmp(right))
    });
    let rrf_scores = if lexical_first {
        weighted_reciprocal_rank_fusion(&vector_ranking, &lexical_ranking, 60.0, 0.25, 0.75)
    } else {
        reciprocal_rank_fusion(&vector_ranking, &lexical_ranking, 60.0)
    };
    let normalized_query = query.trim().to_lowercase();
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
        } else if use_rrf {
            let mut score = rrf_scores.get(&row.id).copied().unwrap_or_default();
            let content = row.content.to_lowercase();
            let filename = row.filename.to_lowercase();
            if lexical_first {
                let overlap = content_token_sets
                    .get(&row.id)
                    .map(|set| query_tokens.intersection(set).count())
                    .unwrap_or_default();
                score += (overlap as f64 * 0.02).min(0.12);
            }
            if !normalized_query.is_empty() && content.contains(&normalized_query) {
                score += 0.15;
            }
            if !normalized_query.is_empty() && filename.contains(&normalized_query) {
                score += 0.10;
            }
            score.min(1.0)
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
                content: Some(row.content.clone()),
                content_sha256: Some(row.content_hash.clone()),
                file_hash: Some(row.file_hash.clone()),
                chunk_index: Some(row.chunk_index),
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
            .min(12)
    } else {
        settings.rag_retrieval_top_k.min(6)
    };
    let candidates = scored
        .into_iter()
        .filter(|(score, source)| {
            include_retrieval_candidate(*score, bm25_only, query_tokens.is_empty())
                && passes_relevance_floor(
                    *score,
                    source.vector_score.unwrap_or_default(),
                    source.lexical_score.unwrap_or_default(),
                    bm25_only,
                    settings.rag_min_retrieval_score,
                )
        })
        .collect();
    Ok(select_diverse_sources(candidates, limit))
}

fn reciprocal_rank_fusion(
    vector_ranking: &[i32],
    lexical_ranking: &[i32],
    rank_constant: f64,
) -> HashMap<i32, f64> {
    weighted_reciprocal_rank_fusion(vector_ranking, lexical_ranking, rank_constant, 1.0, 1.0)
}

fn weighted_reciprocal_rank_fusion(
    vector_ranking: &[i32],
    lexical_ranking: &[i32],
    rank_constant: f64,
    vector_weight: f64,
    lexical_weight: f64,
) -> HashMap<i32, f64> {
    let mut scores = HashMap::new();
    for (ranking, weight) in [
        (vector_ranking, vector_weight),
        (lexical_ranking, lexical_weight),
    ] {
        for (index, id) in ranking.iter().enumerate() {
            *scores.entry(*id).or_insert(0.0) += weight / (rank_constant + index as f64 + 1.0);
        }
    }
    let maximum = scores.values().copied().fold(0.0_f64, f64::max);
    if maximum > 0.0 {
        for score in scores.values_mut() {
            *score /= maximum;
        }
    }
    scores
}

/// Exact identifiers, numeric thresholds and column/field lookups are better
/// anchored by lexical evidence than by semantic similarity.  The offline
/// holdout showed the same pattern: removing vector candidates improved MRR,
/// while graph context still provided the largest recall gain.
pub fn query_prefers_lexical_exact_match(query: &str) -> bool {
    let normalized = query.to_lowercase();
    let identifier_terms = [
        "gse",
        "gsm",
        "srr",
        "sra",
        "srx",
        "samn",
        "id",
        "编号",
        "列名",
        "字段",
        "软件",
        "工具",
        "版本",
        "total_count",
        "detected_gene_rows",
        "ct",
        "阈值",
        "计数",
        "行数",
        "最高",
        "最低",
        "相差",
        "非零",
        "单位",
        "样本",
    ];
    identifier_terms
        .iter()
        .any(|term| normalized.contains(term))
        || (normalized
            .chars()
            .any(|character| character.is_ascii_digit())
            && ["多少", "几个", "比较", "异常", "结果", "值"]
                .iter()
                .any(|term| normalized.contains(term)))
}

pub(crate) fn select_diverse_sources(
    ranked: Vec<(f64, RagSourceRead)>,
    limit: usize,
) -> Vec<RagSourceRead> {
    let mut file_counts = HashMap::<i32, usize>::new();
    let mut selected = Vec::with_capacity(limit);
    for (_, source) in ranked {
        if let Some(file_id) = source.file_id {
            let count = file_counts.entry(file_id).or_default();
            if *count >= 3 {
                continue;
            }
            *count += 1;
        }
        selected.push(source);
        if selected.len() >= limit {
            break;
        }
    }
    selected
}

pub(crate) fn include_retrieval_candidate(
    score: f64,
    bm25_only: bool,
    query_tokens_empty: bool,
) -> bool {
    score > 0.0 || (!bm25_only && query_tokens_empty)
}

fn passes_relevance_floor(
    retrieval_score: f64,
    vector_score: f64,
    lexical_score: f64,
    bm25_only: bool,
    minimum: f64,
) -> bool {
    if bm25_only {
        retrieval_score >= minimum
    } else {
        vector_score >= minimum || lexical_score >= minimum
    }
}

#[cfg(test)]
pub(crate) async fn fetch_vector_candidates(
    pool: &PgPool,
    project_id: i32,
    index_version: &str,
    query_vector: &str,
    candidate_k: usize,
) -> Result<Vec<VectorCandidateRow>, sqlx::Error> {
    let mut connection = pool.acquire().await?;
    fetch_vector_candidates_with_connection(
        &mut connection,
        project_id,
        index_version,
        query_vector,
        candidate_k,
    )
    .await
}

async fn fetch_vector_candidates_with_connection(
    connection: &mut PgConnection,
    project_id: i32,
    index_version: &str,
    query_vector: &str,
    candidate_k: usize,
) -> Result<Vec<VectorCandidateRow>, sqlx::Error> {
    sqlx::query_as(VECTOR_CANDIDATE_SQL)
        .bind(project_id)
        .bind(index_version)
        .bind(query_vector)
        .bind(i64::try_from(candidate_k).unwrap_or(i64::MAX))
        .fetch_all(&mut *connection)
        .await
}

#[cfg(test)]
#[allow(dead_code)]
async fn fetch_vector_scores(
    pool: &PgPool,
    project_id: i32,
    index_version: &str,
    query_vector: &str,
    chunk_ids: &[i32],
) -> Result<Vec<VectorCandidateRow>, sqlx::Error> {
    let mut connection = pool.acquire().await?;
    fetch_vector_scores_with_connection(
        &mut connection,
        project_id,
        index_version,
        query_vector,
        chunk_ids,
    )
    .await
}

async fn fetch_vector_scores_with_connection(
    connection: &mut PgConnection,
    project_id: i32,
    index_version: &str,
    query_vector: &str,
    chunk_ids: &[i32],
) -> Result<Vec<VectorCandidateRow>, sqlx::Error> {
    sqlx::query_as(VECTOR_SCORES_SQL)
        .bind(project_id)
        .bind(index_version)
        .bind(query_vector)
        .bind(chunk_ids)
        .fetch_all(&mut *connection)
        .await
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
        "各自",
        "数量",
        "四个",
        "两个",
        "最高",
        "最低",
        "相差",
    ]
    .iter()
    .any(|keyword| normalized.contains(keyword))
        || tokens(query)
            .iter()
            .any(|token| matches!(token.as_str(), "all" | "list" | "enumerate" | "count"))
}

#[cfg(test)]
mod tests {
    use super::{
        is_collection_query, passes_relevance_floor, query_prefers_lexical_exact_match,
        reciprocal_rank_fusion, select_diverse_sources, weighted_reciprocal_rank_fusion,
        ACTIVE_CHUNKS_SQL, VECTOR_CANDIDATE_SQL, VECTOR_SCORES_SQL,
    };
    use crate::models::RagSourceRead;

    #[test]
    fn test_vector_queries_bind_index_version_and_embedding_separately() {
        for query in [VECTOR_CANDIDATE_SQL, VECTOR_SCORES_SQL] {
            assert!(query.contains("c.index_version = $2"));
            assert!(query.contains("c.embedding <=> $3::vector"));
            assert!(!query.contains("c.embedding <=> $2::vector"));
        }
    }

    #[test]
    fn test_rrf_v1_fuses_rankings_without_score_scale_bias() {
        let scores = reciprocal_rank_fusion(&[10, 20, 30], &[30, 20, 40], 60.0);
        assert!(scores[&20] > scores[&10]);
        assert!(scores[&30] > scores[&10]);
        assert!(scores[&30] > scores[&20]);
        assert!(scores.values().all(|score| *score > 0.0 && *score <= 1.0));
    }

    #[test]
    fn test_exact_queries_weight_lexical_evidence_first() {
        assert!(query_prefers_lexical_exact_match(
            "GSM111619 的 total_count 和 detected_gene_rows 是多少？"
        ));
        assert!(query_prefers_lexical_exact_match("Ct 31.7 是否偏离阈值？"));
        assert!(!query_prefers_lexical_exact_match(
            "请概括这个项目的研究意义"
        ));

        let scores = weighted_reciprocal_rank_fusion(&[3, 2, 1], &[1, 2, 3], 60.0, 0.25, 0.75);
        assert!(scores[&1] > scores[&3]);
    }

    #[test]
    fn test_source_selection_caps_each_file_at_three_chunks() {
        let ranked = (1..=8)
            .map(|id| {
                (
                    1.0 / id as f64,
                    RagSourceRead {
                        chunk_id: Some(id),
                        file_id: Some(if id <= 6 { 1 } else { 2 }),
                        filename: Some("document".to_owned()),
                        dify_document_id: None,
                        snippet: Some("evidence".to_owned()),
                        vector_score: Some(1.0),
                        lexical_score: Some(1.0),
                        retrieval_score: Some(1.0 / id as f64),
                        content: None,
                        content_sha256: None,
                        file_hash: None,
                        chunk_index: None,
                    },
                )
            })
            .collect();
        let selected = select_diverse_sources(ranked, 6);
        assert_eq!(
            selected
                .iter()
                .filter(|source| source.file_id == Some(1))
                .count(),
            3
        );
        assert_eq!(selected.len(), 5);
    }

    #[test]
    fn test_rrf_relevance_floor_uses_actual_evidence_scores() {
        assert!(passes_relevance_floor(1.0, 0.05, 0.8, false, 0.15));
        assert!(!passes_relevance_floor(1.0, 0.05, 0.0, false, 0.15));
        assert!(passes_relevance_floor(0.15, 0.0, 0.15, true, 0.15));
        assert!(!passes_relevance_floor(0.1499, 0.0, 0.1499, true, 0.15));
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
        assert!(vector_sql.contains("c.index_version = $2"));
        assert!(vector_sql.contains("ORDER BY c.embedding <=> $3::vector"));
        assert!(vector_sql.contains("LIMIT $4"));
        assert!(!vector_sql.contains("embedding::text"));
    }

    #[test]
    fn test_collection_query_detection_handles_chinese_and_english_without_substring_false_hits() {
        assert!(is_collection_query("汇总所有样本清单"));
        assert!(is_collection_query("Please list all samples"));
        assert!(is_collection_query("Please enumerate all samples"));
        assert!(is_collection_query("有哪些样本？"));
        assert!(is_collection_query("count samples"));
        assert!(!is_collection_query("small molecule protocol"));
    }
}
