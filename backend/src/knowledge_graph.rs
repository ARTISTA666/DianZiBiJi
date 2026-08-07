use std::{
    collections::{HashMap, HashSet},
    sync::OnceLock,
};

use regex::Regex;
use serde_json::{json, Value};
use sqlx::{FromRow, Postgres, Transaction};

use crate::{
    error::ApiError,
    models::{KnowledgeEntityRead, KnowledgeExtractionRunRead, KnowledgeRelationRead},
};

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
struct ExtractedTerm {
    entity_type: &'static str,
    relation_type: &'static str,
    label: String,
    roles: HashSet<String>,
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
            0,
            0,
            "failed",
            "Project not found",
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

    let version = if let Some(version_id) = note.current_version_id {
        sqlx::query_as::<_, (Value, Value)>(
            "SELECT fixed_fields_json, content_json FROM note_versions WHERE id = $1",
        )
        .bind(version_id)
        .fetch_optional(&mut **transaction)
        .await?
    } else {
        None
    };
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
            let relation = upsert_relation(
                transaction,
                note.project_id,
                note_entity,
                entity,
                term.relation_type,
                Some("note_extraction"),
                Some(note.id),
                0.7,
                json!({"method": "rule_based", "roles": roles}),
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
        entities.len() as i32,
        relations.len() as i32,
        "completed",
        "Knowledge graph extraction completed",
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
    extracted_entities: i32,
    extracted_relations: i32,
    status: &str,
    message: &str,
) -> Result<KnowledgeExtractionRunRead, ApiError> {
    Ok(sqlx::query_as::<_, KnowledgeExtractionRunRead>(
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
    .bind(extracted_entities)
    .bind(extracted_relations)
    .bind(message)
    .fetch_one(&mut **transaction)
    .await?)
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

fn extract_terms(fixed_fields: &Value, content: &Value) -> Vec<ExtractedTerm> {
    let mut terms = Vec::new();
    collect_structured(fixed_fields, &mut terms);
    collect_structured(content, &mut terms);
    let text = flatten_text(&[fixed_fields, content]).join("\n");
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
    let normalized = clean_label(&text).to_lowercase();
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
            .flat_map(|item| split_value(item, keep_sentence))
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

fn flatten_text(values: &[&Value]) -> Vec<String> {
    let mut output = Vec::new();
    for value in values {
        match value {
            Value::String(text) if !text.trim().is_empty() => output.push(text.trim().to_owned()),
            Value::Object(fields) => {
                for (key, item) in fields {
                    output.push(key.clone());
                    output.extend(flatten_text(&[item]));
                }
            }
            Value::Array(items) => {
                for item in items {
                    output.extend(flatten_text(&[item]));
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

fn normalize_entity_label(label: &str) -> String {
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
