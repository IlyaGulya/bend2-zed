# Bend 2 support for Zed

This repository is a Zed development extension for Bend 2. It provides syntax highlighting, bracket matching, function/law/type/constructor outlines, `#` comments and indentation after `:`. Supported roles include constructor field declarations, dotted names, law templates, typed lets, the immediate `?` unsafe suffix and separate GPU `!`/`(` tokens. It also installs and starts the Rust `bend2-lsp`.

The `bend2` grammar is pinned to [Soulthym's upstream `v0.3.0`](https://github.com/Soulthym/tree-sitter-bend2/tree/v0.3.0) at commit `997ec087147eb996731cc542ab4931b97049d2a1`, not our fork. Queries target the upstream grammar's CST, not the previous independent grammar.

## Install locally

1. In Zed, run `zed: install dev extension` and select this repository's root directory.
2. Install a supported Bend 2 CLI (`bend`) for compiler diagnostics and `Base` navigation. The Rust LSP does not bundle the compiler.
3. Open a `.bend` file. Zed fetches and compiles the published grammar revision pinned in `extension.toml`.

For an already installed dev extension, run `zed: rebuild dev extension` after updating the extension code, grammar pin or queries, then restart the language server to load the updated LSP.

When switching the grammar repository (for example, from our fork to upstream), move the old generated `grammars/bend2` checkout to a backup directory before rebuilding. Zed does not replace a cached clone whose `origin` differs from the repository in `extension.toml`; it reports “already exists, but is not a git clone”. Preserve any local changes in the backup.

Network access is required for the first grammar fetch and language-server install. The extension uses a configured binary first, then `bend2-lsp` on PATH, otherwise downloads the pinned Rust server from [GitHub Releases](https://github.com/IlyaGulya/bend2-lsp-rs/releases). No Node.js runtime is needed for the server. Syntax highlighting works independently of the LSP.

This extension uses the separate `bend2` ID because Zed already has a legacy `bend` extension. If both are installed and `.bend` files use the Bend 1 grammar, disable the legacy extension.

## Grammar verification

After installing `tests/requirements.txt`, run `python3 tests/check_highlights.py` to load the exact grammar revision pinned in `extension.toml` from the matching local clone when available, or from GitHub otherwise. It checks input-driven highlight roles and precedence, actual bracket ranges, outlines and captures on the grammar corpus. Requires Python 3.12+, a POSIX C compiler and Git.

The extended gate uses Python 3.12+, a POSIX C compiler with ASan/UBSan, Git and the dependencies in `tests/requirements.txt`:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
.venv/bin/python tests/check_all.py
```

Every gate reads the grammar commit from `extension.toml`; it does not test an accidentally modified grammar checkout:

- `check_highlights.py`: input-driven highlight roles, precedence, bracket pairs and outlines; corpus capture probes.
- `check_recovery.py`: targeted LF/CRLF break/repair checks, intact neighboring declarations and all Zed query captures, plus deterministic corpus edits comparing complete incremental/fresh trees and captures.
- `check_compatibility.py`: supported official syntax for template clauses/calls, unsafe suffixes, dotted field declarations and typed lets; LF/CRLF break/repair and intact following definitions. Whitespace before `?` and late template clauses are syntax errors.
- `check_scanner.py`: real external-scanner transitions, snapshot round trips, truncated input and capacity boundaries under ASan/UBSan.
- `check_upstream.py`: every `.bend` file from the official Bend `v2.0.35` / `79df8d9c40722ee9507a1e253f283b51025f9d6c` reference. Archive, corpus inventory and reviewed fixture hashes are pinned in `tests/bend-reference.json` and `tests/upstream-rejections.json`. Each file has a hard timeout; failures/crashes are not treated as syntax rejections.
- `check_upstream_gate.py`: reviewed positive/negative transitions, compiler-owned constraints, new rejections and infrastructure failures cannot silently become exemptions.

The sweep writes every result, including errors and durations, to `build/upstream-report.json`. New rejections, malformed fixtures becoming accepted, reviewed positive cases becoming rejected, and unresolved valid-source grammar gaps fail the release gate. An expected compiler diagnostic is not a syntax exemption. Cross-declaration constraints are explicitly reviewed as compiler-owned: `err_fill_short.bend` requires matching a definition's parameter count to an earlier resolved law, so its editor tree remains intact while Bend/LSP reports the error. `--diagnostic` permits report collection but explicitly is not a passing release gate; it never updates the baseline. For an offline reference, pass `--reference-dir /path/to/extracted/reference`; the same content hashes are required.

The upstream `v0.3.0` reference sweep visits all 1,644 files: 1,522 clean parses and 122 reviewed syntax rejections. All ten formerly falsely accepted malformed fixtures now reject. The strict release gate passes without rejection-baseline changes or timeout exemptions.

CLI verification passed the full `check_all.py --reference-dir /path/to/extracted/reference` gate against the exact upstream pin: 42 corpus capture probes, 16 targeted break/repair cycles, 252 seeded corpus edits, 32 supported-syntax break/repair cycles, scanner state checks under ASan/UBSan, and release-decision contract tests. The offline corpus run retained pinned content fingerprints and the strict 10-second per-file deadline. A separate parser smoke loaded ABI 15 and all three Zed queries, parsed glued natural infix syntax, preserved a terminal `0` and the following definition after an invalid call assignment target, and restored the original tree/captures after repair under LF/CRLF.

Known limits: syntax recognition does not check constructor resolution/arity or other compiler-owned constraints; compiler diagnostics remain separate. Seeded incremental consistency alone does not prove useful recovery for every damaged buffer. Scanner state uses full-width columns and refuses new scopes when its bounded serialization capacity is exhausted rather than truncating the live stack; deep nesting can therefore be rejected. Standalone scanner fixtures cover ASCII, not Unicode/included ranges. Verification here is through CLI parser/query execution, not the actual Zed UI.

## Language-server scope

The extension uses [the Rust bend2-lsp](https://github.com/IlyaGulya/bend2-lsp-rs), including completion, signature help, navigation, references, rename, formatting, semantic tokens, and compiler diagnostics. Source-based features are indexed, not compiler-derived type inference. Compiler checks require an installed `bend` CLI and are limited by its diagnostic output.

Automatic installation supports macOS, GNU/glibc Linux, and Windows on x86_64 and ARM64. The extension pins the stable `v0.6.1` release, including valid import completion, automatic import suggestions, and indexed symbol auto-import. Server upgrades follow extension releases, not a floating nightly/latest channel. A user-supplied binary is never installed or updated by the extension.

### Organize imports

Focus the `.bend` editor, open the command palette and run **editor: organize
imports** (`editor::OrganizeImports`). The default shortcut is **Alt+Shift+O**
(**Option+Shift+O** on macOS). No diagnostic, import selection, or cursor on an
import is required: Zed requests `source.organizeImports` for the whole current
buffer and applies the returned edit, including unsaved changes.

This requires a server with Organize Imports support (v0.4.0 or newer). A
configured binary or one found on PATH takes precedence over the extension's
download; check the active server if the command does nothing.

Before:

```bend
import ./z.bend as Z # z documentation
# dependency documentation
import ./dep.bend as D
```

After:

```bend
# dependency documentation
import ./dep.bend as D
import ./z.bend as Z # z documentation
```

Imports are sorted by written path and alias within each leading group.
Blank lines and incomplete import suffixes separate groups. Distinct aliases
remain; equivalent indexed targets with the same alias are deduplicated and
their comments retained. Conflicting aliases and multiple unaliased targets
keep their relative order. Comments stay attached, LF/CRLF and final-newline
presence are preserved, and the rest of the buffer is unchanged.
**Unused imports are not removed.**

An already organized file, a file without imports, or a group that cannot be
safely changed produces no action. Zed then leaves the buffer unchanged, without
a success message; repeating the command should normally have this result.
See the server's [full rules](https://github.com/IlyaGulya/bend2-lsp-rs#organize-imports-in-zed).


## Configuration and debugging

Use Zed user settings for personal paths and debug output; use `.zed/settings.json` for shareable project compiler settings. The server's configuration section is `bend2-lsp`, inside Zed's `lsp.bend2.settings`:

```json
{
  "lsp": {
    "bend2": {
      "settings": {
        "bend2-lsp": {
          "compilerPath": "/absolute/path/to/bend",
          "compilerArguments": []
        }
      }
    }
  }
}
```

For a locally built server, set `lsp.bend2.binary.path` to its absolute executable path. Optional `binary.arguments` and `binary.env` are forwarded to the server. Leave the path unset to retain automatic installation.

<<<<<<< Updated upstream
### Automatic import completion

Enable automatic LSP suggestions using the exact language name `"Bend 2"`:

```json
{
  "languages": {
    "Bend 2": {
      "show_completions_on_input": true,
      "completions": { "lsp": true }
    }
  }
}
```

After `import `, type a file-name prefix or fuzzy abbreviation normally, for
example `apd` for `./nested/append.bend`, or continue a directory path with `/`.
A manual completion command is not required. Suggestions use open files and
already indexed imports, including locally cached packages; this does not scan
the whole project or download packages. Open an unknown target file first.

Zed may prioritize an active inline edit prediction over word-triggered LSP
completion. To prefer the LSP popup in that situation, add
`"show_edit_predictions": false` to the same `"Bend 2"` object. This affects only
Bend 2, not other languages. No extra alphabetic trigger characters or language
configuration overrides are needed.

For a local fix, use `lsp.bend2.binary.path` as described above, then restart the
server. A user-supplied or PATH binary takes precedence over the extension's
pinned download, so confirm which executable Zed launches when checking a fix.
=======
The extension appends `[bend2-zed]` diagnostics to `launch.log` in its extension working directory (on macOS: `~/Library/Application Support/Zed/extensions/work/bend2/launch.log`). `extension_loaded` confirms that the diagnostic-enabled extension was instantiated. Launch callbacks record the LSP ID, worktree ID/root, resolved `binary.path`, selection source, and download progress. The workspace-configuration callback also records the effective binary path. Paths may contain personal information; argument values, environment values, server settings, and file contents are not logged. Remove the file to clear the accumulated diagnostics.

Zed handles an explicit `lsp.bend2.binary.path` itself and bypasses the extension's launch callback, so missing `resolving_server`/`server_selected` lines do not prove that the extension failed to load. `workspace_configuration` can still show the effective settings after initialization. The extension also writes to stderr, but WASM stderr inherits the Zed process's stderr and is **not** forwarded into `Zed.log`. Use `launch.log` for extension diagnostics and Zed's `starting language server process` line for the actual launched executable. Logging does not change selection precedence or make launch fail if the diagnostic file cannot be written.
>>>>>>> Stashed changes

For an opt-in performance capture, add the following to the same `bend2` object:

```json
"binary": {
  "env": {
    "BEND2_LSP_TRACE": "/absolute/existing/directory/bend2-trace.json"
  }
}
```

Restart the language server after changing launch settings. Finish the capture by shutting down the server normally, then open the JSON file in [Perfetto](https://ui.perfetto.dev/). The file is truncated at every server start: use a new filename for each capture, especially with multiple projects. Remove the variable and restart to disable recording.

Tracing is local and disabled by default; nothing is uploaded. The server's trace fields exclude source text, identifiers, diagnostic messages, paths/URIs, compiler arguments, stdout, and stderr. Review captures before sharing. Protocol logs are a separate, potentially source-containing debug tool, not a privacy-safe performance trace. See the server's [tracing guide](https://github.com/IlyaGulya/bend2-lsp-rs/blob/main/docs/tracing.md).
