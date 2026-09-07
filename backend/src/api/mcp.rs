use std::{collections::HashSet, convert::Infallible};

use axum::{
    extract::{FromRequestParts, Path, State},
    http::{request::Parts, HeaderMap, HeaderValue, StatusCode},
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::{delete, get},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use sqlx::{PgPool, Row};

use crate::{
    api::{agents, auth::CurrentUser},
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{AgentGenerateRequest, RagGraphContextRead, RagSourceRead},
    permissions::{
        can_access_project, can_manage_project, can_review_project, can_write_project,
        fetch_project,
    },
    rag::{relevant_graph_context, retrieve},
    AppState,
};

// ── JSON-RPC 2.0 types ─────────────────────────────────────────────

#[derive(Deserialize)]
struct JsonRpcRequest {
    jsonrpc: String,
    id: Option<Value>,
    method: String,
    #[serde(default)]
    params: Value,
}

#[derive(Serialize)]
struct JsonRpcResponse {
    jsonrpc: &'static str,
    id: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<JsonRpcError>,
}

#[derive(Serialize)]
struct JsonRpcError {
    code: i32,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<Value>,
}

fn rpc_ok(id: Option<Value>, result: Value) -> Json<JsonRpcResponse> {
    Json(JsonRpcResponse {
        jsonrpc: "2.0",
        id,
        result: Some(result),
        error: None,
    })
}

fn rpc_err(id: Option<Value>, code: i32, message: impl Into<String>) -> Json<JsonRpcResponse> {
    Json(JsonRpcResponse {
        jsonrpc: "2.0",
        id,
        result: None,
        error: Some(JsonRpcError {
            code,
            message: message.into(),
            data: None,
        }),
    })
}

// ── Router ──────────────────────────────────────────────────────────

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/api/mcp",
            get(handle_mcp_stream)
                .post(handle_mcp_request)
                .delete(terminate_mcp_session),
        )
        .route(
            "/api/mcp/tokens",
            get(list_pat_tokens).post(create_pat_token),
        )
        .route("/api/mcp/tokens/{token_id}", delete(revoke_pat_token))
}

struct PatMaterial {
    plaintext: String,
    prefix: String,
    hash: String,
}

fn issue_pat_material() -> PatMaterial {
    let plaintext = format!(
        "eln_mcp_{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    );
    let prefix = plaintext.chars().take(20).collect();
    let hash = format!("{:x}", Sha256::digest(plaintext.as_bytes()));
    PatMaterial {
        plaintext,
        prefix,
        hash,
    }
}

fn scope_allows(scopes: &HashSet<String>, tool: &ToolSpec) -> bool {
    tool.required_scopes
        .iter()
        .all(|scope| scopes.contains(*scope))
}

struct McpPrincipal {
    user: crate::models::UserRecord,
    /// None means first-party session/JWT and derives authorization from the user/project roles.
    pat_scopes: Option<HashSet<String>>,
}

impl FromRequestParts<AppState> for McpPrincipal {
    type Rejection = ApiError;

    async fn from_request_parts(
        parts: &mut Parts,
        state: &AppState,
    ) -> Result<Self, Self::Rejection> {
        let bearer = parts
            .headers
            .get("authorization")
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.strip_prefix("Bearer "));
        if let Some(token) = bearer.filter(|token| token.starts_with("eln_mcp_")) {
            let token_hash = format!("{:x}", Sha256::digest(token.as_bytes()));
            let record: Option<(uuid::Uuid, i32, Value)> = sqlx::query_as(
                r#"SELECT id,user_id,scopes_json FROM mcp_personal_access_tokens
                   WHERE token_hash=$1 AND revoked_at IS NULL AND expires_at > now()"#,
            )
            .bind(token_hash)
            .fetch_optional(&state.pool)
            .await?;
            let (token_id, user_id, scopes_json) = record.ok_or_else(|| {
                ApiError::new(StatusCode::UNAUTHORIZED, "Invalid or expired MCP token")
            })?;
            let user = sqlx::query_as::<_, crate::models::UserRecord>(
                r#"SELECT id,username,password_hash,display_name,email,
                   lower(role::text) AS role,lower(status::text) AS status,auth_version
                   FROM users WHERE id=$1 AND status='ACTIVE'::userstatus"#,
            )
            .bind(user_id)
            .fetch_optional(&state.pool)
            .await?
            .ok_or_else(|| ApiError::new(StatusCode::UNAUTHORIZED, "Invalid MCP user"))?;
            sqlx::query("UPDATE mcp_personal_access_tokens SET last_used_at=now() WHERE id=$1")
                .bind(token_id)
                .execute(&state.pool)
                .await?;
            let scopes = serde_json::from_value::<Vec<String>>(scopes_json)
                .map_err(|_| ApiError::new(StatusCode::UNAUTHORIZED, "Invalid MCP token scopes"))?
                .into_iter()
                .collect();
            return Ok(Self {
                user,
                pat_scopes: Some(scopes),
            });
        }
        let CurrentUser(user) = CurrentUser::from_request_parts(parts, state).await?;
        Ok(Self {
            user,
            pat_scopes: None,
        })
    }
}

#[derive(Deserialize)]
struct CreatePatRequest {
    name: String,
    scopes: Vec<String>,
    #[serde(default = "default_pat_days")]
    expires_in_days: i64,
}

fn default_pat_days() -> i64 {
    30
}

async fn create_pat_token(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Json(payload): Json<CreatePatRequest>,
) -> Result<Json<Value>, ApiError> {
    let name = payload.name.trim();
    if name.is_empty()
        || name.chars().count() > 120
        || !(1..=365).contains(&payload.expires_in_days)
    {
        return Err(ApiError::new(
            axum::http::StatusCode::UNPROCESSABLE_ENTITY,
            "Invalid PAT name or expiry",
        ));
    }
    let allowed: HashSet<&str> = tool_registry()
        .into_iter()
        .flat_map(|tool| tool.required_scopes.iter().copied())
        .chain(["resources:read", "prompts:read"])
        .collect();
    let scopes = payload.scopes.into_iter().collect::<HashSet<_>>();
    if scopes.is_empty() || scopes.iter().any(|scope| !allowed.contains(scope.as_str())) {
        return Err(ApiError::new(
            axum::http::StatusCode::UNPROCESSABLE_ENTITY,
            "Invalid or empty PAT scopes",
        ));
    }
    let material = issue_pat_material();
    let token_id = uuid::Uuid::new_v4();
    let expires_at: chrono::DateTime<chrono::Utc> = sqlx::query_scalar(
        r#"INSERT INTO mcp_personal_access_tokens
           (id,user_id,name,token_prefix,token_hash,scopes_json,expires_at)
           VALUES ($1,$2,$3,$4,$5,$6,now() + make_interval(days => $7::int))
           RETURNING expires_at"#,
    )
    .bind(token_id)
    .bind(user.id)
    .bind(name)
    .bind(&material.prefix)
    .bind(&material.hash)
    .bind(json!(scopes))
    .bind(payload.expires_in_days as i32)
    .fetch_one(&state.pool)
    .await?;
    Ok(Json(json!({
        "id": token_id, "name": name, "token": material.plaintext,
        "token_prefix": material.prefix, "scopes": scopes, "expires_at": expires_at,
        "warning": "该令牌仅展示一次；数据库仅保存哈希。"
    })))
}

