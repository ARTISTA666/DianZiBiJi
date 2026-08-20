// RAG 模块根：统一再导出公共 API、跨模块共享小工具与生成/合并逻辑，并保留需要数据库与模拟 HTTP 服务的集成测试。

use std::collections::HashMap;

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::{ai_provider::GenerationRequest, models::RagSourceRead, AppState};

pub use crate::ai_provider::{GenerationError, GenerationResult};

mod bm25;
mod chunk;
mod citations;
mod graph;
mod index;
mod retrieval;
mod snapshot;

// 公共 API 再导出（与拆分前保持一致，调用方无需改动）
pub use bm25::{bm25_expansion_terms, expand_query_for_bm25};
pub use citations::{
    audit_citations, audit_citations_after_repair, strip_citation_template_placeholders,
};
pub use graph::{
    format_graph_context, graph_context_budget, relevant_graph_context,
    relevant_graph_context_in_transaction, GRAPH_RELATIONS_SCOPE_FILTER,
};
pub use index::{fetch_rag_file, index_file, RagFileRecord};
pub(crate) use retrieval::select_diverse_sources;
pub use retrieval::{
    is_collection_query, query_prefers_lexical_exact_match, retrieve, retrieve_in_transaction,
    ACTIVE_CHUNKS_SQL,
};
pub use snapshot::{
    document_snapshot, document_snapshot_in_transaction, graph_snapshot,
    graph_snapshot_in_transaction, DocumentSnapshot, GraphSnapshot, GRAPH_SCHEMA_VERSION,
};

// 供 crate 内部（api/agents.rs 等）使用的图谱标签函数
pub(crate) use graph::{entity_type_label, relation_label};

// 供集成测试直接访问的 pub(crate) 项
#[cfg(test)]
pub(crate) use bm25::bm25_scores;
#[cfg(test)]
pub(crate) use chunk::chunk_text;
#[cfg(test)]
pub(crate) use retrieval::fetch_vector_candidates;
#[cfg(test)]
pub(crate) use retrieval::{include_retrieval_candidate, ChunkRow};

pub(crate) fn sha256_hex(bytes: impl AsRef<[u8]>) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

