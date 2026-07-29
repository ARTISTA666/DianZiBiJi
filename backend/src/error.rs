use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

#[derive(Debug, thiserror::Error)]
#[error("{detail}")]
pub struct ApiError {
    pub status: StatusCode,
    pub detail: String,
}

impl ApiError {
    pub fn new(status: StatusCode, detail: impl Into<String>) -> Self {
        Self {
            status,
            detail: detail.into(),
        }
    }

    pub fn internal(cause: impl std::fmt::Display) -> Self {
        tracing::error!(%cause, "request failed");
        Self::new(StatusCode::INTERNAL_SERVER_ERROR, "Internal server error")
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (self.status, Json(json!({"detail": self.detail}))).into_response()
    }
}

impl From<sqlx::Error> for ApiError {
    fn from(cause: sqlx::Error) -> Self {
        Self::internal(cause)
    }
}

#[cfg(test)]
mod tests {
    use axum::{body::to_bytes, http::StatusCode, response::IntoResponse};

    use super::ApiError;

    #[tokio::test]
    async fn test_api_error_uses_fastapi_detail_shape() {
        let response = ApiError::new(StatusCode::UNAUTHORIZED, "Invalid token").into_response();

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            &to_bytes(response.into_body(), 1024).await.unwrap()[..],
            br#"{"detail":"Invalid token"}"#
        );
    }
}
