use chrono::Local;
use std::fs::{create_dir_all, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tauri::{Emitter, Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use tauri_plugin_deep_link::DeepLinkExt;

struct BackendState {
    child: Arc<Mutex<Option<CommandChild>>>,
}

// State to store initial deep link URL (for cold start handling)
struct DeepLinkState {
    initial_url: Arc<Mutex<Option<String>>>,
}

fn update_runtime_current_symlink(data_dir: &Path) {
    let runtime_dir = data_dir.join("runtime");
    if !runtime_dir.is_dir() {
        return;
    }
    let mut versions: Vec<_> = std::fs::read_dir(&runtime_dir)
        .into_iter()
        .flatten()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().is_dir() && e.file_name() != "current")
        .collect();
    versions.sort_by_key(|e| e.file_name());

    if let Some(latest) = versions.last() {
        let symlink_path = runtime_dir.join("current");
        let _ = std::fs::remove_file(&symlink_path);
        #[cfg(unix)]
        {
            let _ = std::os::unix::fs::symlink(latest.path(), &symlink_path);
        }
    }
}

fn format_log_line(level: &str, message: &str) -> String {
    format!(
        "{} [{}] {}",
        Local::now().format("%Y-%m-%d %H:%M:%S%.3f"),
        level,
        message
    )
}

#[tauri::command]
fn get_backend_port(port_state: State<'_, Arc<Mutex<u16>>>) -> u16 {
    *port_state.lock().unwrap()
}

#[tauri::command]
fn get_initial_deep_link(state: State<'_, DeepLinkState>) -> Option<String> {
    // Take the value (returns it and sets to None) so it's only processed once
    state.initial_url.lock().unwrap().take()
}

const DEFAULT_BACKEND_PORT: u16 = 17433;

fn db_needs_seed(db_path: &Path) -> bool {
    // Only seed if DB doesn't exist or is empty
    // Python migrations will handle all schema validation and updates
    if !db_path.exists() {
        return true;
    }

    match std::fs::metadata(db_path) {
        Ok(meta) => meta.len() == 0,
        _ => true,
    }
}

fn ensure_db(app_handle: &tauri::AppHandle, data_dir: &PathBuf) -> io::Result<(PathBuf, bool)> {
    let db_path = data_dir.join("app.db");
    let mut seeded = false;

    if db_needs_seed(&db_path) {
        if let Ok(res_dir) = app_handle.path().resource_dir() {
            let seed = res_dir.join(".data").join("app.db");
            if seed.exists() {
                std::fs::copy(&seed, &db_path)?;
                seeded = true;
            } else {
                OpenOptions::new().create(true).write(true).open(&db_path)?;
            }
        } else {
            OpenOptions::new().create(true).write(true).open(&db_path)?;
        }
    }

    Ok((db_path, seeded))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let port_state = Arc::new(Mutex::new(DEFAULT_BACKEND_PORT));

    // Configure updater with public key from environment variable
    let updater = match std::env::var("TAURI_UPDATER_PUBLIC_KEY") {
        Ok(pubkey) if !pubkey.is_empty() => {
            tauri_plugin_updater::Builder::new().pubkey(pubkey).build()
        }
        _ => {
            // If no public key is set, build without it (updates will be disabled)
            tauri_plugin_updater::Builder::new().build()
        }
    };

    let app = tauri::Builder::default()
        .plugin(updater)
        .plugin(tauri_plugin_log::Builder::default().build())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .manage(port_state.clone())
        .setup(move |app| {
            let app_handle = app.handle();
            let host = "127.0.0.1";

            let data_dir = app_handle.path().app_data_dir().map_err(|e| {
                std::io::Error::new(
                    std::io::ErrorKind::Other,
                    format!("failed to resolve app data dir: {e}"),
                )
            })?;
            create_dir_all(&data_dir)?;

            let (db_path, seeded) = ensure_db(&app_handle, &data_dir)?;

            update_runtime_current_symlink(&data_dir);

            let database_url = format!(
                "sqlite+aiosqlite:///{path}",
                path = db_path.to_string_lossy()
            );

            // Prepare log file for sidecar output
            let log_path = data_dir.join("backend.log");
            let mut log_file = OpenOptions::new()
                .create(true)
                .append(true)
                .open(&log_path)
                .map_err(|e| {
                    std::io::Error::new(
                        std::io::ErrorKind::Other,
                        format!("failed to open log file: {e}"),
                    )
                })?;

            if seeded {
                writeln!(
                    log_file,
                    "{}",
                    format_log_line(
                        "system",
                        &format!(
                            "Seeded database from packaged template at {}",
                            db_path.display()
                        )
                    )
                )
                .ok();
            }
            writeln!(
                log_file,
                "{}",
                format_log_line(
                    "system",
                    &format!(
                        "Starting backend on {host}:{DEFAULT_BACKEND_PORT} (preferred), DB={}",
                        db_path.display()
                    )
                )
            )
            .ok();

            // Build comprehensive PATH for sidecar
            // When launched from Finder/Dock, shell profiles aren't sourced so
            // nvm/fnm/volta/bun bin dirs won't be in PATH. Include them explicitly.
            let system_path = std::env::var("PATH").unwrap_or_default();
            let home = std::env::var("HOME").unwrap_or_default();

            let pnpm_home = std::env::var("PNPM_HOME").ok();

            let mut extra_paths = vec![
                "/opt/homebrew/bin".to_string(),
                "/usr/local/bin".to_string(),
                format!("{}/.local/bin", home),
                format!("{}/.bun/bin", home),
                format!("{}/.volta/bin", home),
                format!("{}/.npm-global/bin", home),
                format!("{}/.npm/bin", home),
                format!("{}/.yarn/bin", home),
                format!("{}/Library/pnpm", home),
                format!("{}/.local/share/pnpm", home),
                format!("{}/.asdf/shims", home),
                format!("{}/.asdf/bin", home),
            ];

            // Native installer (curl ... | bash) locations
            let native_current = format!("{}/.local/share/claude/current", home);
            if Path::new(&native_current).is_dir() {
                extra_paths.push(native_current);
            }
            let native_versions = Path::new(&home).join(".local/share/claude/versions");
            if native_versions.is_dir() {
                if let Ok(entries) = std::fs::read_dir(&native_versions) {
                    let mut versions: Vec<PathBuf> = entries
                        .filter_map(|e| e.ok().map(|e| e.path()))
                        .filter(|p| p.is_dir())
                        .collect();
                    versions.sort();
                    versions.reverse();
                    for version in &versions {
                        extra_paths.push(version.to_string_lossy().to_string());
                    }
                }
            }
            if let Some(ref ph) = pnpm_home {
                extra_paths.push(ph.clone());
            }

            // nvm: add ALL version bin dirs (sorted newest-first)
            let nvm_dir_env = std::env::var("NVM_DIR").ok();
            let nvm_dir = match &nvm_dir_env {
                Some(dir) if Path::new(dir).is_dir() => dir.clone(),
                _ => format!("{}/.nvm", home),
            };
            let nvm_versions = Path::new(&nvm_dir).join("versions").join("node");
            if nvm_versions.is_dir() {
                if let Ok(entries) = std::fs::read_dir(&nvm_versions) {
                    let mut versions: Vec<PathBuf> = entries
                        .filter_map(|e| e.ok().map(|e| e.path()))
                        .filter(|p| p.is_dir())
                        .collect();
                    versions.sort();
                    versions.reverse();
                    for version in &versions {
                        extra_paths.push(version.join("bin").to_string_lossy().to_string());
                    }
                }
            }

            // fnm: add ALL version bin dirs (sorted newest-first)
            let fnm_dirs = [
                format!("{}/Library/Application Support/fnm/node-versions", home),
                format!("{}/.local/share/fnm/node-versions", home),
            ];
            for fnm_dir in &fnm_dirs {
                let fnm_path = Path::new(fnm_dir);
                if fnm_path.is_dir() {
                    if let Ok(entries) = std::fs::read_dir(fnm_path) {
                        let mut versions: Vec<PathBuf> = entries
                            .filter_map(|e| e.ok().map(|e| e.path()))
                            .filter(|p| p.is_dir())
                            .collect();
                        versions.sort();
                        versions.reverse();
                        for version in &versions {
                            extra_paths.push(
                                version.join("installation").join("bin").to_string_lossy().to_string()
                            );
                        }
                    }
                }
            }

            let comprehensive_path = format!(
                "{}:{}",
                extra_paths.join(":"),
                system_path
            );

            let command = app_handle
                .shell()
                .sidecar("backend")?
                .args(["--host", host, "--port", &DEFAULT_BACKEND_PORT.to_string()])
                .env("DATABASE_URL", database_url)
                .env("APP_MODE", "desktop")
                .env("IS_HOSTED", "false")
                .env("PYTHONUNBUFFERED", "1")
                .env("PYTHONIOENCODING", "utf-8")
                .env("PATH", comprehensive_path);

            // Tauri inherits the environment of the process that launches it.
            // Forward the local OpenAI-compatible settings to the sidecar when
            // present; the backend encrypts them before persistence.
            let mut command = command;
            for env_name in [
                "LLM_API_KEY",
                "ARK_API_KEY",
                "ARK_APIKEY",
                "OPENAI_API_KEY",
                "LLM_ENDPOINT",
                "OPENAI_BASE_URL",
                "LLM_MODEL",
            ] {
                if let Ok(value) = std::env::var(env_name) {
                    command = command.env(env_name, value);
                }
            }

            let spawn_start = Instant::now();
            let (mut rx, child) = command.spawn()?;
            writeln!(
                log_file,
                "{}",
                format_log_line(
                    "system",
                    &format!("Sidecar process spawned in {} ms", spawn_start.elapsed().as_millis())
                )
            )
            .ok();

            let port_state_for_stdout = port_state.clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            let message = String::from_utf8_lossy(&line);
                            let trimmed = message.trim_end_matches('\n');

                            if let Some(port_str) = trimmed.strip_prefix("BACKEND_PORT:") {
                                if let Ok(actual_port) = port_str.trim().parse::<u16>() {
                                    if let Ok(mut guard) = port_state_for_stdout.lock() {
                                        *guard = actual_port;
                                    }
                                }
                            }

                            let _ = OpenOptions::new()
                                .create(true)
                                .append(true)
                                .open(&log_path)
                                .and_then(|mut f| {
                                    writeln!(
                                        f,
                                        "{}",
                                        format_log_line("stdout", trimmed)
                                    )?;
                                    Ok(())
                                });
                        }
                        CommandEvent::Stderr(line) => {
                            let _ = OpenOptions::new()
                                .create(true)
                                .append(true)
                                .open(&log_path)
                                .and_then(|mut f| {
                                    let message = String::from_utf8_lossy(&line);
                                    writeln!(
                                        f,
                                        "{}",
                                        format_log_line("stderr", message.trim_end_matches('\n'))
                                    )?;
                                    Ok(())
                                });
                        }
                        CommandEvent::Error(message) => {
                            let _ = OpenOptions::new()
                                .create(true)
                                .append(true)
                                .open(&log_path)
                                .and_then(|mut f| {
                                    writeln!(f, "{}", format_log_line("error", &message))?;
                                    Ok(())
                                });
                        }
                        _ => {}
                    }
                }
            });

            app.manage(BackendState {
                child: Arc::new(Mutex::new(Some(child))),
            });

            // Create deep link state to store initial URL (for cold start handling)
            let deep_link_state = DeepLinkState {
                initial_url: Arc::new(Mutex::new(None)),
            };
            let deep_link_state_clone = deep_link_state.initial_url.clone();
            app.manage(deep_link_state);

            // Register deep link handler
            let handle = app.handle().clone();
            app.deep_link().on_open_url(move |event| {
                let urls = event.urls();
                for url in urls {
                    let url_str = url.to_string();
                    log::info!("Deep link received: {}", url_str);

                    // Store in state (for cold start - React might not be ready yet)
                    if let Ok(mut guard) = deep_link_state_clone.lock() {
                        *guard = Some(url_str.clone());
                    }

                    // Bring window to foreground
                    if let Some(window) = handle.get_webview_window("main") {
                        let _ = window.unminimize();  // Restore if minimized
                        let _ = window.show();        // Show if hidden
                        let _ = window.set_focus();   // Bring to front and focus
                    }

                    // Emit to frontend (for warm start - React is already listening)
                    let _ = handle.emit("deep-link-received", url_str);
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_backend_port, get_initial_deep_link])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit { .. } = event {
            if let Some(state) = app_handle.try_state::<BackendState>() {
                if let Ok(mut guard) = state.child.lock() {
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                    }
                }
            }
        }
    });
}
