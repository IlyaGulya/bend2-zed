# Bend 2 support for Zed

This repository is a Zed development extension for Bend 2. It provides Tree-sitter syntax highlighting, `#` comments, indentation after `:`, bracket matching, and outline entries for definitions. It also installs and starts `bend2-lsp` for compiler diagnostics, hover, and formatting.

## Install locally

1. In Zed, run `zed: install dev extension` and select this repository's root directory.
2. Allow Zed to install the pinned `bend2-lsp@0.1.1` npm package through Zed's Node runtime.
3. Open a `.bend` file. Zed fetches the pinned Bend 2 Tree-sitter grammar and builds it on first use.

Network access is required for the first grammar and language-server install. Syntax highlighting works independently of the LSP. If npm installation is blocked by your Zed extension capabilities, allow npm installation for `bend2-lsp` in Zed's `granted_extension_capabilities` settings.

This extension uses the separate `bend2` ID because Zed already has a legacy `bend` extension. If both are installed and `.bend` files use the Bend 1 grammar, disable the legacy extension.

## Verify syntax queries

Run `python3 tests/check_highlights.py` to fetch the exact grammar revision and run its complete upstream parser corpus against the Zed highlight and bracket queries. The check fails if any non-whitespace corpus text lacks a Zed-supported capture or if match-expression and generic delimiters are unpaired. Requires Python 3.12+, Node.js/npm, and network access.

## Language-server scope

`bend2-lsp@0.1.1` is the latest npm release. It provides compiler diagnostics, syntax/documentation hover, formatting, and go-to-definition for imports; it does not provide completion or local-variable type hover. npm declares Node.js `>=26.9.0`; startup was smoke-tested on Node `v22.5.1` and `v23.11.0`, and the server was reported working in Zed 1.21.0. Zed's selected Node runtime depends on its version and settings, so this does not guarantee every LSP request or every Zed configuration.

The official `bend2-fmt-lsp` is formatting-only and is not published to npm, so it is not used here.
