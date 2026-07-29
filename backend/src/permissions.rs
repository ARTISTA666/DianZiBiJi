use axum::http::StatusCode;
use sqlx::PgPool;

use crate::{
    error::ApiError,
    models::{ProjectRead, UserRecord},
};

const PROJECT_COLUMNS: &str = r#"
    id, name, description, is_sensitive,
    lower(status::text) AS status, approval_enabled, owner_user_id
"#;

pub async fn fetch_project(pool: &PgPool, project_id: i32) -> Result<ProjectRead, ApiError> {
    let query = format!("SELECT {PROJECT_COLUMNS} FROM projects WHERE id = $1");
    sqlx::query_as::<_, ProjectRead>(&query)
        .bind(project_id)
        .fetch_optional(pool)
        .await?
        .ok_or_else(|| ApiError::new(StatusCode::NOT_FOUND, "Project not found"))
}

pub async fn require_project_access(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<ProjectRead, ApiError> {
    let project = fetch_project(pool, project_id).await?;
    if can_access_project(pool, user, &project).await? {
        Ok(project)
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Project access denied",
        ))
    }
}

pub async fn require_project_metadata_access(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<ProjectRead, ApiError> {
    let project = fetch_project(pool, project_id).await?;
    if can_access_project(pool, user, &project).await?
        || can_evaluate_project(pool, user, project_id).await?
    {
        Ok(project)
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Project access denied",
        ))
    }
}

pub async fn can_access_project(
    pool: &PgPool,
    user: &UserRecord,
    project: &ProjectRead,
) -> Result<bool, ApiError> {
    if user.role == "super_admin"
        || project.owner_user_id == Some(user.id)
        || (user.role == "pi" && !project.is_sensitive)
    {
        return Ok(true);
    }
    Ok(sqlx::query_scalar::<_, bool>(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM project_members
            WHERE project_id = $1 AND user_id = $2 AND can_read = true
        )
        "#,
    )
    .bind(project.id)
    .bind(user.id)
    .fetch_one(pool)
    .await?)
}

pub async fn can_write_project(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<bool, ApiError> {
    if user.role == "super_admin" {
        return Ok(true);
    }
    membership_flag(pool, user.id, project_id, "can_write").await
}

pub async fn can_manage_project(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<bool, ApiError> {
    if user.role == "super_admin" {
        return Ok(true);
    }
    let owner: bool = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM projects WHERE id = $1 AND owner_user_id = $2)",
    )
    .bind(project_id)
    .bind(user.id)
    .fetch_one(pool)
    .await?;
    if owner {
        return Ok(true);
    }
    Ok(sqlx::query_scalar::<_, bool>(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM project_members
            WHERE project_id = $1 AND user_id = $2
              AND (can_manage = true OR project_role = 'OWNER'::projectrole)
        )
        "#,
    )
    .bind(project_id)
    .bind(user.id)
    .fetch_one(pool)
    .await?)
}

pub async fn require_project_manager(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<ProjectRead, ApiError> {
    let project = require_project_access(pool, user, project_id).await?;
    if can_manage_project(pool, user, project_id).await? {
        Ok(project)
    } else {
        Err(ApiError::new(
            StatusCode::FORBIDDEN,
            "Project manage permission required",
        ))
    }
}

pub async fn can_review_project(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<bool, ApiError> {
    if user.role == "super_admin" {
        return Ok(true);
    }
    Ok(sqlx::query_scalar::<_, bool>(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM project_members
            WHERE project_id = $1 AND user_id = $2
              AND (can_review = true OR can_manage = true)
        ) OR EXISTS(
            SELECT 1 FROM project_reviewers
            WHERE project_id = $1 AND user_id = $2
        )
        "#,
    )
    .bind(project_id)
    .bind(user.id)
    .fetch_one(pool)
    .await?)
}

pub async fn can_evaluate_project(
    pool: &PgPool,
    user: &UserRecord,
    project_id: i32,
) -> Result<bool, ApiError> {
    if user.role == "super_admin" {
        return Ok(true);
    }
    Ok(sqlx::query_scalar::<_, bool>(
        r#"
        SELECT EXISTS(
            SELECT 1 FROM project_members
            WHERE project_id = $1 AND user_id = $2
              AND (can_evaluate = true OR can_manage = true)
        )
        "#,
    )
    .bind(project_id)
    .bind(user.id)
    .fetch_one(pool)
    .await?)
}

pub async fn accessible_project_ids(
    pool: &PgPool,
    user: &UserRecord,
) -> Result<Vec<i32>, ApiError> {
    if user.role == "super_admin" {
        return Ok(sqlx::query_scalar("SELECT id FROM projects ORDER BY id")
            .fetch_all(pool)
            .await?);
    }
    let ids = if user.role == "pi" {
        sqlx::query_scalar(
            r#"
            SELECT DISTINCT p.id
            FROM projects p
            LEFT JOIN project_members pm
              ON pm.project_id = p.id AND pm.user_id = $1 AND pm.can_read = true
            WHERE p.owner_user_id = $1 OR p.is_sensitive = false OR pm.id IS NOT NULL
            ORDER BY p.id
            "#,
        )
        .bind(user.id)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query_scalar(
            r#"
            SELECT DISTINCT p.id
            FROM projects p
            LEFT JOIN project_members pm
              ON pm.project_id = p.id AND pm.user_id = $1 AND pm.can_read = true
            WHERE p.owner_user_id = $1 OR pm.id IS NOT NULL
            ORDER BY p.id
            "#,
        )
        .bind(user.id)
        .fetch_all(pool)
        .await?
    };
    Ok(ids)
}

async fn membership_flag(
    pool: &PgPool,
    user_id: i32,
    project_id: i32,
    flag: &str,
) -> Result<bool, ApiError> {
    let query = format!(
        "SELECT EXISTS(SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2 AND {flag} = true)"
    );
    Ok(sqlx::query_scalar(&query)
        .bind(project_id)
        .bind(user_id)
        .fetch_one(pool)
        .await?)
}
