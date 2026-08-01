use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde_json::{json, Value};
use sqlx::{PgPool, Postgres, Transaction};

use crate::{
    api::auth::{require_admin, CurrentUser},
    api::ClientInfo,
    audit::{write_audit, AuditEvent},
    error::ApiError,
    models::{
        validate_project_role, validate_project_status, ProjectCreate, ProjectListQuery,
        ProjectListResponse, ProjectMemberCreate, ProjectMemberRead, ProjectMemberUpdate,
        ProjectRead, ProjectReviewerCreate, ProjectReviewerRead, ProjectUpdate, UserRecord,
    },
    permissions::{
        can_access_project, fetch_project, require_project_manager, require_project_metadata_access,
    },
    AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/projects", get(list_projects).post(create_project))
        .route(
            "/projects/{project_id}",
            get(get_project).patch(update_project),
        )
        .route(
            "/projects/{project_id}/members",
            get(list_project_members).post(add_project_member),
        )
        .route(
            "/projects/{project_id}/members/{user_id}",
            axum::routing::patch(update_project_member).delete(remove_project_member),
        )
        .route(
            "/projects/{project_id}/reviewers",
            post(add_project_reviewer),
        )
        .route(
            "/projects/{project_id}/reviewers/{user_id}",
            axum::routing::delete(remove_project_reviewer),
        )
}

const PROJECT_COLUMNS: &str = r#"
    id, name, description, is_sensitive,
    lower(status::text) AS status, approval_enabled, owner_user_id
"#;

const MEMBER_COLUMNS: &str = r#"
    id, project_id, user_id, lower(project_role::text) AS project_role,
    can_read, can_write, can_review, can_evaluate, can_manage,
    EXISTS(
        SELECT 1 FROM project_reviewers pr
        WHERE pr.project_id = project_members.project_id
          AND pr.user_id = project_members.user_id
    ) AS is_independent_reviewer
"#;

const PROJECT_MEMBERSHIP_LOCK_NAMESPACE: i32 = 0x454C_4E49;

async fn list_projects(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Query(query): Query<ProjectListQuery>,
) -> Result<Json<ProjectListResponse>, ApiError> {
    if query.skip < 0 || !(1..=100).contains(&query.limit) {
        return Err(validation_error("Invalid pagination parameters"));
    }
    let (predicate, bind_user) = match user.role.as_str() {
        "super_admin" => ("true", false),
        "pi" => (
            "(is_sensitive = false OR id IN (SELECT project_id FROM project_members WHERE user_id = $1 AND (can_read = true OR can_evaluate = true)))",
            true,
        ),
        _ => (
            "id IN (SELECT project_id FROM project_members WHERE user_id = $1 AND (can_read = true OR can_evaluate = true))",
            true,
        ),
    };
    let count_sql = format!("SELECT count(*) FROM projects WHERE {predicate}");
    let items_sql = if bind_user {
        format!(
            "SELECT {PROJECT_COLUMNS} FROM projects WHERE {predicate} ORDER BY id DESC OFFSET $2 LIMIT $3"
        )
    } else {
        format!(
            "SELECT {PROJECT_COLUMNS} FROM projects WHERE {predicate} ORDER BY id DESC OFFSET $1 LIMIT $2"
        )
    };
    let (total, items) = if bind_user {
        let total = sqlx::query_scalar(&count_sql)
            .bind(user.id)
            .fetch_one(&state.pool)
            .await?;
        let items = sqlx::query_as::<_, ProjectRead>(&items_sql)
            .bind(user.id)
            .bind(query.skip)
            .bind(query.limit)
            .fetch_all(&state.pool)
            .await?;
        (total, items)
    } else {
        let total = sqlx::query_scalar(&count_sql)
            .fetch_one(&state.pool)
            .await?;
        let items = sqlx::query_as::<_, ProjectRead>(&items_sql)
            .bind(query.skip)
            .bind(query.limit)
            .fetch_all(&state.pool)
            .await?;
        (total, items)
    };
    Ok(Json(ProjectListResponse {
        items,
        total,
        skip: query.skip,
        limit: query.limit,
    }))
}

async fn create_project(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(admin): CurrentUser,
    Json(payload): Json<ProjectCreate>,
) -> Result<Json<ProjectRead>, ApiError> {
    require_admin(&admin)?;
    if payload.name.trim().is_empty() {
        return Err(validation_error("Project name cannot be empty"));
    }
    if let Some(owner_user_id) = payload.owner_user_id {
        require_user(&state.pool, owner_user_id).await?;
    }
    let duplicate: bool =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM projects WHERE name = $1)")
            .bind(&payload.name)
            .fetch_one(&state.pool)
            .await?;
    if duplicate {
        return Err(ApiError::new(StatusCode::CONFLICT, "项目名称已存在"));
    }
    let mut transaction = state.pool.begin().await?;
    let project_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO projects (
            name, description, is_sensitive, status, approval_enabled,
            owner_user_id, created_at, updated_at
        )
        VALUES ($1, $2, $3, 'ACTIVE'::projectstatus, $4, $5, now(), now())
        RETURNING id
        "#,
    )
    .bind(&payload.name)
    .bind(&payload.description)
    .bind(payload.is_sensitive)
    .bind(payload.approval_enabled)
    .bind(payload.owner_user_id)
    .fetch_one(&mut *transaction)
    .await?;
    if let Some(owner_user_id) = payload.owner_user_id {
        ensure_owner_membership(&mut transaction, project_id, owner_user_id).await?;
    }
    audit_project(
        &mut transaction,
        admin.id,
        "create_project",
        project_id,
        "project",
        project_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_project(&state.pool, project_id).await?))
}

