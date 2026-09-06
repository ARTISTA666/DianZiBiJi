use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, patch, post},
    Json, Router,
};
use serde_json::{json, Value};

use crate::{
    api::auth::CurrentUser,
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    kg_blueprint::{
        parse_blueprint_document, patch_blueprint_edge, patch_blueprint_node, project_blueprint,
    },
    models::{
        BlueprintEdgePatchRequest, BlueprintNodePatchRequest, BlueprintParseRequest,
        BlueprintParseResponse, KnowledgeBlueprintRead, UserRecord,
    },
    permissions::{can_write_project, require_project_access},
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/projects/{project_id}/kg/blueprint/parse",
            post(parse_project_blueprint),
        )
        .route(
            "/projects/{project_id}/kg/blueprint",
            get(get_project_blueprint),
        )
        .route(
            "/projects/{project_id}/kg/blueprint/nodes/{node_id}",
            patch(patch_project_blueprint_node),
        )
        .route(
            "/projects/{project_id}/kg/blueprint/edges/{edge_id}",
            patch(patch_project_blueprint_edge),
        )
}

async fn parse_project_blueprint(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<BlueprintParseRequest>,
) -> Result<Json<BlueprintParseResponse>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let response =
        parse_blueprint_document(&state, &mut transaction, project_id, user.id, &payload).await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "blueprint_parse",
            target_type: Some("kg_blueprint_document"),
            target_id: Some(response.document_id),
            detail: json!({
                "title": payload.title,
                "source_kind": payload.source_kind,
                "parse_mode": response.parse_mode,
                "nodes_added": response.nodes_added,
                "nodes_updated": response.nodes_updated,
                "edges_added": response.edges_added,
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(response))
}

async fn get_project_blueprint(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<KnowledgeBlueprintRead>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    let blueprint = project_blueprint(&mut transaction, project_id).await?;
    transaction.commit().await?;
    Ok(Json(blueprint))
}

async fn patch_project_blueprint_node(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, node_id)): Path<(i32, i32)>,
    Json(payload): Json<BlueprintNodePatchRequest>,
) -> Result<Json<Value>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    patch_blueprint_node(
        &mut transaction,
        project_id,
        node_id,
        payload.status.as_deref(),
        payload.description.as_deref(),
    )
    .await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "blueprint_node_patch",
            target_type: Some("kg_blueprint_node"),
            target_id: Some(node_id),
            detail: json!({
                "status": payload.status,
                "description_changed": payload.description.is_some(),
            }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({"updated": true, "id": node_id})))
}

async fn patch_project_blueprint_edge(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, edge_id)): Path<(i32, i32)>,
    Json(payload): Json<BlueprintEdgePatchRequest>,
) -> Result<Json<Value>, ApiError> {
    require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    patch_blueprint_edge(
        &mut transaction,
        project_id,
        edge_id,
        payload.status.as_deref(),
    )
    .await?;
    write_audit(
        &mut *transaction,
        AuditEvent {
            actor_user_id: Some(user.id),
            project_id: Some(project_id),
            action: "blueprint_edge_patch",
            target_type: Some("kg_blueprint_edge"),
            target_id: Some(edge_id),
            detail: json!({ "status": payload.status }),
            ip_address: client.ip_opt().map(str::to_owned),
            user_agent: client.ua_opt().map(str::to_owned),
        },
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({"updated": true, "id": edge_id})))
}

