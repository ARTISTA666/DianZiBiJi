use std::{
    collections::{HashMap, VecDeque},
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};

use reqwest::redirect::Policy;
use serde_json::{json, Value};
use sqlx::PgPool;
use thiserror::Error;
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

use crate::{
    config::Settings,
    embedding::{EmbeddingError, EmbeddingService},
};

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub settings: Arc<Settings>,
    pub client: reqwest::Client,
    pub embeddings: EmbeddingService,
    pub(crate) generation_limiter: Arc<Semaphore>,
    // Process-local by design; horizontally scaled deployments need shared
    // source-aware protection if one budget must span every backend replica.
    login_attempt_limiter: Arc<Semaphore>,
    login_rate_limiter: Arc<Mutex<LoginRateLimiter>>,
    worker_id: Arc<str>,
    started_at: Instant,
    metrics: Arc<Mutex<Metrics>>,
}

#[derive(Default)]
struct Metrics {
    in_flight: u64,
    total_requests: u64,
    status_counts: HashMap<String, u64>,
    total_duration_ms: u64,
    max_duration_ms: u64,
    latency_samples_ms: VecDeque<u64>,
}

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
enum LoginRateLimitKey {
    Username(String),
    Overflow,
}

#[derive(Clone, Copy, Debug)]
struct LoginFailureWindow {
    failures: usize,
    started_at: Instant,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct LoginFailureDecision {
    pub(crate) limited: bool,
    pub(crate) delay: Duration,
}

#[derive(Debug)]
struct LoginRateLimiter {
    entries: HashMap<LoginRateLimitKey, LoginFailureWindow>,
    max_attempts: usize,
    window: Duration,
    max_entries: usize,
    failure_delay_base: Duration,
    failure_delay_max: Duration,
}

impl LoginRateLimiter {
    fn new(
        max_attempts: usize,
        window: Duration,
        max_entries: usize,
        failure_delay_base: Duration,
        failure_delay_max: Duration,
    ) -> Self {
        Self {
            entries: HashMap::new(),
            max_attempts,
            window,
            max_entries,
            failure_delay_base,
            failure_delay_max,
        }
    }

    fn record_failure_at(&mut self, username: &str, now: Instant) -> LoginFailureDecision {
        let key = self.storage_key(username, now);
        let window = self.window;
        let entry = self.entries.entry(key).or_insert(LoginFailureWindow {
            failures: 0,
            started_at: now,
        });
        if now.saturating_duration_since(entry.started_at) >= window {
            *entry = LoginFailureWindow {
                failures: 0,
                started_at: now,
            };
        }
        entry.failures = entry.failures.saturating_add(1);
        let failures = entry.failures;
        LoginFailureDecision {
            limited: failures >= self.max_attempts,
            delay: self.failure_delay(failures),
        }
    }

    fn clear_at(&mut self, username: &str, now: Instant) {
        let key = self.storage_key(username, now);
        self.entries.remove(&key);
    }

    #[cfg(test)]
    fn clear(&mut self, username: &str) {
        self.clear_at(username, Instant::now());
    }

    #[cfg(test)]
    fn entry_count(&self) -> usize {
        self.entries.len()
    }

    fn storage_key(&mut self, username: &str, now: Instant) -> LoginRateLimitKey {
        let candidate = if username.is_ascii() && username.len() <= 64 {
            LoginRateLimitKey::Username(username.to_owned())
        } else {
            return LoginRateLimitKey::Overflow;
        };
        if self.entries.contains_key(&candidate) {
            return candidate;
        }

        let normal_capacity = self.max_entries.saturating_sub(1);
        if self.normal_entry_count() >= normal_capacity {
            let window = self.window;
            self.entries
                .retain(|_, entry| now.saturating_duration_since(entry.started_at) < window);
        }
        if self.normal_entry_count() < normal_capacity {
            candidate
        } else {
            LoginRateLimitKey::Overflow
        }
    }

    fn normal_entry_count(&self) -> usize {
        self.entries
            .keys()
            .filter(|key| matches!(key, LoginRateLimitKey::Username(_)))
            .count()
    }

