use axum::{extract::State, routing::post, Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sqlx::{PgPool, Row};

use crate::{
    api::auth::CurrentUser,
    models::{RagGraphContextRead, RagSourceRead},
    permissions::{can_access_project, fetch_project},
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
    Router::new().route("/api/mcp", post(handle_mcp_request))
}

async fn handle_mcp_request(
    State(state): State<AppState>,
    user: CurrentUser,
    Json(request): Json<JsonRpcRequest>,
) -> Json<JsonRpcResponse> {
    if request.jsonrpc != "2.0" {
        return rpc_err(
            request.id,
            -32600,
            "Invalid Request: jsonrpc must be \"2.0\"",
        );
    }
    match request.method.as_str() {
        "initialize" => handle_initialize(request.id),
        "tools/list" => handle_tools_list(request.id),
        "tools/call" => match handle_tools_call(&state, &user.0, request.params.clone()).await {
            Ok(result) => rpc_ok(request.id, result),
            Err(err) => rpc_err(request.id, err.0, err.1),
        },
        _ => rpc_err(request.id, -32601, "Method not found"),
    }
}

// ── initialize ──────────────────────────────────────────────────────

fn handle_initialize(id: Option<Value>) -> Json<JsonRpcResponse> {
    rpc_ok(
        id,
        json!({
            "protocolVersion": "2025-03-26",
            "serverInfo": {
                "name": "eln-mcp-server",
                "version": "1.0.0"
            },
            "capabilities": {
                "tools": {}
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
    vec![
        json!({
            "name": "search_notes",
            "description": "搜索项目中的已审核实验笔记，支持按关键词和日期范围过滤。返回笔记标题、实验类型、日期和关键字段摘要。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": { "type": "integer", "description": "项目编号" },
                    "keyword": { "type": "string", "description": "搜索关键词（匹配标题和实验类型）" },
                    "date_from": { "type": "string", "description": "起始日期 YYYY-MM-DD" },
                    "date_to": { "type": "string", "description": "结束日期 YYYY-MM-DD" }
                },
                "required": ["project_id"]
            }
        }),
        json!({
            "name": "query_knowledge_graph",
            "description": "查询项目知识图谱中与查询语义相关的实体关系。返回图谱关系列表，包含源实体、目标实体和关系类型。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": { "type": "integer", "description": "项目编号" },
                    "query": { "type": "string", "description": "查询文本，用于语义匹配图谱关系" },
                    "limit": { "type": "integer", "description": "返回关系数量上限（默认 10）" }
                },
                "required": ["project_id", "query"]
            }
        }),
        json!({
            "name": "retrieve_documents",
            "description": "在项目已审核资料库中进行 RAG 检索，返回与查询最相关的文档片段及评分。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": { "type": "integer", "description": "项目编号" },
                    "query": { "type": "string", "description": "检索查询文本" }
                },
                "required": ["project_id", "query"]
            }
        }),
        json!({
            "name": "list_agent_tasks",
            "description": "列出可用的 Agent 任务类型及其说明。Agent 任务可自动生成实验总结、周报、文献综述等结构化内容。",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }),
    ]
}

// ── tools/call ──────────────────────────────────────────────────────

async fn handle_tools_call(
    state: &AppState,
    user: &crate::models::UserRecord,
    params: Value,
) -> Result<Value, (i32, String)> {
    let tool_name = params
        .get("name")
        .and_then(Value::as_str)
        .ok_or((-32602, "Missing tool name".to_owned()))?;
    let arguments = params.get("arguments").cloned().unwrap_or(json!({}));

    match tool_name {
        "search_notes" => call_search_notes(&state.pool, user, arguments).await,
        "query_knowledge_graph" => call_query_knowledge_graph(&state.pool, user, arguments).await,
        "retrieve_documents" => call_retrieve_documents(state, user, arguments).await,
        "list_agent_tasks" => Ok(call_list_agent_tasks()),
        _ => Err((-32602, format!("Unknown tool: {tool_name}"))),
    }
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
    fn test_tool_definitions_are_valid_json_schema() {
        let tools = tool_definitions();
        assert_eq!(tools.len(), 4);
        for tool in &tools {
            assert!(tool.get("name").and_then(Value::as_str).is_some());
            assert!(tool.get("description").and_then(Value::as_str).is_some());
            assert!(tool.get("inputSchema").is_some());
        }
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
        assert_eq!(result["protocolVersion"], "2025-03-26");
        assert_eq!(result["serverInfo"]["name"], "eln-mcp-server");
        assert!(result["capabilities"]["tools"].is_object());
    }

    #[test]
    fn test_tools_list_returns_all_tools() {
        let resp = handle_tools_list(Some(json!(1)));
        let json = serde_json::to_value(&*resp).unwrap();
        let tools = json["result"]["tools"].as_array().unwrap();
        assert_eq!(tools.len(), 4);
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
}
