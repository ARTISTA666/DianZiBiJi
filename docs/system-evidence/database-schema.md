# 数据库实表结构

> 本文件由运行中的数据库反射生成，不是按模型文件手工填写。

## agent_generation_runs

当前记录数：2

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('agent_generation_runs_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| user_id | INTEGER | 否 |  |
| task_type | VARCHAR(60) | 否 |  |
| input_params_json | JSON | 否 |  |
| title | VARCHAR(255) | 否 |  |
| body | TEXT | 否 |  |
| source_note_ids_json | JSON | 否 |  |
| source_file_ids_json | JSON | 否 |  |
| source_graph_relation_ids_json | JSON | 否 |  |
| provider | VARCHAR(40) | 否 |  |
| model_name | VARCHAR(120) | 是 |  |
| prompt_version | VARCHAR(40) | 否 |  |
| usage_json | JSON | 否 |  |
| status | VARCHAR(40) | 否 |  |
| response_ms | INTEGER | 否 |  |
| message | TEXT | 是 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：project_id -> projects(id); user_id -> users(id)
- 索引：ix_agent_generation_runs_project_id, ix_agent_generation_runs_provider, ix_agent_generation_runs_status, ix_agent_generation_runs_task_type, ix_agent_generation_runs_user_id

## ai_experiment_runs

当前记录数：8

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('ai_experiment_runs_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| created_by | INTEGER | 否 |  |
| name | VARCHAR(255) | 否 |  |
| status | VARCHAR(40) | 否 |  |
| questions_json | JSON | 否 |  |
| modes_json | JSON | 否 |  |
| config_snapshot_json | JSON | 否 |  |
| summary_json | JSON | 否 |  |
| total_cases | INTEGER | 否 |  |
| completed_cases | INTEGER | 否 |  |
| failed_cases | INTEGER | 否 |  |
| created_at | TIMESTAMP | 否 | now() |
| completed_at | TIMESTAMP | 是 |  |

- 主键：id
- 外键：created_by -> users(id); project_id -> projects(id)
- 索引：ix_ai_experiment_runs_created_by, ix_ai_experiment_runs_project_id, ix_ai_experiment_runs_status

## ai_query_evaluations

当前记录数：0

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('ai_query_evaluations_id_seq'::regclass) |
| query_log_id | INTEGER | 否 |  |
| evaluator_user_id | INTEGER | 否 |  |
| score | INTEGER | 否 |  |
| is_accurate | BOOLEAN | 否 |  |
| is_traceable | BOOLEAN | 否 |  |
| comment | TEXT | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |
| review_protocol | VARCHAR(40) | 否 | 'unblinded'::character varying |

- 主键：id
- 外键：evaluator_user_id -> users(id); query_log_id -> ai_query_logs(id)
- 索引：ix_ai_query_evaluations_evaluator_user_id, ix_ai_query_evaluations_query_log_id, ix_ai_query_evaluations_review_protocol, uq_ai_query_evaluation_log_evaluator

## ai_query_logs

当前记录数：303

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('ai_query_logs_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| user_id | INTEGER | 否 |  |
| question | TEXT | 否 |  |
| answer | TEXT | 是 |  |
| rag_mode | VARCHAR(40) | 否 |  |
| graph_hit_count | INTEGER | 否 |  |
| source_count | INTEGER | 否 |  |
| response_ms | INTEGER | 否 |  |
| conversation_id | VARCHAR(160) | 是 |  |
| graph_context_json | JSON | 否 |  |
| sources_json | JSON | 否 |  |
| provider | VARCHAR(40) | 否 |  |
| model_name | VARCHAR(120) | 是 |  |
| prompt_version | VARCHAR(40) | 否 |  |
| retrieval_config_json | JSON | 否 |  |
| usage_json | JSON | 否 |  |
| fallback_reason | TEXT | 是 |  |
| error_message | TEXT | 是 |  |
| experiment_run_id | INTEGER | 是 |  |
| experiment_case_index | INTEGER | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| experiment_repetition_index | INTEGER | 是 |  |
| experiment_execution_order | INTEGER | 是 |  |

- 主键：id
- 外键：experiment_run_id -> ai_experiment_runs(id); project_id -> projects(id); user_id -> users(id)
- 索引：ix_ai_query_logs_conversation_id, ix_ai_query_logs_experiment_run_id, ix_ai_query_logs_model_name, ix_ai_query_logs_project_id, ix_ai_query_logs_provider, ix_ai_query_logs_rag_mode, ix_ai_query_logs_user_id

## alembic_version

当前记录数：1

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| version_num | VARCHAR(32) | 否 |  |

- 主键：version_num
- 外键：无
- 索引：无

## audit_logs

当前记录数：156

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('audit_logs_id_seq'::regclass) |
| actor_user_id | INTEGER | 是 |  |
| project_id | INTEGER | 是 |  |
| action | VARCHAR(80) | 否 |  |
| target_type | VARCHAR(80) | 是 |  |
| target_id | INTEGER | 是 |  |
| detail_json | JSON | 否 |  |
| ip_address | VARCHAR(80) | 是 |  |
| user_agent | VARCHAR(255) | 是 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：actor_user_id -> users(id); project_id -> projects(id)
- 索引：ix_audit_logs_action, ix_audit_logs_actor_user_id, ix_audit_logs_project_id

## experiment_notes

当前记录数：12

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('experiment_notes_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| template_id | INTEGER | 是 |  |
| title | VARCHAR(200) | 否 |  |
| experiment_type | VARCHAR(120) | 否 |  |
| experiment_date | DATE | 是 |  |
| owner_user_id | INTEGER | 否 |  |
| status | VARCHAR(9) | 否 |  |
| current_version_id | INTEGER | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：owner_user_id -> users(id); project_id -> projects(id)
- 索引：ix_experiment_notes_experiment_type, ix_experiment_notes_owner_user_id, ix_experiment_notes_project_id, ix_experiment_notes_status, ix_experiment_notes_title

## experiment_templates

当前记录数：5

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('experiment_templates_id_seq'::regclass) |
| name | VARCHAR(120) | 否 |  |
| experiment_type | VARCHAR(120) | 否 |  |
| schema_json | JSON | 否 |  |
| default_content_json | JSON | 否 |  |
| is_active | BOOLEAN | 否 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：无
- 索引：ix_experiment_templates_experiment_type, ix_experiment_templates_name

## file_ocr_results

当前记录数：1

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('file_ocr_results_id_seq'::regclass) |
| file_id | INTEGER | 否 |  |
| project_id | INTEGER | 否 |  |
| created_by | INTEGER | 否 |  |
| file_hash | VARCHAR(64) | 否 |  |
| raw_text | TEXT | 否 |  |
| corrected_text | TEXT | 否 |  |
| extraction_method | VARCHAR(80) | 否 |  |
| character_count | INTEGER | 否 |  |
| truncated | BOOLEAN | 否 |  |
| review_status | VARCHAR(40) | 否 |  |
| reviewed_by | INTEGER | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| reviewed_at | TIMESTAMP | 是 |  |

- 主键：id
- 外键：created_by -> users(id); file_id -> files(id); project_id -> projects(id); reviewed_by -> users(id)
- 索引：ix_file_ocr_results_created_by, ix_file_ocr_results_file_hash, ix_file_ocr_results_file_id, ix_file_ocr_results_project_id, ix_file_ocr_results_review_status, ix_file_ocr_results_reviewed_by

## files

当前记录数：19

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('files_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| note_id | INTEGER | 是 |  |
| uploaded_by | INTEGER | 否 |  |
| file_category | VARCHAR(18) | 否 |  |
| original_filename | VARCHAR(255) | 否 |  |
| storage_path | VARCHAR(500) | 否 |  |
| mime_type | VARCHAR(160) | 是 |  |
| file_size | INTEGER | 否 |  |
| file_hash | VARCHAR(64) | 否 |  |
| status | VARCHAR(8) | 否 |  |
| knowledge_sync_status | VARCHAR(40) | 否 |  |
| knowledge_synced_at | TIMESTAMP | 是 |  |
| knowledge_sync_message | TEXT | 是 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：note_id -> experiment_notes(id); project_id -> projects(id); uploaded_by -> users(id)
- 索引：ix_files_file_hash, ix_files_knowledge_sync_status, ix_files_note_id, ix_files_project_id, ix_files_status, ix_files_uploaded_by

## group_members

当前记录数：0

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('group_members_id_seq'::regclass) |
| group_id | INTEGER | 否 |  |
| user_id | INTEGER | 否 |  |
| group_role | VARCHAR(64) | 否 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：group_id -> groups(id); user_id -> users(id)
- 索引：ix_group_members_group_id, ix_group_members_user_id

## group_projects

当前记录数：0

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('group_projects_id_seq'::regclass) |
| group_id | INTEGER | 否 |  |
| project_id | INTEGER | 否 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：group_id -> groups(id); project_id -> projects(id)
- 索引：ix_group_projects_group_id, ix_group_projects_project_id

## groups

当前记录数：0

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('groups_id_seq'::regclass) |
| name | VARCHAR(120) | 否 |  |
| description | TEXT | 是 |  |
| leader_user_id | INTEGER | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：leader_user_id -> users(id)
- 索引：groups_name_key

## kg_entities

当前记录数：126

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('kg_entities_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| entity_type | VARCHAR(40) | 否 |  |
| label | VARCHAR(255) | 否 |  |
| normalized_label | VARCHAR(255) | 否 |  |
| natural_key | VARCHAR(320) | 否 |  |
| source_type | VARCHAR(40) | 是 |  |
| source_id | INTEGER | 是 |  |
| properties | JSON | 否 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：project_id -> projects(id)
- 索引：ix_kg_entities_entity_type, ix_kg_entities_label, ix_kg_entities_natural_key, ix_kg_entities_normalized_label, ix_kg_entities_project_id, ix_kg_entities_source_id, ix_kg_entities_source_type, uq_kg_entity_project_natural_key

## kg_extraction_runs

当前记录数：20

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('kg_extraction_runs_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| note_id | INTEGER | 否 |  |
| triggered_by | INTEGER | 否 |  |
| status | VARCHAR(40) | 否 |  |
| extracted_entities | INTEGER | 否 |  |
| extracted_relations | INTEGER | 否 |  |
| message | TEXT | 是 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：note_id -> experiment_notes(id); project_id -> projects(id); triggered_by -> users(id)
- 索引：ix_kg_extraction_runs_note_id, ix_kg_extraction_runs_project_id, ix_kg_extraction_runs_status, ix_kg_extraction_runs_triggered_by

## kg_relations

当前记录数：222

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('kg_relations_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| source_entity_id | INTEGER | 否 |  |
| target_entity_id | INTEGER | 否 |  |
| relation_type | VARCHAR(60) | 否 |  |
| source_type | VARCHAR(40) | 是 |  |
| source_id | INTEGER | 是 |  |
| confidence | DOUBLE PRECISION | 否 |  |
| properties | JSON | 否 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：project_id -> projects(id); source_entity_id -> kg_entities(id); target_entity_id -> kg_entities(id)
- 索引：ix_kg_relations_project_id, ix_kg_relations_relation_type, ix_kg_relations_source_entity_id, ix_kg_relations_source_id, ix_kg_relations_source_type, ix_kg_relations_target_entity_id, uq_kg_relation_project_source_target_type

## note_approvals

当前记录数：12

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('note_approvals_id_seq'::regclass) |
| note_id | INTEGER | 否 |  |
| version_id | INTEGER | 否 |  |
| reviewer_user_id | INTEGER | 否 |  |
| action | VARCHAR(40) | 否 |  |
| comment | TEXT | 是 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：note_id -> experiment_notes(id); reviewer_user_id -> users(id); version_id -> note_versions(id)
- 索引：ix_note_approvals_action, ix_note_approvals_note_id, ix_note_approvals_reviewer_user_id, ix_note_approvals_version_id

## note_versions

当前记录数：12

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('note_versions_id_seq'::regclass) |
| note_id | INTEGER | 否 |  |
| version_number | INTEGER | 否 |  |
| fixed_fields_json | JSON | 否 |  |
| content_json | JSON | 否 |  |
| created_by | INTEGER | 否 |  |
| change_summary | TEXT | 是 |  |
| is_locked | BOOLEAN | 否 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：created_by -> users(id); note_id -> experiment_notes(id)
- 索引：ix_note_versions_note_id

## project_members

当前记录数：2

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('project_members_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| user_id | INTEGER | 否 |  |
| project_role | VARCHAR(8) | 否 |  |
| can_read | BOOLEAN | 否 |  |
| can_write | BOOLEAN | 否 |  |
| can_review | BOOLEAN | 否 |  |
| can_manage | BOOLEAN | 否 |  |
| created_at | TIMESTAMP | 否 | now() |
| can_evaluate | BOOLEAN | 否 | false |

- 主键：id
- 外键：project_id -> projects(id); user_id -> users(id)
- 索引：ix_project_members_project_id, ix_project_members_user_id, uq_project_member

## project_rag_datasets

当前记录数：4

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('project_rag_datasets_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| dify_dataset_id | VARCHAR(120) | 否 |  |
| dify_dataset_name | VARCHAR(255) | 否 |  |
| status | VARCHAR(40) | 否 |  |
| created_by | INTEGER | 否 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |
| provider | VARCHAR(40) | 否 | 'local_deepseek'::character varying |
| embedding_model | VARCHAR(160) | 否 | 'BAAI/bge-small-zh-v1.5'::character varying |
| generation_model | VARCHAR(120) | 否 | 'deepseek-v4-flash'::character varying |

- 主键：id
- 外键：created_by -> users(id); project_id -> projects(id)
- 索引：ix_project_rag_datasets_created_by, ix_project_rag_datasets_dify_dataset_id, ix_project_rag_datasets_project_id, ix_project_rag_datasets_provider, ix_project_rag_datasets_status, uq_project_rag_dataset

## project_reviewers

当前记录数：0

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('project_reviewers_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| user_id | INTEGER | 否 |  |
| review_scope | VARCHAR(120) | 否 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：project_id -> projects(id); user_id -> users(id)
- 索引：ix_project_reviewers_project_id, ix_project_reviewers_user_id, uq_project_reviewer

## projects

当前记录数：4

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('projects_id_seq'::regclass) |
| name | VARCHAR(160) | 否 |  |
| description | TEXT | 是 |  |
| is_sensitive | BOOLEAN | 否 |  |
| status | VARCHAR(8) | 否 |  |
| approval_enabled | BOOLEAN | 否 |  |
| owner_user_id | INTEGER | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：owner_user_id -> users(id)
- 索引：ix_projects_name

## rag_document_chunks

当前记录数：999

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('rag_document_chunks_id_seq'::regclass) |
| project_id | INTEGER | 否 |  |
| file_id | INTEGER | 否 |  |
| chunk_index | INTEGER | 否 |  |
| content | TEXT | 否 |  |
| content_hash | VARCHAR(64) | 否 |  |
| character_count | INTEGER | 否 |  |
| embedding | NULL | 否 |  |
| metadata_json | JSON | 否 |  |
| created_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：file_id -> files(id); project_id -> projects(id)
- 索引：ix_rag_document_chunks_content_hash, ix_rag_document_chunks_file_id, ix_rag_document_chunks_project_id, uq_rag_chunk_file_index

## rag_file_syncs

当前记录数：9

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('rag_file_syncs_id_seq'::regclass) |
| file_id | INTEGER | 否 |  |
| project_id | INTEGER | 否 |  |
| dify_dataset_id | VARCHAR(120) | 否 |  |
| dify_document_id | VARCHAR(120) | 是 |  |
| sync_status | VARCHAR(40) | 否 |  |
| sync_message | TEXT | 是 |  |
| synced_at | TIMESTAMP | 是 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |
| chunk_count | INTEGER | 否 | 0 |
| content_hash | VARCHAR(64) | 是 |  |

- 主键：id
- 外键：file_id -> files(id); project_id -> projects(id)
- 索引：ix_rag_file_syncs_content_hash, ix_rag_file_syncs_dify_dataset_id, ix_rag_file_syncs_dify_document_id, ix_rag_file_syncs_file_id, ix_rag_file_syncs_project_id, ix_rag_file_syncs_sync_status, uq_rag_file_sync_file

## search_documents

当前记录数：0

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('search_documents_id_seq'::regclass) |
| note_id | INTEGER | 否 |  |
| project_id | INTEGER | 否 |  |
| title | VARCHAR(300) | 否 |  |
| search_text | TEXT | 否 |  |
| source_ids | TEXT | 否 |  |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：note_id -> experiment_notes(id); project_id -> projects(id)
- 索引：ix_search_documents_note_id, ix_search_documents_project_id

## users

当前记录数：2

| 字段 | 类型 | 可空 | 默认值 |
| --- | --- | --- | --- |
| id | INTEGER | 否 | nextval('users_id_seq'::regclass) |
| username | VARCHAR(64) | 否 |  |
| password_hash | VARCHAR(255) | 否 |  |
| display_name | VARCHAR(120) | 否 |  |
| email | VARCHAR(255) | 是 |  |
| role | VARCHAR(13) | 否 |  |
| status | VARCHAR(8) | 否 |  |
| created_at | TIMESTAMP | 否 | now() |
| updated_at | TIMESTAMP | 否 | now() |

- 主键：id
- 外键：无
- 索引：ix_users_id, ix_users_username