async fn get_project(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<ProjectRead>, ApiError> {
    Ok(Json(
        require_project_metadata_access(&state.pool, &user, project_id).await?,
    ))
}

async fn update_project(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<ProjectUpdate>,
) -> Result<Json<ProjectRead>, ApiError> {
    require_project_manager(&state.pool, &user, project_id).await?;
    if let Some(status) = &payload.status {
        validate_project_status(status).map_err(validation_error)?;
    }
    if let Some(owner_user_id) = payload.owner_user_id {
        require_user(&state.pool, owner_user_id).await?;
    }
    let mut transaction = state.pool.begin().await?;
    lock_project_membership(&mut transaction, project_id).await?;
    let user =
        require_project_manager_in_transaction(&mut transaction, &user, project_id, &[]).await?;
    protect_reviewer_independence_for_project_update(
        &mut transaction,
        project_id,
        payload.is_sensitive,
        payload.owner_user_id,
    )
    .await?;
    if let Some(name) = payload.name {
        sqlx::query("UPDATE projects SET name = $2, updated_at = now() WHERE id = $1")
            .bind(project_id)
            .bind(name)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(description) = payload.description {
        sqlx::query("UPDATE projects SET description = $2, updated_at = now() WHERE id = $1")
            .bind(project_id)
            .bind(description)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(is_sensitive) = payload.is_sensitive {
        sqlx::query("UPDATE projects SET is_sensitive = $2, updated_at = now() WHERE id = $1")
            .bind(project_id)
            .bind(is_sensitive)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(status) = payload.status {
        sqlx::query("UPDATE projects SET status = upper($2)::projectstatus, updated_at = now() WHERE id = $1")
            .bind(project_id)
            .bind(status)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(approval_enabled) = payload.approval_enabled {
        sqlx::query("UPDATE projects SET approval_enabled = $2, updated_at = now() WHERE id = $1")
            .bind(project_id)
            .bind(approval_enabled)
            .execute(&mut *transaction)
            .await?;
    }
    if let Some(owner_user_id) = payload.owner_user_id {
        sqlx::query("UPDATE projects SET owner_user_id = $2, updated_at = now() WHERE id = $1")
            .bind(project_id)
            .bind(owner_user_id)
            .execute(&mut *transaction)
            .await?;
        ensure_owner_membership(&mut transaction, project_id, owner_user_id).await?;
    }
    audit_project(
        &mut transaction,
        user.id,
        "update_project",
        project_id,
        "project",
        project_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(fetch_project(&state.pool, project_id).await?))
}

async fn add_project_member(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<ProjectMemberCreate>,
) -> Result<Json<Value>, ApiError> {
    require_project_manager(&state.pool, &user, project_id).await?;
    require_user(&state.pool, payload.user_id).await?;
    validate_project_role(&payload.project_role).map_err(validation_error)?;
    let mut transaction = state.pool.begin().await?;
    lock_project_membership(&mut transaction, project_id).await?;
    let user =
        require_project_manager_in_transaction(&mut transaction, &user, project_id, &[]).await?;
    reject_independent_reviewer_member_mutation(&mut transaction, project_id, payload.user_id)
        .await?;
    let membership =
        fetch_optional_membership(&mut transaction, project_id, payload.user_id).await?;
    let next_is_manager =
        payload.can_read && (payload.can_manage || payload.project_role == "owner");
    protect_manager_transition(
        &mut transaction,
        project_id,
        membership.as_ref(),
        next_is_manager,
    )
    .await?;
    protect_project_owner_transition(
        &mut transaction,
        project_id,
        payload.user_id,
        next_is_manager,
    )
    .await?;
    if payload.user_id == user.id && user.role != "super_admin" && !next_is_manager {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot remove your own project manage access",
        ));
    }
    sqlx::query(
        r#"
        INSERT INTO project_members (
            project_id, user_id, project_role, can_read, can_write,
            can_review, can_evaluate, can_manage, created_at
        )
        VALUES ($1, $2, upper($3)::projectrole, $4, $5, $6, $7, $8, now())
        ON CONFLICT (project_id, user_id) DO UPDATE SET
            project_role = EXCLUDED.project_role,
            can_read = EXCLUDED.can_read,
            can_write = EXCLUDED.can_write,
            can_review = EXCLUDED.can_review,
            can_evaluate = EXCLUDED.can_evaluate,
            can_manage = EXCLUDED.can_manage
        "#,
    )
    .bind(project_id)
    .bind(payload.user_id)
    .bind(&payload.project_role)
    .bind(payload.can_read)
    .bind(payload.can_write)
    .bind(payload.can_review)
    .bind(payload.can_evaluate)
    .bind(payload.can_manage)
    .execute(&mut *transaction)
    .await?;
    audit_project(
        &mut transaction,
        user.id,
        "update_project_member",
        project_id,
        "user",
        payload.user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({"ok": true})))
}

async fn list_project_members(
    State(state): State<AppState>,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
) -> Result<Json<Vec<ProjectMemberRead>>, ApiError> {
    let project = require_project_metadata_access(&state.pool, &user, project_id).await?;
    if can_access_project(&state.pool, &user, &project).await? {
        let query = format!(
            "SELECT {MEMBER_COLUMNS} FROM project_members WHERE project_id = $1 ORDER BY id"
        );
        return Ok(Json(
            sqlx::query_as::<_, ProjectMemberRead>(&query)
                .bind(project_id)
                .fetch_all(&state.pool)
                .await?,
        ));
    }
    let query = format!(
        "SELECT {MEMBER_COLUMNS} FROM project_members WHERE project_id = $1 AND user_id = $2 ORDER BY id"
    );
    Ok(Json(
        sqlx::query_as::<_, ProjectMemberRead>(&query)
            .bind(project_id)
            .bind(user.id)
            .fetch_all(&state.pool)
            .await?,
    ))
}

async fn update_project_member(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, user_id)): Path<(i32, i32)>,
    Json(payload): Json<ProjectMemberUpdate>,
) -> Result<Json<ProjectMemberRead>, ApiError> {
    require_project_manager(&state.pool, &user, project_id).await?;
    if let Some(role) = &payload.project_role {
        validate_project_role(role).map_err(validation_error)?;
    }
    let mut transaction = state.pool.begin().await?;
    lock_project_membership(&mut transaction, project_id).await?;
    let user =
        require_project_manager_in_transaction(&mut transaction, &user, project_id, &[]).await?;
    reject_independent_reviewer_member_mutation(&mut transaction, project_id, user_id).await?;
    let membership = fetch_membership_in_transaction(&mut transaction, project_id, user_id).await?;
    let was_manager = is_manager(&membership);
    let next_role = payload
        .project_role
        .as_deref()
        .unwrap_or(&membership.project_role);
    let next_can_read = payload.can_read.unwrap_or(membership.can_read);
    let next_can_manage = payload.can_manage.unwrap_or(membership.can_manage);
    let next_is_manager = next_can_read && (next_can_manage || next_role == "owner");
    if was_manager {
        protect_manager_transition(
            &mut transaction,
            project_id,
            Some(&membership),
            next_is_manager,
        )
        .await?;
    }
    protect_project_owner_transition(&mut transaction, project_id, user_id, next_is_manager)
        .await?;
    if user_id == user.id && user.role != "super_admin" && !next_is_manager {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot remove your own project manage access",
        ));
    }
    if let Some(role) = payload.project_role {
        sqlx::query("UPDATE project_members SET project_role = upper($3)::projectrole WHERE project_id = $1 AND user_id = $2")
            .bind(project_id).bind(user_id).bind(role).execute(&mut *transaction).await?;
    }
    for (column, value) in [
        ("can_read", payload.can_read),
        ("can_write", payload.can_write),
        ("can_review", payload.can_review),
        ("can_evaluate", payload.can_evaluate),
        ("can_manage", payload.can_manage),
    ] {
        if let Some(value) = value {
            let query = format!(
                "UPDATE project_members SET {column} = $3 WHERE project_id = $1 AND user_id = $2"
            );
            sqlx::query(&query)
                .bind(project_id)
                .bind(user_id)
                .bind(value)
                .execute(&mut *transaction)
                .await?;
        }
    }
    let updated = fetch_membership_in_transaction(&mut transaction, project_id, user_id).await?;
    audit_project(
        &mut transaction,
        user.id,
        "update_project_member",
        project_id,
        "user",
        user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(updated))
}

async fn remove_project_member(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, user_id)): Path<(i32, i32)>,
) -> Result<Json<Value>, ApiError> {
    require_project_manager(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    lock_project_membership(&mut transaction, project_id).await?;
    let user =
        require_project_manager_in_transaction(&mut transaction, &user, project_id, &[]).await?;
    reject_independent_reviewer_member_mutation(&mut transaction, project_id, user_id).await?;
    let membership = fetch_membership_in_transaction(&mut transaction, project_id, user_id).await?;
    protect_manager_transition(&mut transaction, project_id, Some(&membership), false).await?;
    protect_project_owner_transition(&mut transaction, project_id, user_id, false).await?;
    if user_id == user.id && user.role != "super_admin" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot remove yourself from project managers",
        ));
    }
    sqlx::query("DELETE FROM project_members WHERE project_id = $1 AND user_id = $2")
        .bind(project_id)
        .bind(user_id)
        .execute(&mut *transaction)
        .await?;
    audit_project(
        &mut transaction,
        user.id,
        "change_permission",
        project_id,
        "user",
        user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({"ok": true})))
}

