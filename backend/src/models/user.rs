use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, sqlx::FromRow)]
pub struct UserRecord {
    pub id: i32,
    pub username: String,
    pub password_hash: String,
    pub display_name: String,
    pub email: Option<String>,
    pub role: String,
    pub status: String,
    pub auth_version: i32,
}

#[derive(Debug, Serialize)]
pub struct CurrentUserResponse {
    pub id: i32,
    pub username: String,
    pub display_name: String,
    pub role: String,
}

#[derive(Debug, Deserialize)]
pub struct LoginRequest {
    pub username: String,
    pub password: String,
}

#[derive(Debug, Serialize)]
pub struct TokenResponse {
    pub access_token: String,
    pub token_type: &'static str,
}

#[derive(Debug, Deserialize)]
pub struct UserCreate {
    pub username: String,
    pub password: String,
    pub display_name: String,
    pub email: Option<String>,
    #[serde(default = "default_member_role")]
    pub role: String,
}

fn default_member_role() -> String {
    "member".to_owned()
}

#[derive(Debug, Default, Deserialize)]
pub struct UserUpdate {
    pub display_name: Option<String>,
    pub email: Option<String>,
    pub role: Option<String>,
    pub status: Option<String>,
    pub password: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct UserPasswordChange {
    pub current_password: String,
    pub new_password: String,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct UserRead {
    pub id: i32,
    pub username: String,
    pub display_name: String,
    pub email: Option<String>,
    pub role: String,
    pub status: String,
}

fn validate_membership(
    value: &str,
    allowed: &[&str],
    unsupported: &'static str,
) -> Result<(), &'static str> {
    if allowed.contains(&value) {
        Ok(())
    } else {
        Err(unsupported)
    }
}

pub fn validate_role(value: &str) -> Result<(), &'static str> {
    validate_membership(
        value,
        &[
            "super_admin",
            "pi",
            "group_leader",
            "project_owner",
            "reviewer",
            "member",
        ],
        "Unsupported user role",
    )
}

pub fn validate_user_status(value: &str) -> Result<(), &'static str> {
    validate_membership(value, &["active", "disabled"], "Unsupported user status")
}