async fn list_pat_tokens(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
) -> Result<Json<Value>, ApiError> {
    type PatTokenRow = (
        uuid::Uuid,
        String,
        String,
        Value,
        chrono::DateTime<chrono::Utc>,
        Option<chrono::DateTime<chrono::Utc>>,
        Option<chrono::DateTime<chrono::Utc>>,
    );
    let rows: Vec<PatTokenRow> = sqlx::query_as(
        "SELECT id,name,token_prefix,scopes_json,expires_at,revoked_at,last_used_at FROM mcp_personal_access_tokens WHERE user_id=$1 ORDER BY created_at DESC"
    ).bind(user.id).fetch_all(&state.pool).await?;
    Ok(Json(
        json!({"tokens":rows.into_iter().map(|row| json!({"id":row.0,"name":row.1,"token_prefix":row.2,"scopes":row.3,"expires_at":row.4,"revoked_at":row.5,"last_used_at":row.6})).collect::<Vec<_>>() }),
    ))
}

async fn revoke_pat_token(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(token_id): Path<uuid::Uuid>,
) -> Result<Json<Value>, ApiError> {
    let result = sqlx::query("UPDATE mcp_personal_access_tokens SET revoked_at=COALESCE(revoked_at,now()) WHERE id=$1 AND user_id=$2")
        .bind(token_id).bind(user.id).execute(&state.pool).await?;
    if result.rows_affected() == 0 {
        return Err(ApiError::new(
            axum::http::StatusCode::NOT_FOUND,
            "PAT not found",
        ));
    }
    Ok(Json(json!({"id":token_id,"revoked":true})))
}

const MCP_PROTOCOL_VERSION: &str = "2025-06-18";

fn validate_transport_headers(state: &AppState, headers: &HeaderMap) -> Result<(), ApiError> {
    if let Some(version) = headers
        .get("mcp-protocol-version")
        .and_then(|value| value.to_str().ok())
    {
        if version != MCP_PROTOCOL_VERSION {
            return Err(ApiError::new(
                StatusCode::BAD_REQUEST,
                "Unsupported MCP-Protocol-Version",
            ));
        }
    }
    if let Some(origin) = headers.get("origin").and_then(|value| value.to_str().ok()) {
        if !state
            .settings
            .cors_origin_list()
            .iter()
            .any(|allowed| allowed == origin)
        {
            return Err(ApiError::new(StatusCode::FORBIDDEN, "Untrusted MCP Origin"));
        }
    }
    Ok(())
}

async fn validate_mcp_session(
    state: &AppState,
    principal: &McpPrincipal,
    headers: &HeaderMap,
) -> Result<uuid::Uuid, ApiError> {
    let id = headers
        .get("mcp-session-id")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| uuid::Uuid::parse_str(value).ok())
        .ok_or_else(|| ApiError::new(StatusCode::BAD_REQUEST, "Mcp-Session-Id is required"))?;
    let updated = sqlx::query(
        "UPDATE mcp_http_sessions SET last_seen_at=now() WHERE id=$1 AND user_id=$2 AND expires_at>now()",
    ).bind(id).bind(principal.user.id).execute(&state.pool).await?;
    if updated.rows_affected() != 1 {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "MCP session not found or expired",
        ));
    }
    Ok(id)
}

async fn handle_mcp_stream(
    State(state): State<AppState>,
    principal: McpPrincipal,
    headers: HeaderMap,
) -> Result<Response, ApiError> {
    validate_transport_headers(&state, &headers)?;
    validate_mcp_session(&state, &principal, &headers).await?;
    let stream = tokio_stream::pending::<Result<Event, Infallible>>();
    Ok(Sse::new(stream)
        .keep_alive(KeepAlive::default())
        .into_response())
}

async fn terminate_mcp_session(
    State(state): State<AppState>,
    principal: McpPrincipal,
    headers: HeaderMap,
) -> Result<StatusCode, ApiError> {
    validate_transport_headers(&state, &headers)?;
    let id = validate_mcp_session(&state, &principal, &headers).await?;
    sqlx::query("DELETE FROM mcp_http_sessions WHERE id=$1 AND user_id=$2")
        .bind(id)
        .bind(principal.user.id)
        .execute(&state.pool)
        .await?;
    Ok(StatusCode::NO_CONTENT)
}

async fn handle_mcp_request(
    State(state): State<AppState>,
    principal: McpPrincipal,
    headers: HeaderMap,
    Json(request): Json<JsonRpcRequest>,
) -> Result<Response, ApiError> {
    validate_transport_headers(&state, &headers)?;
    if request.jsonrpc != "2.0" {
        return Ok(rpc_err(
            request.id,
            -32600,
            "Invalid Request: jsonrpc must be \"2.0\"",
        )
        .into_response());
    }
    let is_initialize = request.method == "initialize";
    if !is_initialize && headers.contains_key("mcp-session-id") {
        validate_mcp_session(&state, &principal, &headers).await?;
    }
    if request.id.is_none() {
        return Ok(StatusCode::ACCEPTED.into_response());
    }
    let rpc = match request.method.as_str() {
        "initialize" => handle_initialize(request.id),
        "tools/list" => handle_tools_list(request.id),
        "tools/call" => match handle_tools_call(
            &state,
            &principal.user,
            principal.pat_scopes.as_ref(),
            request.params.clone(),
        )
        .await
        {
            Ok(result) => rpc_ok(request.id, result),
            Err(err) => rpc_err(request.id, err.0, err.1),
        },
        "resources/list"
            if principal
                .pat_scopes
                .as_ref()
                .is_some_and(|scopes| !scopes.contains("resources:read")) =>
        {
            rpc_err(request.id, -32003, "MCP token lacks resources:read scope")
        }
        "resources/list" => match handle_resources_list(&state.pool, &principal.user).await {
            Ok(result) => rpc_ok(request.id, result),
            Err(err) => rpc_err(request.id, err.0, err.1),
        },
        "resources/read"
            if principal
                .pat_scopes
                .as_ref()
                .is_some_and(|scopes| !scopes.contains("resources:read")) =>
        {
            rpc_err(request.id, -32003, "MCP token lacks resources:read scope")
        }
        "resources/read" => {
            match handle_resource_read(&state.pool, &principal.user, &request.params).await {
                Ok(result) => rpc_ok(request.id, result),
                Err(err) => rpc_err(request.id, err.0, err.1),
            }
        }
        "prompts/list"
            if principal
                .pat_scopes
                .as_ref()
                .is_some_and(|scopes| !scopes.contains("prompts:read")) =>
        {
            rpc_err(request.id, -32003, "MCP token lacks prompts:read scope")
        }
        "prompts/list" => rpc_ok(request.id, json!({"prompts": prompt_definitions()})),
        "prompts/get"
            if principal
                .pat_scopes
                .as_ref()
                .is_some_and(|scopes| !scopes.contains("prompts:read")) =>
        {
            rpc_err(request.id, -32003, "MCP token lacks prompts:read scope")
        }
        "prompts/get" => match handle_prompt_get(&request.params) {
            Ok(result) => rpc_ok(request.id, result),
            Err(err) => rpc_err(request.id, err.0, err.1),
        },
        _ => rpc_err(request.id, -32601, "Method not found"),
    };
    let mut response = rpc.into_response();
    response.headers_mut().insert(
        "mcp-protocol-version",
        HeaderValue::from_static(MCP_PROTOCOL_VERSION),
    );
    if is_initialize {
        let session_id = uuid::Uuid::new_v4();
        sqlx::query(
            "INSERT INTO mcp_http_sessions (id,user_id,protocol_version,expires_at) VALUES ($1,$2,$3,now()+interval '8 hours')",
        ).bind(session_id).bind(principal.user.id).bind(MCP_PROTOCOL_VERSION).execute(&state.pool).await?;
        response.headers_mut().insert(
            "mcp-session-id",
            HeaderValue::from_str(&session_id.to_string()).expect("UUID is valid ASCII"),
        );
    }
    Ok(response)
}

