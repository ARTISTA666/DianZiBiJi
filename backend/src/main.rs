use std::{env, ffi::OsString, net::SocketAddr, time::Duration};

use eln_backend::{
    api::schedule_queued_experiments,
    build_app,
    config::Settings,
    db::{
        connect_database, initialize_database, recover_interrupted_experiment_runs,
        STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS,
    },
    AppState,
};
use sqlx::PgPool;
use tracing::{error, info, warn};

const STALE_EXPERIMENT_REAPER_INTERVAL: Duration =
    Duration::from_secs(STALE_EXPERIMENT_REAPER_INTERVAL_SECONDS);

#[derive(Debug, Eq, PartialEq)]
enum StartupMode {
    Serve,
    CheckConfig,
}

fn startup_mode(arguments: impl IntoIterator<Item = OsString>) -> Result<StartupMode, String> {
    let mut arguments = arguments.into_iter();
    let _program = arguments.next();
    match arguments.next() {
        None => Ok(StartupMode::Serve),
        Some(argument) if argument == "--check-config" && arguments.next().is_none() => {
            Ok(StartupMode::CheckConfig)
        }
        Some(argument) => Err(format!(
            "unknown startup argument: {}",
            argument.to_string_lossy()
        )),
    }
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install SIGTERM handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}

fn bind_address() -> Result<SocketAddr, std::net::AddrParseError> {
    env::var("BACKEND_BIND")
        .unwrap_or_else(|_| "0.0.0.0:8000".to_owned())
        .parse()
}

fn monitor_stale_experiment_runs(pool: PgPool) {
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(STALE_EXPERIMENT_REAPER_INTERVAL);
        interval.tick().await;
        loop {
            interval.tick().await;
            match recover_interrupted_experiment_runs(&pool).await {
                Ok(0) => {}
                Ok(recovered) => {
                    warn!(recovered, "recovered stale RAG experiment runs");
                }
                Err(recovery_error) => {
                    error!(%recovery_error, "failed to recover stale RAG experiment runs");
                }
            }
        }
    });
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let startup_mode = startup_mode(env::args_os())
        .map_err(|message| std::io::Error::new(std::io::ErrorKind::InvalidInput, message))?;
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "eln_backend=info,tower_http=info".into()),
        )
        .init();

    let settings = Settings::from_env()?;
    info!(
        app_env = %settings.app_env,
        revision = %settings.app_revision,
        seed_demo_data = settings.seed_demo_data,
        "effective runtime configuration"
    );
    if startup_mode == StartupMode::CheckConfig {
        println!("Rust runtime configuration is valid.");
        return Ok(());
    }
    let pool = connect_database(&settings).await?;
    initialize_database(&pool, &settings).await?;
    let recovered = recover_interrupted_experiment_runs(&pool).await?;
    if recovered > 0 {
        warn!(recovered, "recovered interrupted RAG experiment runs");
    }
    monitor_stale_experiment_runs(pool.clone());
    let state = AppState::new(pool, settings)?;
    let scheduled = schedule_queued_experiments(&state).await?;
    if scheduled > 0 {
        info!(scheduled, "scheduled queued RAG experiment runs");
    }
    let address = bind_address()?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    info!(%address, "Rust backend listening");

    axum::serve(listener, build_app(state))
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;

    use super::{bind_address, startup_mode, StartupMode};

    #[test]
    fn default_bind_address_is_valid() {
        if std::env::var_os("BACKEND_BIND").is_none() {
            assert_eq!(bind_address().unwrap().to_string(), "0.0.0.0:8000");
        }
    }

    #[test]
    fn check_config_is_an_explicit_db_free_startup_mode() {
        assert_eq!(
            startup_mode([
                OsString::from("eln-backend"),
                OsString::from("--check-config"),
            ])
            .unwrap(),
            StartupMode::CheckConfig
        );
        assert_eq!(
            startup_mode([OsString::from("eln-backend")]).unwrap(),
            StartupMode::Serve
        );
        assert!(
            startup_mode([OsString::from("eln-backend"), OsString::from("--unknown"),]).is_err()
        );
    }
}