    fn failure_delay(&self, failures: usize) -> Duration {
        let shift = failures.saturating_sub(1).min(31) as u32;
        self.failure_delay_base
            .saturating_mul(1_u32 << shift)
            .min(self.failure_delay_max)
    }
}

#[derive(Debug, Error)]
pub enum StateError {
    #[error("Failed to construct HTTP client: {0}")]
    HttpClient(#[from] reqwest::Error),
    #[error("Failed to configure embedding model: {0}")]
    Embedding(#[from] EmbeddingError),
}

impl AppState {
    pub fn new(pool: PgPool, settings: Settings) -> Result<Self, StateError> {
        let embeddings = EmbeddingService::new(&settings)?;
        let generation_limiter = Arc::new(Semaphore::new(settings.deepseek_max_concurrency));
        let login_attempt_limiter =
            Arc::new(Semaphore::new(settings.login_max_concurrent_attempts));
        let login_rate_limiter = Arc::new(Mutex::new(LoginRateLimiter::new(
            settings.login_rate_limit_max_attempts,
            Duration::from_secs(settings.login_rate_limit_window_seconds),
            settings.login_rate_limit_max_entries,
            Duration::from_millis(settings.login_failure_delay_base_ms),
            Duration::from_millis(settings.login_failure_delay_max_ms),
        )));
        Ok(Self {
            pool,
            settings: Arc::new(settings),
            client: reqwest::Client::builder()
                .redirect(Policy::none())
                .build()?,
            embeddings,
            generation_limiter,
            login_attempt_limiter,
            login_rate_limiter,
            worker_id: Arc::from(uuid::Uuid::new_v4().to_string()),
            started_at: Instant::now(),
            metrics: Arc::new(Mutex::new(Metrics::default())),
        })
    }

    pub(crate) fn worker_id(&self) -> &str {
        &self.worker_id
    }

    pub(crate) fn try_acquire_login_attempt(&self) -> Option<OwnedSemaphorePermit> {
        self.login_attempt_limiter.clone().try_acquire_owned().ok()
    }

    pub(crate) fn record_login_failure(&self, username: &str) -> LoginFailureDecision {
        self.login_rate_limiter
            .lock()
            .unwrap()
            .record_failure_at(username, Instant::now())
    }

    pub(crate) fn clear_login_failures(&self, username: &str) {
        self.login_rate_limiter
            .lock()
            .unwrap()
            .clear_at(username, Instant::now());
    }

    pub fn request_started(&self) {
        self.metrics.lock().unwrap().in_flight += 1;
    }

    pub fn request_finished(&self, status: u16, duration_ms: u64) {
        let mut metrics = self.metrics.lock().unwrap();
        metrics.in_flight = metrics.in_flight.saturating_sub(1);
        metrics.total_requests += 1;
        metrics.total_duration_ms += duration_ms;
        metrics.max_duration_ms = metrics.max_duration_ms.max(duration_ms);
        *metrics
            .status_counts
            .entry(format!("{}xx", status / 100))
            .or_default() += 1;
        if metrics.latency_samples_ms.len() == 500 {
            metrics.latency_samples_ms.pop_front();
        }
        metrics.latency_samples_ms.push_back(duration_ms);
    }

    pub fn metrics_snapshot(&self) -> Value {
        let metrics = self.metrics.lock().unwrap();
        let mut samples: Vec<_> = metrics.latency_samples_ms.iter().copied().collect();
        samples.sort_unstable();
        let p95_index = samples
            .len()
            .saturating_mul(95)
            .div_ceil(100)
            .saturating_sub(1);
        let average = if metrics.total_requests == 0 {
            0.0
        } else {
            metrics.total_duration_ms as f64 / metrics.total_requests as f64
        };
        json!({
            "status": "ok",
            "revision": self.settings.app_revision,
            "uptime_seconds": (self.started_at.elapsed().as_secs_f64() * 1000.0).round() / 1000.0,
            "in_flight": metrics.in_flight,
            "total_requests": metrics.total_requests,
            "status_counts": metrics.status_counts,
            "avg_duration_ms": (average * 100.0).round() / 100.0,
            "p95_duration_ms": samples.get(p95_index).copied().unwrap_or(0),
            "max_duration_ms": metrics.max_duration_ms,
            "latency_sample_count": samples.len(),
        })
    }
}

#[cfg(test)]
mod tests {
    use std::{
        collections::HashMap,
        time::{Duration, Instant},
    };

    use sqlx::postgres::PgPoolOptions;

    use super::{AppState, LoginRateLimiter};
    use crate::config::Settings;

    #[tokio::test]
    async fn test_app_state_can_be_built_with_lazy_database_pool() {
        let settings = Settings::from_map(&HashMap::new()).unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();

        let state = AppState::new(pool, settings).unwrap();

        assert_eq!(state.settings.app_revision, "unversioned");
    }

    #[test]
    fn test_login_rate_limiter_reaches_threshold_and_success_clears_failures() {
        let start = Instant::now();
        let mut limiter = LoginRateLimiter::new(
            3,
            Duration::from_secs(60),
            16,
            Duration::from_millis(100),
            Duration::from_millis(500),
        );

        let first = limiter.record_failure_at("alice", start);
        let second = limiter.record_failure_at("alice", start);
        let third = limiter.record_failure_at("alice", start);
        let fourth = limiter.record_failure_at("alice", start);

        assert!(!first.limited);
        assert_eq!(first.delay, Duration::from_millis(100));
        assert!(!second.limited);
        assert_eq!(second.delay, Duration::from_millis(200));
        assert!(third.limited);
        assert_eq!(third.delay, Duration::from_millis(400));
        assert!(fourth.limited);
        assert_eq!(fourth.delay, Duration::from_millis(500));

        limiter.clear("alice");

        let after_success = limiter.record_failure_at("alice", start);
        assert!(!after_success.limited);
        assert_eq!(after_success.delay, Duration::from_millis(100));
    }

    #[test]
    fn test_login_rate_limiter_expires_window_automatically() {
        let start = Instant::now();
        let mut limiter = LoginRateLimiter::new(
            2,
            Duration::from_secs(10),
            16,
            Duration::from_millis(10),
            Duration::from_millis(100),
        );

        assert!(!limiter.record_failure_at("alice", start).limited);
        assert!(limiter.record_failure_at("alice", start).limited);

        let expired = limiter.record_failure_at("alice", start + Duration::from_secs(10));
        assert!(!expired.limited);
        assert_eq!(expired.delay, Duration::from_millis(10));
        assert_eq!(limiter.entry_count(), 1);
    }

    #[test]
    fn test_login_rate_limiter_bounds_random_username_entries() {
        let start = Instant::now();
        let mut limiter = LoginRateLimiter::new(
            2,
            Duration::from_secs(60),
            3,
            Duration::from_millis(10),
            Duration::from_millis(100),
        );

        assert!(!limiter.record_failure_at("random-a", start).limited);
        assert!(!limiter.record_failure_at("random-b", start).limited);
        assert!(!limiter.record_failure_at("random-c", start).limited);
        assert!(limiter.record_failure_at("random-d", start).limited);

        assert_eq!(limiter.entry_count(), 3);
    }

    #[tokio::test]
    async fn test_app_state_bounds_concurrent_login_work() {
        let settings = Settings::from_map(&HashMap::from([(
            "LOGIN_MAX_CONCURRENT_ATTEMPTS".to_owned(),
            "1".to_owned(),
        )]))
        .unwrap();
        let pool = PgPoolOptions::new()
            .connect_lazy("postgresql://unused:unused@127.0.0.1/unused")
            .unwrap();
        let state = AppState::new(pool, settings).unwrap();

        let first = state.try_acquire_login_attempt().unwrap();
        assert!(state.try_acquire_login_attempt().is_none());
        drop(first);
        assert!(state.try_acquire_login_attempt().is_some());
    }
}
