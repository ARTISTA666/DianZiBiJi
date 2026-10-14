use std::{
    collections::{HashMap, HashSet},
    sync::OnceLock,
};

use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{FromRow, Postgres, Transaction};

use crate::{
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{KnowledgeEntityRead, KnowledgeExtractionRunRead, KnowledgeRelationRead},
};

const EXTRACTION_RULE_VERSION: &str = "kg-rules-v2-atomic-arrays";

#[derive(Debug, FromRow)]
struct ExtractableNote {
    id: i32,
    project_id: i32,
    title: String,
    experiment_type: String,
    experiment_date: Option<chrono::NaiveDate>,
    owner_user_id: i32,
    current_version_id: Option<i32>,
}

#[derive(Debug, FromRow)]
struct EntityCandidate {
    id: i32,
    label: String,
    properties: Value,
}

#[derive(Debug, FromRow)]
struct RelationCandidate {
    id: i32,
    properties: Value,
}

#[derive(Clone, Debug)]
pub(crate) struct ExtractedTerm {
    pub(crate) entity_type: &'static str,
    pub(crate) relation_type: &'static str,
    pub(crate) label: String,
    pub(crate) roles: HashSet<String>,
}

pub async fn extract_note(
    transaction: &mut Transaction<'_, Postgres>,
    note_id: i32,
    triggered_by: i32,
    rebuild: bool,
) -> Result<KnowledgeExtractionRunRead, ApiError> {
    let note = sqlx::query_as::<_, ExtractableNote>(
        r#"
        SELECT id, project_id, title, experiment_type, experiment_date,
               owner_user_id, current_version_id
        FROM experiment_notes WHERE id = $1
        "#,
    )
    .bind(note_id)
    .fetch_optional(&mut **transaction)
    .await?
    .ok_or_else(|| ApiError::internal("Note not found during graph extraction"))?;
    let version = if let Some(version_id) = note.current_version_id {
        sqlx::query_as::<_, (Value, Value)>(
            "SELECT fixed_fields_json, content_json FROM note_versions WHERE id = $1 AND note_id = $2",
        )
        .bind(version_id)
        .bind(note.id)
        .fetch_optional(&mut **transaction)
        .await?
    } else {
        None
    };
    let provenance = extraction_provenance(note.current_version_id, version.as_ref());
    if rebuild {
        clear_note_graph(transaction, note_id).await?;
    }

    let project_name: Option<String> =
        sqlx::query_scalar("SELECT name FROM projects WHERE id = $1")
            .bind(note.project_id)
            .fetch_optional(&mut **transaction)
            .await?;
    let Some(project_name) = project_name else {
        return record_run(
            transaction,
            &note,
            triggered_by,
            (0, 0),
            "failed",
            "Project not found",
            &provenance,
        )
        .await;
    };

    let mut entities = HashSet::new();
    let mut relations = HashSet::new();
    let project_entity = upsert_entity(
        transaction,
        note.project_id,
        "project",
        &project_name,
        Some("project"),
        Some(note.project_id),
        json!({"project_id": note.project_id}),
    )
    .await?;
    let note_entity = upsert_entity(
        transaction,
        note.project_id,
        "note",
        &note.title,
        Some("note"),
        Some(note.id),
        json!({
            "note_id": note.id,
            "status": "approved",
            "experiment_date": note.experiment_date.map(|date| date.to_string()),
        }),
    )
    .await?;
    entities.extend([project_entity, note_entity]);
    relations.insert(
        upsert_relation(
            transaction,
            note.project_id,
            project_entity,
            note_entity,
            "has_note",
            Some("note"),
            Some(note.id),
            1.0,
            json!({}),
        )
        .await?,
    );

    if let Some((display_name, username)) = sqlx::query_as::<_, (String, String)>(
        "SELECT display_name, username FROM users WHERE id = $1",
    )
    .bind(note.owner_user_id)
    .fetch_optional(&mut **transaction)
    .await?
    {
        let owner_entity = upsert_entity(
            transaction,
            note.project_id,
            "user",
            &display_name,
            Some("user"),
            Some(note.owner_user_id),
            json!({"user_id": note.owner_user_id, "username": username}),
        )
        .await?;
        entities.insert(owner_entity);
        relations.insert(
            upsert_relation(
                transaction,
                note.project_id,
                note_entity,
                owner_entity,
                "created_by",
                Some("note"),
                Some(note.id),
                1.0,
                json!({}),
            )
            .await?,
        );
    }

    if !note.experiment_type.trim().is_empty() {
        let experiment_type = upsert_entity(
            transaction,
            note.project_id,
            "experiment_type",
            &note.experiment_type,
            None,
            None,
            json!({"experiment_type": note.experiment_type}),
        )
        .await?;
        entities.insert(experiment_type);
        relations.insert(
            upsert_relation(
                transaction,
                note.project_id,
                note_entity,
                experiment_type,
                "has_experiment_type",
                Some("note"),
                Some(note.id),
                1.0,
                json!({}),
            )
            .await?,
        );
    }

    let files = sqlx::query_as::<_, (i32, String, String, String)>(
        r#"
        SELECT id, original_filename, lower(file_category::text), lower(status::text)
        FROM files WHERE project_id = $1 AND note_id = $2 ORDER BY id
        "#,
    )
    .bind(note.project_id)
    .bind(note.id)
    .fetch_all(&mut **transaction)
    .await?;
    for (file_id, filename, category, status) in files {
        let file_entity = upsert_entity(
            transaction,
            note.project_id,
            "file",
            &filename,
            Some("file"),
            Some(file_id),
            json!({"file_id": file_id, "category": category, "status": status}),
        )
        .await?;
        entities.insert(file_entity);
        relations.insert(
            upsert_relation(
                transaction,
                note.project_id,
                note_entity,
                file_entity,
                "has_attachment",
                Some("note"),
                Some(note.id),
                1.0,
                json!({}),
            )
            .await?,
        );
    }

    if let Some((fixed_fields, content)) = version {
        for term in extract_terms(&fixed_fields, &content) {
            let entity = upsert_entity(
                transaction,
                note.project_id,
                term.entity_type,
                &term.label,
                None,
                None,
                json!({"extraction": "rule_based"}),
            )
            .await?;
            let mut roles: Vec<String> = term.roles.into_iter().collect();
            roles.sort();
            let mut properties = provenance.clone();
            properties["method"] = json!("rule_based");
            properties["roles"] = json!(roles);
            let relation = upsert_relation(
                transaction,
                note.project_id,
                note_entity,
                entity,
                term.relation_type,
                Some("note_extraction"),
                Some(note.id),
                0.7,
                properties,
            )
            .await?;
            entities.insert(entity);
            relations.insert(relation);
        }
    }

    record_run(
        transaction,
        &note,
        triggered_by,
        (entities.len() as i32, relations.len() as i32),
        "completed",
        "Knowledge graph extraction completed",
        &provenance,
    )
    .await
}

