// 索引构建：读取文件、提取文本、切分并批量写入向量 chunk。

use serde_json::json;
use sha2::{Digest, Sha256};
use sqlx::{FromRow, PgPool, Postgres, QueryBuilder, Transaction};

use super::{chunk::chunk_text, vector_literal};
use crate::{
    error::ApiError,
    ocr::{extract_text, OcrSource},
    AppState,
};

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
    let metadata =
        json!({"filename": file.original_filename, "chunk_version": settings.rag_index_version});
    for range in rag_insert_batch_ranges(chunks.len()) {
        let mut query = QueryBuilder::<Postgres>::new(
            "INSERT INTO rag_document_chunks (\
                project_id, file_id, chunk_index, content, content_hash,\
                character_count, embedding, metadata_json, chunk_version, index_version, created_at\
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
                // 必须用 push_unseparated：push_values 闭包内是逗号分隔的 Separated，
                // 若用 push 会在占位符与类型转换之间插入逗号，生成非法 SQL。
                .push_unseparated("::vector")
                .push_bind(metadata.clone())
                .push_bind(&settings.rag_index_version)
                .push_bind(&settings.rag_index_version)
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

pub(crate) fn validate_embedding_dimensions(
    embedding: &[f32],
    expected: usize,
) -> Result<(), String> {
    if embedding.len() == expected {
        Ok(())
    } else {
        Err(format!(
            "Embedding vector has {} dimensions; expected {expected}",
            embedding.len()
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::{rag_insert_batch_ranges, validate_embedding_dimensions};

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
}