async fn add_project_reviewer(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path(project_id): Path<i32>,
    Json(payload): Json<ProjectReviewerCreate>,
) -> Result<Json<ProjectReviewerRead>, ApiError> {
    require_project_manager(&state.pool, &user, project_id).await?;
    require_user(&state.pool, payload.user_id).await?;
    let mut transaction = state.pool.begin().await?;
    lock_project_membership(&mut transaction, project_id).await?;
    let user = require_project_manager_in_transaction(
        &mut transaction,
        &user,
        project_id,
        &[payload.user_id],
    )
    .await?;
    let membership =
        fetch_optional_membership(&mut transaction, project_id, payload.user_id).await?;
    protect_manager_transition(&mut transaction, project_id, membership.as_ref(), false).await?;
    protect_project_owner_transition(&mut transaction, project_id, payload.user_id, false).await?;
    protect_independent_reviewer_assignment(&mut transaction, project_id, payload.user_id).await?;
    if payload.user_id == user.id && user.role != "super_admin" {
        return Err(ApiError::new(
            StatusCode::CONFLICT,
            "Cannot make yourself an independent project reviewer",
        ));
    }
    let reviewer_id: i32 = sqlx::query_scalar(
        r#"
        INSERT INTO project_reviewers (project_id, user_id, review_scope, created_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (project_id, user_id) DO UPDATE
        SET review_scope = EXCLUDED.review_scope
        RETURNING id
        "#,
    )
    .bind(project_id)
    .bind(payload.user_id)
    .bind(&payload.review_scope)
    .fetch_one(&mut *transaction)
    .await?;
    sqlx::query(
        r#"
        INSERT INTO project_members (
            project_id, user_id, project_role, can_read, can_write,
            can_review, can_evaluate, can_manage, created_at
        )
        VALUES ($1, $2, 'REVIEWER'::projectrole, false, false, false, true, false, now())
        ON CONFLICT (project_id, user_id) DO UPDATE SET
            project_role = 'REVIEWER'::projectrole,
            can_read = false,
            can_write = false,
            can_review = false,
            can_evaluate = true,
            can_manage = false
        "#,
    )
    .bind(project_id)
    .bind(payload.user_id)
    .execute(&mut *transaction)
    .await?;
    audit_project(
        &mut transaction,
        user.id,
        "change_permission",
        project_id,
        "user",
        payload.user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(
        sqlx::query_as::<_, ProjectReviewerRead>(
            "SELECT id, project_id, user_id, review_scope FROM project_reviewers WHERE id = $1",
        )
        .bind(reviewer_id)
        .fetch_one(&state.pool)
        .await?,
    ))
}

async fn remove_project_reviewer(
    State(state): State<AppState>,
    client: ClientInfo,
    CurrentUser(user): CurrentUser,
    Path((project_id, user_id)): Path<(i32, i32)>,
) -> Result<Json<Value>, ApiError> {
    require_project_manager(&state.pool, &user, project_id).await?;
    let mut transaction = state.pool.begin().await?;
    lock_project_membership(&mut transaction, project_id).await?;
    let user =
        require_project_manager_in_transaction(&mut transaction, &user, project_id, &[]).await?;
    let deleted =
        sqlx::query("DELETE FROM project_reviewers WHERE project_id = $1 AND user_id = $2")
            .bind(project_id)
            .bind(user_id)
            .execute(&mut *transaction)
            .await?;
    if deleted.rows_affected() == 0 {
        return Err(ApiError::new(
            StatusCode::NOT_FOUND,
            "Project reviewer not found",
        ));
    }
    sqlx::query("DELETE FROM project_members WHERE project_id = $1 AND user_id = $2")
        .bind(project_id)
        .bind(user_id)
        .execute(&mut *transaction)
        .await?;
    audit_project(
        &mut transaction,
        user.id,
        "change_permission",
        project_id,
        "user",
        user_id,
        client.ip_opt(),
        client.ua_opt(),
    )
    .await?;
    transaction.commit().await?;
    Ok(Json(json!({"ok": true})))
}

async fn ensure_owner_membership(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
) -> Result<(), ApiError> {
    sqlx::query(
        r#"
        INSERT INTO project_members (
            project_id, user_id, project_role, can_read, can_write,
            can_review, can_evaluate, can_manage, created_at
        )
        VALUES ($1, $2, 'OWNER'::projectrole, true, true, true, true, true, now())
        ON CONFLICT (project_id, user_id) DO UPDATE SET
            project_role = 'OWNER'::projectrole,
            can_read = true,
            can_write = true,
            can_review = true,
            can_evaluate = true,
            can_manage = true
        "#,
    )
    .bind(project_id)
    .bind(user_id)
    .execute(&mut **transaction)
    .await?;
    Ok(())
}

async fn lock_project_membership(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<(), ApiError> {
    sqlx::query("SELECT pg_advisory_xact_lock($1, $2)")
        .bind(PROJECT_MEMBERSHIP_LOCK_NAMESPACE)
        .bind(project_id)
        .fetch_one(&mut **transaction)
        .await?;
    Ok(())
}

async fn require_project_manager_in_transaction(
    transaction: &mut Transaction<'_, Postgres>,
    user: &UserRecord,
    project_id: i32,
    additional_user_ids: &[i32],
) -> Result<UserRecord, ApiError> {
    // Every project mutation takes user-row locks only after the project advisory
    // lock and in ascending user-id order. Including the actor, all existing
    // independent reviewers, and any prospective reviewer prevents cross-project
    // A->B / B->A reviewer assignments from creating a row-lock cycle.
    let locked_users = sqlx::query_as::<_, UserRecord>(
        r#"
        SELECT u.id, u.username, u.password_hash, u.display_name, u.email,
               lower(u.role::text) AS role, lower(u.status::text) AS status,
               u.auth_version
        FROM users u
        WHERE u.id = $2
           OR u.id = ANY($3)
           OR EXISTS(
               SELECT 1 FROM project_reviewers pr
               WHERE pr.project_id = $1 AND pr.user_id = u.id
           )
        ORDER BY u.id
        FOR NO KEY UPDATE OF u /* project_actor_reviewer_user_lock */
        "#,
    )
    .bind(project_id)
    .bind(user.id)
    .bind(additional_user_ids)
    .fetch_all(&mut **transaction)
    .await?;
    let current_user = locked_users
        .into_iter()
        .find(|candidate| candidate.id == user.id)
        .ok_or_else(|| ApiError::new(StatusCode::UNAUTHORIZED, "User authorization changed"))?;
    if current_user.status != "active" || current_user.auth_version != user.auth_version {
        return Err(ApiError::new(
            StatusCode::UNAUTHORIZED,
            "User authorization changed",
        ));
    }
    if current_user.role == "super_admin" {
        return Ok(current_user);
    }
    let allowed: bool = sqlx::query_scalar(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM projects p
            WHERE p.id = $1 AND (
                p.owner_user_id = $2 OR EXISTS(
                    SELECT 1 FROM project_members pm
                    WHERE pm.project_id = p.id AND pm.user_id = $2
                      AND pm.can_read = true
                      AND (pm.can_manage = true OR pm.project_role = 'OWNER'::projectrole)
                )
            )
        )
        "#,
    )
    .bind(project_id)
    .bind(current_user.id)
    .fetch_one(&mut **transaction)
    .await?;
    if allowed {
        Ok(current_user)
    } else {
        Err(ApiError::new(StatusCode::FORBIDDEN, "需要项目管理权限"))
    }
}

async fn reject_independent_reviewer_member_mutation(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
) -> Result<(), ApiError> {
    let is_independent_reviewer: bool = sqlx::query_scalar(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM project_reviewers
            WHERE project_id = $1 AND user_id = $2
        )
        "#,
    )
    .bind(project_id)
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?;
    if is_independent_reviewer {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            "Independent reviewers must be managed through reviewer endpoints",
        ))
    } else {
        Ok(())
    }
}

