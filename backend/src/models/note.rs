use chrono::{DateTime, NaiveDate, Utc};
use serde::{de::Deserializer, Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Default, Deserialize)]
pub struct NoteListQuery {
    pub skip: Option<i64>,
    pub limit: Option<i64>,
    pub status: Option<String>,
    pub search: Option<String>,
    pub sort: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct NoteCreate {
    pub title: String,
    pub experiment_type: String,
    pub experiment_date: Option<NaiveDate>,
    pub template_id: Option<i32>,
    #[serde(default = "empty_json_object")]
    pub fixed_fields_json: Value,
    #[serde(default = "empty_json_object")]
    pub content_json: Value,
    /// 自由文本正文。content_json 尚无 "text" 键时会归一写入 content_json["text"]。
    #[serde(default)]
    pub content_text: Option<String>,
}

fn empty_json_object() -> Value {
    serde_json::json!({})
}

#[derive(Debug, Default, Deserialize)]
pub struct NoteUpdate {
    pub title: Option<String>,
    pub experiment_type: Option<String>,
    pub experiment_date: Option<NaiveDate>,
    /// `None` keeps the current template; `Some(None)` explicitly clears it.
    #[serde(default, deserialize_with = "deserialize_nullable_field")]
    pub template_id: Option<Option<i32>>,
    pub fixed_fields_json: Option<Value>,
    pub content_json: Option<Value>,
    /// 自由文本正文。content_json 尚无 "text" 键时会归一写入 content_json["text"]。
    #[serde(default)]
    pub content_text: Option<String>,
    pub change_summary: Option<String>,
}

/// Preserve the distinction between an omitted PATCH field and an explicit
/// JSON `null`, so callers can clear nullable values without changing the
/// semantics of existing partial updates.
pub fn deserialize_nullable_field<'de, D, T>(deserializer: D) -> Result<Option<Option<T>>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Ok(Some(Option::<T>::deserialize(deserializer)?))
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct NoteRead {
    pub id: i32,
    pub project_id: i32,
    pub template_id: Option<i32>,
    pub title: String,
    pub experiment_type: String,
    pub experiment_date: Option<NaiveDate>,
    pub owner_user_id: i32,
    pub status: String,
    pub current_version_id: Option<i32>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct NoteVersionRead {
    pub id: i32,
    pub note_id: i32,
    pub version_number: i32,
    pub fixed_fields_json: Value,
    pub content_json: Value,
    pub created_by: i32,
    pub change_summary: Option<String>,
    pub is_locked: bool,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Default, Deserialize)]
pub struct ApprovalRequest {
    pub comment: Option<String>,
}

#[derive(Clone, Debug, Serialize, sqlx::FromRow)]
pub struct NoteApprovalRead {
    pub id: i32,
    pub note_id: i32,
    pub version_id: i32,
    pub reviewer_user_id: i32,
    pub action: String,
    pub comment: Option<String>,
    pub created_at: DateTime<Utc>,
}

#[cfg(test)]
mod tests {
    use super::NoteUpdate;

    #[test]
    fn note_update_round_trips_template_id() {
        let update: NoteUpdate = serde_json::from_str(r#"{"template_id": 5}"#).unwrap();
        assert_eq!(update.template_id, Some(Some(5)));
    }

    #[test]
    fn note_update_can_clear_template_id() {
        let update: NoteUpdate = serde_json::from_str(r#"{"template_id": null}"#).unwrap();
        assert_eq!(update.template_id, Some(None));
    }

    #[test]
    fn note_update_omitted_template_keeps_partial_update_semantics() {
        let update: NoteUpdate = serde_json::from_str(r#"{"title": "revised"}"#).unwrap();
        assert_eq!(update.template_id, None);
    }
}
