# Bend 2 support for Zed

This repository is a Zed development extension for Bend 2. It provides Tree-sitter syntax highlighting, `#` comments, indentation after `:`, bracket matching, and outline entries for definitions. It also installs and starts `bend2-lsp` for compiler diagnostics, hover, and formatting.

## Install locally

1. In Zed, run `zed: install dev extension` and select this repository's root directory.
2. Allow the extension to install the pinned `bend2-lsp` npm package when Zed requests it. The extension installs `bend2-lsp@0.1.0` through Zed's Node runtime; this release requires Node.js 22 or newer.
3. Open a `.bend` file. Zed fetches the pinned Bend 2 Tree-sitter grammar and builds it on first use.

Network access is required for the first grammar and language-server install. Syntax highlighting works independently of the LSP. If npm installation is blocked by your Zed extension capabilities, allow npm installation for `bend2-lsp` in Zed's `granted_extension_capabilities` settings.

This extension uses the separate `bend2` ID because Zed already has a legacy `bend` extension. If both are installed and `.bend` files use the Bend 1 grammar, disable the legacy extension.

## Language-server scope

`bend2-lsp` is the community Bend 2 server linked from the Bend project. The pinned release provides compiler diagnostics, syntax/documentation hover, and formatting. It does not provide completion, local-variable type hover, or go-to-definition. The extension pins version `0.1.0` because its Node.js `>=22` requirement is compatible with Zed's Node runtime; `0.1.1` adds import go-to-definition but requires Node.js `>=26.9`.

The official `bend2-fmt-lsp` is formatting-only and is not published to npm, so it is not used here.
