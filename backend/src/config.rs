use std::{collections::HashMap, env};

use thiserror::Error;

#[derive(Clone, Debug)]
pub struct Settings {
    pub app_env: String,
    pub postgres_db: String,
    pub postgres_user: String,
    pub postgres_password: String,
    pub postgres_host: String,
    pub postgres_port: u16,
    pub secret_key: String,
    pub bootstrap_admin_username: String,
    pub bootstrap_admin_password: String,
    pub seed_demo_data: bool,
    pub access_token_expire_minutes: i64,
    pub login_rate_limit_max_attempts: usize,
    pub login_rate_limit_window_seconds: u64,
    pub login_rate_limit_max_entries: usize,
    pub login_failure_delay_base_ms: u64,
    pub login_failure_delay_max_ms: u64,
    pub login_max_concurrent_attempts: usize,
    pub global_rate_limit_read_per_minute: u64,
    pub global_rate_limit_write_per_minute: u64,
    pub cors_origins: String,
    pub app_revision: String,
    pub deepseek_api_base_url: String,
    pub deepseek_api_key: String,
    pub deepseek_model: String,
    pub deepseek_max_concurrency: usize,
    pub embedding_model: String,
    pub embedding_backend: String,
    pub embedding_dimension: usize,
    pub rag_chunk_size: usize,
    pub rag_chunk_overlap: usize,
    pub rag_retrieval_top_k: usize,
    pub rag_collection_retrieval_top_k: usize,
    pub rag_vector_candidate_k: usize,
    pub rag_graph_top_k: usize,
    pub rag_graph_min_score: f64,
    pub document_text_max_chars: usize,
    pub upload_max_bytes: usize,
    pub storage_root: String,
    pub ocr_languages: String,
    pub ocr_preprocessing: String,
    pub ocr_page_segmentation_mode: u8,
    database_url_override: Option<String>,
}

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("Invalid {name}: {value}")]
    InvalidValue { name: &'static str, value: String },
    #[error("Unsafe {env} configuration: {problems}")]
    UnsafeRuntime { env: String, problems: String },
}

impl Settings {
    pub fn from_env() -> Result<Self, ConfigError> {
        Self::from_map(&env::vars().collect())
    }

