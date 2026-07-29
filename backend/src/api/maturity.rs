use std::{
    collections::HashSet,
    fs,
    path::{Path, PathBuf},
};

use axum::{extract::State, routing::get, Json, Router};
use chrono::{DateTime, Duration, Utc};
use serde_json::{json, Map, Value};

use crate::{api::auth::CurrentUser, AppState};

const INTERNAL_REQUIRED: &[&str] = &[
    "retrieval",
    "rag_experiment",
    "agent",
    "system",
    "evidence_manifest",
];
const FINAL_REQUIRED: &[&str] = &[
    "internal release-candidate gate passed",
    "production configuration was checked in production mode",
    "external confirmatory human-review freeze passed",
    "long soak evidence passed",
    "real TLS deployment evidence passed",
    "offsite encrypted backup evidence passed",
    "final maturity evidence manifest verified",
];
const COMPLETION_REQUIRED: &[&str] = &[
    "final maturity gate passed before reporting review",
    "confirmatory freeze exists and validates",
    "human review export uses confirmatory protocol",
    "human review export is complete",
    "human review methods match frozen methods",
    "human review reviewers match frozen reviewers",
    "human review questions match frozen questions",
    "human review covers every frozen question and method",
    "confirmatory review evidence manifest verified",
];
const MAX_GATE_AGE_HOURS: i64 = 168;

struct GateSpec {
    key: &'static str,
    title: &'static str,
    filename: &'static str,
    scope: &'static str,
}

const GATES: &[GateSpec] = &[
    GateSpec {
        key: "internal_release",
        title: "内部门禁",
        filename: "main-maturity-gate-latest.json",
        scope: "full-system release-candidate maturity gate",
    },
    GateSpec {
        key: "final_maturity",
        title: "最终成熟门禁",
        filename: "final-maturity-gate-latest.json",
        scope: "final maturity gate for confirmatory human review",
    },
    GateSpec {
        key: "confirmatory_review_completion",
        title: "确认性人工评审完成门禁",
        filename: "confirmatory-review-completion-latest.json",
        scope: "confirmatory human review completion gate",
    },
];

pub fn router() -> Router<AppState> {
    Router::new().route("/maturity/status", get(maturity_status))
}

async fn maturity_status(
    State(state): State<AppState>,
    CurrentUser(_user): CurrentUser,
) -> Json<Value> {
    Json(maturity_payload(
        &find_maturity_root(),
        &state.settings.app_revision,
    ))
}

fn maturity_payload(root: &Path, runtime_revision: &str) -> Value {
    let gates: Vec<Value> = GATES
        .iter()
        .map(|spec| {
            gate_status_for_revision(
                root,
                spec.key,
                spec.title,
                spec.filename,
                spec.scope,
                runtime_revision,
            )
        })
        .collect();
    let final_passed = gate_passed(&gates, "final_maturity");
    let completion_passed = gate_passed(&gates, "confirmatory_review_completion");
    json!({
        "passed": gates.iter().all(|gate| gate["passed"] == Value::Bool(true)),
        "human_review_allowed": final_passed,
        "human_review_report_allowed": final_passed && completion_passed,
        "gates": gates
    })
}

fn gate_passed(gates: &[Value], key: &str) -> bool {
    gates.iter().any(|gate| {
        gate["key"] == Value::String(key.to_owned()) && gate["passed"] == Value::Bool(true)
    })
}

fn find_maturity_root() -> PathBuf {
    if let Some(path) = std::env::var_os("MATURITY_ROOT") {
        return PathBuf::from(path);
    }
    let current = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    let mut candidate = Some(current.as_path());
    while let Some(path) = candidate {
        if path.join("docs/experiments").is_dir() {
            return path.to_path_buf();
        }
        candidate = path.parent();
    }
    current
}