// ── initialize ──────────────────────────────────────────────────────

fn handle_initialize(id: Option<Value>) -> Json<JsonRpcResponse> {
    rpc_ok(
        id,
        json!({
            "protocolVersion": "2025-06-18",
            "serverInfo": {
                "name": "eln-mcp-server",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {"listChanged": false},
                "resources": {"subscribe": false, "listChanged": false},
                "prompts": {"listChanged": false}
            }
        }),
    )
}

// ── tools/list ──────────────────────────────────────────────────────

fn handle_tools_list(id: Option<Value>) -> Json<JsonRpcResponse> {
    rpc_ok(
        id,
        json!({
            "tools": tool_definitions()
        }),
    )
}

fn tool_definitions() -> Vec<Value> {
    tool_registry()
        .into_iter()
        .map(|tool| tool.as_mcp())
        .collect()
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ToolRisk {
    ReadOnly,
    Low,
    High,
}

#[derive(Clone, Debug)]
pub struct ToolSpec {
    pub name: &'static str,
    pub description: &'static str,
    pub input_schema: Value,
    pub required_scopes: &'static [&'static str],
    pub risk: ToolRisk,
    pub requires_confirmation: bool,
    pub requires_idempotency_key: bool,
    pub audit_action: &'static str,
}

impl ToolSpec {
    fn as_mcp(&self) -> Value {
        json!({
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.risk == ToolRisk::ReadOnly,
                "destructiveHint": self.risk == ToolRisk::High,
                "idempotentHint": self.requires_idempotency_key
            },
            "_meta": {
                "eln/scopes": self.required_scopes,
                "eln/risk": self.risk,
                "eln/requiresConfirmation": self.requires_confirmation,
                "eln/auditAction": self.audit_action
            }
        })
    }
}

fn object_schema(properties: Value, required: &[&str]) -> Value {
    json!({"type": "object", "properties": properties, "required": required, "additionalProperties": false})
}

pub fn tool_registry() -> Vec<ToolSpec> {
    let project = json!({"project_id": {"type": "integer", "minimum": 1}});
    vec![
        ToolSpec {
            name: "search_notes",
            description: "搜索当前用户可访问项目中的已审核实验笔记。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"keyword":{"type":"string"},"date_from":{"type":"string","format":"date"},"date_to":{"type":"string","format":"date"}}),
                &["project_id"],
            ),
            required_scopes: &["project:read", "notes:read"],
            risk: ToolRisk::ReadOnly,
            requires_confirmation: false,
            requires_idempotency_key: false,
            audit_action: "mcp_search_notes",
        },
        ToolSpec {
            name: "retrieve_documents",
            description: "对当前项目已审核资料执行 RAG 检索。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"query":{"type":"string","minLength":1,"maxLength":4000}}),
                &["project_id", "query"],
            ),
            required_scopes: &["project:read", "rag:read"],
            risk: ToolRisk::ReadOnly,
            requires_confirmation: false,
            requires_idempotency_key: false,
            audit_action: "mcp_retrieve_documents",
        },
        ToolSpec {
            name: "query_knowledge_graph",
            description: "查询当前项目知识图谱。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"query":{"type":"string","minLength":1},"limit":{"type":"integer","minimum":1,"maximum":50}}),
                &["project_id", "query"],
            ),
            required_scopes: &["project:read", "graph:read"],
            risk: ToolRisk::ReadOnly,
            requires_confirmation: false,
            requires_idempotency_key: false,
            audit_action: "mcp_query_graph",
        },
        ToolSpec {
            name: "list_project_members",
            description: "读取项目成员及权限。",
            input_schema: object_schema(project.clone(), &["project_id"]),
            required_scopes: &["project:read", "members:read"],
            risk: ToolRisk::ReadOnly,
            requires_confirmation: false,
            requires_idempotency_key: false,
            audit_action: "mcp_list_members",
        },
        ToolSpec {
            name: "list_agent_tasks",
            description: "列出六类固定 Agent 任务模板。",
            input_schema: object_schema(json!({}), &[]),
            required_scopes: &["agent:read"],
            risk: ToolRisk::ReadOnly,
            requires_confirmation: false,
            requires_idempotency_key: false,
            audit_action: "mcp_list_agent_tasks",
        },
        ToolSpec {
            name: "create_draft_note",
            description: "创建可逆的草稿实验笔记。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"title":{"type":"string","minLength":1,"maxLength":300},"experiment_type":{"type":"string"},"content":{"type":"object"},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "title", "idempotency_key"],
            ),
            required_scopes: &["project:write", "notes:draft"],
            risk: ToolRisk::Low,
            requires_confirmation: false,
            requires_idempotency_key: true,
            audit_action: "mcp_create_draft_note",
        },
        ToolSpec {
            name: "create_report_draft",
            description: "生成并保存报告草稿。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"task_type":{"type":"string"},"parameters":{"type":"object"},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "task_type", "idempotency_key"],
            ),
            required_scopes: &["project:write", "agent:draft"],
            risk: ToolRisk::Low,
            requires_confirmation: false,
            requires_idempotency_key: true,
            audit_action: "mcp_create_report_draft",
        },
        ToolSpec {
            name: "submit_note_review",
            description: "提交笔记审核；执行前必须由用户确认。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"note_id":{"type":"integer","minimum":1},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "note_id", "idempotency_key"],
            ),
            required_scopes: &["project:write", "notes:submit"],
            risk: ToolRisk::High,
            requires_confirmation: true,
            requires_idempotency_key: true,
            audit_action: "mcp_submit_note_review",
        },
        ToolSpec {
            name: "review_note",
            description: "审批或拒绝笔记；执行前必须由用户确认。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"note_id":{"type":"integer","minimum":1},"decision":{"type":"string","enum":["approve","reject"]},"comment":{"type":"string"},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "note_id", "decision", "idempotency_key"],
            ),
            required_scopes: &["project:review", "notes:review"],
            risk: ToolRisk::High,
            requires_confirmation: true,
            requires_idempotency_key: true,
            audit_action: "mcp_review_note",
        },
        ToolSpec {
            name: "review_document",
            description: "审核资料并决定是否入库；执行前必须由用户确认。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"file_id":{"type":"integer","minimum":1},"decision":{"type":"string","enum":["approve","reject"]},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "file_id", "decision", "idempotency_key"],
            ),
            required_scopes: &["project:review", "files:review"],
            risk: ToolRisk::High,
            requires_confirmation: true,
            requires_idempotency_key: true,
            audit_action: "mcp_review_document",
        },
        ToolSpec {
            name: "rebuild_project_index",
            description: "重建项目 RAG 索引；执行前必须由用户确认。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"target":{"type":"string","enum":["rag","graph","all"]},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "target", "idempotency_key"],
            ),
            required_scopes: &["project:manage", "index:rebuild"],
            risk: ToolRisk::High,
            requires_confirmation: true,
            requires_idempotency_key: true,
            audit_action: "mcp_rebuild_index",
        },
        ToolSpec {
            name: "change_project_member",
            description: "变更成员或权限；执行前必须由用户确认。",
            input_schema: object_schema(
                json!({"project_id":{"type":"integer","minimum":1},"user_id":{"type":"integer","minimum":1},"role":{"type":"string","enum":["owner","reviewer","member","viewer"]},"can_read":{"type":"boolean"},"can_write":{"type":"boolean"},"can_review":{"type":"boolean"},"can_evaluate":{"type":"boolean"},"can_manage":{"type":"boolean"},"idempotency_key":{"type":"string","minLength":8,"maxLength":100}}),
                &["project_id", "user_id", "idempotency_key"],
            ),
            required_scopes: &["project:manage", "members:write"],
            risk: ToolRisk::High,
            requires_confirmation: true,
            requires_idempotency_key: true,
            audit_action: "mcp_change_member",
        },
    ]
}

