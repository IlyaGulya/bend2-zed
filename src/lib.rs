use std::{env, fs::OpenOptions, io::Write, path::PathBuf};
use zed_extension_api::{self as zed, settings::LspSettings, LanguageServerId, Result, Worktree};

const RELEASE: &str = "v0.6.1";

fn log_launch(message: std::fmt::Arguments<'_>) {
    eprintln!("[bend2-zed] {message}");
    let result = OpenOptions::new()
        .create(true)
        .append(true)
        .open("launch.log")
        .and_then(|mut file| writeln!(file, "[bend2-zed] {message}"));
    if let Err(error) = result {
        eprintln!("[bend2-zed] launch_log_write_failed error={error}");
    }
}

struct Bend2Extension;

impl Bend2Extension {
    fn server_path(&self, id: &LanguageServerId, worktree: &Worktree) -> Result<String> {
        if let Some(path) = worktree.which("bend2-lsp") {
            log_launch(format_args!(
                "server_selected lsp_id={} worktree_id={} source=PATH path={path:?}",
                id.as_ref(), worktree.id()
            ));
            return Ok(path);
        }
        let target = match zed::current_platform() {
            (zed::Os::Mac, zed::Architecture::Aarch64) => "aarch64-apple-darwin",
            (zed::Os::Mac, zed::Architecture::X8664) => "x86_64-apple-darwin",
            (zed::Os::Linux, zed::Architecture::Aarch64) => "aarch64-unknown-linux-gnu",
            (zed::Os::Linux, zed::Architecture::X8664) => "x86_64-unknown-linux-gnu",
            (zed::Os::Windows, zed::Architecture::Aarch64) => "aarch64-pc-windows-msvc",
            (zed::Os::Windows, zed::Architecture::X8664) => "x86_64-pc-windows-msvc",
            _ => return Err("No bend2-lsp binary is available for this platform".into()),
        };
        let suffix = if target.contains("windows") {
            ".exe"
        } else {
            ""
        };
        let filename = format!("bend2-lsp-{RELEASE}-{target}{suffix}");
        let path = PathBuf::from(&filename);
        if !path.is_file() {
            log_launch(format_args!(
                "download_begin release={RELEASE} target={target} destination={filename:?}"
            ));
            zed::set_language_server_installation_status(
                id,
                &zed::LanguageServerInstallationStatus::Downloading,
            );
            let temporary = format!("{filename}.download");
            let url = format!(
                "https://github.com/IlyaGulya/bend2-lsp-rs/releases/download/{RELEASE}/bend2-lsp-{target}{suffix}"
            );
            zed::download_file(&url, &temporary, zed::DownloadedFileType::Uncompressed)?;
            zed::make_file_executable(&temporary)?;
            std::fs::rename(&temporary, &path).map_err(|error| error.to_string())?;
            log_launch(format_args!("download_complete release={RELEASE} target={target}"));
        }
        let absolute_path = env::current_dir()
            .map_err(|error| error.to_string())?
            .join(path)
            .to_string_lossy()
            .into_owned();
        log_launch(format_args!(
            "server_selected lsp_id={} worktree_id={} source=release_cache release={RELEASE} target={target} path={absolute_path:?}",
            id.as_ref(), worktree.id()
        ));
        Ok(absolute_path)
    }
}

impl zed::Extension for Bend2Extension {
    fn new() -> Self {
        log_launch(format_args!("extension_loaded pinned_release={RELEASE} diagnostics_file=launch.log"));
        Self
    }

    fn language_server_command(
        &mut self,
        id: &LanguageServerId,
        worktree: &Worktree,
    ) -> Result<zed::Command> {
        log_launch(format_args!(
            "resolving_server lsp_id={} worktree_id={} root={:?} pinned_release={RELEASE}",
            id.as_ref(), worktree.id(), worktree.root_path()
        ));
        let binary = LspSettings::for_worktree(id.as_ref(), worktree)
            .map_err(|error| {
                log_launch(format_args!(
                    "settings_read_failed lsp_id={} worktree_id={}",
                    id.as_ref(), worktree.id()
                ));
                error
            })?
            .binary;
        log_launch(format_args!(
            "settings_resolved lsp_id={} worktree_id={} binary_path={:?} arguments_override={} env_override_count={}",
            id.as_ref(),
            worktree.id(),
            binary.as_ref().and_then(|binary| binary.path.as_deref()),
            binary.as_ref().is_some_and(|binary| binary.arguments.is_some()),
            binary.as_ref().and_then(|binary| binary.env.as_ref()).map_or(0, |env| env.len())
        ));
        let command = match binary.as_ref().and_then(|binary| binary.path.clone()) {
            Some(path) => {
                log_launch(format_args!(
                    "server_selected lsp_id={} worktree_id={} source=settings path={path:?}",
                    id.as_ref(), worktree.id()
                ));
                path
            }
            None => self.server_path(id, worktree)?,
        };
        let mut environment: std::collections::HashMap<_, _> =
            worktree.shell_env().into_iter().collect();
        if let Some(overrides) = binary.as_ref().and_then(|binary| binary.env.as_ref()) {
            environment.extend(
                overrides
                    .iter()
                    .map(|(key, value)| (key.clone(), value.clone())),
            );
        }
        Ok(zed::Command {
            command,
            args: binary
                .as_ref()
                .and_then(|binary| binary.arguments.clone())
                .unwrap_or_default(),
            env: environment.into_iter().collect(),
        })
    }

    fn language_server_workspace_configuration(
        &mut self,
        id: &LanguageServerId,
        worktree: &Worktree,
    ) -> Result<Option<zed::serde_json::Value>> {
        let settings = LspSettings::for_worktree(id.as_ref(), worktree)?;
        log_launch(format_args!(
            "workspace_configuration lsp_id={} worktree_id={} root={:?} binary_path={:?}",
            id.as_ref(),
            worktree.id(),
            worktree.root_path(),
            settings.binary.as_ref().and_then(|binary| binary.path.as_deref())
        ));
        Ok(settings.settings)
    }
}

zed::register_extension!(Bend2Extension);
