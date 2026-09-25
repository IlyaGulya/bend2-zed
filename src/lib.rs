use std::{env, path::PathBuf};
use zed_extension_api::{self as zed, LanguageServerId, Result, Worktree};

const PACKAGE_NAME: &str = "bend2-lsp";
const PACKAGE_VERSION: &str = "0.1.0";
const SERVER_RELATIVE_PATH: &str = "node_modules/bend2-lsp/dist/server.js";

struct Bend2Extension {
    did_find_server: bool,
}

impl Bend2Extension {
    fn server_script_path(&mut self, language_server_id: &LanguageServerId) -> Result<PathBuf> {
        let extension_dir = env::current_dir().map_err(|error| error.to_string())?;
        let server_path = extension_dir.join(SERVER_RELATIVE_PATH);
        if self.did_find_server && server_path.is_file() {
            return Ok(server_path);
        }

        zed::set_language_server_installation_status(
            language_server_id,
            &zed::LanguageServerInstallationStatus::CheckingForUpdate,
        );

        let installed_version = zed::npm_package_installed_version(PACKAGE_NAME)?;
        if !server_path.is_file() || installed_version.as_deref() != Some(PACKAGE_VERSION) {
            zed::set_language_server_installation_status(
                language_server_id,
                &zed::LanguageServerInstallationStatus::Downloading,
            );
            zed::npm_install_package(PACKAGE_NAME, PACKAGE_VERSION)?;
        }

        if !server_path.is_file() {
            return Err(format!(
                "installed {PACKAGE_NAME}@{PACKAGE_VERSION}, but {SERVER_RELATIVE_PATH} was not found"
            ));
        }

        self.did_find_server = true;
        Ok(server_path)
    }
}

impl zed::Extension for Bend2Extension {
    fn new() -> Self {
        Self {
            did_find_server: false,
        }
    }

    fn language_server_command(
        &mut self,
        language_server_id: &LanguageServerId,
        _worktree: &Worktree,
    ) -> Result<zed::Command> {
        let server_path = self.server_script_path(language_server_id)?;
        Ok(zed::Command {
            command: zed::node_binary_path()?,
            args: vec![
                server_path.to_string_lossy().into_owned(),
                "--stdio".to_string(),
            ],
            env: Default::default(),
        })
    }
}

zed::register_extension!(Bend2Extension);