    pub fn from_map(values: &HashMap<String, String>) -> Result<Self, ConfigError> {
        let get = |name: &str, default: &str| {
            values
                .get(name)
                .cloned()
                .unwrap_or_else(|| default.to_owned())
        };
        let settings = Self {
            app_env: get("APP_ENV", "development"),
            postgres_db: get("POSTGRES_DB", "eln"),
            postgres_user: get("POSTGRES_USER", "eln_user"),
            postgres_password: get("POSTGRES_PASSWORD", "eln_password"),
            postgres_host: get("POSTGRES_HOST", "localhost"),
            postgres_port: parse(values, "POSTGRES_PORT", 5432)?,
            secret_key: get("SECRET_KEY", "change-me-in-production"),
            bootstrap_admin_username: get("BOOTSTRAP_ADMIN_USERNAME", "admin"),
            bootstrap_admin_password: get("BOOTSTRAP_ADMIN_PASSWORD", "admin123"),
            seed_demo_data: parse_bool(values, "SEED_DEMO_DATA", false)?,
            access_token_expire_minutes: parse(values, "ACCESS_TOKEN_EXPIRE_MINUTES", 480)?,
            login_rate_limit_max_attempts: parse(values, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 5)?,
            login_rate_limit_window_seconds: parse(values, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 300)?,
            login_rate_limit_max_entries: parse(values, "LOGIN_RATE_LIMIT_MAX_ENTRIES", 10_000)?,
            login_failure_delay_base_ms: parse(values, "LOGIN_FAILURE_DELAY_BASE_MS", 100)?,
            login_failure_delay_max_ms: parse(values, "LOGIN_FAILURE_DELAY_MAX_MS", 2_000)?,
            login_max_concurrent_attempts: parse(values, "LOGIN_MAX_CONCURRENT_ATTEMPTS", 4)?,
            global_rate_limit_read_per_minute: parse(
                values,
                "GLOBAL_RATE_LIMIT_READ_PER_MINUTE",
                600,
            )?,
            global_rate_limit_write_per_minute: parse(
                values,
                "GLOBAL_RATE_LIMIT_WRITE_PER_MINUTE",
                120,
            )?,
            cors_origins: get(
                "CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            ),
            app_revision: get("APP_REVISION", "unversioned"),
            deepseek_api_base_url: get("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com"),
            deepseek_api_key: get("DEEPSEEK_API_KEY", ""),
            deepseek_model: get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            deepseek_max_concurrency: parse(values, "DEEPSEEK_MAX_CONCURRENCY", 4)?,
            embedding_model: get("EMBEDDING_MODEL", "rust-hash-512-v1"),
            embedding_backend: get("EMBEDDING_BACKEND", "hash"),
            embedding_dimension: parse(values, "EMBEDDING_DIMENSION", 512)?,
            rag_chunk_size: parse(values, "RAG_CHUNK_SIZE", 700)?,
            rag_chunk_overlap: parse(values, "RAG_CHUNK_OVERLAP", 120)?,
            rag_retrieval_top_k: parse(values, "RAG_RETRIEVAL_TOP_K", 6)?,
            rag_collection_retrieval_top_k: parse(values, "RAG_COLLECTION_RETRIEVAL_TOP_K", 12)?,
            rag_vector_candidate_k: parse(values, "RAG_VECTOR_CANDIDATE_K", 30)?,
            rag_graph_top_k: parse(values, "RAG_GRAPH_TOP_K", 10)?,
            rag_graph_min_score: parse(values, "RAG_GRAPH_MIN_SCORE", 1.0)?,
            document_text_max_chars: parse(values, "DOCUMENT_TEXT_MAX_CHARS", 2_000_000)?,
            upload_max_bytes: parse(values, "UPLOAD_MAX_BYTES", 50 * 1024 * 1024)?,
            storage_root: get("STORAGE_ROOT", "/storage"),
            ocr_languages: get("OCR_LANGUAGES", "chi_sim+eng"),
            ocr_preprocessing: get("OCR_PREPROCESSING", "grayscale_otsu"),
            ocr_page_segmentation_mode: parse(values, "OCR_PAGE_SEGMENTATION_MODE", 3)?,
            database_url_override: values.get("DATABASE_URL").cloned(),
        };
        settings.validate_runtime()?;
        Ok(settings)
    }

    pub fn normalized_deepseek_model(&self) -> &str {
        self.deepseek_model
            .split_once('#')
            .map_or(self.deepseek_model.as_str(), |(model, _)| model)
            .trim()
    }

    pub fn cors_origin_list(&self) -> Vec<String> {
        self.cors_origins
            .split(',')
            .map(str::trim)
            .filter(|origin| !origin.is_empty())
            .map(str::to_owned)
            .collect()
    }

    pub fn database_url(&self) -> String {
        if let Some(url) = &self.database_url_override {
            return url.replace("postgresql+psycopg://", "postgresql://");
        }
        format!(
            "postgresql://{}:{}@{}:{}/{}",
            percent_encode(&self.postgres_user),
            percent_encode(&self.postgres_password),
            self.postgres_host,
            self.postgres_port,
            percent_encode(&self.postgres_db),
        )
    }

    fn validate_runtime(&self) -> Result<(), ConfigError> {
        self.validate_embedding()?;
        if !(1..=128).contains(&self.deepseek_max_concurrency) {
            return Err(ConfigError::InvalidValue {
                name: "DEEPSEEK_MAX_CONCURRENCY",
                value: self.deepseek_max_concurrency.to_string(),
            });
        }
        validate_range(
            "LOGIN_RATE_LIMIT_MAX_ATTEMPTS",
            self.login_rate_limit_max_attempts,
            1,
            100,
        )?;
        validate_range(
            "LOGIN_RATE_LIMIT_WINDOW_SECONDS",
            self.login_rate_limit_window_seconds,
            1,
            86_400,
        )?;
        validate_range(
            "LOGIN_RATE_LIMIT_MAX_ENTRIES",
            self.login_rate_limit_max_entries,
            2,
            1_000_000,
        )?;
        validate_range(
            "LOGIN_FAILURE_DELAY_BASE_MS",
            self.login_failure_delay_base_ms,
            1,
            30_000,
        )?;
        validate_range(
            "LOGIN_FAILURE_DELAY_MAX_MS",
            self.login_failure_delay_max_ms,
            1,
            30_000,
        )?;
        if self.login_failure_delay_base_ms > self.login_failure_delay_max_ms {
            return Err(ConfigError::InvalidValue {
                name: "LOGIN_FAILURE_DELAY_BASE_MS",
                value: self.login_failure_delay_base_ms.to_string(),
            });
        }
        validate_range(
            "LOGIN_MAX_CONCURRENT_ATTEMPTS",
            self.login_max_concurrent_attempts,
            1,
            256,
        )?;
        validate_range(
            "GLOBAL_RATE_LIMIT_READ_PER_MINUTE",
            self.global_rate_limit_read_per_minute,
            1,
            1_000_000,
        )?;
        validate_range(
            "GLOBAL_RATE_LIMIT_WRITE_PER_MINUTE",
            self.global_rate_limit_write_per_minute,
            1,
            1_000_000,
        )?;
        // Secret hygiene is enforced for every non-development environment so
        // a deployment cannot run with default credentials just because
        // APP_ENV was left unset or misspelled short of "production".
        if self.app_env == "development" {
            return Ok(());
        }
        let mut problems = Vec::new();
        if self.secret_key == "change-me-in-production" || self.secret_key.len() < 32 {
            problems.push("SECRET_KEY must be changed and contain at least 32 characters");
        }
        if self.bootstrap_admin_password == "admin123" || self.bootstrap_admin_password.len() < 12 {
            problems.push(
                "BOOTSTRAP_ADMIN_PASSWORD must be changed and contain at least 12 characters",
            );
        }
        if self.postgres_password == "eln_password" || self.postgres_password.len() < 12 {
            problems.push("POSTGRES_PASSWORD must be changed and contain at least 12 characters");
        }
        if self.seed_demo_data {
            problems.push("SEED_DEMO_DATA must be false");
        }
        if self.app_env == "production" {
            // Deployment metadata is only mandatory for real releases.
            if self.deepseek_api_key.trim().is_empty() {
                problems.push("DEEPSEEK_API_KEY must be configured");
            }
            if self.app_revision.trim().is_empty() || self.app_revision == "unversioned" {
                problems.push("APP_REVISION must identify the deployed release");
            }
        }
        if problems.is_empty() {
            Ok(())
        } else {
            Err(ConfigError::UnsafeRuntime {
                env: self.app_env.clone(),
                problems: problems.join("; "),
            })
        }
    }

    fn validate_embedding(&self) -> Result<(), ConfigError> {
        if self.embedding_backend != "hash" {
            return Err(ConfigError::InvalidValue {
                name: "EMBEDDING_BACKEND",
                value: self.embedding_backend.clone(),
            });
        }
        if self.embedding_model != "rust-hash-512-v1" {
            return Err(ConfigError::InvalidValue {
                name: "EMBEDDING_MODEL",
                value: self.embedding_model.clone(),
            });
        }
        if self.embedding_dimension != 512 {
            return Err(ConfigError::InvalidValue {
                name: "EMBEDDING_DIMENSION",
                value: self.embedding_dimension.to_string(),
            });
        }
        Ok(())
    }
}

fn parse<T>(
    values: &HashMap<String, String>,
    name: &'static str,
    default: T,
) -> Result<T, ConfigError>
where
    T: std::str::FromStr,
{
    let Some(value) = values.get(name) else {
        return Ok(default);
    };
    value.parse().map_err(|_| ConfigError::InvalidValue {
        name,
        value: value.clone(),
    })
}

fn parse_bool(
    values: &HashMap<String, String>,
    name: &'static str,
    default: bool,
) -> Result<bool, ConfigError> {
    let Some(value) = values.get(name) else {
        return Ok(default);
    };
    match value.to_ascii_lowercase().as_str() {
        "true" | "1" | "yes" | "on" => Ok(true),
        "false" | "0" | "no" | "off" => Ok(false),
        _ => Err(ConfigError::InvalidValue {
            name,
            value: value.clone(),
        }),
    }
}

fn validate_range<T>(
    name: &'static str,
    value: T,
    minimum: T,
    maximum: T,
) -> Result<(), ConfigError>
where
    T: Copy + PartialOrd + ToString,
{
    if value < minimum || value > maximum {
        Err(ConfigError::InvalidValue {
            name,
            value: value.to_string(),
        })
    } else {
        Ok(())
    }
}

fn percent_encode(value: &str) -> String {
    value
        .bytes()
        .map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'.' | b'_' | b'~' => {
                (byte as char).to_string()
            }
            _ => format!("%{byte:02X}"),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::Settings;

    #[test]
    fn test_settings_builds_database_url_and_normalizes_model() {
        let values = HashMap::from([
            ("POSTGRES_USER".to_owned(), "user@lab".to_owned()),
            ("POSTGRES_PASSWORD".to_owned(), "p/a ss".to_owned()),
            ("POSTGRES_HOST".to_owned(), "db".to_owned()),
            ("POSTGRES_PORT".to_owned(), "5544".to_owned()),
            ("POSTGRES_DB".to_owned(), "eln".to_owned()),
            (
                "DEEPSEEK_MODEL".to_owned(),
                "deepseek-chat # local note".to_owned(),
            ),
        ]);

        let settings = Settings::from_map(&values).unwrap();

        assert_eq!(
            settings.database_url(),
            "postgresql://user%40lab:p%2Fa%20ss@db:5544/eln"
        );
        assert_eq!(settings.normalized_deepseek_model(), "deepseek-chat");
        assert_eq!(settings.deepseek_max_concurrency, 4);
        assert_eq!(settings.login_rate_limit_max_attempts, 5);
        assert_eq!(settings.login_rate_limit_window_seconds, 300);
        assert_eq!(settings.login_rate_limit_max_entries, 10_000);
        assert_eq!(settings.login_failure_delay_base_ms, 100);
        assert_eq!(settings.login_failure_delay_max_ms, 2_000);
        assert_eq!(settings.login_max_concurrent_attempts, 4);
        assert_eq!(settings.storage_root, "/storage");

        let overridden = Settings::from_map(&HashMap::from([(
            "STORAGE_ROOT".to_owned(),
            "/tmp/eln-storage-test".to_owned(),
        )]))
        .unwrap();
        assert_eq!(overridden.storage_root, "/tmp/eln-storage-test");
    }

    #[test]
    fn test_settings_rejects_unsafe_production_defaults() {
        let values = HashMap::from([("APP_ENV".to_owned(), "production".to_owned())]);

        let error = Settings::from_map(&values).unwrap_err();

        assert!(error.to_string().contains("SECRET_KEY"));
        assert!(error.to_string().contains("DEEPSEEK_API_KEY"));
        assert!(error.to_string().contains("APP_REVISION"));
    }

    #[test]
    fn hash_backend_rejects_a_misleading_model_name() {
        let values = HashMap::from([(
            "EMBEDDING_MODEL".to_owned(),
            "BAAI/bge-small-zh-v1.5".to_owned(),
        )]);

        let error = Settings::from_map(&values).unwrap_err();

        assert!(error.to_string().contains("EMBEDDING_MODEL"));
    }

    #[test]
    fn deepseek_concurrency_must_be_positive() {
        let values = HashMap::from([("DEEPSEEK_MAX_CONCURRENCY".to_owned(), "0".to_owned())]);

        let error = Settings::from_map(&values).unwrap_err();

        assert!(error.to_string().contains("DEEPSEEK_MAX_CONCURRENCY"));
    }

    #[test]
    fn login_rate_limit_values_must_be_safe() {
        for (name, value) in [
            ("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "0"),
            ("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "0"),
            ("LOGIN_RATE_LIMIT_MAX_ENTRIES", "1"),
            ("LOGIN_FAILURE_DELAY_BASE_MS", "0"),
            ("LOGIN_FAILURE_DELAY_MAX_MS", "0"),
            ("LOGIN_MAX_CONCURRENT_ATTEMPTS", "0"),
        ] {
            let error = Settings::from_map(&HashMap::from([(name.to_owned(), value.to_owned())]))
                .unwrap_err();

            assert!(error.to_string().contains(name));
        }

        let error = Settings::from_map(&HashMap::from([
            ("LOGIN_FAILURE_DELAY_BASE_MS".to_owned(), "500".to_owned()),
            ("LOGIN_FAILURE_DELAY_MAX_MS".to_owned(), "100".to_owned()),
        ]))
        .unwrap_err();
        assert!(error.to_string().contains("LOGIN_FAILURE_DELAY_BASE_MS"));
    }
}