pub fn find_tool(name: &str) -> Option<ToolSpec> {
    tool_registry().into_iter().find(|tool| tool.name == name)
}

fn requires_pending_action(tool: &ToolSpec) -> bool {
    tool.risk == ToolRisk::High && tool.requires_confirmation
}

fn prompt_definitions() -> Vec<Value> {
    [
        ("experiment_summary", "实验总结"),
        ("weekly_report", "周报"),
        ("stage_report", "项目阶段报告"),
        ("graph_overview", "实验过程图谱概览"),
        ("literature_review", "文献综述草稿"),
        ("anomaly_detection", "实验异常检测"),
    ]
    .into_iter()
    .map(|(name, description)| {
        json!({
            "name": name,
            "description": description,
            "arguments": [
                {"name": "project_id", "description": "项目编号", "required": true},
                {"name": "date_from", "description": "起始日期 YYYY-MM-DD", "required": false},
                {"name": "date_to", "description": "结束日期 YYYY-MM-DD", "required": false}
            ],
            "_meta": {"promptVersion": "agent-v10-evidence-ledger"}
        })
    })
    .collect()
}

fn handle_prompt_get(params: &Value) -> Result<Value, (i32, String)> {
    let name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or((-32602, "Missing prompt name".to_owned()))?;
    if !prompt_definitions()
        .iter()
        .any(|prompt| prompt["name"] == name)
    {
        return Err((-32602, format!("Unknown prompt: {name}")));
    }
    let arguments = params
        .get("arguments")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let project_id = arguments
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or((-32602, "project_id is required".to_owned()))?;
    Ok(json!({
        "description": format!("固定任务模板 {name}"),
        "messages": [{
            "role": "user",
            "content": {"type": "text", "text": format!(
                "执行固定任务 {name}。project_id={project_id}，date_from={}，date_to={}。只能使用当前项目已审核证据并保留引用。",
                arguments.get("date_from").and_then(Value::as_str).unwrap_or("未指定"),
                arguments.get("date_to").and_then(Value::as_str).unwrap_or("未指定")
            )}
        }],
        "_meta": {"promptVersion": "agent-v10-evidence-ledger"}
    }))
}

// ── tools/call ──────────────────────────────────────────────────────

pub(crate) async fn handle_tools_call(
    state: &AppState,
    user: &crate::models::UserRecord,
    pat_scopes: Option<&HashSet<String>>,
    params: Value,
) -> Result<Value, (i32, String)> {
    let tool_name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or((-32602, "Missing tool name".to_owned()))?;
    let arguments = params.get("arguments").cloned().unwrap_or(json!({}));
    let tool = find_tool(tool_name).ok_or((-32602, format!("Unknown tool: {tool_name}")))?;
    if pat_scopes.is_some_and(|scopes| !scope_allows(scopes, &tool)) {
        return Err((
            -32003,
            format!("MCP token lacks required scopes for {tool_name}"),
        ));
    }
    if tool.requires_idempotency_key
        && arguments
            .get("idempotency_key")
            .and_then(Value::as_str)
            .is_none()
    {
        return Err((-32602, "idempotency_key is required".to_owned()));
    }
    let project_id = arguments
        .get("project_id")
        .and_then(Value::as_i64)
        .map(|value| value as i32);
    if requires_pending_action(&tool) {
        let project_id = project_id.ok_or((-32602, "project_id is required".to_owned()))?;
        let permitted = match tool.name {
            "submit_note_review" => can_write_project(&state.pool, user, project_id).await,
            "review_note" | "review_document" => {
                can_review_project(&state.pool, user, project_id).await
            }
            _ => can_manage_project(&state.pool, user, project_id).await,
        }
        .map_err(|error| (-32603, error.detail))?;
        if !permitted {
            return Err((
                -32003,
                format!("Current project permissions do not allow {tool_name}"),
            ));
        }
    }
    let result = if requires_pending_action(&tool) {
        create_pending_action(state, user, &tool, arguments).await
    } else {
        match tool_name {
            "search_notes" => call_search_notes(&state.pool, user, arguments).await,
            "query_knowledge_graph" => {
                call_query_knowledge_graph(&state.pool, user, arguments).await
            }
            "retrieve_documents" => call_retrieve_documents(state, user, arguments).await,
            "list_agent_tasks" => Ok(call_list_agent_tasks()),
            "list_project_members" => call_list_project_members(&state.pool, user, arguments).await,
            "create_draft_note" => call_create_draft_note(state, user, arguments).await,
            "create_report_draft" => call_create_report_draft(state, user, arguments).await,
            _ => Err((
                -32602,
                format!("Tool is registered but not available in this release: {tool_name}"),
            )),
        }
    };
    if result.is_ok() {
        let outcome = if requires_pending_action(&tool) {
            "confirmation_required"
        } else {
            "completed"
        };
        if let Err(error) = write_audit(
            &state.pool,
            AuditEvent {
                actor_user_id: Some(user.id),
                project_id,
                action: tool.audit_action,
                target_type: Some("mcp_tool_call"),
                target_id: None,
                detail: json!({
                    "tool": tool.name,
                    "risk": tool.risk,
                    "outcome": outcome,
                    "authentication": if pat_scopes.is_some() { "pat" } else { "first_party" }
                }),
                ip_address: None,
                user_agent: Some("mcp".to_owned()),
            },
        )
        .await
        {
            tracing::error!(tool = tool.name, error = %error, "Failed to persist MCP tool audit event");
        }
    }
    result
}

