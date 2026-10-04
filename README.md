# Bend 2 support for Zed

This repository is a Zed development extension for Bend 2. It provides Tree-sitter syntax highlighting for named and dotted constructor fields, leading law template clauses, immediate `?` unsafe-definition suffixes, ordinary/erased/grouped typed lets, comparison match subjects, monadic `do` matches with bind/return arms, `#` comments, indentation after `:`, bracket matching, outline entries for definitions, and recovery of later declarations after some malformed code (including an unfinished empty call). Keywords inside parse-error nodes remain highlighted; deeply unclosed expressions can still disrupt the surrounding syntax tree. Pair destructuring and quantified-constructor patterns unsupported by Bend remain explicit invalid-pattern nodes; the language server reports them as compiler errors. It also installs and starts the Rust `bend2-lsp`.

## Install locally

1. In Zed, run `zed: install dev extension` and select this repository's root directory.
2. Install a supported Bend 2 CLI (`bend`) for compiler diagnostics and `Base` navigation. The Rust LSP does not bundle the compiler.
3. Open a `.bend` file. Zed fetches and compiles the published grammar revision pinned in `extension.toml`.

Network access is required for the first grammar fetch and language-server install. The extension uses a configured binary first, then `bend2-lsp` on PATH, otherwise downloads the pinned Rust server from [GitHub Releases](https://github.com/IlyaGulya/bend2-lsp-rs/releases). No Node.js runtime is needed for the server. Syntax highlighting works independently of the LSP.

This extension uses the separate `bend2` ID because Zed already has a legacy `bend` extension. If both are installed and `.bend` files use the Bend 1 grammar, disable the legacy extension.

## Grammar verification

Run `python3 tests/check_highlights.py` to load the exact grammar revision pinned in `extension.toml` from the matching local clone when available, or from GitHub otherwise. It checks the parser corpus, highlight and bracket queries, and keyword highlighting following an unfinished call. Requires Python 3.12+, Node.js/npm (for the Tree-sitter CLI only), and Git.

The extended gate uses Python 3.12+, a POSIX C compiler with ASan/UBSan, Node.js/npm for the CLI, and Git:

```sh
python3 -m venv .venv
.venv/bin/pip install -r tests/requirements.txt
.venv/bin/python tests/check_all.py
```

Every gate reads the grammar commit from `extension.toml`; it does not test an accidentally modified grammar checkout:

- `check_highlights.py`: corpus trees and Zed-supported highlight/bracket queries.
- `check_recovery.py`: targeted LF/CRLF break/repair checks, intact neighboring declarations and all Zed query captures, plus deterministic corpus edits comparing complete incremental/fresh trees and captures.
- `check_compatibility.py`: official syntax regressions for template clauses/calls, unsafe suffixes, dotted fields and typed lets; LF/CRLF break/repair and intact following definitions. Misplaced template clauses and whitespace before `?` remain errors.
- `check_scanner.py`: real external-scanner transitions, snapshot round trips, truncated input and capacity boundaries under ASan/UBSan.
- `check_upstream.py`: every `.bend` file from the official Bend `v2.0.35` / `79df8d9c40722ee9507a1e253f283b51025f9d6c` reference. Archive, corpus inventory and reviewed fixture hashes are pinned in `tests/bend-reference.json` and `tests/upstream-rejections.json`. Each file has a hard timeout; failures/crashes are not treated as syntax rejections.
- `check_upstream_gate.py`: reviewed positive/negative transitions, compiler-owned constraints, new rejections and infrastructure failures cannot silently become exemptions.

The sweep writes every result, including errors and durations, to `build/upstream-report.json`. New rejections, malformed fixtures becoming accepted, reviewed positive cases becoming rejected, and unresolved valid-source grammar gaps fail the release gate. An expected compiler diagnostic is not a syntax exemption. Cross-declaration constraints are explicitly reviewed as compiler-owned: `err_fill_short.bend` requires matching a definition's parameter count to an earlier resolved law, so its editor tree remains intact while Bend/LSP reports the error. `--diagnostic` permits report collection but explicitly is not a passing release gate; it never updates the baseline. For an offline reference, pass `--reference-dir /path/to/extracted/reference`; the same content hashes are required.

The repaired reference sweep visits all 1,644 files: 1,544 clean parses (including `bend2/base.bend` and all 25 repaired compatibility fixtures) and 100 reviewed malformed-syntax rejections. The reviewed corpus gate passes. This is not proof that every accepted program compiles: name-sensitive constraints and typing remain compiler-owned.

The complete gate was verified using `check_all.py --reference-dir /path/to/extracted/reference`, including the same content fingerprints and strict 10-second per-file deadline. An earlier timeout on the 5.7 MB proof benchmark was not reproduced in isolated worker checks; its historical cause remains unknown. No retries or timeout exemptions were added. A later network-enabled run exceeded its outer command deadline, so offline verification is provided independently of archive-download availability.

Known limits: damaged nested matches retain keyword colors but do not guarantee intact later case-clause structure. Seeded incremental consistency checks alone do not prove useful recovery. Scanner snapshots preserve at most 512 layout frames; deeper stacks are truncated, and columns above 32767 collide with the lambda flag. Standalone scanner fixtures cover ASCII, not Unicode/included ranges. These checks exercise parser/query behavior, not the actual Zed UI.

## Language-server scope

The extension uses [the Rust bend2-lsp](https://github.com/IlyaGulya/bend2-lsp-rs), including completion, signature help, navigation, references, rename, formatting, semantic tokens, and compiler diagnostics. Source-based features are indexed, not compiler-derived type inference. Compiler checks require an installed `bend` CLI and are limited by its diagnostic output.

Automatic installation supports macOS, GNU/glibc Linux, and Windows on x86_64 and ARM64. The extension pins the stable `v0.2.5` release. Server upgrades follow extension releases, not a floating nightly/latest channel. A user-supplied binary is never installed or updated by the extension.

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