#[cfg(test)]
fn gate_status(root: &Path, key: &str, title: &str, filename: &str, scope: &str) -> Value {
    gate_status_for_revision(
        root,
        key,
        title,
        filename,
        scope,
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
}

fn gate_status_for_revision(
    root: &Path,
    key: &str,
    title: &str,
    filename: &str,
    scope: &str,
    runtime_revision: &str,
) -> Value {
    let relative = PathBuf::from("docs/experiments").join(filename);
    let path = root.join(&relative);
    if !path.is_file() {
        let display = relative.to_string_lossy();
        return json!({
            "key": key,
            "title": title,
            "path": display,
            "exists": false,
            "passed": false,
            "generated_at": Value::Null,
            "blockers": [format!("missing: {display}")]
        });
    }
    let text = match fs::read_to_string(&path) {
        Ok(text) => text,
        Err(error) => {
            return failed_gate(
                key,
                title,
                &relative,
                true,
                None,
                vec![format!("invalid JSON: {error}")],
            )
        }
    };
    let payload: Value = match serde_json::from_str(&text) {
        Ok(value) => value,
        Err(error) => {
            return failed_gate(
                key,
                title,
                &relative,
                true,
                None,
                vec![format!(
                    "invalid JSON: {}",
                    json_error_message(&text, &error)
                )],
            )
        }
    };
    let Some(payload) = payload.as_object() else {
        return failed_gate(
            key,
            title,
            &relative,
            true,
            None,
            vec!["gate report must be a JSON object".to_owned()],
        );
    };

    let failures_missing = !payload.contains_key("failures");
    let mut blockers = failure_blockers(payload.get("failures"));
    let raw_passed = payload.get("passed");
    if !matches!(raw_passed, Some(Value::Bool(_))) {
        blockers.push(format!(
            "invalid passed field: expected boolean true/false, got {}",
            raw_passed.map_or("NoneType", json_type_name)
        ));
    }
    let generated_at = payload
        .get("generated_at")
        .and_then(Value::as_str)
        .map(str::to_owned);
    let source_revision = payload
        .get("source_revision")
        .and_then(Value::as_str)
        .map(str::to_owned);
    if raw_passed == Some(&Value::Bool(true)) {
        if failures_missing {
            blockers.push(
                "invalid failures field: expected explicit empty list for passed gate".to_owned(),
            );
        }
        match generated_at.as_deref() {
            None => blockers.push(
                "invalid generated_at field: expected timestamp string for passed gate".to_owned(),
            ),
            Some(value) => {
                if let Some(blocker) = timestamp_blocker(value) {
                    blockers.push(blocker);
                }
            }
        }
        if payload.get("scope").and_then(Value::as_str) != Some(scope) {
            blockers.push(format!("invalid scope field: expected {scope}"));
        }
        if !source_revision
            .as_deref()
            .is_some_and(valid_source_revision)
        {
            blockers.push(
                "invalid source_revision field: expected 40 or 64 lowercase hex characters"
                    .to_owned(),
            );
        } else if !valid_source_revision(runtime_revision) {
            blockers.push("runtime APP_REVISION is not a release revision".to_owned());
        } else if source_revision.as_deref() != Some(runtime_revision) {
            blockers.push("source_revision does not match runtime APP_REVISION".to_owned());
        }
        if let Some(blocker) = evidence_blocker(key, payload) {
            blockers.push(blocker);
        }
    }
    let passed = raw_passed == Some(&Value::Bool(true)) && blockers.is_empty();
    if !passed && blockers.is_empty() {
        blockers.push("gate report is failed but contains no failure details".to_owned());
    }
    json!({
        "key": key,
        "title": title,
        "path": relative.to_string_lossy(),
        "exists": true,
        "passed": passed,
        "generated_at": generated_at,
        "source_revision": source_revision,
        "blockers": blockers
    })
}

fn failed_gate(
    key: &str,
    title: &str,
    relative: &Path,
    exists: bool,
    generated_at: Option<String>,
    blockers: Vec<String>,
) -> Value {
    json!({
        "key": key,
        "title": title,
        "path": relative.to_string_lossy(),
        "exists": exists,
        "passed": false,
        "generated_at": generated_at,
        "blockers": blockers
    })
}

fn failure_blockers(value: Option<&Value>) -> Vec<String> {
    match value {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items.iter().map(blocker_text).collect(),
        Some(other) => vec![format!(
            "invalid failures field: expected list, got {}",
            json_type_name(other)
        )],
    }
}

fn blocker_text(value: &Value) -> String {
    let Some(item) = value.as_object() else {
        return value
            .as_str()
            .map(str::to_owned)
            .unwrap_or_else(|| value.to_string());
    };
    let name = item
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or("unnamed failure");
    match item.get("detail") {
        Some(Value::String(detail)) if !detail.is_empty() => format!("{name}: {detail}"),
        Some(Value::Object(detail)) => structured_blocker(name, detail),
        _ => name.to_owned(),
    }
}

fn structured_blocker(name: &str, detail: &Map<String, Value>) -> String {
    if let Some(paths) = detail
        .get("missing_required_paths")
        .and_then(Value::as_array)
        .filter(|paths| !paths.is_empty())
    {
        let paths = paths
            .iter()
            .take(5)
            .map(value_text)
            .collect::<Vec<_>>()
            .join(", ");
        return format!("{name}: missing {paths}");
    }
    if let Some(error) = detail.get("error").and_then(Value::as_str) {
        return format!("{name}: {error}");
    }
    let mut status_parts = Vec::new();
    for label in ["standalone", "embedded"] {
        if let Some(status) = detail
            .get(label)
            .and_then(Value::as_object)
            .and_then(|value| value.get("status"))
            .and_then(Value::as_str)
        {
            status_parts.push(format!("{label}={status}"));
        }
    }
    let mut failed_checks = HashSet::new();
    for nested in detail.values().filter_map(Value::as_object) {
        if let Some(checks) = nested.get("checks").and_then(Value::as_object) {
            for (name, passed) in checks {
                if passed == &Value::Bool(false) {
                    failed_checks.insert(name.clone());
                }
            }
        }
    }
    if !status_parts.is_empty() || !failed_checks.is_empty() {
        let mut parts = status_parts;
        if !failed_checks.is_empty() {
            let mut checks: Vec<String> = failed_checks.into_iter().collect();
            checks.sort();
            checks.truncate(8);
            parts.push(format!("failed checks: {}", checks.join(", ")));
        }
        return format!("{name}: {}", parts.join("; "));
    }
    let mut gate_parts = Vec::new();
    if let Some(passed) = detail.get("passed").and_then(Value::as_bool) {
        gate_parts.push(format!("passed={}", python_bool(passed)));
    }
    if let Some(empty) = detail.get("failures_empty").and_then(Value::as_bool) {
        gate_parts.push(format!("failures_empty={}", python_bool(empty)));
    }
    if let Some(scope) = detail.get("scope").and_then(Value::as_str) {
        gate_parts.push(format!("scope={scope}"));
    }
    if let Some(source) = detail.get("source").and_then(Value::as_str) {
        gate_parts.push(format!("source={source}"));
    }
    if gate_parts.is_empty() {
        name.to_owned()
    } else {
        format!("{name}: {}", gate_parts.join("; "))
    }
}

fn evidence_blocker(key: &str, payload: &Map<String, Value>) -> Option<String> {
    let required = required_items(key);
    let checks: Vec<&Value> = if key == "internal_release" {
        let Some(groups) = payload.get("groups").and_then(Value::as_object) else {
            return Some(
                "invalid groups field: expected non-empty check groups for passed gate".to_owned(),
            );
        };
        if groups.is_empty() {
            return Some(
                "invalid groups field: expected non-empty check groups for passed gate".to_owned(),
            );
        }
        let mut missing: Vec<&str> = required
            .iter()
            .copied()
            .filter(|name| !groups.contains_key(*name))
            .collect();
        missing.sort_unstable();
        if !missing.is_empty() {
            return Some(format!(
                "invalid groups field: missing required groups {}",
                missing.join(", ")
            ));
        }
        if groups.values().any(|value| !value.is_array()) {
            return Some("invalid groups field: every group must be a check list".to_owned());
        }
        let mut empty: Vec<&str> = required
            .iter()
            .copied()
            .filter(|name| groups[*name].as_array().is_some_and(Vec::is_empty))
            .collect();
        empty.sort_unstable();
        if !empty.is_empty() {
            return Some(format!(
                "invalid groups field: empty required groups {}",
                empty.join(", ")
            ));
        }
        let checks: Vec<&Value> = groups
            .values()
            .filter_map(Value::as_array)
            .flatten()
            .collect();
        if checks.is_empty() {
            return Some(
                "invalid groups field: expected non-empty check groups for passed gate".to_owned(),
            );
        }
        checks
    } else {
        let Some(checks) = payload.get("checks").and_then(Value::as_array) else {
            return Some(
                "invalid checks field: expected non-empty list for passed gate".to_owned(),
            );
        };
        if checks.is_empty() {
            return Some(
                "invalid checks field: expected non-empty list for passed gate".to_owned(),
            );
        }
        let names: HashSet<&str> = checks
            .iter()
            .filter_map(Value::as_object)
            .filter_map(|item| item.get("name"))
            .filter_map(Value::as_str)
            .collect();
        let mut missing: Vec<&str> = required
            .iter()
            .copied()
            .filter(|name| !names.contains(name))
            .collect();
        missing.sort_unstable();
        if !missing.is_empty() {
            return Some(format!(
                "invalid checks field: missing required checks {}",
                missing.join(", ")
            ));
        }
        checks.iter().collect()
    };
    if checks.iter().any(|item| {
        item.as_object().and_then(|item| item.get("passed")) != Some(&Value::Bool(true))
    }) {
        Some("invalid checks field: every check must be passed".to_owned())
    } else {
        None
    }
}

fn required_items(key: &str) -> &'static [&'static str] {
    match key {
        "internal_release" => INTERNAL_REQUIRED,
        "final_maturity" => FINAL_REQUIRED,
        "confirmatory_review_completion" => COMPLETION_REQUIRED,
        _ => &[],
    }
}