async fn call_create_report_draft(
    state: &AppState,
    user: &crate::models::UserRecord,
    args: Value,
) -> Result<Value, (i32, String)> {
    let project_id = args
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or((-32602, "project_id is required".to_owned()))? as i32;
    verify_project_access(&state.pool, user, project_id).await?;
    if !can_write_project(&state.pool, user, project_id)
        .await
        .map_err(|error| (-32603, error.detail))?
    {
        return Err((-32003, "Write permission is required".to_owned()));
    }
    let task_type = args
        .get("task_type")
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or((-32602, "task_type is required".to_owned()))?;
    let parameters = args.get("parameters").cloned().unwrap_or_else(|| json!({}));
    let parse_date = |name: &str| -> Result<Option<chrono::NaiveDate>, (i32, String)> {
        parameters
            .get(name)
            .and_then(Value::as_str)
            .map(|value| {
                chrono::NaiveDate::parse_from_str(value, "%Y-%m-%d")
                    .map_err(|_| (-32602, format!("{name} must use YYYY-MM-DD")))
            })
            .transpose()
    };
    let date_from = parse_date("date_from")?;
    let date_to = parse_date("date_to")?;
    let idempotency_key = args
        .get("idempotency_key")
        .and_then(Value::as_str)
        .ok_or((-32602, "idempotency_key is required".to_owned()))?;
    let arguments_hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&args).unwrap_or_default())
    );
    if let Some((stored_hash, result)) = sqlx::query_as::<_, (String, Value)>(
        "SELECT arguments_hash,result_json FROM tool_execution_keys WHERE user_id=$1 AND tool_name='create_report_draft' AND idempotency_key=$2",
    )
    .bind(user.id)
    .bind(idempotency_key)
    .fetch_optional(&state.pool)
    .await
    .map_err(|error| (-32603, format!("Database error: {error}")))?
    {
        if stored_hash != arguments_hash {
            return Err((
                -32602,
                "Idempotency key was reused with different parameters".to_owned(),
            ));
        }
        if result["structuredContent"]["status"] == "running" {
            return Err((-32002, "Report draft generation is already running".to_owned()));
        }
        return Ok(result);
    }
    let reserved = sqlx::query(
        "INSERT INTO tool_execution_keys (user_id,tool_name,idempotency_key,arguments_hash,result_json) VALUES ($1,'create_report_draft',$2,$3,$4) ON CONFLICT DO NOTHING",
    )
    .bind(user.id)
    .bind(idempotency_key)
    .bind(&arguments_hash)
    .bind(json!({"structuredContent":{"status":"running"}}))
    .execute(&state.pool)
    .await
    .map_err(|error| (-32603, format!("Database error: {error}")))?;
    if reserved.rows_affected() == 0 {
        return Err((
            -32002,
            "Report draft generation is already running".to_owned(),
        ));
    }
    let generated = agents::generate_agent_output_action(
        state.clone(),
        user.clone(),
        AgentGenerateRequest {
            project_id,
            task_type: task_type.to_owned(),
            date_from,
            date_to,
        },
        None,
        Some("mcp-create-report-draft"),
    )
    .await;
    let run = match generated {
        Ok(run) => run.0,
        Err(error) => {
            sqlx::query("DELETE FROM tool_execution_keys WHERE user_id=$1 AND tool_name='create_report_draft' AND idempotency_key=$2 AND arguments_hash=$3")
                .bind(user.id).bind(idempotency_key).bind(&arguments_hash).execute(&state.pool).await
                .map_err(|delete_error| (-32603, format!("Report generation failed: {}; reservation cleanup failed: {delete_error}", error.detail)))?;
            return Err((-32603, error.detail));
        }
    };
    let result = json!({
        "content":[{"type":"text","text":"报告草稿已生成"}],
        "structuredContent":{"status":"completed","draft":true,"run":run}
    });
    sqlx::query("UPDATE tool_execution_keys SET result_json=$4 WHERE user_id=$1 AND tool_name='create_report_draft' AND idempotency_key=$2 AND arguments_hash=$3")
        .bind(user.id).bind(idempotency_key).bind(arguments_hash).bind(&result).execute(&state.pool).await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
    Ok(result)
}

async fn call_list_project_members(
    pool: &PgPool,
    user: &crate::models::UserRecord,
    args: Value,
) -> Result<Value, (i32, String)> {
    let project_id = args
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or((-32602, "project_id is required".to_owned()))? as i32;
    verify_project_access(pool, user, project_id).await?;
    let rows: Vec<(i32, String, String, bool)> = sqlx::query_as(
        r#"SELECT u.id,u.display_name,lower(pm.project_role::text),pm.can_evaluate
           FROM project_members pm JOIN users u ON u.id=pm.user_id
           WHERE pm.project_id=$1 ORDER BY u.id"#,
    )
    .bind(project_id)
    .fetch_all(pool)
    .await
    .map_err(|error| (-32603, format!("Database error: {error}")))?;
    Ok(
        json!({"content":[{"type":"text","text":format!("共 {} 名项目成员",rows.len())}],"structuredContent":{"members":rows.into_iter().map(|row|json!({"user_id":row.0,"display_name":row.1,"role":row.2,"can_evaluate":row.3})).collect::<Vec<_>>()}}),
    )
}

async fn call_create_draft_note(
    state: &AppState,
    user: &crate::models::UserRecord,
    args: Value,
) -> Result<Value, (i32, String)> {
    let project_id = args
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or((-32602, "project_id is required".to_owned()))? as i32;
    verify_project_access(&state.pool, user, project_id).await?;
    if !can_write_project(&state.pool, user, project_id)
        .await
        .map_err(|error| (-32603, error.detail))?
    {
        return Err((-32003, "Write permission is required".to_owned()));
    }
    let title = args
        .get("title")
        .and_then(Value::as_str)
        .filter(|title| !title.trim().is_empty())
        .ok_or((-32602, "title is required".to_owned()))?;
    let experiment_type = args
        .get("experiment_type")
        .and_then(Value::as_str)
        .unwrap_or("其他");
    let content = args
        .get("content")
        .cloned()
        .unwrap_or_else(|| json!({"type":"doc","content":[]}));
    let idempotency_key = args
        .get("idempotency_key")
        .and_then(Value::as_str)
        .ok_or((-32602, "idempotency_key is required".to_owned()))?;
    let arguments_hash = format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&args).unwrap_or_default())
    );
    let existing: Option<(String,Value)> = sqlx::query_as(
        "SELECT arguments_hash,result_json FROM tool_execution_keys WHERE user_id=$1 AND tool_name='create_draft_note' AND idempotency_key=$2"
    ).bind(user.id).bind(idempotency_key).fetch_optional(&state.pool).await.map_err(|error| (-32603, format!("Database error: {error}")))?;
    if let Some((stored_hash, result)) = existing {
        if stored_hash != arguments_hash {
            return Err((
                -32602,
                "Idempotency key was reused with different parameters".to_owned(),
            ));
        }
        return Ok(result);
    }
    let mut transaction = state
        .pool
        .begin()
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
    let note_id: i32 = sqlx::query_scalar(
        r#"INSERT INTO experiment_notes (project_id,title,experiment_type,owner_user_id,status,created_at,updated_at)
           VALUES ($1,$2,$3,$4,'DRAFT'::notestatus,now(),now()) RETURNING id"#,
    ).bind(project_id).bind(title.trim()).bind(experiment_type).bind(user.id)
    .fetch_one(&mut *transaction).await.map_err(|error| (-32603, format!("Database error: {error}")))?;
    let version_id: i32 = sqlx::query_scalar(
        r#"INSERT INTO note_versions (note_id,version_number,fixed_fields_json,content_json,created_by,change_summary,is_locked,created_at)
           VALUES ($1,1,'{}'::json,$2,$3,'Created by Agent tool',false,now()) RETURNING id"#,
    ).bind(note_id).bind(&content).bind(user.id).fetch_one(&mut *transaction).await.map_err(|error| (-32603, format!("Database error: {error}")))?;
    sqlx::query("UPDATE experiment_notes SET current_version_id=$2 WHERE id=$1")
        .bind(note_id)
        .bind(version_id)
        .execute(&mut *transaction)
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
    let result = json!({"content":[{"type":"text","text":"草稿笔记已创建"}],"structuredContent":{"status":"completed","note_id":note_id,"project_id":project_id,"draft":true}});
    sqlx::query("INSERT INTO tool_execution_keys (user_id,tool_name,idempotency_key,arguments_hash,result_json) VALUES ($1,'create_draft_note',$2,$3,$4)")
        .bind(user.id).bind(idempotency_key).bind(arguments_hash).bind(&result).execute(&mut *transaction).await.map_err(|error| (-32603, format!("Database error: {error}")))?;
    transaction
        .commit()
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
    Ok(result)
}

