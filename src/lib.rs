use std::{env, path::PathBuf};
use zed_extension_api::{self as zed, settings::LspSettings, LanguageServerId, Result, Worktree};

const RELEASE: &str = "v0.2.5";

struct Bend2Extension;

impl Bend2Extension {
    fn server_path(&self, id: &LanguageServerId, worktree: &Worktree) -> Result<String> {
        if let Some(path) = worktree.which("bend2-lsp") {
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
        }
        Ok(env::current_dir()
            .map_err(|error| error.to_string())?
            .join(path)
            .to_string_lossy()
            .into_owned())
    }
}

impl zed::Extension for Bend2Extension {
    fn new() -> Self {
        Self
    }

    fn language_server_command(
        &mut self,
        id: &LanguageServerId,
        worktree: &Worktree,
    ) -> Result<zed::Command> {
        let binary = LspSettings::for_worktree(id.as_ref(), worktree)?.binary;
        let command = match binary.as_ref().and_then(|binary| binary.path.clone()) {
            Some(path) => path,
            None => self.server_path(id, worktree)?,
        };
        let mut environment: std::collections::HashMap<_, _> =
            worktree.shell_env().into_iter().collect();
        if let Some(overrides) = binary.as_ref().and_then(|binary| binary.env.as_ref()) {
            environment.extend(overrides.iter().map(|(key, value)| (key.clone(), value.clone())));
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
        Ok(LspSettings::for_worktree(id.as_ref(), worktree)?.settings)
    }
}

zed::register_extension!(Bend2Extension);