fn timestamp_blocker(value: &str) -> Option<String> {
    match DateTime::parse_from_rfc3339(value) {
        Err(_) => Some(
            "invalid generated_at field: expected ISO timestamp string for passed gate".to_owned(),
        ),
        Ok(generated_at)
            if generated_at.with_timezone(&Utc) > Utc::now() + Duration::minutes(5) =>
        {
            Some("invalid generated_at field: timestamp is in the future".to_owned())
        }
        Ok(generated_at)
            if generated_at.with_timezone(&Utc)
                < Utc::now() - Duration::hours(MAX_GATE_AGE_HOURS) =>
        {
            Some(format!(
                "invalid generated_at field: timestamp is older than {MAX_GATE_AGE_HOURS} hours"
            ))
        }
        Ok(_) => None,
    }
}

fn valid_source_revision(value: &str) -> bool {
    matches!(value.len(), 40 | 64)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn json_type_name(value: &Value) -> &'static str {
    match value {
        Value::Null => "NoneType",
        Value::Bool(_) => "bool",
        Value::Number(_) => "int",
        Value::String(_) => "str",
        Value::Array(_) => "list",
        Value::Object(_) => "dict",
    }
}

fn value_text(value: &Value) -> String {
    value
        .as_str()
        .map(str::to_owned)
        .unwrap_or_else(|| value.to_string())
}