async fn create_pending_action(
    state: &AppState,
    user: &crate::models::UserRecord,
    tool: &ToolSpec,
    arguments: Value,
) -> Result<Value, (i32, String)> {
    let project_id = arguments
        .get("project_id")
        .and_then(Value::as_i64)
        .map(|value| value as i32);
    if let Some(project_id) = project_id {
        verify_project_access(&state.pool, user, project_id).await?;
    }
    let idempotency_key = arguments
        .get("idempotency_key")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned();
    let encoded = serde_json::to_vec(&arguments).map_err(|error| (-32602, error.to_string()))?;
    let arguments_hash = format!("{:x}", Sha256::digest(&encoded));
    let summary = format!(
        "{} {}",
        tool.name,
        arguments_hash.get(..12).unwrap_or(&arguments_hash)
    );
    let existing: Option<uuid::Uuid> = sqlx::query_scalar(
        "SELECT id FROM agent_pending_actions WHERE user_id=$1 AND tool_name=$2 AND idempotency_key=$3",
    )
    .bind(user.id)
    .bind(tool.name)
    .bind(&idempotency_key)
    .fetch_optional(&state.pool)
    .await
    .map_err(|error| (-32603, format!("Database error: {error}")))?;
    let pending_id = if let Some(existing) = existing {
        existing
    } else {
        let pending_id = uuid::Uuid::new_v4();
        sqlx::query(
            r#"
            INSERT INTO agent_pending_actions (
                id, user_id, project_id, tool_name, arguments_json, arguments_summary,
                arguments_hash, idempotency_key, status, expires_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'pending',now() + interval '10 minutes')
            "#,
        )
        .bind(pending_id)
        .bind(user.id)
        .bind(project_id)
        .bind(tool.name)
        .bind(arguments)
        .bind(&summary)
        .bind(&arguments_hash)
        .bind(&idempotency_key)
        .execute(&state.pool)
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
        pending_id
    };
    Ok(json!({
        "isError": true,
        "content": [{"type":"text","text":"该操作需要用户在 10 分钟内明确确认。"}],
        "structuredContent": {
            "code": "confirmation_required",
            "pending_action_id": pending_id,
            "expires_in_seconds": 600,
            "tool": tool.name,
            "arguments_summary": summary
        }
    }))
}

async fn handle_resources_list(
    pool: &PgPool,
    user: &crate::models::UserRecord,
) -> Result<Value, (i32, String)> {
    let projects: Vec<(i32, String)> = sqlx::query_as(
        "SELECT id, name FROM projects WHERE status='ACTIVE'::projectstatus ORDER BY id",
    )
    .fetch_all(pool)
    .await
    .map_err(|error| (-32603, format!("Database error: {error}")))?;
    let mut resources = Vec::new();
    for (project_id, project_name) in projects {
        if verify_project_access(pool, user, project_id).await.is_err() {
            continue;
        }
        let notes: Vec<(i32, String)> = sqlx::query_as(
            "SELECT id,title FROM experiment_notes WHERE project_id=$1 AND status='APPROVED'::notestatus ORDER BY id DESC LIMIT 100",
        )
        .bind(project_id)
        .fetch_all(pool)
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
        resources.extend(notes.into_iter().map(|(id, name)| {
            json!({
                "uri":format!("eln://projects/{project_id}/notes/{id}"), "name":name,
                "title":format!("{project_name} / 已审核笔记"), "mimeType":"application/json"
            })
        }));
        let files: Vec<(i32, String)> = sqlx::query_as(
            "SELECT id,original_filename FROM files WHERE project_id=$1 AND status='APPROVED'::filestatus AND file_category='KNOWLEDGE_DOCUMENT'::filecategory ORDER BY id DESC LIMIT 100",
        )
        .bind(project_id)
        .fetch_all(pool)
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
        resources.extend(files.into_iter().map(|(id, name)| {
            json!({
                "uri":format!("eln://projects/{project_id}/documents/{id}"), "name":name,
                "title":format!("{project_name} / 已审核资料"), "mimeType":"application/json"
            })
        }));
        let runs: Vec<(i32, String)> = sqlx::query_as(
            "SELECT id,title FROM agent_generation_runs WHERE project_id=$1 AND user_id=$2 ORDER BY id DESC LIMIT 100",
        )
        .bind(project_id)
        .bind(user.id)
        .fetch_all(pool)
        .await
        .map_err(|error| (-32603, format!("Database error: {error}")))?;
        resources.extend(runs.into_iter().map(|(id, name)| {
            json!({
                "uri":format!("eln://projects/{project_id}/agent-runs/{id}"), "name":name,
                "title":format!("{project_name} / Agent 运行结果"), "mimeType":"application/json"
            })
        }));
    }
    Ok(json!({"resources":resources}))
}