pub(crate) fn round6(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

pub(crate) fn vector_literal(vector: &[f32]) -> String {
    format!(
        "[{}]",
        vector
            .iter()
            .map(|value| format!("{value:.9}"))
            .collect::<Vec<_>>()
            .join(",")
    )
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
    state
        .ai_provider
        .generate(GenerationRequest {
            system_prompt: system_prompt.to_owned(),
            user_prompt: user_prompt.to_owned(),
            temperature,
            max_tokens,
            tools: Vec::new(),
        })
        .await
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

    use super::*;
    use crate::{
        config::Settings,
        db::{connect_database, initialize_database},
        embedding::hash_embedding,
        models::RagSourceRead,
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

    #[test]
    fn test_chunk_embedding_and_citation_contract() {
        let chunks = chunk_text(&"a".repeat(500), 200, 20);
        assert!(!chunks.is_empty());
        assert_eq!(hash_embedding("PCR Taq", 512).len(), 512);
        let audit = audit_citations("Result [S1], bad [G2]", 1, 1);
        assert!(!audit.passed);
        assert_eq!(audit.invalid_citations, ["[G2]"]);
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
                content: None,
                content_sha256: None,
                file_hash: None,
                chunk_index: None,
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
            content: None,
            content_sha256: None,
            file_hash: None,
            chunk_index: None,
        }]);

        assert!(formatted.chars().count() <= 9_000);
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
            ("RAG_INDEX_VERSION".to_owned(), "structured-v1".to_owned()),
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
        // 与查询向量首个非零分量的哈希符号对齐，保证 near/medium 向量的余弦
        // 确定性为正，不受 hash_embedding 符号位随机性影响。
        let sign = if query_embedding[query_index] >= 0.0 {
            1.0
        } else {
            -1.0
        };
        let mut near_embedding = vec![0.0_f32; 512];
        near_embedding[query_index] = 0.99 * sign;
        near_embedding[orthogonal_index] = 0.1;
        let mut medium_embedding = vec![0.0_f32; 512];
        medium_embedding[query_index] = 0.95 * sign;
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
                    character_count, embedding, metadata_json, chunk_version, index_version
                ) VALUES ($1, $2, 0, $3, $4, $5, $6::vector, '{}'::json, $7, $8)
                RETURNING id
                "#,
            )
            .bind(project_id)
            .bind(file_ids[index])
            .bind(contents[index])
            .bind(format!("candidate-chunk-{suffix}-{index}"))
            .bind(contents[index].chars().count() as i32)
            .bind(&embeddings[index])
            .bind(&state.settings.rag_index_version)
            .bind(&state.settings.rag_index_version)
            .fetch_one(&pool)
            .await
            .unwrap();
            chunk_ids.push(chunk_id);
        }

        let mut stale_chunk_ids = Vec::new();
        for (stale_index, stale_version) in [(4, "legacy-v1"), (5, "legacy-unknown")] {
            let stale_chunk_id: i32 = sqlx::query_scalar(
                r#"
                INSERT INTO rag_document_chunks (
                    project_id, file_id, chunk_index, content, content_hash,
                    character_count, embedding, metadata_json, chunk_version, index_version
                ) VALUES ($1, $2, $3, $4, $5, $6, $7::vector, '{}'::json, $8, $9)
                RETURNING id
                "#,
            )
            .bind(project_id)
            .bind(file_ids[0])
            .bind(stale_index)
            .bind(format!("stale {stale_version} raremarker evidence"))
            .bind(format!("stale-chunk-{suffix}-{stale_version}"))
            .bind(4_i32)
            .bind(&embeddings[0])
            .bind(stale_version)
            .bind(stale_version)
            .fetch_one(&pool)
            .await
            .unwrap();
            stale_chunk_ids.push(stale_chunk_id);
        }

        let vector_candidates = fetch_vector_candidates(
            &pool,
            project_id,
            "structured-v1",
            &vector_literal(&query_embedding),
            2,
        )
        .await
        .unwrap();
        assert_eq!(vector_candidates.len(), 2);
        assert_eq!(vector_candidates[0].id, chunk_ids[0]);
        assert!(!vector_candidates
            .iter()
            .any(|candidate| candidate.id == chunk_ids[2]));

        // 验证距离排序算子能命中 HNSW 索引。注意：VECTOR_CANDIDATE_SQL 的
        // ORDER BY 带有 c.id 并列排序键，HNSW 的 pathkey 无法覆盖双键排序，
        // 规划器此时必然退化为显式 Sort，因此不能用完整候选 SQL 断言计划。
        let mut explain = pool.begin().await.unwrap();
        sqlx::raw_sql(
            "SET LOCAL enable_seqscan = off; SET LOCAL enable_bitmapscan = off; SET LOCAL enable_sort = off",
        )
        .execute(&mut *explain)
        .await
        .unwrap();
        let plan: Value = sqlx::query_scalar(
            "EXPLAIN (FORMAT JSON) SELECT c.id FROM rag_document_chunks c \
             ORDER BY c.embedding <=> $1::vector LIMIT $2",
        )
        .bind(vector_literal(&query_embedding))
        .bind(2_i64)
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
        assert!(
            results
                .iter()
                .any(|source| source.file_id == Some(file_ids[2])),
            "expected lexical rescue in results: {results:?}"
        );
        assert!(results.iter().all(|source| {
            source
                .chunk_id
                .is_some_and(|chunk_id| !stale_chunk_ids.contains(&chunk_id))
        }));
    }

    #[tokio::test]
    async fn test_retrieval_min_score_filters_low_relevance_candidates() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let username = format!("rag_minscore_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url.clone()),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), username.clone()),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustMinScore123!".to_owned(),
            ),
            ("EMBEDDING_BACKEND".to_owned(), "hash".to_owned()),
            ("RAG_INDEX_VERSION".to_owned(), "structured-v1".to_owned()),
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
        .bind(format!("RAG min score project {suffix}"))
        .bind(user_id)
        .fetch_one(&pool)
        .await
        .unwrap();
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
        .bind(format!("minscore-{suffix}.txt"))
        .bind(format!("/tmp/minscore-{suffix}.txt"))
        .bind(format!("minscore-{suffix}"))
        .fetch_one(&pool)
        .await
        .unwrap();
        let content = "PCR protocol uses Taq polymerase at 58 C.";
        sqlx::query(
            r#"
                INSERT INTO rag_document_chunks (
                    project_id, file_id, chunk_index, content, content_hash,
                    character_count, embedding, metadata_json, chunk_version, index_version
                ) VALUES ($1, $2, 0, $3, $4, $5, $6::vector, '{}'::json, $7, $8)
                "#,
        )
        .bind(project_id)
        .bind(file_id)
        .bind(content)
        .bind(format!("minscore-chunk-{suffix}"))
        .bind(content.chars().count() as i32)
        .bind(vector_literal(&hash_embedding(content, 512)))
        .bind(&state.settings.rag_index_version)
        .bind(&state.settings.rag_index_version)
        .execute(&pool)
        .await
        .unwrap();

        // 默认阈值 0.15：哈希碰撞产生的低相关度候选必须被过滤。
        let filtered = retrieve(&state, project_id, "golf sierra mountain xyzzy", false)
            .await
            .unwrap();
        assert!(
            filtered.is_empty(),
            "low-relevance result leaked: {filtered:?}"
        );
        // 相关查询高于默认阈值，不受影响。
        let relevant = retrieve(&state, project_id, "What does the PCR protocol use?", false)
            .await
            .unwrap();
        assert_eq!(relevant.len(), 1);

        // 阈值设为 0 时恢复旧行为：所有正分候选都会返回。
        let legacy_settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url.clone()),
            ("RAG_MIN_RETRIEVAL_SCORE".to_owned(), "0".to_owned()),
            ("EMBEDDING_BACKEND".to_owned(), "hash".to_owned()),
            ("RAG_INDEX_VERSION".to_owned(), "structured-v1".to_owned()),
        ]))
        .unwrap();
        let legacy_state = AppState::new(pool.clone(), legacy_settings).unwrap();
        let legacy = retrieve(
            &legacy_state,
            project_id,
            "golf sierra mountain xyzzy",
            false,
        )
        .await
        .unwrap();
        assert_eq!(legacy.len(), 1);
        let legacy_vector_score = legacy[0].vector_score.unwrap();
        assert!(legacy_vector_score > 0.0 && legacy_vector_score < 0.15);

        // 边界值：恰好等于阈值的 bm25_only 候选应通过，略高于阈值则被过滤。
        let lexical_score = bm25_scores(
            &[ChunkRow {
                id: 1,
                file_id,
                filename: format!("minscore-{suffix}.txt"),
                file_hash: format!("file-{suffix}"),
                chunk_index: 0,
                content_hash: format!("content-{suffix}"),
                content: content.to_owned(),
            }],
            "polymerase taq",
        )[&1];
        let boundary_settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url.clone()),
            (
                "RAG_MIN_RETRIEVAL_SCORE".to_owned(),
                lexical_score.to_string(),
            ),
            ("EMBEDDING_BACKEND".to_owned(), "hash".to_owned()),
            ("RAG_INDEX_VERSION".to_owned(), "structured-v1".to_owned()),
        ]))
        .unwrap();
        let boundary_state = AppState::new(pool.clone(), boundary_settings).unwrap();
        let at_threshold = retrieve(&boundary_state, project_id, "polymerase taq", true)
            .await
            .unwrap();
        assert_eq!(at_threshold.len(), 1);
        let above_settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "RAG_MIN_RETRIEVAL_SCORE".to_owned(),
                (lexical_score + 0.0001).to_string(),
            ),
            ("EMBEDDING_BACKEND".to_owned(), "hash".to_owned()),
            ("RAG_INDEX_VERSION".to_owned(), "structured-v1".to_owned()),
        ]))
        .unwrap();
        let above_state = AppState::new(pool.clone(), above_settings).unwrap();
        let above_threshold = retrieve(&above_state, project_id, "polymerase taq", true)
            .await
            .unwrap();
        assert!(above_threshold.is_empty());
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
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    [("retry-after", "0")],
                    "retry",
                )
                    .into_response();
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
        let first = tokio::time::timeout(Duration::from_millis(500), first)
            .await
            .expect("Retry-After header should override exponential backoff")
            .unwrap()
            .unwrap();
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