async fn fetch_optional_membership(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
) -> Result<Option<ProjectMemberRead>, ApiError> {
    let query = format!(
        "SELECT {MEMBER_COLUMNS} FROM project_members WHERE project_id = $1 AND user_id = $2"
    );
    Ok(sqlx::query_as::<_, ProjectMemberRead>(&query)
        .bind(project_id)
        .bind(user_id)
        .fetch_optional(&mut **transaction)
        .await?)
}

async fn fetch_membership_in_transaction(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
) -> Result<ProjectMemberRead, ApiError> {
    fetch_optional_membership(transaction, project_id, user_id)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Project member not found"))
}

async fn manager_count_in_transaction(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
) -> Result<i64, ApiError> {
    Ok(sqlx::query_scalar(
        r#"
        SELECT count(*) FROM project_members
        WHERE project_id = $1 AND can_read = true
          AND (can_manage = true OR project_role = 'OWNER'::projectrole)
        "#,
    )
    .bind(project_id)
    .fetch_one(&mut **transaction)
    .await?)
}

async fn protect_manager_transition(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    membership: Option<&ProjectMemberRead>,
    next_is_manager: bool,
) -> Result<(), ApiError> {
    if membership.is_some_and(is_manager)
        && !next_is_manager
        && manager_count_in_transaction(transaction, project_id).await? <= 1
    {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            "项目至少需保留一名管理员",
        ))
    } else {
        Ok(())
    }
}

async fn protect_project_owner_transition(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
    next_is_manager: bool,
) -> Result<(), ApiError> {
    if next_is_manager {
        return Ok(());
    }
    let is_owner: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM projects WHERE id = $1 AND owner_user_id = $2)",
    )
    .bind(project_id)
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?;
    if is_owner {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            "Transfer project ownership before removing owner manage access",
        ))
    } else {
        Ok(())
    }
}

async fn protect_independent_reviewer_assignment(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    user_id: i32,
) -> Result<(), ApiError> {
    let exists: Option<i32> = sqlx::query_scalar(
        "SELECT id FROM users WHERE id = $1 FOR NO KEY UPDATE /* reviewer_assignment_user_lock */",
    )
    .bind(user_id)
    .fetch_optional(&mut **transaction)
    .await?;
    if exists.is_none() {
        return Err(ApiError::new(StatusCode::NOT_FOUND, "User not found"));
    }
    let has_automatic_access: bool = sqlx::query_scalar(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM projects p
            JOIN users u ON u.id = $2
            WHERE p.id = $1 AND (
                u.role = 'SUPER_ADMIN'::userrole
                OR p.owner_user_id = u.id
                OR (u.role = 'PI'::userrole AND p.is_sensitive = false)
            )
        )
        "#,
    )
    .bind(project_id)
    .bind(user_id)
    .fetch_one(&mut **transaction)
    .await?;
    if has_automatic_access {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            "User has automatic project access and cannot be an independent reviewer",
        ))
    } else {
        Ok(())
    }
}

async fn protect_reviewer_independence_for_project_update(
    transaction: &mut Transaction<'_, Postgres>,
    project_id: i32,
    next_is_sensitive: Option<bool>,
    next_owner_user_id: Option<i32>,
) -> Result<(), ApiError> {
    if next_is_sensitive.is_none() && next_owner_user_id.is_none() {
        return Ok(());
    }
    sqlx::query(
        r#"
        SELECT u.id
        FROM project_reviewers pr
        JOIN users u ON u.id = pr.user_id
        WHERE pr.project_id = $1
        ORDER BY u.id
        FOR NO KEY UPDATE OF u /* reviewer_independence_user_lock */
        "#,
    )
    .bind(project_id)
    .fetch_all(&mut **transaction)
    .await?;
    let violates_independence: bool = sqlx::query_scalar(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM projects p
            JOIN project_reviewers pr ON pr.project_id = p.id
            JOIN users u ON u.id = pr.user_id
            WHERE p.id = $1 AND (
                u.role = 'SUPER_ADMIN'::userrole
                OR COALESCE($3, p.owner_user_id) = u.id
                OR (
                    u.role = 'PI'::userrole
                    AND COALESCE($2, p.is_sensitive) = false
                )
            )
        )
        "#,
    )
    .bind(project_id)
    .bind(next_is_sensitive)
    .bind(next_owner_user_id)
    .fetch_one(&mut **transaction)
    .await?;
    if violates_independence {
        Err(ApiError::new(
            StatusCode::CONFLICT,
            "Project update would give an independent reviewer automatic content access",
        ))
    } else {
        Ok(())
    }
}

fn is_manager(membership: &ProjectMemberRead) -> bool {
    membership.can_read && (membership.can_manage || membership.project_role == "owner")
}

async fn require_user(pool: &PgPool, user_id: i32) -> Result<(), ApiError> {
    let exists: bool = sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM users WHERE id = $1)")
        .bind(user_id)
        .fetch_one(pool)
        .await?;
    if exists {
        Ok(())
    } else {
        Err(ApiError::new(StatusCode::NOT_FOUND, "User not found"))
    }
}

#[allow(clippy::too_many_arguments)]
async fn audit_project(
    transaction: &mut Transaction<'_, Postgres>,
    actor_id: i32,
    action: &str,
    project_id: i32,
    target_type: &str,
    target_id: i32,
    ip_address: Option<&str>,
    user_agent: Option<&str>,
) -> Result<(), ApiError> {
    write_audit(
        &mut **transaction,
        AuditEvent {
            actor_user_id: Some(actor_id),
            project_id: Some(project_id),
            action,
            target_type: Some(target_type),
            target_id: Some(target_id),
            detail: json!({}),
            ip_address: ip_address.map(str::to_owned),
            user_agent: user_agent.map(str::to_owned),
        },
    )
    .await?;
    Ok(())
}