async fn handle_resource_read(
    pool: &PgPool,
    user: &crate::models::UserRecord,
    params: &Value,
) -> Result<Value, (i32, String)> {
    let uri = params
        .get("uri")
        .and_then(Value::as_str)
        .ok_or((-32602, "uri is required".to_owned()))?;
    let parts = uri
        .strip_prefix("eln://projects/")
        .ok_or((-32602, "Unsupported resource URI".to_owned()))?
        .split('/')
        .collect::<Vec<_>>();
    if parts.len() != 3 {
        return Err((-32602, "Unsupported resource URI".to_owned()));
    }
    let project_id = parts[0]
        .parse::<i32>()
        .map_err(|_| (-32602, "Invalid project id".to_owned()))?;
    let resource_id = parts[2]
        .parse::<i32>()
        .map_err(|_| (-32602, "Invalid resource id".to_owned()))?;
    verify_project_access(pool, user, project_id).await?;
    let value = match parts[1] {
        "notes" => sqlx::query_scalar::<_, Value>("SELECT jsonb_build_object('id',id,'title',title,'experiment_type',experiment_type,'experiment_date',experiment_date,'content',content_json) FROM experiment_notes WHERE id=$1 AND project_id=$2 AND status='APPROVED'::notestatus")
            .bind(resource_id).bind(project_id).fetch_optional(pool).await,
        "documents" => sqlx::query_scalar::<_, Value>("SELECT jsonb_build_object('id',id,'filename',original_filename,'metadata',metadata_json,'knowledge_sync_status',knowledge_sync_status) FROM files WHERE id=$1 AND project_id=$2 AND status='APPROVED'::filestatus AND file_category='KNOWLEDGE_DOCUMENT'::filecategory")
            .bind(resource_id).bind(project_id).fetch_optional(pool).await,
        "agent-runs" => sqlx::query_scalar::<_, Value>("SELECT jsonb_build_object('id',id,'task_type',task_type,'title',title,'body',body,'status',status,'model_name',model_name,'prompt_version',prompt_version) FROM agent_generation_runs WHERE id=$1 AND project_id=$2 AND user_id=$3")
            .bind(resource_id).bind(project_id).bind(user.id).fetch_optional(pool).await,
        _ => return Err((-32602, "Unsupported resource type".to_owned())),
    }
    .map_err(|error| (-32603, format!("Database error: {error}")))?
    .ok_or((-32602, "Resource not found".to_owned()))?;
    Ok(json!({"contents":[{"uri":uri,"mimeType":"application/json","text":value.to_string()}]}))
}

async fn verify_project_access(
    pool: &PgPool,
    user: &crate::models::UserRecord,
    project_id: i32,
) -> Result<(), (i32, String)> {
    let project = fetch_project(pool, project_id).await.map_err(|_| {
        (
            -32603,
            format!("Project {project_id} not found or inaccessible"),
        )
    })?;
    let can_access = can_access_project(pool, user, &project)
        .await
        .map_err(|e| (-32603, format!("Database error: {e}")))?;
    if !can_access {
        return Err((-32603, "No access to this project".to_owned()));
    }
    Ok(())
}

// ── Tool: search_notes ──────────────────────────────────────────────

async fn call_search_notes(
    pool: &PgPool,
    user: &crate::models::UserRecord,
    args: Value,
) -> Result<Value, (i32, String)> {
    let project_id = args
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or_else(|| (-32602, "project_id is required".to_owned()))? as i32;
    verify_project_access(pool, user, project_id).await?;

    let keyword = args.get("keyword").and_then(Value::as_str).unwrap_or("");
    let date_from: Option<String> = args
        .get("date_from")
        .and_then(Value::as_str)
        .map(str::to_owned);
    let date_to: Option<String> = args
        .get("date_to")
        .and_then(Value::as_str)
        .map(str::to_owned);

    // Build query with typed binds: project_id always bound as i32 first.
    let mut query_text = r#"
        SELECT n.id, n.title, n.experiment_type, n.experiment_date
        FROM experiment_notes n
        WHERE n.project_id = $1
          AND n.status = 'APPROVED'::notestatus
    "#
    .to_owned();
    let mut param_idx = 2u32;
    let mut keyword_pattern: Option<String> = None;

    if !keyword.is_empty() {
        query_text.push_str(&format!(
            " AND (n.title ILIKE ${param_idx} OR n.experiment_type ILIKE ${param_idx})"
        ));
        keyword_pattern = Some(format!("%{keyword}%"));
        param_idx += 1;
    }
    if date_from.is_some() {
        query_text.push_str(&format!(" AND n.experiment_date >= ${param_idx}::date"));
        param_idx += 1;
    }
    if date_to.is_some() {
        query_text.push_str(&format!(" AND n.experiment_date <= ${param_idx}::date"));
    }
    query_text.push_str(" ORDER BY n.experiment_date DESC, n.id LIMIT 20");

    let mut db_query = sqlx::query(&query_text).bind(project_id);
    if let Some(ref pattern) = keyword_pattern {
        db_query = db_query.bind(pattern.as_str());
    }
    if let Some(ref from) = date_from {
        db_query = db_query.bind(from.as_str());
    }
    if let Some(ref to) = date_to {
        db_query = db_query.bind(to.as_str());
    }
    let rows = db_query
        .fetch_all(pool)
        .await
        .map_err(|e| (-32603i32, format!("Database error: {e}")))?;

    let notes: Vec<Value> = rows
        .iter()
        .map(|row| {
            json!({
                "id": row.try_get::<i32, _>("id").unwrap_or(0),
                "title": row.try_get::<String, _>("title").unwrap_or_default(),
                "experiment_type": row.try_get::<String, _>("experiment_type").unwrap_or_default(),
                "experiment_date": row.try_get::<Option<chrono::NaiveDate>, _>("experiment_date").unwrap_or(None).map(|d| d.to_string()),
            })
        })
        .collect();

    Ok(json!({
        "content": [{ "type": "text", "text": format!("找到 {} 条实验笔记", notes.len()) }],
        "structuredContent": { "notes": notes }
    }))
}

// ── Tool: query_knowledge_graph ─────────────────────────────────────

async fn call_query_knowledge_graph(
    pool: &PgPool,
    user: &crate::models::UserRecord,
    args: Value,
) -> Result<Value, (i32, String)> {
    let project_id = args
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or_else(|| (-32602, "project_id is required".to_owned()))? as i32;
    verify_project_access(pool, user, project_id).await?;

    let query = args
        .get("query")
        .and_then(Value::as_str)
        .ok_or_else(|| (-32602, "query is required".to_owned()))?;
    let query = crate::api::rag::validate_query(query).map_err(|error| (-32602, error.detail))?;
    let limit = args.get("limit").and_then(Value::as_u64).unwrap_or(10) as usize;

    let context = relevant_graph_context(pool, project_id, query, limit.min(50), 0.0)
        .await
        .map_err(|e| (-32603i32, format!("Database error: {e}")))?;

    let relations: Vec<Value> = context.iter().map(format_graph_relation).collect();

    Ok(json!({
        "content": [{ "type": "text", "text": format!("找到 {} 条相关图谱关系", relations.len()) }],
        "structuredContent": { "relations": relations }
    }))
}

fn format_graph_relation(rel: &RagGraphContextRead) -> Value {
    json!({
        "relation_id": rel.relation_id,
        "relation_type": rel.relation_type,
        "relation_label": rel.relation_label,
        "source": {
            "entity_id": rel.source_entity_id,
            "label": rel.source_label,
            "entity_type": rel.source_entity_type,
        },
        "target": {
            "entity_id": rel.target_entity_id,
            "label": rel.target_label,
            "entity_type": rel.target_entity_type,
        },
        "confidence": rel.confidence,
    })
}

// ── Tool: retrieve_documents ────────────────────────────────────────

