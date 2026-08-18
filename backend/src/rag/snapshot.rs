// 快照逻辑：文档/图谱证据快照的查询、内容哈希校验与哈希汇总。

use std::collections::HashSet;

use serde_json::{json, Value};
use sqlx::{FromRow, PgConnection, PgPool, Postgres, Transaction};

use super::{graph::scoped_graph_relations_sql, sha256_hex};
use crate::error::ApiError;

/// Version of the knowledge-graph schema consumed by the production Rust retriever.
///
/// The graph rows are produced by the legacy extraction pipeline, so this value
/// deliberately matches `backend/app/services/kg_constants.py`. It is exported
/// with experiment evidence so a paper run cannot silently mix graph schemas.
pub const GRAPH_SCHEMA_VERSION: &str = "kg-v3-numbered-list-expansion";

#[derive(Clone, Debug)]
pub struct DocumentSnapshot {
    pub hash: String,
    pub chunk_count: i64,
}

#[derive(Clone, Debug)]
pub struct GraphSnapshot {
    pub hash: String,
    pub entity_count: i64,
    pub relation_count: i64,
}

#[derive(Debug, FromRow)]
struct DocumentSnapshotRow {
    chunk_id: i32,
    file_id: i32,
    filename: String,
    file_hash: String,
    chunk_index: i32,
    stored_content_hash: String,
    content: String,
    embedding_text: String,
}

#[derive(Debug, FromRow)]
struct GraphSnapshotRow {
    relation_id: i32,
    relation_type: String,
    source_type: Option<String>,
    source_id: Option<i32>,
    source_entity_id: i32,
    confidence: f64,
    relation_properties: Value,
    source_entity_type: String,
    source_label: String,
    source_normalized_label: String,
    source_natural_key: String,
    source_properties: Value,
    target_entity_type: String,
    target_entity_id: i32,
    target_label: String,
    target_normalized_label: String,
    target_natural_key: String,
    target_properties: Value,
}

const DOCUMENT_SNAPSHOT_SQL: &str = r#"
    SELECT c.id AS chunk_id, c.file_id, f.original_filename AS filename, f.file_hash,
           c.chunk_index, c.content_hash AS stored_content_hash, c.content,
           c.embedding::text AS embedding_text
    FROM rag_document_chunks c
    JOIN files f ON f.id = c.file_id
    WHERE c.project_id = $1
      AND f.status = 'APPROVED'::filestatus
      AND f.file_category = 'KNOWLEDGE_DOCUMENT'::filecategory
      AND f.knowledge_sync_status = 'synced'
      AND c.index_version = $2
    ORDER BY c.id
"#;

const GRAPH_SNAPSHOT_SELECT: &str = r#"
    r.id AS relation_id, r.relation_type, r.source_type, r.source_id,
    r.source_entity_id, r.target_entity_id, r.confidence,
    r.properties AS relation_properties,
    s.entity_type AS source_entity_type, s.label AS source_label,
    s.normalized_label AS source_normalized_label,
    s.natural_key AS source_natural_key, s.properties AS source_properties,
    t.entity_type AS target_entity_type, t.label AS target_label,
    t.normalized_label AS target_normalized_label,
    t.natural_key AS target_natural_key, t.properties AS target_properties
"#;

fn graph_snapshot_sql() -> String {
    scoped_graph_relations_sql(GRAPH_SNAPSHOT_SELECT)
}

fn require_content_hash(content: &str, stored: &str) -> Result<(), ApiError> {
    let actual = sha256_hex(content.as_bytes());
    if actual == stored {
        Ok(())
    } else {
        Err(ApiError::new(
            axum::http::StatusCode::CONFLICT,
            format!("RAG content hash mismatch: stored={stored}, actual={actual}"),
        ))
    }
}

async fn document_snapshot_with_connection(
    connection: &mut PgConnection,
    project_id: i32,
    index_version: &str,
) -> Result<DocumentSnapshot, ApiError> {
    let rows = sqlx::query_as::<_, DocumentSnapshotRow>(DOCUMENT_SNAPSHOT_SQL)
        .bind(project_id)
        .bind(index_version)
        .fetch_all(&mut *connection)
        .await?;
    let mut material = Vec::with_capacity(rows.len());
    for row in &rows {
        require_content_hash(&row.content, &row.stored_content_hash)?;
        material.push(json!({
            "chunk_id": row.chunk_id,
            "file_id": row.file_id,
            "filename": row.filename,
            "file_hash": row.file_hash,
            "chunk_index": row.chunk_index,
            "content_sha256": sha256_hex(row.content.as_bytes()),
            "stored_content_hash": row.stored_content_hash,
            "embedding_sha256": sha256_hex(row.embedding_text.as_bytes()),
            "index_version": index_version,
        }));
    }
    let snapshot_material = serde_json::to_vec(&json!({
        "index_version": index_version,
        "chunks": material,
    }))
    .map_err(|error| ApiError::internal(error.to_string()))?;
    Ok(DocumentSnapshot {
        hash: sha256_hex(snapshot_material),
        chunk_count: rows.len() as i64,
    })
}