async fn require_write(
    state: &AppState,
    user: &UserRecord,
    project_id: i32,
) -> Result<(), ApiError> {
    if can_write_project(&state.pool, user, project_id).await? {
        Ok(())
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Write permission required",
        ))
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use axum::{
        body::{to_bytes, Body},
        http::{Request, StatusCode},
        Router,
    };
    use serde_json::{json, Value};
    use tower::ServiceExt;
    use uuid::Uuid;

    use crate::{
        build_app,
        config::Settings,
        db::{connect_database, initialize_database},
        AppState,
    };

    async fn call(
        app: &Router,
        method: &str,
        path: &str,
        token: Option<&str>,
        body: Option<Value>,
    ) -> (StatusCode, Value) {
        let mut request = Request::builder().method(method).uri(path);
        if let Some(token) = token {
            request = request.header("authorization", format!("Bearer {token}"));
        }
        if body.is_some() {
            request = request.header("content-type", "application/json");
        }
        let response = app
            .clone()
            .oneshot(
                request
                    .body(body.map_or_else(Body::empty, |value| Body::from(value.to_string())))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 256 * 1024).await.unwrap();
        let body = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, body)
    }

    async fn setup(database_url: &str, prefix: &str) -> (Router, String, i64) {
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("{prefix}_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url.to_owned()),
            ("SECRET_KEY".to_owned(), "rust-blueprint-secret".to_owned()),
            (
                "BOOTSTRAP_ADMIN_USERNAME".to_owned(),
                admin_username.clone(),
            ),
            (
                "BOOTSTRAP_ADMIN_PASSWORD".to_owned(),
                "RustAdmin123!".to_owned(),
            ),
        ]))
        .unwrap();
        let pool = connect_database(&settings).await.unwrap();
        initialize_database(&pool, &settings).await.unwrap();
        let app = build_app(AppState::new(pool, settings).unwrap());
        let (_, login) = call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": admin_username, "password": "RustAdmin123!"})),
        )
        .await;
        let admin = login["access_token"].as_str().unwrap().to_owned();
        let (_, project) = call(
            &app,
            "POST",
            "/projects",
            Some(&admin),
            Some(json!({
                "name": format!("Blueprint Project {suffix}"),
                "approval_enabled": false
            })),
        )
        .await;
        let project_id = project["id"].as_i64().unwrap();
        (app, admin, project_id)
    }

    /// 规则兜底解析（测试库未配置 AI key）：计划文本中的试剂/仪器/结果应成为蓝图节点。
    #[tokio::test]
    async fn test_blueprint_rule_parse_and_coverage() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, project_id) = setup(&database_url, "bp_rule").await;

        let plan_text = "本课题使用试剂：CCK-8 试剂盒、DMEM 培养基；使用仪器：BioTek Synergy H1；预期实验结果：细胞活力 95%。";
        let (parse_status, parse) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(json!({
                "title": "课题计划书",
                "source_kind": "plan_document",
                "text": plan_text
            })),
        )
        .await;
        assert_eq!(parse_status, StatusCode::OK);
        assert_eq!(parse["parse_mode"], "rule_based");
        assert!(parse["nodes_added"].as_i64().unwrap() >= 4);

        // 覆盖前：全部 planned、无证据
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(blueprint["coverage"]["covered_nodes"], 0);
        assert!(blueprint["coverage"]["total_nodes"].as_i64().unwrap() >= 4);

        // 审核通过一条笔记，抽取出的实体与蓝图节点同名 → 覆盖度上升
        let (_, note) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/notes"),
            Some(&admin),
            Some(json!({
                "title": "Viability assay",
                "experiment_type": "Cell assay",
                "fixed_fields_json": {},
                "content_text": plan_text
            })),
        )
        .await;
        let note_id = note["id"].as_i64().unwrap();
        call(
            &app,
            "POST",
            &format!("/notes/{note_id}/submit"),
            Some(&admin),
            None,
        )
        .await;
        call(
            &app,
            "POST",
            &format!("/notes/{note_id}/kg/extract"),
            Some(&admin),
            None,
        )
        .await;

        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        let covered = blueprint["coverage"]["covered_nodes"].as_i64().unwrap();
        assert!(covered >= 4, "expected coverage >= 4, got {covered}");
        assert_eq!(
            blueprint["coverage"]["covered_nodes"],
            blueprint["coverage"]["total_nodes"]
        );
        let nodes = blueprint["nodes"].as_array().unwrap();
        let covered_node = nodes
            .iter()
            .find(|node| node["evidence"]["entity_count"].as_i64().unwrap() > 0)
            .expect("expected at least one covered node");
        assert!(covered_node["evidence"]["last_evidence_at"].is_string());
    }

    /// 冲突优先级：组会纪要（priority 更小）应覆盖计划书来源的节点描述与来源；
    /// 学生手动（priority 更大）不得覆盖已有来源。
    #[tokio::test]
    async fn test_blueprint_conflict_priority_resolution() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, project_id) = setup(&database_url, "bp_prio").await;

        let plan_text = "使用试剂：CCK-8 试剂盒\n实验结果：细胞活力 95%";
        call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(json!({
                "title": "课题计划书",
                "source_kind": "plan_document",
                "text": plan_text
            })),
        )
        .await;
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        let node = blueprint["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|node| node["label"] == "CCK-8 试剂盒")
            .expect("plan node should exist");
        let node_id = node["id"].as_i64().unwrap();
        assert_eq!(node["source_kind"], "plan_document");
        assert_eq!(node["priority"], 50);

        // 组会纪要（priority 10）覆盖：来源与描述应切换
        call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(json!({
                "title": "组会纪要-09-06",
                "source_kind": "meeting_note",
                "text": "使用试剂：CCK-8 试剂盒\n实验结果：细胞活力 95%",
                "priority": 10
            })),
        )
        .await;
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        let node = blueprint["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|node| node["id"].as_i64().unwrap() == node_id)
            .expect("meeting parse should update the same node in place");
        assert_eq!(node["label"], "CCK-8 试剂盒");
        assert_eq!(node["source_kind"], "meeting_note");
        assert_eq!(node["priority"], 10);
        assert_eq!(node["source_label"], "组会纪要-09-06");

        // 手动修正 priority 100 不得覆盖 meeting_note 来源
        let patch_status = call(
            &app,
            "PATCH",
            &format!("/projects/{project_id}/kg/blueprint/nodes/{node_id}"),
            Some(&admin),
            Some(json!({"status": "retired"})),
        )
        .await;
        assert_eq!(patch_status.0, StatusCode::OK);
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        assert!(blueprint["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .all(|node| node["id"].as_i64().unwrap() != node_id));
        // 覆盖度总数同步减少
        assert_eq!(blueprint["coverage"]["total_nodes"], 1);
    }

    /// 无写权限用户不能解析/修正蓝图；同型同名活跃节点唯一（重复解析不产生重复节点）。
    #[tokio::test]
    async fn test_blueprint_idempotent_and_permission_boundaries() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, project_id) = setup(&database_url, "bp_perm").await;

        let payload = json!({
            "title": "计划书",
            "source_kind": "plan_document",
            "text": "使用试剂：PBS 缓冲液；使用仪器：离心机"
        });
        let (first_status, first) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(payload.clone()),
        )
        .await;
        assert_eq!(first_status, StatusCode::OK);
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        let total = blueprint["coverage"]["total_nodes"].as_i64().unwrap();
        let (second_status, second) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(payload),
        )
        .await;
        assert_eq!(second_status, StatusCode::OK);
        assert_eq!(second["nodes_added"], 0);
        assert!(second["nodes_updated"].as_i64().unwrap() >= 0);
        assert_eq!(first["nodes_added"], total);

        // 非项目成员（新建账号）不得读取或解析
        call(
            &app,
            "POST",
            "/users",
            Some(&admin),
            Some(json!({
                "username": "outsider_bp",
                "password": "Outsider123!",
                "display_name": "外部用户"
            })),
        )
        .await;
        let (_, outsider_login) = call(
            &app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": "outsider_bp", "password": "Outsider123!"})),
        )
        .await;
        let outsider = outsider_login["access_token"].as_str().unwrap();
        let (get_status, _) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(outsider),
            None,
        )
        .await;
        assert_eq!(get_status, StatusCode::FORBIDDEN);
        let (parse_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(outsider),
            Some(json!({
                "title": "越权",
                "source_kind": "plan_document",
                "text": "使用试剂：越权试剂"
            })),
        )
        .await;
        assert_eq!(parse_status, StatusCode::FORBIDDEN);

        // 非法来源与空文本被拒
        let (bad_source_status, _) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(json!({
                "title": "坏来源",
                "source_kind": "tweet",
                "text": "使用试剂：PBS 缓冲液"
            })),
        )
        .await;
        assert_eq!(bad_source_status, StatusCode::BAD_REQUEST);
    }
}