fn python_bool(value: bool) -> &'static str {
    if value {
        "True"
    } else {
        "False"
    }
}

fn json_error_message(text: &str, error: &serde_json::Error) -> String {
    let trimmed = text.trim_start();
    if trimmed.starts_with('{')
        && trimmed
            .chars()
            .nth(1)
            .is_some_and(|next| next != '"' && next != '}')
    {
        "Expecting property name enclosed in double quotes".to_owned()
    } else {
        error.to_string()
    }
}

#[cfg(test)]
mod tests {
    use std::{fs, path::PathBuf};

    use chrono::{Duration, SecondsFormat, Utc};
    use serde_json::{json, Map, Value};
    use uuid::Uuid;

    use super::{
        gate_status, gate_status_for_revision, maturity_payload, COMPLETION_REQUIRED,
        FINAL_REQUIRED, INTERNAL_REQUIRED,
    };

    fn root() -> PathBuf {
        let root = PathBuf::from("/tmp").join(format!("eln-maturity-{}", Uuid::new_v4()));
        fs::create_dir_all(root.join("docs/experiments")).unwrap();
        root
    }

    fn passed_checks(scope: &str, required: &[&str]) -> Value {
        json!({
            "generated_at": Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
            "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "scope": scope,
            "passed": true,
            "checks": required.iter().map(|name| json!({"name": name, "passed": true})).collect::<Vec<_>>(),
            "failures": []
        })
    }