pub async fn document_snapshot(
    pool: &PgPool,
    project_id: i32,
    index_version: &str,
) -> Result<DocumentSnapshot, ApiError> {
    let mut connection = pool.acquire().await?;
    document_snapshot_with_connection(&mut connection, project_id, index_version).await
}

pub async fn document_snapshot_in_transaction(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    index_version: &str,
) -> Result<DocumentSnapshot, ApiError> {
    document_snapshot_with_connection(transaction, project_id, index_version).await
}

async fn graph_snapshot_with_connection(
    connection: &mut PgConnection,
    project_id: i32,
) -> Result<GraphSnapshot, ApiError> {
    let graph_sql = graph_snapshot_sql();
    let rows = sqlx::query_as::<_, GraphSnapshotRow>(&graph_sql)
        .bind(project_id)
        .fetch_all(&mut *connection)
        .await?;
    let mut entities = HashSet::new();
    let mut material = Vec::with_capacity(rows.len());
    for row in &rows {
        entities.insert(row.source_entity_id);
        entities.insert(row.target_entity_id);
        material.push(json!({
            "relation_id": row.relation_id,
            "relation_type": row.relation_type,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "source_entity_id": row.source_entity_id,
            "confidence": row.confidence,
            "relation_properties": row.relation_properties,
            "source_entity_type": row.source_entity_type,
            "source_label": row.source_label,
            "source_normalized_label": row.source_normalized_label,
            "source_natural_key": row.source_natural_key,
            "source_properties": row.source_properties,
            "target_entity_type": row.target_entity_type,
            "target_entity_id": row.target_entity_id,
            "target_label": row.target_label,
            "target_normalized_label": row.target_normalized_label,
            "target_natural_key": row.target_natural_key,
            "target_properties": row.target_properties,
        }));
    }
    let snapshot_material = serde_json::to_vec(&json!({
        "graph_schema_version": GRAPH_SCHEMA_VERSION,
        "relations": material,
    }))
    .map_err(|error| ApiError::internal(error.to_string()))?;
    Ok(GraphSnapshot {
        hash: sha256_hex(snapshot_material),
        entity_count: entities.len() as i64,
        relation_count: rows.len() as i64,
    })
}

pub async fn graph_snapshot(pool: &PgPool, project_id: i32) -> Result<GraphSnapshot, ApiError> {
    let mut connection = pool.acquire().await?;
    graph_snapshot_with_connection(&mut connection, project_id).await
}

pub async fn graph_snapshot_in_transaction(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<GraphSnapshot, ApiError> {
    graph_snapshot_with_connection(transaction, project_id).await
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::{graph_snapshot_sql, DOCUMENT_SNAPSHOT_SQL};
    use crate::rag::GRAPH_RELATIONS_SCOPE_FILTER;

    #[test]
    fn test_snapshot_sql_contains_all_order_and_identity_fields() {
        assert!(DOCUMENT_SNAPSHOT_SQL.contains("c.id AS chunk_id"));
        assert!(DOCUMENT_SNAPSHOT_SQL.contains("ORDER BY c.id"));
        let graph_sql = graph_snapshot_sql();
        for field in [
            "r.id AS relation_id",
            "r.source_entity_id",
            "r.target_entity_id",
            "ORDER BY r.id",
        ] {
            assert!(
                graph_sql.contains(field),
                "missing graph snapshot field: {field}"
            );
        }
        assert!(graph_sql.contains(GRAPH_RELATIONS_SCOPE_FILTER));
    }

    #[test]
    fn test_graph_snapshot_entity_count_semantics_use_endpoint_ids() {
        let endpoint_ids = [10, 10, 11, 12];
        let entities = endpoint_ids.iter().copied().collect::<HashSet<_>>();
        assert_eq!(entities.len(), 3);
    }
}