fn validation_error(detail: &'static str) -> ApiError {
    ApiError::new(StatusCode::UNPROCESSABLE_ENTITY, detail)
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
    use sqlx::PgPool;
    use tower::ServiceExt;
    use uuid::Uuid;

    use crate::{
        build_app,
        config::Settings,
        db::{connect_database, initialize_database},
        AppState,
    };

    async fn request_json(
        app: &Router,
        method: &str,
        path: &str,
        token: Option<&str>,
        body: Option<Value>,
    ) -> (StatusCode, Value) {
        let mut builder = Request::builder().method(method).uri(path);
        if let Some(token) = token {
            builder = builder.header("authorization", format!("Bearer {token}"));
        }
        if body.is_some() {
            builder = builder.header("content-type", "application/json");
        }
        let response = app
            .clone()
            .oneshot(
                builder
                    .body(body.map_or_else(Body::empty, |value| Body::from(value.to_string())))
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), 64 * 1024).await.unwrap();
        let payload = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap()
        };
        (status, payload)
    }

    async fn login(app: &Router, username: &str, password: &str) -> String {
        let (status, payload) = request_json(
            app,
            "POST",
            "/auth/login",
            None,
            Some(json!({"username": username, "password": password})),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        payload["access_token"].as_str().unwrap().to_owned()
    }

    async fn test_project_app() -> Option<(Router, PgPool, String)> {
        let database_url = std::env::var("TEST_DATABASE_URL").ok()?;
        let admin_username = format!(
            "project_guard_admin_{}",
            &Uuid::new_v4().simple().to_string()[..8]
        );
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-integration-secret".to_owned(),
            ),
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
        let app = build_app(AppState::new(pool.clone(), settings).unwrap());
        let admin_token = login(&app, &admin_username, "RustAdmin123!").await;
        Some((app, pool, admin_token))
    }

    async fn create_test_user(
        app: &Router,
        admin_token: &str,
        role: &str,
    ) -> (i64, String, String) {
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let username = format!("project_guard_user_{suffix}");
        let password = "ProjectGuard123!".to_owned();
        let (status, user) = request_json(
            app,
            "POST",
            "/users",
            Some(admin_token),
            Some(json!({
                "username": username,
                "password": password,
                "display_name": "Project Guard User",
                "role": role
            })),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        (user["id"].as_i64().unwrap(), username, password)
    }

    async fn create_test_project(app: &Router, admin_token: &str, owner_id: i64) -> i64 {
        let (status, project) = request_json(
            app,
            "POST",
            "/projects",
            Some(admin_token),
            Some(json!({
                "name": format!("Project Guard {}", Uuid::new_v4()),
                "description": "Project manager invariant test",
                "is_sensitive": true,
                "approval_enabled": true,
                "owner_user_id": owner_id
            })),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        project["id"].as_i64().unwrap()
    }

    fn member_payload(user_id: i64, can_manage: bool) -> Value {
        json!({
            "user_id": user_id,
            "project_role": if can_manage { "owner" } else { "member" },
            "can_read": true,
            "can_write": can_manage,
            "can_review": can_manage,
            "can_evaluate": can_manage,
            "can_manage": can_manage
        })
    }

    #[tokio::test]
    async fn test_add_member_cannot_demote_self_or_last_manager() {
        let Some((app, _, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, owner_name, owner_password) =
            create_test_user(&app, &admin_token, "member").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let owner_token = login(&app, &owner_name, &owner_password).await;

        let (self_demotion, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&owner_token),
            Some(member_payload(owner_id, false)),
        )
        .await;
        assert_eq!(self_demotion, StatusCode::CONFLICT);

        let (last_manager_demotion, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            Some(member_payload(owner_id, false)),
        )
        .await;
        assert_eq!(last_manager_demotion, StatusCode::CONFLICT);

        let (patched_last_manager, _) = request_json(
            &app,
            "PATCH",
            &format!("/projects/{project_id}/members/{owner_id}"),
            Some(&admin_token),
            Some(json!({
                "project_role": "member",
                "can_manage": false
            })),
        )
        .await;
        assert_eq!(patched_last_manager, StatusCode::CONFLICT);

        let (deleted_last_manager, _) = request_json(
            &app,
            "DELETE",
            &format!("/projects/{project_id}/members/{owner_id}"),
            Some(&admin_token),
            None,
        )
        .await;
        assert_eq!(deleted_last_manager, StatusCode::CONFLICT);

        let (second_manager_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (added_second_manager, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            Some(member_payload(second_manager_id, true)),
        )
        .await;
        assert_eq!(added_second_manager, StatusCode::OK);

        let (demoted_owner, _) = request_json(
            &app,
            "PATCH",
            &format!("/projects/{project_id}/members/{owner_id}"),
            Some(&admin_token),
            Some(json!({
                "project_role": "member",
                "can_manage": false
            })),
        )
        .await;
        assert_eq!(demoted_owner, StatusCode::CONFLICT);

        let (deleted_owner, _) = request_json(
            &app,
            "DELETE",
            &format!("/projects/{project_id}/members/{owner_id}"),
            Some(&admin_token),
            None,
        )
        .await;
        assert_eq!(deleted_owner, StatusCode::CONFLICT);

        let (owner_as_reviewer, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": owner_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(owner_as_reviewer, StatusCode::CONFLICT);
    }

    #[tokio::test]
    async fn test_project_reviewer_has_blind_metadata_only_access() {
        let Some((app, _, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, owner_name, owner_password) =
            create_test_user(&app, &admin_token, "member").await;
        let (reviewer_id, reviewer_name, reviewer_password) =
            create_test_user(&app, &admin_token, "reviewer").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let owner_token = login(&app, &owner_name, &owner_password).await;
        let reviewer_token = login(&app, &reviewer_name, &reviewer_password).await;

        let (created, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&owner_token),
            Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(created, StatusCode::OK);

        let (metadata, _) = request_json(
            &app,
            "GET",
            &format!("/projects/{project_id}"),
            Some(&reviewer_token),
            None,
        )
        .await;
        assert_eq!(metadata, StatusCode::OK);

        let (members_status, members) = request_json(
            &app,
            "GET",
            &format!("/projects/{project_id}/members"),
            Some(&reviewer_token),
            None,
        )
        .await;
        assert_eq!(members_status, StatusCode::OK);
        let memberships = members.as_array().unwrap();
        assert_eq!(memberships.len(), 1);
        assert_eq!(memberships[0]["user_id"], reviewer_id);
        assert_eq!(memberships[0]["can_read"], false);
        assert_eq!(memberships[0]["can_write"], false);
        assert_eq!(memberships[0]["can_review"], false);
        assert_eq!(memberships[0]["can_evaluate"], true);
        assert_eq!(memberships[0]["can_manage"], false);

        let (ordinary_content, _) = request_json(
            &app,
            "GET",
            &format!("/projects/{project_id}/notes"),
            Some(&reviewer_token),
            None,
        )
        .await;
        assert_eq!(ordinary_content, StatusCode::FORBIDDEN);

        let (blind_review, _) = request_json(
            &app,
            "GET",
            &format!("/projects/{project_id}/rag/blind-review/batches"),
            Some(&reviewer_token),
            None,
        )
        .await;
        assert_eq!(blind_review, StatusCode::OK);
    }

    #[tokio::test]
    async fn test_member_mutations_reject_independent_reviewer() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (reviewer_id, _, _) = create_test_user(&app, &admin_token, "reviewer").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(added, StatusCode::OK);

        let (members_status, members) = request_json(
            &app,
            "GET",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            None,
        )
        .await;
        assert_eq!(members_status, StatusCode::OK);
        let reviewer_member = members
            .as_array()
            .unwrap()
            .iter()
            .find(|member| member["user_id"] == reviewer_id)
            .unwrap();
        assert_eq!(reviewer_member["is_independent_reviewer"], true);

        let mutations = [
            (
                "POST",
                format!("/projects/{project_id}/members"),
                Some(json!({
                    "user_id": reviewer_id,
                    "project_role": "member",
                    "can_read": true,
                    "can_write": true,
                    "can_review": true,
                    "can_evaluate": false,
                    "can_manage": false
                })),
            ),
            (
                "PATCH",
                format!("/projects/{project_id}/members/{reviewer_id}"),
                Some(json!({"can_read": true})),
            ),
            (
                "DELETE",
                format!("/projects/{project_id}/members/{reviewer_id}"),
                None,
            ),
        ];
        for (method, path, body) in mutations {
            let (status, response) =
                request_json(&app, method, &path, Some(&admin_token), body).await;
            assert_eq!(status, StatusCode::CONFLICT, "{method} {path}");
            assert_eq!(
                response["detail"],
                "Independent reviewers must be managed through reviewer endpoints"
            );
        }

        let membership: (String, bool, bool, bool, bool, bool) = sqlx::query_as(
            r#"
            SELECT lower(project_role::text), can_read, can_write,
                   can_review, can_evaluate, can_manage
            FROM project_members
            WHERE project_id = $1 AND user_id = $2
            "#,
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(
            membership,
            ("reviewer".to_owned(), false, false, false, true, false)
        );
        let reviewer_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_reviewers WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(reviewer_count, 1);

        let (removed, _) = request_json(
            &app,
            "DELETE",
            &format!("/projects/{project_id}/reviewers/{reviewer_id}"),
            Some(&admin_token),
            None,
        )
        .await;
        assert_eq!(removed, StatusCode::OK);
        let reviewer_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_reviewers WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        let member_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_members WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(reviewer_count, 0);
        assert_eq!(member_count, 0);
    }

    #[tokio::test]
    async fn test_add_reviewer_rejects_automatic_project_access() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (pi_id, _, _) = create_test_user(&app, &admin_token, "pi").await;
        let (other_admin_id, _, _) = create_test_user(&app, &admin_token, "super_admin").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;

        for target_id in [owner_id, other_admin_id] {
            let (status, _) = request_json(
                &app,
                "POST",
                &format!("/projects/{project_id}/reviewers"),
                Some(&admin_token),
                Some(json!({"user_id": target_id, "review_scope": "all"})),
            )
            .await;
            assert_eq!(status, StatusCode::CONFLICT);
        }

        let (made_public, _) = request_json(
            &app,
            "PATCH",
            &format!("/projects/{project_id}"),
            Some(&admin_token),
            Some(json!({"is_sensitive": false})),
        )
        .await;
        assert_eq!(made_public, StatusCode::OK);
        let (public_pi, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": pi_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(public_pi, StatusCode::CONFLICT);

        let sensitive_project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (sensitive_pi, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{sensitive_project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": pi_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(sensitive_pi, StatusCode::OK);

        let rejected_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_reviewers WHERE project_id = $1 AND user_id = ANY($2)",
        )
        .bind(project_id as i32)
        .bind(vec![owner_id as i32, other_admin_id as i32, pi_id as i32])
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(rejected_count, 0);
    }

    #[tokio::test]
    async fn test_add_reviewer_rechecks_role_after_user_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (reviewer_id, _, _) = create_test_user(&app, &admin_token, "reviewer").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;

        let mut blocker = pool.begin().await.unwrap();
        sqlx::query("SELECT id FROM users WHERE id = $1 FOR UPDATE")
            .bind(reviewer_id as i32)
            .fetch_one(&mut *blocker)
            .await
            .unwrap();
        let reviewer_app = app.clone();
        let reviewer_path = format!("/projects/{project_id}/reviewers");
        let mut assignment = tokio::spawn(async move {
            request_json(
                &reviewer_app,
                "POST",
                &reviewer_path,
                Some(&admin_token),
                Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
            )
            .await
        });

        let mut waiting_for_user_lock = false;
        for _ in 0..100 {
            waiting_for_user_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND query LIKE '%project_actor_reviewer_user_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_user_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_user_lock,
            "reviewer assignment did not wait on the target user row"
        );

        sqlx::query("UPDATE users SET role = 'SUPER_ADMIN'::userrole WHERE id = $1")
            .bind(reviewer_id as i32)
            .execute(&mut *blocker)
            .await
            .unwrap();
        blocker.commit().await.unwrap();

        let (status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut assignment)
            .await
            .expect("reviewer assignment should resume after user lock release")
            .unwrap();
        assert_eq!(status, StatusCode::CONFLICT);
        let reviewer_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_reviewers WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(reviewer_count, 0);
    }

    #[tokio::test]
    async fn test_update_project_rejects_public_pi_reviewer_transition() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (pi_id, _, _) = create_test_user(&app, &admin_token, "pi").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": pi_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(added, StatusCode::OK);

        let (made_public, _) = request_json(
            &app,
            "PATCH",
            &format!("/projects/{project_id}"),
            Some(&admin_token),
            Some(json!({"is_sensitive": false})),
        )
        .await;
        assert_eq!(made_public, StatusCode::CONFLICT);
        let persisted: bool = sqlx::query_scalar("SELECT is_sensitive FROM projects WHERE id = $1")
            .bind(project_id as i32)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert!(persisted);
    }

    #[tokio::test]
    async fn test_update_project_rechecks_reviewer_roles_after_user_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (reviewer_id, _, _) = create_test_user(&app, &admin_token, "reviewer").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(added, StatusCode::OK);

        let mut blocker = pool.begin().await.unwrap();
        sqlx::query("SELECT id FROM users WHERE id = $1 FOR UPDATE")
            .bind(reviewer_id as i32)
            .fetch_one(&mut *blocker)
            .await
            .unwrap();
        let patch_app = app.clone();
        let patch_path = format!("/projects/{project_id}");
        let mut patch = tokio::spawn(async move {
            request_json(
                &patch_app,
                "PATCH",
                &patch_path,
                Some(&admin_token),
                Some(json!({"is_sensitive": false})),
            )
            .await
        });

        let mut waiting_for_user_lock = false;
        for _ in 0..100 {
            waiting_for_user_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND query LIKE '%project_actor_reviewer_user_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_user_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_user_lock,
            "project update did not wait on independent reviewer user rows"
        );

        sqlx::query("UPDATE users SET role = 'PI'::userrole WHERE id = $1")
            .bind(reviewer_id as i32)
            .execute(&mut *blocker)
            .await
            .unwrap();
        blocker.commit().await.unwrap();

        let (status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut patch)
            .await
            .expect("project update should resume after reviewer user lock release")
            .unwrap();
        assert_eq!(status, StatusCode::CONFLICT);
        let persisted: bool = sqlx::query_scalar("SELECT is_sensitive FROM projects WHERE id = $1")
            .bind(project_id as i32)
            .fetch_one(&pool)
            .await
            .unwrap();
        assert!(persisted);
    }

    #[tokio::test]
    async fn test_reviewer_role_locks_do_not_deadlock_cross_project_audits() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (actor_a, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (actor_b, _, _) = create_test_user(&app, &admin_token, "member").await;
        let project_a = create_test_project(&app, &admin_token, actor_a).await;
        let project_b = create_test_project(&app, &admin_token, actor_b).await;
        for (project_id, reviewer_id) in [(project_a, actor_b), (project_b, actor_a)] {
            let (status, _) = request_json(
                &app,
                "POST",
                &format!("/projects/{project_id}/reviewers"),
                Some(&admin_token),
                Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
            )
            .await;
            assert_eq!(status, StatusCode::OK);
        }

        let mut transaction_a = pool.begin().await.unwrap();
        super::lock_project_membership(&mut transaction_a, project_a as i32)
            .await
            .unwrap();
        super::protect_reviewer_independence_for_project_update(
            &mut transaction_a,
            project_a as i32,
            Some(true),
            None,
        )
        .await
        .unwrap();
        let mut transaction_b = pool.begin().await.unwrap();
        super::lock_project_membership(&mut transaction_b, project_b as i32)
            .await
            .unwrap();
        super::protect_reviewer_independence_for_project_update(
            &mut transaction_b,
            project_b as i32,
            Some(true),
            None,
        )
        .await
        .unwrap();

        let (audit_a, audit_b) = tokio::time::timeout(std::time::Duration::from_secs(3), async {
            tokio::join!(
                super::audit_project(
                    &mut transaction_a,
                    actor_a as i32,
                    "update_project",
                    project_a as i32,
                    "project",
                    project_a as i32,
                    None,
                    None,
                ),
                super::audit_project(
                    &mut transaction_b,
                    actor_b as i32,
                    "update_project",
                    project_b as i32,
                    "project",
                    project_b as i32,
                    None,
                    None,
                )
            )
        })
        .await
        .expect("cross-project audit writes must not deadlock");
        audit_a.unwrap();
        audit_b.unwrap();
        transaction_a.rollback().await.unwrap();
        transaction_b.rollback().await.unwrap();
    }

    #[tokio::test]
    async fn test_update_project_rechecks_manager_after_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (manager_id, manager_name, manager_password) =
            create_test_user(&app, &admin_token, "member").await;
        let (replacement_owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added_manager, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            Some(member_payload(manager_id, true)),
        )
        .await;
        assert_eq!(added_manager, StatusCode::OK);
        let manager_token = login(&app, &manager_name, &manager_password).await;

        let mut blocker = pool.begin().await.unwrap();
        super::lock_project_membership(&mut blocker, project_id as i32)
            .await
            .unwrap();
        let patch_app = app.clone();
        let patch_path = format!("/projects/{project_id}");
        let mut patch = tokio::spawn(async move {
            request_json(
                &patch_app,
                "PATCH",
                &patch_path,
                Some(&manager_token),
                Some(json!({
                    "is_sensitive": false,
                    "status": "archived",
                    "owner_user_id": replacement_owner_id
                })),
            )
            .await
        });

        let mut waiting_for_lock = false;
        for _ in 0..100 {
            waiting_for_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE '%pg_advisory_xact_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_lock,
            "project update did not wait for project lock"
        );

        sqlx::query(
            r#"
            UPDATE project_members
            SET project_role = 'MEMBER'::projectrole,
                can_read = false, can_manage = false
            WHERE project_id = $1 AND user_id = $2
            "#,
        )
        .bind(project_id as i32)
        .bind(manager_id as i32)
        .execute(&mut *blocker)
        .await
        .unwrap();
        blocker.commit().await.unwrap();

        let (patch_status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut patch)
            .await
            .expect("project update should resume after lock release")
            .unwrap();
        assert_eq!(patch_status, StatusCode::FORBIDDEN);
        let persisted: (bool, String, Option<i32>) = sqlx::query_as(
            "SELECT is_sensitive, lower(status::text), owner_user_id FROM projects WHERE id = $1",
        )
        .bind(project_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(
            persisted,
            (true, "active".to_owned(), Some(owner_id as i32))
        );
    }

    #[tokio::test]
    async fn test_update_project_rechecks_disabled_actor_after_project_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (manager_id, manager_name, manager_password) =
            create_test_user(&app, &admin_token, "member").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added_manager, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            Some(member_payload(manager_id, true)),
        )
        .await;
        assert_eq!(added_manager, StatusCode::OK);
        let manager_token = login(&app, &manager_name, &manager_password).await;

        let mut blocker = pool.begin().await.unwrap();
        super::lock_project_membership(&mut blocker, project_id as i32)
            .await
            .unwrap();
        let patch_app = app.clone();
        let patch_path = format!("/projects/{project_id}");
        let mut patch = tokio::spawn(async move {
            request_json(
                &patch_app,
                "PATCH",
                &patch_path,
                Some(&manager_token),
                Some(json!({"description": "must not be committed"})),
            )
            .await
        });

        let mut waiting_for_lock = false;
        for _ in 0..100 {
            waiting_for_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE '%pg_advisory_xact_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_lock,
            "project update did not wait for project lock"
        );

        sqlx::query(
            r#"
            UPDATE users
            SET status = 'DISABLED'::userstatus,
                auth_version = auth_version + 1
            WHERE id = $1
            "#,
        )
        .bind(manager_id as i32)
        .execute(&mut *blocker)
        .await
        .unwrap();
        blocker.commit().await.unwrap();

        let (status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut patch)
            .await
            .expect("project update should resume after project lock release")
            .unwrap();
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        let description: Option<String> =
            sqlx::query_scalar("SELECT description FROM projects WHERE id = $1")
                .bind(project_id as i32)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(
            description.as_deref(),
            Some("Project manager invariant test")
        );
    }

    #[tokio::test]
    async fn test_update_project_rechecks_current_super_admin_role_after_project_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (actor_id, actor_name, actor_password) =
            create_test_user(&app, &admin_token, "super_admin").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let actor_token = login(&app, &actor_name, &actor_password).await;

        let mut blocker = pool.begin().await.unwrap();
        super::lock_project_membership(&mut blocker, project_id as i32)
            .await
            .unwrap();
        let patch_app = app.clone();
        let patch_path = format!("/projects/{project_id}");
        let mut patch = tokio::spawn(async move {
            request_json(
                &patch_app,
                "PATCH",
                &patch_path,
                Some(&actor_token),
                Some(json!({"description": "stale super admin update"})),
            )
            .await
        });

        let mut waiting_for_lock = false;
        for _ in 0..100 {
            waiting_for_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE '%pg_advisory_xact_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_lock,
            "project update did not wait for project lock"
        );

        // Keep auth_version unchanged so this specifically proves the role is
        // reloaded after the advisory lock, rather than trusting CurrentUser.
        sqlx::query("UPDATE users SET role = 'MEMBER'::userrole WHERE id = $1")
            .bind(actor_id as i32)
            .execute(&mut *blocker)
            .await
            .unwrap();
        blocker.commit().await.unwrap();

        let (status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut patch)
            .await
            .expect("project update should resume after project lock release")
            .unwrap();
        assert_eq!(status, StatusCode::FORBIDDEN);
        let description: Option<String> =
            sqlx::query_scalar("SELECT description FROM projects WHERE id = $1")
                .bind(project_id as i32)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(
            description.as_deref(),
            Some("Project manager invariant test")
        );
    }

    #[tokio::test]
    async fn test_add_reviewer_uses_reloaded_actor_role_after_project_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (actor_id, actor_name, actor_password) =
            create_test_user(&app, &admin_token, "super_admin").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added_manager, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            Some(member_payload(actor_id, true)),
        )
        .await;
        assert_eq!(added_manager, StatusCode::OK);
        let actor_token = login(&app, &actor_name, &actor_password).await;

        let mut blocker = pool.begin().await.unwrap();
        super::lock_project_membership(&mut blocker, project_id as i32)
            .await
            .unwrap();
        let reviewer_app = app.clone();
        let reviewer_path = format!("/projects/{project_id}/reviewers");
        let mut assignment = tokio::spawn(async move {
            request_json(
                &reviewer_app,
                "POST",
                &reviewer_path,
                Some(&actor_token),
                Some(json!({"user_id": actor_id, "review_scope": "all"})),
            )
            .await
        });

        let mut waiting_for_lock = false;
        for _ in 0..100 {
            waiting_for_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE '%pg_advisory_xact_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_lock,
            "reviewer assignment did not wait for project lock"
        );

        // Preserve auth_version to isolate the downstream role-snapshot check.
        sqlx::query("UPDATE users SET role = 'MEMBER'::userrole WHERE id = $1")
            .bind(actor_id as i32)
            .execute(&mut *blocker)
            .await
            .unwrap();
        blocker.commit().await.unwrap();

        let (status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut assignment)
            .await
            .expect("reviewer assignment should resume after project lock release")
            .unwrap();
        assert_eq!(status, StatusCode::CONFLICT);
        let reviewer_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_reviewers WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(actor_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(reviewer_count, 0);
    }

    #[tokio::test]
    async fn test_remove_reviewer_rechecks_manager_after_project_lock_wait() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let (manager_id, manager_name, manager_password) =
            create_test_user(&app, &admin_token, "member").await;
        let (reviewer_id, _, _) = create_test_user(&app, &admin_token, "reviewer").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await;
        let (added_manager, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/members"),
            Some(&admin_token),
            Some(member_payload(manager_id, true)),
        )
        .await;
        assert_eq!(added_manager, StatusCode::OK);
        let (added_reviewer, _) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&admin_token),
            Some(json!({"user_id": reviewer_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(added_reviewer, StatusCode::OK);
        let manager_token = login(&app, &manager_name, &manager_password).await;

        let mut blocker = pool.begin().await.unwrap();
        super::lock_project_membership(&mut blocker, project_id as i32)
            .await
            .unwrap();
        let delete_app = app.clone();
        let delete_path = format!("/projects/{project_id}/reviewers/{reviewer_id}");
        let mut deletion = tokio::spawn(async move {
            request_json(
                &delete_app,
                "DELETE",
                &delete_path,
                Some(&manager_token),
                None,
            )
            .await
        });

        let mut waiting_for_project_lock = false;
        for _ in 0..100 {
            waiting_for_project_lock = sqlx::query_scalar(
                r#"
                SELECT EXISTS(
                    SELECT 1 FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND state = 'active'
                      AND wait_event_type = 'Lock'
                      AND wait_event = 'advisory'
                      AND query LIKE '%pg_advisory_xact_lock%'
                )
                "#,
            )
            .fetch_one(&pool)
            .await
            .unwrap();
            if waiting_for_project_lock {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
        }
        assert!(
            waiting_for_project_lock,
            "reviewer removal did not wait for the project lock"
        );

        sqlx::query(
            r#"
            UPDATE project_members
            SET project_role = 'MEMBER'::projectrole,
                can_read = false, can_manage = false
            WHERE project_id = $1 AND user_id = $2
            "#,
        )
        .bind(project_id as i32)
        .bind(manager_id as i32)
        .execute(&mut *blocker)
        .await
        .unwrap();
        blocker.commit().await.unwrap();

        let (status, _) = tokio::time::timeout(std::time::Duration::from_secs(2), &mut deletion)
            .await
            .expect("reviewer removal should resume after project lock release")
            .unwrap();
        assert_eq!(status, StatusCode::FORBIDDEN);
        let reviewer_count: i64 = sqlx::query_scalar(
            "SELECT count(*) FROM project_reviewers WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(reviewer_count, 1);
        let can_evaluate: bool = sqlx::query_scalar(
            "SELECT can_evaluate FROM project_members WHERE project_id = $1 AND user_id = $2",
        )
        .bind(project_id as i32)
        .bind(reviewer_id as i32)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert!(can_evaluate);
    }

    #[tokio::test]
    async fn test_project_membership_lock_serializes_mutations() {
        let Some((app, pool, admin_token)) = test_project_app().await else {
            return;
        };
        let (owner_id, _, _) = create_test_user(&app, &admin_token, "member").await;
        let project_id = create_test_project(&app, &admin_token, owner_id).await as i32;
        let mut first = pool.begin().await.unwrap();
        super::lock_project_membership(&mut first, project_id)
            .await
            .unwrap();

        let second_pool = pool.clone();
        let mut contender = tokio::spawn(async move {
            let mut second = second_pool.begin().await.unwrap();
            super::lock_project_membership(&mut second, project_id)
                .await
                .unwrap();
            second.rollback().await.unwrap();
        });
        assert!(
            tokio::time::timeout(std::time::Duration::from_millis(150), &mut contender)
                .await
                .is_err()
        );

        first.commit().await.unwrap();
        tokio::time::timeout(std::time::Duration::from_secs(2), contender)
            .await
            .expect("contending mutation should resume after transaction commit")
            .unwrap();
    }

    #[tokio::test]
    async fn test_project_crud_membership_permissions_and_pagination() {
        let Ok(database_url) = std::env::var("TEST_DATABASE_URL") else {
            return;
        };
        let suffix = &Uuid::new_v4().simple().to_string()[..8];
        let admin_username = format!("project_admin_{suffix}");
        let settings = Settings::from_map(&HashMap::from([
            ("DATABASE_URL".to_owned(), database_url),
            (
                "SECRET_KEY".to_owned(),
                "rust-integration-secret".to_owned(),
            ),
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
        let admin_token = login(&app, &admin_username, "RustAdmin123!").await;
        let owner_name = format!("project_owner_{suffix}");
        let outsider_name = format!("project_outsider_{suffix}");

        let (_, owner) = request_json(
            &app,
            "POST",
            "/users",
            Some(&admin_token),
            Some(json!({
                "username": owner_name,
                "password": "OwnerPass123!",
                "display_name": "Owner",
                "role": "member"
            })),
        )
        .await;
        let (_, outsider) = request_json(
            &app,
            "POST",
            "/users",
            Some(&admin_token),
            Some(json!({
                "username": outsider_name,
                "password": "OutsiderPass123!",
                "display_name": "Outsider",
                "role": "member"
            })),
        )
        .await;
        let owner_id = owner["id"].as_i64().unwrap();
        let outsider_id = outsider["id"].as_i64().unwrap();

        let (created_status, project) = request_json(
            &app,
            "POST",
            "/projects",
            Some(&admin_token),
            Some(json!({
                "name": format!("Rust Project {suffix}"),
                "description": "Rust integration project",
                "is_sensitive": true,
                "approval_enabled": true,
                "owner_user_id": owner_id
            })),
        )
        .await;
        assert_eq!(created_status, StatusCode::OK);
        let project_id = project["id"].as_i64().unwrap();
        let owner_token = login(&app, &owner_name, "OwnerPass123!").await;
        let outsider_token = login(&app, &outsider_name, "OutsiderPass123!").await;

        let (listed_status, listed) = request_json(
            &app,
            "GET",
            "/projects?skip=0&limit=20",
            Some(&owner_token),
            None,
        )
        .await;
        assert_eq!(listed_status, StatusCode::OK);
        assert!(listed["items"]
            .as_array()
            .unwrap()
            .iter()
            .any(|item| item["id"] == project_id));

        let (forbidden, _) = request_json(
            &app,
            "GET",
            &format!("/projects/{project_id}"),
            Some(&outsider_token),
            None,
        )
        .await;
        assert_eq!(forbidden, StatusCode::FORBIDDEN);

        let (updated, body) = request_json(
            &app,
            "PATCH",
            &format!("/projects/{project_id}"),
            Some(&owner_token),
            Some(json!({"description": "Updated by owner"})),
        )
        .await;
        assert_eq!(updated, StatusCode::OK);
        assert_eq!(body["description"], "Updated by owner");

        let (reviewer, body) = request_json(
            &app,
            "POST",
            &format!("/projects/{project_id}/reviewers"),
            Some(&owner_token),
            Some(json!({"user_id": outsider_id, "review_scope": "all"})),
        )
        .await;
        assert_eq!(reviewer, StatusCode::OK);
        assert_eq!(body["user_id"], outsider_id);

        let (last_manager, body) = request_json(
            &app,
            "DELETE",
            &format!("/projects/{project_id}/members/{owner_id}"),
            Some(&owner_token),
            None,
        )
        .await;
        assert_eq!(last_manager, StatusCode::CONFLICT);
        assert_eq!(body["detail"], "项目至少需保留一名管理员");
    }
}