async fn call_retrieve_documents(
    state: &AppState,
    user: &crate::models::UserRecord,
    args: Value,
) -> Result<Value, (i32, String)> {
    let project_id = args
        .get("project_id")
        .and_then(Value::as_i64)
        .ok_or_else(|| (-32602, "project_id is required".to_owned()))? as i32;
    verify_project_access(&state.pool, user, project_id).await?;

    let query = args
        .get("query")
        .and_then(Value::as_str)
        .ok_or_else(|| (-32602, "query is required".to_owned()))?;
    let query = crate::api::rag::validate_query(query).map_err(|error| (-32602, error.detail))?;

    let sources = retrieve(state, project_id, query, false)
        .await
        .map_err(|e| (-32603i32, format!("Retrieval error: {e}")))?;

    let chunks: Vec<Value> = sources.iter().map(format_rag_source).collect();

    Ok(json!({
        "content": [{ "type": "text", "text": format!("检索到 {} 个相关文档片段", chunks.len()) }],
        "structuredContent": { "chunks": chunks }
    }))
}

fn format_rag_source(source: &RagSourceRead) -> Value {
    json!({
        "chunk_id": source.chunk_id,
        "file_id": source.file_id,
        "filename": source.filename,
        "snippet": source.snippet,
        "vector_score": source.vector_score,
        "lexical_score": source.lexical_score,
        "retrieval_score": source.retrieval_score,
    })
}

// ── Tool: list_agent_tasks ──────────────────────────────────────────

fn call_list_agent_tasks() -> Value {
    let tasks = vec![
        json!({"type": "experiment_summary", "label": "实验总结", "description": "汇总指定范围内的实验笔记，生成结构化实验总结。"}),
        json!({"type": "weekly_report", "label": "周报", "description": "生成一周内的实验工作周报。"}),
        json!({"type": "stage_report", "label": "项目阶段报告", "description": "按阶段汇总实验进展和成果。"}),
        json!({"type": "graph_overview", "label": "实验过程图谱概览", "description": "基于知识图谱生成实验实体关系概览。"}),
        json!({"type": "literature_review", "label": "文献综述草稿", "description": "按实验主题分节整理文献综述草稿。"}),
        json!({"type": "anomaly_detection", "label": "实验异常检测", "description": "检查实验记录中的数值异常和数据问题。"}),
    ];
    json!({
        "content": [{ "type": "text", "text": format!("共 {} 种可用任务类型", tasks.len()) }],
        "structuredContent": { "tasks": tasks }
    })
}

// ── Tests ───────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tool_registry_declares_security_and_execution_policy() {
        let tools = tool_registry();
        assert!(tools.len() >= 8);
        for tool in tools {
            assert!(!tool.required_scopes.is_empty());
            assert!(!tool.audit_action.is_empty());
            if tool.risk == ToolRisk::High {
                assert!(tool.requires_confirmation);
                assert!(tool.requires_idempotency_key);
            }
        }
        assert_eq!(find_tool("create_draft_note").unwrap().risk, ToolRisk::Low);
        assert_eq!(
            find_tool("submit_note_review").unwrap().risk,
            ToolRisk::High
        );
    }

    #[test]
    fn test_rpc_ok_serializes_without_error() {
        let resp = rpc_ok(Some(json!(1)), json!({"hello": "world"}));
        let json = serde_json::to_value(&*resp).unwrap();
        assert_eq!(json["jsonrpc"], "2.0");
        assert_eq!(json["id"], 1);
        assert!(json.get("error").is_none());
        assert_eq!(json["result"]["hello"], "world");
    }

    #[test]
    fn test_rpc_err_serializes_without_result() {
        let resp = rpc_err(Some(json!(2)), -32601, "Method not found");
        let json = serde_json::to_value(&*resp).unwrap();
        assert_eq!(json["jsonrpc"], "2.0");
        assert_eq!(json["error"]["code"], -32601);
        assert!(json.get("result").is_none());
    }

    #[test]
    fn test_initialize_response_contains_server_info() {
        let resp = handle_initialize(Some(json!(1)));
        let json = serde_json::to_value(&*resp).unwrap();
        let result = &json["result"];
        assert_eq!(result["protocolVersion"], "2025-06-18");
        assert_eq!(result["serverInfo"]["name"], "eln-mcp-server");
        assert!(result["capabilities"]["tools"].is_object());
        assert!(result["capabilities"]["resources"].is_object());
        assert!(result["capabilities"]["prompts"].is_object());
    }

    #[test]
    fn test_tools_list_returns_all_tools() {
        let resp = handle_tools_list(Some(json!(1)));
        let json = serde_json::to_value(&*resp).unwrap();
        let tools = json["result"]["tools"].as_array().unwrap();
        assert!(tools.len() >= 8);
        let names: Vec<&str> = tools.iter().filter_map(|t| t["name"].as_str()).collect();
        assert!(names.contains(&"search_notes"));
        assert!(names.contains(&"query_knowledge_graph"));
        assert!(names.contains(&"retrieve_documents"));
        assert!(names.contains(&"list_agent_tasks"));
    }

    #[test]
    fn test_list_agent_tasks_returns_all_types() {
        let result = call_list_agent_tasks();
        let tasks = result["structuredContent"]["tasks"].as_array().unwrap();
        assert_eq!(tasks.len(), 6);
    }

    #[test]
    fn test_prompt_catalog_exposes_six_versioned_task_templates() {
        let prompts = prompt_definitions();
        assert_eq!(prompts.len(), 6);
        assert!(prompts
            .iter()
            .all(|prompt| prompt["_meta"]["promptVersion"] == "agent-v10-evidence-ledger"));
        assert!(prompts.iter().all(|prompt| {
            prompt["arguments"].as_array().is_some_and(|arguments| {
                arguments
                    .iter()
                    .any(|argument| argument["name"] == "project_id")
            })
        }));
    }

    #[test]
    fn test_high_risk_tools_never_dispatch_without_confirmation() {
        let tool = find_tool("review_note").unwrap();
        assert!(requires_pending_action(&tool));
        assert!(!requires_pending_action(
            &find_tool("create_draft_note").unwrap()
        ));
    }

    #[test]
    fn test_pat_material_is_one_way_and_prefixed() {
        let material = issue_pat_material();
        assert!(material.plaintext.starts_with("eln_mcp_"));
        assert_ne!(material.plaintext, material.hash);
        assert_eq!(material.hash.len(), 64);
        assert!(material.plaintext.starts_with(&material.prefix));
    }

    #[test]
    fn test_pat_scope_requires_every_tool_scope() {
        let scopes =
            std::collections::HashSet::from(["project:read".to_owned(), "notes:read".to_owned()]);
        assert!(scope_allows(&scopes, &find_tool("search_notes").unwrap()));
        assert!(!scope_allows(
            &scopes,
            &find_tool("retrieve_documents").unwrap()
        ));
    }

    #[test]
    fn test_mcp_query_uses_rag_input_contract() {
        let blank = crate::api::rag::validate_query("  ").unwrap_err();
        assert_eq!(blank.status, axum::http::StatusCode::UNPROCESSABLE_ENTITY);
        let too_long = crate::api::rag::validate_query(&"x".repeat(4_001)).unwrap_err();
        assert_eq!(
            too_long.status,
            axum::http::StatusCode::UNPROCESSABLE_ENTITY
        );
    }
}