pub async fn clear_note_graph(
    transaction: &mut Transaction<'_, Postgres>,
    note_id: i32,
) -> Result<(), ApiError> {
    let entity_ids: Vec<i32> = sqlx::query_scalar(
        r#"
        SELECT source_entity_id FROM kg_relations
        WHERE source_type IN ('note', 'note_extraction') AND source_id = $1
        UNION
        SELECT target_entity_id FROM kg_relations
        WHERE source_type IN ('note', 'note_extraction') AND source_id = $1
        UNION
        SELECT id FROM kg_entities WHERE source_type = 'note' AND source_id = $1
        "#,
    )
    .bind(note_id)
    .fetch_all(&mut **transaction)
    .await?;
    sqlx::query(
        "DELETE FROM kg_relations WHERE source_type IN ('note', 'note_extraction') AND source_id = $1",
    )
    .bind(note_id)
    .execute(&mut **transaction)
    .await?;
    if !entity_ids.is_empty() {
        sqlx::query(
            r#"
            DELETE FROM kg_entities e
            WHERE e.id = ANY($1)
              AND NOT EXISTS (
                  SELECT 1 FROM kg_relations r
                  WHERE r.source_entity_id = e.id OR r.target_entity_id = e.id
              )
              AND (e.source_type IS NULL OR (e.source_type = 'note' AND e.source_id = $2))
            "#,
        )
        .bind(&entity_ids)
        .bind(note_id)
        .execute(&mut **transaction)
        .await?;
    }
    Ok(())
}