    #[test]
    fn test_passed_gate_rejects_stale_timestamp() {
        let root = root();
        let mut payload = passed_checks(
            "final maturity gate for confirmatory human review",
            FINAL_REQUIRED,
        );
        payload["generated_at"] = Value::String(
            (Utc::now() - Duration::hours(169)).to_rfc3339_opts(SecondsFormat::Secs, true),
        );
        fs::write(
            root.join("docs/experiments/final.json"),
            payload.to_string(),
        )
        .unwrap();

        let status = gate_status(
            &root,
            "final_maturity",
            "最终成熟门禁",
            "final.json",
            "final maturity gate for confirmatory human review",
        );

        assert_eq!(status["passed"], false);
        assert_eq!(
            status["blockers"],
            json!(["invalid generated_at field: timestamp is older than 168 hours"])
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn test_passed_gate_requires_source_revision() {
        let root = root();
        let mut payload = passed_checks(
            "final maturity gate for confirmatory human review",
            FINAL_REQUIRED,
        );
        payload.as_object_mut().unwrap().remove("source_revision");
        fs::write(
            root.join("docs/experiments/final.json"),
            payload.to_string(),
        )
        .unwrap();

        let status = gate_status(
            &root,
            "final_maturity",
            "最终成熟门禁",
            "final.json",
            "final maturity gate for confirmatory human review",
        );

        assert_eq!(status["passed"], false);
        assert_eq!(
            status["blockers"],
            json!(["invalid source_revision field: expected 40 or 64 lowercase hex characters"])
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn test_passed_gate_source_revision_must_match_runtime() {
        let root = root();
        let payload = passed_checks(
            "final maturity gate for confirmatory human review",
            FINAL_REQUIRED,
        );
        fs::write(
            root.join("docs/experiments/final.json"),
            payload.to_string(),
        )
        .unwrap();

        let status = gate_status_for_revision(
            &root,
            "final_maturity",
            "最终成熟门禁",
            "final.json",
            "final maturity gate for confirmatory human review",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        );

        assert_eq!(status["passed"], false);
        assert_eq!(
            status["blockers"],
            json!(["source_revision does not match runtime APP_REVISION"])
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn test_failed_gate_exposes_structured_blocker() {
        let root = root();
        fs::write(
            root.join("docs/experiments/final.json"),
            json!({
                "passed": false,
                "failures": [{
                    "name": "final maturity evidence manifest verified",
                    "detail": {"missing_required_paths": ["docs/a.json", "docs/b.json"]}
                }]
            })
            .to_string(),
        )
        .unwrap();

        let status = gate_status(
            &root,
            "final_maturity",
            "最终成熟门禁",
            "final.json",
            "scope",
        );

        assert_eq!(
            status["blockers"],
            json!(["final maturity evidence manifest verified: missing docs/a.json, docs/b.json"])
        );
        assert_eq!(status["exists"], true);
        assert_eq!(status["passed"], false);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn test_passed_gate_validates_scope_timestamp_and_required_checks() {
        let root = root();
        let payload = passed_checks(
            "final maturity gate for confirmatory human review",
            FINAL_REQUIRED,
        );
        fs::write(
            root.join("docs/experiments/final.json"),
            payload.to_string(),
        )
        .unwrap();
        let status = gate_status(
            &root,
            "final_maturity",
            "最终成熟门禁",
            "final.json",
            "final maturity gate for confirmatory human review",
        );
        assert_eq!(status["passed"], true);
        assert_eq!(status["blockers"], json!([]));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn test_maturity_payload_separates_review_start_and_reporting() {
        let root = root();
        let groups = INTERNAL_REQUIRED
            .iter()
            .map(|name| ((*name).to_owned(), json!([{"name": name, "passed": true}])))
            .collect::<Map<String, Value>>();
        fs::write(
            root.join("docs/experiments/main-maturity-gate-latest.json"),
            json!({
                "generated_at": Utc::now().to_rfc3339_opts(SecondsFormat::Secs, true),
                "source_revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "scope": "full-system release-candidate maturity gate",
                "passed": true,
                "groups": groups,
                "failures": []
            })
            .to_string(),
        )
        .unwrap();
        fs::write(
            root.join("docs/experiments/final-maturity-gate-latest.json"),
            passed_checks(
                "final maturity gate for confirmatory human review",
                FINAL_REQUIRED,
            )
            .to_string(),
        )
        .unwrap();
        let mut completion = passed_checks(
            "confirmatory human review completion gate",
            COMPLETION_REQUIRED,
        );
        completion["passed"] = Value::Bool(false);
        completion["failures"] = json!([{"name": "human review export is complete"}]);
        fs::write(
            root.join("docs/experiments/confirmatory-review-completion-latest.json"),
            completion.to_string(),
        )
        .unwrap();

        let status = maturity_payload(&root, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
        assert_eq!(status["passed"], false);
        assert_eq!(status["human_review_allowed"], true);
        assert_eq!(status["human_review_report_allowed"], false);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn test_corrupt_gate_has_compatible_error() {
        let root = root();
        fs::write(root.join("docs/experiments/final.json"), "{not-json").unwrap();
        let status = gate_status(
            &root,
            "final_maturity",
            "最终成熟门禁",
            "final.json",
            "scope",
        );
        assert_eq!(
            status["blockers"],
            json!(["invalid JSON: Expecting property name enclosed in double quotes"])
        );
        fs::remove_dir_all(root).unwrap();
    }
}
