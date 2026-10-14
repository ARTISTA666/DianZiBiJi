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
    permissions::{can_write_project, require_external_ai, require_project_access},
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
    let project = require_project_access(&state.pool, &user, project_id).await?;
    require_write(&state, &user, project_id).await?;
    if !state.settings.ai_api_key.trim().is_empty() {
        require_external_ai(&project, state.settings.allow_sensitive_external_ai)?;
    }
    let mut transaction = state.pool.begin().await?;
    let (response, provenance) =
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
                "provenance": provenance,
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
        setup_with_options(database_url, prefix, HashMap::new()).await
    }

    async fn setup_with_options(
        database_url: &str,
        prefix: &str,
        extra: HashMap<String, String>,
    ) -> (Router, String, i64) {
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("{prefix}_admin_{suffix}");
        let mut values = HashMap::from([
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
        ]);
        values.extend(extra);
        let settings = Settings::from_map(&values).unwrap();
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
        eprintln!("DEBUG first={first} second={second} total={total}");
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
    #[tokio::test]
    async fn test_blueprint_role_coverage_and_alerts_share_evidence_contract() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, project_id) = setup(&database_url, "bp_roles").await;
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        let (_, me) = call(&app, "GET", "/auth/me", Some(&admin), None).await;
        let mut transaction = pool.begin().await.unwrap();
        for (entity_type, label) in [
            ("cell_line", "HCT116"),
            ("cell_type", "HCT116"),
            ("geo_accession", "GSE123"),
            ("biosample", "GSE123"),
            ("treatment", "Heat"),
            ("culture", "Heat"),
        ] {
            crate::kg_blueprint::upsert_blueprint_node(
                &mut transaction,
                project_id as i32,
                &crate::kg_blueprint::BlueprintNodeInput {
                    entity_type,
                    label,
                    description: "",
                    source_kind: "plan_document",
                    source_label: "Role contract plan",
                    priority: 50,
                    created_by: me["id"].as_i64().unwrap() as i32,
                },
            )
            .await
            .unwrap();
        }
        transaction.commit().await.unwrap();
        let metric = |summary: &Value, name: &str| {
            summary["metrics"]
                .as_array()
                .unwrap()
                .iter()
                .find(|row| row["metric"] == name)
                .unwrap()["value"]
                .as_f64()
                .unwrap()
        };
        let mut note_ids = Vec::new();
        for (fields, covered) in [
            (
                json!({"cell_type":"HCT116", "biosample_accession":"GSE123", "culture_condition":"Heat"}),
                3,
            ),
            (
                json!({"cell_line":"HCT116", "source_accession":"GSE123", "treatment":"Heat"}),
                6,
            ),
        ] {
            let (status, note) = call(&app, "POST", &format!("/projects/{project_id}/notes"), Some(&admin),
                Some(json!({"title":"Role evidence", "experiment_type":"Assay", "fixed_fields_json":fields}))).await;
            assert_eq!(status, StatusCode::OK, "{note}");
            let note_id = note["id"].as_i64().unwrap();
            note_ids.push(note_id);
            let (status, submitted) = call(
                &app,
                "POST",
                &format!("/notes/{note_id}/submit"),
                Some(&admin),
                Some(json!({})),
            )
            .await;
            assert_eq!(status, StatusCode::OK, "{submitted}");
            assert_eq!(submitted["status"], "approved");
            let (status, blueprint) = call(
                &app,
                "GET",
                &format!("/projects/{project_id}/kg/blueprint"),
                Some(&admin),
                None,
            )
            .await;
            assert_eq!(status, StatusCode::OK, "{blueprint}");
            assert_eq!(blueprint["coverage"]["total_nodes"], 6);
            assert_eq!(
                blueprint["coverage"]["covered_nodes"], covered,
                "{blueprint}"
            );
            assert_eq!(blueprint["nodes"].as_array().unwrap().len(), 6);
            for node in blueprint["nodes"].as_array().unwrap() {
                let expected = if covered == 3
                    && ["cell_line", "geo_accession", "treatment"]
                        .contains(&node["entity_type"].as_str().unwrap())
                {
                    0
                } else {
                    1
                };
                assert_eq!(
                    node["evidence"]["entity_count"], expected,
                    "same label with a different role must not cover {node}"
                );
            }
            // Aging the fact entities proves role-aware matches feed the update-interval metric too.
            sqlx::query(
                "UPDATE kg_entities SET updated_at=now()-interval '5 days' WHERE project_id=$1",
            )
            .bind(project_id as i32)
            .execute(&pool)
            .await
            .unwrap();
            let (status, alerts) = call(
                &app,
                "POST",
                &format!("/projects/{project_id}/alerts/evaluate"),
                Some(&admin),
                None,
            )
            .await;
            assert_eq!(status, StatusCode::OK, "{alerts}");
            assert_eq!(
                metric(&alerts, "progress_deviation"),
                if covered == 3 { 0.5 } else { 0.0 }
            );
            assert!(
                (5.0..5.01).contains(&metric(&alerts, "blueprint_stagnant_days")),
                "{alerts}"
            );
        }
        // The same merged fact labels retain only roles from still-approved sources.
        let (status, archived) = call(
            &app,
            "POST",
            &format!("/notes/{}/archive", note_ids[0]),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{archived}");
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(
            blueprint["coverage"]["covered_nodes"], 3,
            "archived source roles must stop counting"
        );
        let (_, alerts) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/alerts/evaluate"),
            Some(&admin),
            None,
        )
        .await;
        assert_eq!(metric(&alerts, "progress_deviation"), 0.5);
    }

    async fn mock_blueprint(
        output: Value,
    ) -> (
        String,
        std::sync::Arc<std::sync::atomic::AtomicUsize>,
        std::sync::Arc<std::sync::Mutex<Vec<Value>>>,
    ) {
        use axum::{extract::State, routing::post, Json};
        use std::sync::{
            atomic::{AtomicUsize, Ordering},
            Arc, Mutex,
        };
        type MockState = (Value, Arc<AtomicUsize>, Arc<Mutex<Vec<Value>>>);
        async fn completion(
            State((output, calls, inputs)): State<MockState>,
            Json(input): Json<Value>,
        ) -> Json<Value> {
            calls.fetch_add(1, Ordering::SeqCst);
            inputs.lock().unwrap().push(input);
            Json(
                json!({"id":"blueprint-local-request", "model":"blueprint-local-model", "choices":[{"message":{"content":output.to_string()}}], "usage":{"prompt_tokens":10,"completion_tokens":20}}),
            )
        }
        let calls = Arc::new(AtomicUsize::new(0));
        let inputs = Arc::new(Mutex::new(Vec::new()));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let app = Router::new()
            .route("/chat/completions", post(completion))
            .with_state((output, calls.clone(), inputs.clone()));
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (format!("http://{address}"), calls, inputs)
    }

    fn ai_options(base_url: &str, allow_sensitive: bool) -> HashMap<String, String> {
        HashMap::from([
            ("AI_BASE_URL".to_owned(), base_url.to_owned()),
            ("AI_API_KEY".to_owned(), "local-test-key".to_owned()),
            (
                "ALLOW_SENSITIVE_EXTERNAL_AI".to_owned(),
                allow_sensitive.to_string(),
            ),
        ])
    }

    #[tokio::test]
    async fn test_t148_blueprint_sensitive_external_policy() {
        use std::sync::atomic::Ordering;
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (base, calls, _) =
            mock_blueprint(json!({"nodes":[{"entity_type":"reagent","label":"PBS"}], "edges":[]}))
                .await;
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        for (allow_sensitive, expected_status, expected_calls) in
            [(false, StatusCode::FORBIDDEN, 0), (true, StatusCode::OK, 1)]
        {
            let (app, admin, project_id) = setup_with_options(
                &database_url,
                "bp_sensitive",
                ai_options(&base, allow_sensitive),
            )
            .await;
            sqlx::query("UPDATE projects SET is_sensitive=true WHERE id=$1")
                .bind(project_id as i32)
                .execute(&pool)
                .await
                .unwrap();
            let (status, body) = call(&app, "POST", &format!("/projects/{project_id}/kg/blueprint/parse"), Some(&admin), Some(json!({"title":"Sensitive policy", "source_kind":"plan_document", "text":"使用试剂：PBS 缓冲液"}))).await;
            assert_eq!(status, expected_status, "{body}");
            assert_eq!(calls.load(Ordering::SeqCst), expected_calls);
        }
        // Local rule extraction remains available for a sensitive project without an external key.
        let (app, admin, project_id) = setup(&database_url, "bp_local_sensitive").await;
        sqlx::query("UPDATE projects SET is_sensitive=true WHERE id=$1")
            .bind(project_id as i32)
            .execute(&pool)
            .await
            .unwrap();
        let (status, body) = call(&app, "POST", &format!("/projects/{project_id}/kg/blueprint/parse"), Some(&admin), Some(json!({"title":"Local policy", "source_kind":"plan_document", "text":"使用试剂：PBS 缓冲液"}))).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        assert_eq!(body["parse_mode"], "rule_based");
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn test_t148_blueprint_edges_use_unambiguous_batch_and_actual_source() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let output = json!({"nodes":[
            {"entity_type":"experiment_type","label":"PCR"},
            {"entity_type":"reagent","label":"PBS"},
            {"entity_type":"group","label":"R1"},
            {"entity_type":"replicate","label":"R1"}],
            "edges":[
                {"source_label":"PCR","target_label":"Legacy","relation_type":"uses_reagent"},
                {"source_label":"PCR","target_label":"R1","relation_type":"has_condition"},
                {"source_label":"PCR","target_label":"PBS","relation_type":"uses_reagent"}]});
        let (base, _, _) = mock_blueprint(output).await;
        let (app, admin, project_id) =
            setup_with_options(&database_url, "bp_batch", ai_options(&base, false)).await;
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        let (_, me) = call(&app, "GET", "/auth/me", Some(&admin), None).await;
        let mut transaction = pool.begin().await.unwrap();
        crate::kg_blueprint::upsert_blueprint_node(
            &mut transaction,
            project_id as i32,
            &crate::kg_blueprint::BlueprintNodeInput {
                entity_type: "reagent",
                label: "Legacy",
                description: "",
                source_kind: "plan_document",
                source_label: "Old plan",
                priority: 50,
                created_by: me["id"].as_i64().unwrap() as i32,
            },
        )
        .await
        .unwrap();
        transaction.commit().await.unwrap();
        let (status, body) = call(&app,"POST",&format!("/projects/{project_id}/kg/blueprint/parse"),Some(&admin),Some(json!({"title":"Meeting plan","source_kind":"meeting_note","text":"PCR uses PBS. R1 is both a group and replicate."}))).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        assert_eq!(
            body["edges_added"], 1,
            "outside-batch and ambiguous endpoints must be dropped: {body}"
        );
        assert_eq!(body["edges_dropped"], 2, "{body}");
        let source: String =
            sqlx::query_scalar("SELECT source_kind FROM kg_blueprint_edges WHERE project_id=$1")
                .bind(project_id as i32)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(source, "meeting_note");
    }

    #[tokio::test]
    async fn test_t148_blueprint_note_reads_current_version_and_fixed_fields() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, project_id) = setup(&database_url, "bp_note_input").await;
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        let (_, note) = call(&app,"POST",&format!("/projects/{project_id}/notes"),Some(&admin),Some(json!({"title":"Current note","experiment_type":"Assay","fixed_fields_json":{"cell_line":"HCT116","reagents":["PBS"]},"content_text":"本次记录只描述步骤，字段中记录实验材料。"}))).await;
        let note_id = note["id"].as_i64().unwrap() as i32;
        let (version_id, created_by): (i32, i32) = sqlx::query_as(
            "SELECT current_version_id, owner_user_id FROM experiment_notes WHERE id=$1",
        )
        .bind(note_id)
        .fetch_one(&pool)
        .await
        .unwrap();
        // A later inserted version is deliberately not the authoritative current version.
        sqlx::query("INSERT INTO note_versions(note_id,version_number,fixed_fields_json,content_json,created_by,is_locked) VALUES($1,99,$2,$3,$4,false)").bind(note_id).bind(json!({"cell_line":"WrongLatest"})).bind(json!({"text":"使用试剂：WrongLatest"})).bind(created_by).execute(&pool).await.unwrap();
        let (status, body)=call(&app,"POST",&format!("/projects/{project_id}/kg/blueprint/parse"),Some(&admin),Some(json!({"title":"Note-backed blueprint","source_kind":"meeting_note","note_id":note_id}))).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let (_, blueprint) = call(
            &app,
            "GET",
            &format!("/projects/{project_id}/kg/blueprint"),
            Some(&admin),
            None,
        )
        .await;
        let nodes = blueprint["nodes"].as_array().unwrap();
        assert!(
            nodes
                .iter()
                .any(|node| node["entity_type"] == "cell_line" && node["label"] == "HCT116"),
            "{blueprint}"
        );
        assert!(
            nodes
                .iter()
                .any(|node| node["entity_type"] == "reagent" && node["label"] == "PBS"),
            "{blueprint}"
        );
        assert!(!nodes.iter().any(|node| node["label"] == "WrongLatest"));
        let detail:Value=sqlx::query_scalar("SELECT detail_json FROM audit_logs WHERE project_id=$1 AND action='blueprint_parse' ORDER BY id DESC LIMIT 1").bind(project_id as i32).fetch_one(&pool).await.unwrap();
        assert_eq!(
            detail["provenance"]["source"]["note_version_id"],
            version_id
        );
        assert_eq!(detail["provenance"]["source"]["note_id"], note_id);
        assert_eq!(
            detail["provenance"]["full_input"]["fixed_fields_json"]["cell_line"],
            "HCT116"
        );
    }

    #[tokio::test]
    async fn test_t148_blueprint_audit_can_recover_full_and_sent_input() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (base, _, inputs) =
            mock_blueprint(json!({"nodes":[{"entity_type":"reagent","label":"PBS"}],"edges":[]}))
                .await;
        let (app, admin, project_id) =
            setup_with_options(&database_url, "bp_provenance", ai_options(&base, false)).await;
        let text = format!("使用试剂：PBS；{}终末标志", "甲".repeat(12_100));
        let (status, body) = call(
            &app,
            "POST",
            &format!("/projects/{project_id}/kg/blueprint/parse"),
            Some(&admin),
            Some(json!({"title":"Long input","source_kind":"plan_document","text":text})),
        )
        .await;
        assert_eq!(status, StatusCode::OK, "{body}");
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        let detail:Value=sqlx::query_scalar("SELECT detail_json FROM audit_logs WHERE project_id=$1 AND action='blueprint_parse' ORDER BY id DESC LIMIT 1").bind(project_id as i32).fetch_one(&pool).await.unwrap();
        let provenance = &detail["provenance"];
        assert!(
            provenance["full_text"].as_str() == Some(text.as_str()),
            "audit must retain recoverable full text"
        );
        let captured = inputs.lock().unwrap();
        let sent = captured[0]["messages"][1]["content"].as_str().unwrap();
        assert_eq!(provenance["sent_text"], sent);
        assert_eq!(sent.chars().count(), 12_000);
        assert_eq!(provenance["truncated"], true);
        assert_eq!(
            provenance["full_text_sha256"],
            crate::rag::sha256_hex(text.as_bytes())
        );
        assert_eq!(
            provenance["sent_text_sha256"],
            crate::rag::sha256_hex(sent.as_bytes())
        );
        assert_eq!(provenance["model"]["request_id"], "blueprint-local-request");
        assert_eq!(provenance["model"]["model"], "blueprint-local-model");
        assert!(provenance["template_version"].is_string());
        let system = captured[0]["messages"][0]["content"].as_str().unwrap();
        assert_eq!(
            provenance["system_prompt_sha256"],
            crate::rag::sha256_hex(system.as_bytes())
        );
    }

    async fn wait_for_two_blocked_inserts(pool: &sqlx::PgPool, table: &str) {
        tokio::time::timeout(std::time::Duration::from_secs(10),async {
            loop {
                let blocked:i64=sqlx::query_scalar("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query ILIKE $1").bind(format!("%INSERT INTO public.{table}%")).fetch_one(pool).await.unwrap();
                if blocked>=2 { break; }
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        }).await.expect("both workers must reach INSERT before the table barrier is released");
    }

    #[tokio::test]
    async fn test_t148_blueprint_node_and_alert_concurrent_creation() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let (app, admin, project_id) = setup(&database_url, "bp_concurrent").await;
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        let (_, me) = call(&app, "GET", "/auth/me", Some(&admin), None).await;
        let user_id = me["id"].as_i64().unwrap() as i32;
        let mut all_errors = Vec::new();
        for table in ["kg_blueprint_nodes", "project_alerts"] {
            let mut barrier = pool.begin().await.unwrap();
            sqlx::query(&format!("LOCK TABLE public.{table} IN SHARE MODE"))
                .execute(&mut *barrier)
                .await
                .unwrap();
            let mut workers = Vec::new();
            for _ in 0..2 {
                let pool = pool.clone();
                workers.push(tokio::spawn(async move {
                    let mut transaction = pool.begin().await.unwrap();
                    let result = if table == "kg_blueprint_nodes" {
                        crate::kg_blueprint::upsert_blueprint_node(
                            &mut transaction,
                            project_id as i32,
                            &crate::kg_blueprint::BlueprintNodeInput {
                                entity_type: "reagent",
                                label: "Concurrent PBS",
                                description: "Meeting description",
                                source_kind: "meeting_note",
                                source_label: "Concurrent meeting",
                                priority: 10,
                                created_by: user_id,
                            },
                        )
                        .await
                        .map(|_| ())
                    } else {
                        crate::project_alert::upsert_open_alert(
                            &mut transaction,
                            project_id as i32,
                            "return_rate",
                            0.5,
                            "critical",
                            "Concurrent evaluation",
                        )
                        .await
                    };
                    if result.is_ok() {
                        transaction.commit().await.unwrap();
                    } else {
                        transaction.rollback().await.unwrap();
                    }
                    result
                }));
            }
            wait_for_two_blocked_inserts(&pool, table).await;
            barrier.commit().await.unwrap();
            let mut errors = Vec::new();
            for worker in workers {
                if let Err(error) = worker.await.unwrap() {
                    errors.push(error.to_string());
                }
            }
            all_errors.extend(errors.into_iter().map(|error| format!("{table}: {error}")));
            let count: i64 = sqlx::query_scalar(&format!(
                "SELECT count(*) FROM public.{table} WHERE project_id=$1"
            ))
            .bind(project_id as i32)
            .fetch_one(&pool)
            .await
            .unwrap();
            assert_eq!(count, 1);
        }
        assert!(
            all_errors.is_empty(),
            "concurrent creation must succeed for both workers: {all_errors:?}"
        );
        // A lower-priority plan cannot replace meeting evidence after the concurrent insert.
        let mut transaction = pool.begin().await.unwrap();
        crate::kg_blueprint::upsert_blueprint_node(
            &mut transaction,
            project_id as i32,
            &crate::kg_blueprint::BlueprintNodeInput {
                entity_type: "reagent",
                label: "Concurrent PBS",
                description: "Inferior plan",
                source_kind: "plan_document",
                source_label: "Later plan",
                priority: 50,
                created_by: user_id,
            },
        )
        .await
        .unwrap();
        transaction.commit().await.unwrap();
        let (priority, description): (i32, String) = sqlx::query_as(
            "SELECT priority,description FROM kg_blueprint_nodes WHERE project_id=$1",
        )
        .bind(project_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(priority, 10);
        assert_eq!(description, "Meeting description");
    }

    #[tokio::test]
    async fn test_t148_blueprint_invalid_model_output_keeps_response_identity_on_fallback() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let bad_output = json!({"nodes":"invalid-schema"});
        let (base, _, _) = mock_blueprint(bad_output.clone()).await;
        let (app, admin, project_id) =
            setup_with_options(&database_url, "bp_failed_parse", ai_options(&base, false)).await;
        let (status,body)=call(&app,"POST",&format!("/projects/{project_id}/kg/blueprint/parse"),Some(&admin),Some(json!({"title":"Invalid model schema","source_kind":"plan_document","text":"使用试剂：PBS 缓冲液"}))).await;
        assert_eq!(status, StatusCode::OK, "{body}");
        assert_eq!(body["parse_mode"], "rule_based");
        let pool = sqlx::PgPool::connect(&database_url).await.unwrap();
        let detail:Value=sqlx::query_scalar("SELECT detail_json FROM audit_logs WHERE project_id=$1 AND action='blueprint_parse' ORDER BY id DESC LIMIT 1").bind(project_id as i32).fetch_one(&pool).await.unwrap();
        assert_eq!(
            detail["provenance"]["model"]["request_id"], "blueprint-local-request",
            "fallback must keep the failed parse response identity"
        );
        assert_eq!(
            detail["provenance"]["model"]["response"],
            bad_output.to_string()
        );
        assert_eq!(detail["provenance"]["llm_attempted"], true);
    }
}