pub async fn project_graph(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<(Vec<KnowledgeEntityRead>, Vec<KnowledgeRelationRead>), ApiError> {
    let relations = sqlx::query_as::<_, KnowledgeRelationRead>(
        r#"
        SELECT id, project_id, source_entity_id, target_entity_id, relation_type,
               source_type, source_id, confidence, properties, created_at
        FROM kg_relations r
        WHERE project_id = $1
          AND (
              source_type NOT IN ('note', 'note_extraction')
              OR source_type IS NULL
              OR source_id IN (
                  SELECT id FROM experiment_notes
                  WHERE project_id = $1 AND status = 'APPROVED'::notestatus
              )
          )
        ORDER BY id
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut **transaction)
    .await?;
    let entity_ids: Vec<i32> = relations
        .iter()
        .flat_map(|relation| [relation.source_entity_id, relation.target_entity_id])
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    let entities = if entity_ids.is_empty() {
        Vec::new()
    } else {
        sqlx::query_as::<_, KnowledgeEntityRead>(
            r#"
            SELECT id, project_id, entity_type, label, normalized_label, natural_key,
                   source_type, source_id, properties, created_at, updated_at
            FROM kg_entities WHERE id = ANY($1) ORDER BY id
            "#,
        )
        .bind(&entity_ids)
        .fetch_all(&mut **transaction)
        .await?
    };
    Ok((entities, relations))
}

pub async fn note_graph(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    note_id: i32,
) -> Result<(Vec<KnowledgeEntityRead>, Vec<KnowledgeRelationRead>), ApiError> {
    let natural_key = format!("note:note:{note_id}");
    let note_entity_id: Option<i32> =
        sqlx::query_scalar("SELECT id FROM kg_entities WHERE project_id = $1 AND natural_key = $2")
            .bind(project_id)
            .bind(natural_key)
            .fetch_optional(&mut **transaction)
            .await?;
    let Some(note_entity_id) = note_entity_id else {
        return Ok((Vec::new(), Vec::new()));
    };
    let relations = sqlx::query_as::<_, KnowledgeRelationRead>(
        r#"
        SELECT id, project_id, source_entity_id, target_entity_id, relation_type,
               source_type, source_id, confidence, properties, created_at
        FROM kg_relations
        WHERE project_id = $1 AND (source_entity_id = $2 OR target_entity_id = $2)
        ORDER BY id
        "#,
    )
    .bind(project_id)
    .bind(note_entity_id)
    .fetch_all(&mut **transaction)
    .await?;
    let entity_ids: Vec<i32> = relations
        .iter()
        .flat_map(|relation| [relation.source_entity_id, relation.target_entity_id])
        .chain(std::iter::once(note_entity_id))
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    let entities = sqlx::query_as::<_, KnowledgeEntityRead>(
        r#"
        SELECT id, project_id, entity_type, label, normalized_label, natural_key,
               source_type, source_id, properties, created_at, updated_at
        FROM kg_entities WHERE id = ANY($1) ORDER BY id
        "#,
    )
    .bind(&entity_ids)
    .fetch_all(&mut **transaction)
    .await?;
    Ok((entities, relations))
}

async fn record_run(
    transaction: &mut Transaction<'_, Postgres>,
    note: &ExtractableNote,
    triggered_by: i32,
    counts: (i32, i32),
    status: &str,
    message: &str,
    provenance: &Value,
) -> Result<KnowledgeExtractionRunRead, ApiError> {
    let run = sqlx::query_as::<_, KnowledgeExtractionRunRead>(
        r#"
        INSERT INTO kg_extraction_runs (
            project_id, note_id, triggered_by, status, extracted_entities,
            extracted_relations, message, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        RETURNING id, project_id, note_id, triggered_by, status,
                  extracted_entities, extracted_relations, message, created_at
        "#,
    )
    .bind(note.project_id)
    .bind(note.id)
    .bind(triggered_by)
    .bind(status)
    .bind(counts.0)
    .bind(counts.1)
    .bind(message)
    .fetch_one(&mut **transaction)
    .await?;
    let mut detail = provenance.clone();
    detail["run_id"] = json!(run.id);
    detail["note_id"] = json!(note.id);
    write_audit(
        &mut **transaction,
        AuditEvent {
            actor_user_id: Some(triggered_by),
            project_id: Some(note.project_id),
            action: "kg_extraction_provenance",
            target_type: Some("kg_extraction_run"),
            target_id: Some(run.id),
            detail,
            ip_address: None,
            user_agent: None,
        },
    )
    .await?;
    Ok(run)
}

fn extraction_provenance(version_id: Option<i32>, version: Option<&(Value, Value)>) -> Value {
    let content_hash = version.map(|(fixed_fields, content)| {
        let input = json!({"fixed_fields": fixed_fields, "content": content});
        format!(
            "{:x}",
            Sha256::digest(serde_json::to_vec(&input).expect("JSON values serialize"))
        )
    });
    json!({
        "source_note_version_id": version_id,
        "source_status": if version.is_some() { "available" } else if version_id.is_some() { "missing_version" } else { "no_current_version" },
        "content_hash": content_hash,
        "content_hash_algorithm": "sha256-json-fields-content-v1",
        "source_scope": "note_version_fields_and_content",
        "rule_version": EXTRACTION_RULE_VERSION,
    })
}

#[allow(clippy::too_many_arguments)]
async fn upsert_entity(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    entity_type: &str,
    label: &str,
    source_type: Option<&str>,
    source_id: Option<i32>,
    properties: Value,
) -> Result<i32, ApiError> {
    let label = clean_label(label);
    let normalized_label = normalize_entity_label(&label);
    let uses_source_key =
        matches!(source_type, Some("project" | "note" | "user" | "file")) && source_id.is_some();
    let natural_key = if uses_source_key {
        format!(
            "{entity_type}:{}:{}",
            source_type.unwrap(),
            source_id.unwrap()
        )
    } else {
        format!("{entity_type}:{normalized_label}")
    };
    let mut entity = sqlx::query_as::<_, EntityCandidate>(
        r#"
        SELECT id, label, properties FROM kg_entities
        WHERE project_id = $1 AND natural_key = $2
        "#,
    )
    .bind(project_id)
    .bind(&natural_key)
    .fetch_optional(&mut **transaction)
    .await?;
    if entity.is_none() && !uses_source_key {
        let candidates = sqlx::query_as::<_, EntityCandidate>(
            r#"
            SELECT id, label, properties FROM kg_entities
            WHERE project_id = $1 AND entity_type = $2 AND source_type IS NULL
            "#,
        )
        .bind(project_id)
        .bind(entity_type)
        .fetch_all(&mut **transaction)
        .await?;
        entity = candidates
            .into_iter()
            .find(|candidate| normalize_entity_label(&candidate.label) == normalized_label);
    }
    if let Some(entity) = entity {
        let merged = merge_properties(entity.properties, properties);
        sqlx::query(
            r#"
            UPDATE kg_entities
            SET label = $2, normalized_label = $3, natural_key = $4,
                properties = $5, updated_at = now()
            WHERE id = $1
            "#,
        )
        .bind(entity.id)
        .bind(&label)
        .bind(&normalized_label)
        .bind(&natural_key)
        .bind(merged)
        .execute(&mut **transaction)
        .await?;
        return Ok(entity.id);
    }
    Ok(sqlx::query_scalar(
        r#"
        INSERT INTO kg_entities (
            project_id, entity_type, label, normalized_label, natural_key,
            source_type, source_id, properties, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now(), now())
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(entity_type)
    .bind(label)
    .bind(normalized_label)
    .bind(natural_key)
    .bind(source_type)
    .bind(source_id)
    .bind(properties)
    .fetch_one(&mut **transaction)
    .await?)
}

#[allow(clippy::too_many_arguments)]
async fn upsert_relation(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    source_entity_id: i32,
    target_entity_id: i32,
    relation_type: &str,
    source_type: Option<&str>,
    source_id: Option<i32>,
    confidence: f64,
    properties: Value,
) -> Result<i32, ApiError> {
    let relation = sqlx::query_as::<_, RelationCandidate>(
        r#"
        SELECT id, properties FROM kg_relations
        WHERE project_id = $1 AND source_entity_id = $2
          AND target_entity_id = $3 AND relation_type = $4
        "#,
    )
    .bind(project_id)
    .bind(source_entity_id)
    .bind(target_entity_id)
    .bind(relation_type)
    .fetch_optional(&mut **transaction)
    .await?;
    if let Some(relation) = relation {
        let merged = merge_properties(relation.properties, properties);
        sqlx::query(
            r#"
            UPDATE kg_relations
            SET source_type = COALESCE($2, source_type),
                source_id = COALESCE($3, source_id), confidence = $4, properties = $5
            WHERE id = $1
            "#,
        )
        .bind(relation.id)
        .bind(source_type)
        .bind(source_id)
        .bind(confidence)
        .bind(merged)
        .execute(&mut **transaction)
        .await?;
        return Ok(relation.id);
    }
    Ok(sqlx::query_scalar(
        r#"
        INSERT INTO kg_relations (
            project_id, source_entity_id, target_entity_id, relation_type,
            source_type, source_id, confidence, properties, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(source_entity_id)
    .bind(target_entity_id)
    .bind(relation_type)
    .bind(source_type)
    .bind(source_id)
    .bind(confidence)
    .bind(properties)
    .fetch_one(&mut **transaction)
    .await?)
}

pub(crate) fn extract_terms(fixed_fields: &Value, content: &Value) -> Vec<ExtractedTerm> {
    let mut terms = Vec::new();
    collect_structured(fixed_fields, &mut terms);
    collect_structured(content, &mut terms);
    // Structured arrays were already extracted with their declared boundaries.
    // Do not interpret their labels again as free-text prefixes.
    let text = flatten_text(&[fixed_fields, content], false).join("\n");
    let patterns = [
        (
            "reagent",
            "uses_reagent",
            r"(?i)(?:reagents?|试剂|材料|药品)[:：]\s*([^\n。；;]+)",
            false,
        ),
        (
            "instrument",
            "uses_instrument",
            r"(?i)(?:instruments?|仪器|设备)[:：]\s*([^\n。；;]+)",
            false,
        ),
        (
            "sample",
            "uses_sample",
            r"(?i)(?:samples?|样本|样品)[:：]\s*([^\n。；;]+)",
            false,
        ),
        (
            "result",
            "produces_result",
            r"(?i)(?:results?|结果|观察|结论)[:：]\s*([^\n]+)",
            true,
        ),
        (
            "result",
            "produces_result",
            r"(?i)(count_matrix_gene_rows=\d+)",
            true,
        ),
    ];
    for (entity_type, relation_type, pattern, keep_sentence) in patterns {
        let regex = Regex::new(pattern).expect("knowledge extraction regex is valid");
        for captures in regex.captures_iter(&text) {
            for label in split_string(&captures[1], keep_sentence) {
                terms.push(term(entity_type, relation_type, label, None));
            }
        }
    }
    let all_text = flatten_text(&[fixed_fields, content], true).join("\n");
    let normalized = clean_label(&all_text).to_lowercase();
    if normalized.contains("htseq 生成基因级原始计数")
        || normalized.contains("raw gene-level count")
    {
        terms.push(term(
            "result",
            "produces_result",
            "基因级 HTSeq 计数矩阵".to_owned(),
            Some("data_boundary"),
        ));
        terms.push(term(
            "result",
            "produces_result",
            "不是原始 FASTQ".to_owned(),
            Some("data_boundary"),
        ));
    }
    if normalized.contains("不据此进行差异表达显著性推断") {
        terms.push(term(
            "result",
            "produces_result",
            "不据此进行差异表达显著性推断".to_owned(),
            Some("data_boundary"),
        ));
    }
    dedupe_terms(terms)
}

fn collect_structured(value: &Value, terms: &mut Vec<ExtractedTerm>) {
    match value {
        Value::Object(fields) => {
            for (key, item) in fields {
                if let Some((entity_type, relation_type, role, keep_sentence)) = classify_key(key) {
                    for label in split_value(item, keep_sentence) {
                        terms.push(term(entity_type, relation_type, label, role));
                    }
                }
                collect_structured(item, terms);
            }
        }
        Value::Array(items) => {
            for item in items {
                collect_structured(item, terms);
            }
        }
        _ => {}
    }
}

fn classify_key(key: &str) -> Option<(&'static str, &'static str, Option<&'static str>, bool)> {
    let key = key.to_lowercase();
    let exact = match key.as_str() {
        "cell_line" => Some((
            "biological_source",
            "has_biological_source",
            Some("cell_line"),
            false,
        )),
        "cell_type" => Some((
            "biological_source",
            "has_biological_source",
            Some("cell_type"),
            false,
        )),
        "condition" => Some(("condition", "has_condition", Some("group"), false)),
        "shrna_construct" => Some(("condition", "has_condition", Some("perturbation"), false)),
        "treatment" => Some(("condition", "has_condition", Some("treatment"), false)),
        "culture_condition" => Some(("condition", "has_condition", Some("culture"), false)),
        "replicate_label" => Some(("condition", "has_condition", Some("replicate"), false)),
        "alignment_method" => Some((
            "software",
            "uses_software",
            Some("alignment_software"),
            false,
        )),
        "count_method" => Some(("software", "uses_software", Some("count_software"), false)),
        "processing_software" => Some((
            "software",
            "uses_software",
            Some("processing_software"),
            false,
        )),
        "source_accession" => Some(("identifier", "has_identifier", Some("geo_accession"), false)),
        "sra_accession" => Some(("identifier", "has_identifier", Some("sra_accession"), false)),
        "biosample_accession" => Some((
            "identifier",
            "has_identifier",
            Some("biosample_accession"),
            false,
        )),
        "count_column" => Some(("identifier", "has_identifier", Some("count_column"), false)),
        "genome_build" => Some((
            "identifier",
            "has_identifier",
            Some("reference_genome"),
            false,
        )),
        _ => None,
    };
    if exact.is_some() {
        return exact;
    }
    let aliases: [(&[&str], &str, &str, bool); 8] = [
        (
            &["reagent", "试剂", "材料", "药品"],
            "reagent",
            "uses_reagent",
            false,
        ),
        (
            &["instrument", "仪器", "设备"],
            "instrument",
            "uses_instrument",
            false,
        ),
        (&["sample", "样本", "样品"], "sample", "uses_sample", false),
        (
            &["result", "结果", "观察", "结论"],
            "result",
            "produces_result",
            true,
        ),
        (
            &["cell_line", "cell type", "细胞系", "细胞类型"],
            "biological_source",
            "has_biological_source",
            false,
        ),
        (
            &["condition", "treatment", "培养条件", "分组"],
            "condition",
            "has_condition",
            false,
        ),
        (
            &["software", "计数方法", "处理软件", "比对软件"],
            "software",
            "uses_software",
            false,
        ),
        (
            &["accession", "登录号", "参考基因组", "列名"],
            "identifier",
            "has_identifier",
            false,
        ),
    ];
    aliases
        .into_iter()
        .find(|(keys, _, _, _)| keys.iter().any(|alias| key.contains(alias)))
        .map(|(_, entity_type, relation_type, keep)| (entity_type, relation_type, None, keep))
}

fn term(
    entity_type: &'static str,
    relation_type: &'static str,
    label: String,
    role: Option<&str>,
) -> ExtractedTerm {
    let mut roles = HashSet::new();
    if let Some(role) = role {
        roles.insert(role.to_owned());
    }
    if entity_type == "result" {
        let normalized = label.to_lowercase();
        for (needle, role) in [
            ("total_count", "total_count"),
            ("detected_gene_rows", "detected_gene_rows"),
            ("count_matrix_gene_rows", "count_matrix_gene_rows"),
        ] {
            if normalized.contains(needle) {
                roles.insert(role.to_owned());
            }
        }
        if normalized.contains("fastq")
            || normalized.contains("差异表达")
            || normalized.contains("基因级 htseq 计数矩阵")
        {
            roles.insert("data_boundary".to_owned());
        }
        if normalized.contains("rin") || normalized.contains("quality") {
            roles.insert("quality_result".to_owned());
        }
    }
    ExtractedTerm {
        entity_type,
        relation_type,
        label: clean_label(&label),
        roles,
    }
}

fn split_value(value: &Value, keep_sentence: bool) -> Vec<String> {
    match value {
        Value::Array(items) => items
            .iter()
            .flat_map(|item| match item {
                // An array already declares term boundaries. Punctuation inside
                // an element belongs to that term; legacy strings still split.
                Value::String(text) => vec![text.trim().to_owned()],
                _ => split_value(item, keep_sentence),
            })
            .collect(),
        Value::String(text) => split_string(text, keep_sentence),
        Value::Null | Value::Object(_) => Vec::new(),
        other => vec![other.to_string()],
    }
}

fn split_string(value: &str, keep_sentence: bool) -> Vec<String> {
    let pattern = if keep_sentence {
        r"[\n；;]+"
    } else {
        r"[,，、；;\n]+"
    };
    Regex::new(pattern)
        .expect("term splitter is valid")
        .split(value.trim())
        .map(|item| item.trim_matches([' ', '-', '\t']))
        .filter(|item| !item.is_empty())
        .map(str::to_owned)
        .collect()
}

fn dedupe_terms(terms: Vec<ExtractedTerm>) -> Vec<ExtractedTerm> {
    let mut by_key: HashMap<(String, String), ExtractedTerm> = HashMap::new();
    for item in terms.into_iter().filter(|item| !item.label.is_empty()) {
        let key = (
            item.entity_type.to_owned(),
            normalize_entity_label(&item.label),
        );
        by_key
            .entry(key)
            .and_modify(|existing| existing.roles.extend(item.roles.clone()))
            .or_insert(item);
    }
    let mut values: Vec<_> = by_key.into_values().collect();
    values.sort_by(|left, right| {
        left.entity_type
            .cmp(right.entity_type)
            .then_with(|| left.label.cmp(&right.label))
    });
    values
}

fn flatten_text(values: &[&Value], include_structured_arrays: bool) -> Vec<String> {
    let mut output = Vec::new();
    for value in values {
        match value {
            Value::String(text) if !text.trim().is_empty() => output.push(text.trim().to_owned()),
            Value::Object(fields) => {
                for (key, item) in fields {
                    if !include_structured_arrays && item.is_array() && classify_key(key).is_some()
                    {
                        continue;
                    }
                    output.push(key.clone());
                    output.extend(flatten_text(&[item], include_structured_arrays));
                }
            }
            Value::Array(items) => {
                for item in items {
                    output.extend(flatten_text(&[item], include_structured_arrays));
                }
            }
            Value::Number(number) => output.push(number.to_string()),
            Value::Bool(boolean) => output.push(boolean.to_string()),
            _ => {}
        }
    }
    output
}

fn merge_properties(current: Value, incoming: Value) -> Value {
    let mut current = current.as_object().cloned().unwrap_or_default();
    let incoming = incoming.as_object().cloned().unwrap_or_default();
    for (key, value) in incoming {
        if key == "roles" {
            let mut roles: HashSet<String> = current
                .get("roles")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect();
            roles.extend(
                value
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(Value::as_str)
                    .map(str::to_owned),
            );
            let mut roles: Vec<_> = roles.into_iter().collect();
            roles.sort();
            current.insert("roles".to_owned(), json!(roles));
        } else {
            current.insert(key, value);
        }
    }
    Value::Object(current)
}

fn clean_label(label: &str) -> String {
    label.split_whitespace().collect::<Vec<_>>().join(" ")
}

pub(crate) fn normalize_entity_label(label: &str) -> String {
    let mut normalized = String::new();
    for character in clean_label(label).chars() {
        let character = match character as u32 {
            0xFF01..=0xFF5E => char::from_u32(character as u32 - 0xFEE0).unwrap_or(character),
            0x3000 => ' ',
            _ => character,
        };
        for lowercase in character.to_lowercase() {
            if lowercase.is_ascii_punctuation()
                || matches!(
                    lowercase,
                    '，' | '。'
                        | '、'
                        | '；'
                        | '：'
                        | '！'
                        | '？'
                        | '（'
                        | '）'
                        | '【'
                        | '】'
                        | '\u{201c}'
                        | '\u{201d}'
                        | '\u{2018}'
                        | '\u{2019}'
                        | '—'
                        | '–'
                        | '·'
                )
            {
                normalized.push(' ');
            } else {
                normalized.push(lowercase);
            }
        }
    }
    let result: String = normalized.split_whitespace().collect::<Vec<_>>().join(" ");
    resolve_synonyms(&result)
}

/// 科研术语同义词消歧：将常见缩写/别名统一为规范形式。
/// 每个同义词组的首个元素为规范形式。
static ENTITY_SYNONYMS: OnceLock<HashMap<&'static str, &'static str>> = OnceLock::new();

fn entity_synonyms() -> &'static HashMap<&'static str, &'static str> {
    ENTITY_SYNONYMS.get_or_init(|| {
        let groups: Vec<(&str, &[&str])> = vec![
            ("磷酸盐缓冲液", &["pbs"]),
            ("聚合酶链反应", &["pcr"]),
            ("western blot", &["wb", "免疫印迹"]),
            (
                "实时荧光定量聚合酶链反应",
                &["rt-qpcr", "qpcr", "real-time pcr"],
            ),
            ("十二烷基硫酸钠", &["sds"]),
            ("乙二胺四乙酸", &["edta"]),
            ("三羟甲基氨基甲烷", &["tris"]),
            ("二甲基亚砜", &["dmso"]),
            ("牛血清白蛋白", &["bsa"]),
            ("胎牛血清", &["fbs", "fetal bovine serum"]),
            ("光密度", &["od", "optical density"]),
            ("细胞计数试剂盒", &["cck-8", "cck8"]),
            ("转录组", &["rna-seq", "rnaseq"]),
        ];
        let mut map = HashMap::new();
        for (canonical, synonyms) in groups {
            for synonym in synonyms {
                map.insert(*synonym, canonical);
            }
        }
        map
    })
}

fn resolve_synonyms(normalized: &str) -> String {
    let synonyms = entity_synonyms();
    if synonyms.is_empty() {
        return normalized.to_owned();
    }
    // 整体匹配优先
    if let Some(&canonical) = synonyms.get(normalized) {
        return canonical.to_owned();
    }
    // 逐 token 替换
    let tokens: Vec<&str> = normalized.split_whitespace().collect();
    let mut changed = false;
    let resolved: Vec<&str> = tokens
        .iter()
        .map(|token| {
            if let Some(&canonical) = synonyms.get(token) {
                changed = true;
                canonical
            } else {
                token
            }
        })
        .collect();
    if changed {
        resolved.join(" ")
    } else {
        normalized.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::{extract_terms, normalize_entity_label, resolve_synonyms, split_string};
    use serde_json::json;

    #[tokio::test]
    async fn t148_run_and_fact_relations_preserve_exact_version_provenance() {
        use crate::{
            config::Settings,
            db::{connect_database, initialize_database},
        };
        use sha2::{Digest, Sha256};
        use std::collections::HashMap;
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let username = format!("kg_provenance_{}", uuid::Uuid::new_v4().simple());
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            ("SECRET_KEY".to_owned(), "kg-provenance-test".to_owned()),
            ("BOOTSTRAP_ADMIN_USERNAME".to_owned(), username.clone()),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let user_id: i32 = sqlx::query_scalar("SELECT id FROM users WHERE username=$1")
            .bind(username)
            .fetch_one(&pool)
            .await
            .unwrap();
        let mut transaction = pool.begin().await.unwrap();
        let project_id: i32 = sqlx::query_scalar("INSERT INTO projects (name,is_sensitive,status,approval_enabled,owner_user_id) VALUES ('KG provenance test',false,'ACTIVE',true,$1) RETURNING id")
            .bind(user_id).fetch_one(&mut *transaction).await.unwrap();
        let note_id: i32 = sqlx::query_scalar("INSERT INTO experiment_notes (project_id,title,experiment_type,owner_user_id,status) VALUES ($1,'Versioned extraction','PCR',$2,'APPROVED') RETURNING id")
            .bind(project_id).bind(user_id).fetch_one(&mut *transaction).await.unwrap();
        let mut first_run_id = None;
        let mut first_detail = None;
        for (number, fixed_fields) in [
            json!({"samples":["样本1、2"]}),
            json!({"samples":["样本3、4"]}),
        ]
        .into_iter()
        .enumerate()
        {
            let content = json!({"text":"仪器：PCR 仪"});
            let version_id: i32 = sqlx::query_scalar("INSERT INTO note_versions (note_id,version_number,fixed_fields_json,content_json,created_by,is_locked) VALUES ($1,$2,$3,$4,$5,true) RETURNING id")
                .bind(note_id).bind(number as i32 + 1).bind(&fixed_fields).bind(&content).bind(user_id)
                .fetch_one(&mut *transaction).await.unwrap();
            sqlx::query("UPDATE experiment_notes SET current_version_id=$1 WHERE id=$2")
                .bind(version_id)
                .bind(note_id)
                .execute(&mut *transaction)
                .await
                .unwrap();
            let run = super::extract_note(&mut transaction, note_id, user_id, true)
                .await
                .unwrap();
            assert_eq!(
                run.message.as_deref(),
                Some("Knowledge graph extraction completed")
            );
            let detail: Option<serde_json::Value> = sqlx::query_scalar("SELECT detail_json FROM audit_logs WHERE action='kg_extraction_provenance' AND target_type='kg_extraction_run' AND target_id=$1")
                .bind(run.id).fetch_optional(&mut *transaction).await.unwrap();
            let detail =
                detail.expect("each extraction run must have provenance in the same transaction");
            let expected_hash = format!(
                "{:x}",
                Sha256::digest(
                    serde_json::to_vec(&json!({"fixed_fields":fixed_fields,"content":content}))
                        .unwrap()
                )
            );
            assert_eq!(detail["source_note_version_id"], version_id);
            assert_eq!(detail["content_hash"], expected_hash);
            assert_eq!(detail["source_status"], "available");
            assert!(detail["rule_version"]
                .as_str()
                .is_some_and(|value| !value.is_empty()));
            let facts: Vec<serde_json::Value> = sqlx::query_scalar("SELECT properties FROM kg_relations WHERE source_type='note_extraction' AND source_id=$1")
                .bind(note_id).fetch_all(&mut *transaction).await.unwrap();
            assert!(!facts.is_empty());
            for fact in facts {
                for key in ["source_note_version_id", "content_hash", "rule_version"] {
                    assert_eq!(fact[key], detail[key]);
                }
            }
            if number == 0 {
                first_run_id = Some(run.id);
                first_detail = Some(detail);
            }
        }
        let retained: serde_json::Value = sqlx::query_scalar("SELECT detail_json FROM audit_logs WHERE action='kg_extraction_provenance' AND target_id=$1")
            .bind(first_run_id).fetch_one(&mut *transaction).await.unwrap();
        assert_eq!(
            retained,
            first_detail.unwrap(),
            "later rebuilds must not rewrite earlier run provenance"
        );
        sqlx::query("UPDATE experiment_notes SET current_version_id=NULL WHERE id=$1")
            .bind(note_id)
            .execute(&mut *transaction)
            .await
            .unwrap();
        let no_version = super::extract_note(&mut transaction, note_id, user_id, true)
            .await
            .unwrap();
        let detail: serde_json::Value = sqlx::query_scalar("SELECT detail_json FROM audit_logs WHERE action='kg_extraction_provenance' AND target_id=$1")
            .bind(no_version.id).fetch_one(&mut *transaction).await.unwrap();
        assert!(detail["source_note_version_id"].is_null());
        assert!(detail["content_hash"].is_null());
        assert_eq!(detail["source_status"], "no_current_version");
        transaction.rollback().await.unwrap();
        let rolled_back_audits: i64 = sqlx::query_scalar("SELECT count(*) FROM audit_logs WHERE project_id=$1 AND action='kg_extraction_provenance'")
            .bind(project_id).fetch_one(&pool).await.unwrap();
        assert_eq!(rolled_back_audits, 0);
    }

    #[test]
    fn test_graph_term_normalization_and_splitting() {
        assert_eq!(
            normalize_entity_label("Ｔａｑ-DNA Polymerase"),
            "taq dna polymerase"
        );
        assert_eq!(split_string("PBS、Trypsin", false), ["PBS", "Trypsin"]);
        assert_eq!(
            split_string("初始结果；第二结果", true),
            ["初始结果", "第二结果"]
        );
    }

    #[test]
    fn t148_array_elements_preserve_t136_sample_punctuation() {
        let sample = "plates from Madina, Taylor, and Janella’s transformation on July 5th";
        let terms = extract_terms(&json!({"samples": [sample]}), &json!({}));
        let labels: Vec<_> = terms
            .iter()
            .filter(|term| term.entity_type == "sample")
            .map(|term| term.label.as_str())
            .collect();
        assert_eq!(labels, [sample]);
    }

    #[test]
    fn t148_array_labels_are_not_resplit_by_body_regex() {
        let terms = extract_terms(
            &json!({"samples": ["样本：cDNA 样本 1、2、阴性对照"]}),
            &json!({"text": "样本：独立正文样本"}),
        );
        let labels: Vec<_> = terms
            .iter()
            .filter(|term| term.entity_type == "sample")
            .map(|term| term.label.as_str())
            .collect();
        assert_eq!(labels.len(), 2);
        assert!(labels.contains(&"样本：cDNA 样本 1、2、阴性对照"));
        assert!(labels.contains(&"独立正文样本"));
    }

    #[test]
    fn t148_chinese_arrays_dedupe_and_keep_body_supplements() {
        let terms = extract_terms(
            &json!({"samples": ["cDNA 样本 1、2、阴性对照", "cDNA 样本 1、2、阴性对照"],
                "reagents": "PBS、Trypsin", "results": ["初始结果；第二结果"]}),
            &json!({"text": "仪器：BioTek Synergy H1\n结果：细胞活力 95%"}),
        );
        let labels = |kind: &str| -> Vec<&str> {
            terms
                .iter()
                .filter(|term| term.entity_type == kind)
                .map(|term| term.label.as_str())
                .collect()
        };
        assert_eq!(labels("sample"), ["cDNA 样本 1、2、阴性对照"]);
        assert_eq!(labels("reagent").len(), 2);
        assert!(labels("reagent").contains(&"PBS"));
        assert!(labels("reagent").contains(&"Trypsin"));
        assert_eq!(labels("instrument"), ["BioTek Synergy H1"]);
        assert!(labels("result").contains(&"初始结果；第二结果"));
        assert!(labels("result").contains(&"细胞活力 95%"));
    }

    #[test]
    fn test_result_quality_roles_match_python_extraction() {
        let terms = extract_terms(&json!({}), &json!({"results": "RIN=8.5; quality=good"}));
        let roles = terms
            .iter()
            .filter(|term| term.entity_type == "result")
            .flat_map(|term| term.roles.iter())
            .collect::<std::collections::HashSet<_>>();

        assert!(roles.iter().any(|role| role.as_str() == "quality_result"));
    }

    /// 锁定“前缀包含关键词可匹配”行为：“使用试剂：/实验结果：”中的
    /// “试剂：/结果：”子串应能命中正则，保证 content_text 归一后的
    /// content_json["text"] 自由文本可被提取。
    #[test]
    fn test_extract_terms_from_free_text_content_text_prefixes() {
        let content = json!({
            "text": "使用试剂：CCK-8 试剂盒、DMEM 培养基\n使用仪器：BioTek Synergy H1\n实验结果：细胞活力 95%"
        });
        let terms = extract_terms(&json!({}), &content);
        let has_term = |entity_type: &str, relation_type: &str, label: &str| {
            terms.iter().any(|term| {
                term.entity_type == entity_type
                    && term.relation_type == relation_type
                    && term.label == label
            })
        };
        assert!(has_term("reagent", "uses_reagent", "CCK-8 试剂盒"));
        assert!(has_term("reagent", "uses_reagent", "DMEM 培养基"));
        assert!(has_term(
            "instrument",
            "uses_instrument",
            "BioTek Synergy H1"
        ));
        assert!(has_term("result", "produces_result", "细胞活力 95%"));
    }

    #[test]
    fn test_resolve_synonyms_maps_abbreviations_to_canonical() {
        assert_eq!(resolve_synonyms("pbs"), "磷酸盐缓冲液");
        assert_eq!(resolve_synonyms("wb"), "western blot");
        assert_eq!(resolve_synonyms("fbs"), "胎牛血清");
        assert_eq!(resolve_synonyms("cck-8"), "细胞计数试剂盒");
        assert_eq!(resolve_synonyms("rna-seq"), "转录组");
    }

    #[test]
    fn test_resolve_synonyms_preserves_unknown_tokens() {
        assert_eq!(resolve_synonyms("dmem 培养基"), "dmem 培养基");
        assert_eq!(resolve_synonyms("taq polymerase"), "taq polymerase");
    }

    #[test]
    fn test_normalize_entity_label_includes_synonym_resolution() {
        // "PBS" 归一化后为 "pbs"，再经同义词解析为 "磷酸盐缓冲液"
        assert_eq!(normalize_entity_label("PBS"), "磷酸盐缓冲液");
        // "WB" → "wb" → "western blot"
        assert_eq!(normalize_entity_label("WB"), "western blot");
        // "FBS" → "fbs" → "胎牛血清"
        assert_eq!(normalize_entity_label("FBS"), "胎牛血清");
    }

    #[test]
    fn test_normalize_entity_label_synonym_in_compound_label() {
        // 复合标签中仅替换匹配的 token
        let result = normalize_entity_label("PBS buffer");
        assert_eq!(result, "磷酸盐缓冲液 buffer");
    }
}
