# Совместимость Bend2 LSP с Node.js в Zed

## Короткий ответ

- **`bend2-lsp@0.1.0`: да.** Его `engines.node` — `>=22`, что соответствует Zed 1.21.0 (system Node минимум `22.0.0`, managed Node `v24.11.0`). LSP `initialize`/`shutdown` smoke прошёл на Node `v22.5.1` и `v23.11.0`. [npm 0.1.0](https://registry.npmjs.org/bend2-lsp/0.1.0) · [исходник Zed 1.21.0](https://github.com/zed-industries/zed/blob/v1.21.0/crates/node_runtime/src/node_runtime.rs#L606-L607)
- **`bend2-lsp@0.1.1`: запуск подтверждён, хотя объявлен Node `>=26.9.0`.** Порог выше Zed managed `v24.11.0` и протестированных Node `v22.5.1`/`v23.11.0`, но LSP smoke прошёл на обеих версиях. Значит, сервер способен стартовать на Node, допустимом для Zed 1.21.0; это фактическая проверка запуска, а не официально заявленная поддержка версии. [npm 0.1.1](https://registry.npmjs.org/bend2-lsp/0.1.1)

Проверка ограничена запуском процесса, LSP `initialize`, `shutdown` и успешным выходом. Она не проверяет диагностику, форматирование и переход к определению.

Под «заявленной совместимостью» здесь понимаю соответствие `engines.node`; smoke подтверждает только запуск процесса и LSP handshake, а не работу всех функций.

## Что гарантирует API и что делает Zed сейчас

Документация Zed предписывает вернуть из `language_server_command` структуру `Command` с исполняемым файлом, аргументами и окружением; [документация API](https://zed.dev/docs/extensions/languages#language-servers). API `node_binary_path()` описан только как возвращающий «путь к Node binary, используемому Zed» — версия или минимальная версия этим контрактом не гарантируется. [Документация функции](https://docs.rs/zed_extension_api/latest/zed_extension_api/fn.node_binary_path.html)

В этой среде `zed --version` вернул `Zed 1.21.0`, а `node --version` — `v23.11.0`. Последняя команда показывает Node в shell, но не доказывает, что именно его возвращает `node_binary_path()`: Zed может выбрать настроенный системный или managed runtime. Исходник релиза Zed 1.21.0 фиксирует managed Node `v24.11.0` и минимальную версию системного Node `22.0.0`; это версия конкретного релиза, не обещание API для всех будущих версий. [managed Node](https://github.com/zed-industries/zed/blob/v1.21.0/crates/node_runtime/src/node_runtime.rs#L606-L607) · [минимум system Node](https://github.com/zed-industries/zed/blob/v1.21.0/crates/node_runtime/src/node_runtime.rs#L859-L879) · [выбор runtime](https://github.com/zed-industries/zed/blob/v1.21.0/crates/node_runtime/src/node_runtime.rs#L110-L181)

В этом расширении сервер запускается как дочерняя команда: оно устанавливает `bend2-lsp@0.1.1`, выбирает `node_modules/bend2-lsp/dist/server.js`, затем возвращает `zed::Command` с `zed::node_binary_path()` и аргументом `--stdio`. Сборка расширения в WASI не означает, что этот JS-сервер исполняется в WASI. [Код расширения](../src/lib.rs)

## Пакеты и пределы проверки

Обе npm-версии публикуют `dist/server.js` как исполняемый файл (`bin`) и имеют тип пакета `module`. У `0.1.0` `engines.node` — `>=22`, у `0.1.1` — `>=26.9.0`; различаются и зависимости `vscode-languageserver` (`^9.0.1` против `10.1.1`). Сборка `0.1.1` задаёт esbuild target `node26` для сервера и worker. Это подтверждает, что новый релиз целит в Node 26, но само по себе не доказывает невозможность запуска в более старом Node — smoke прошёл на 22.5.1 и 23.11.0. [npm 0.1.0](https://registry.npmjs.org/bend2-lsp/0.1.0) · [npm 0.1.1](https://registry.npmjs.org/bend2-lsp/0.1.1) · [build.mjs 0.1.1](https://github.com/don2e4/bend2-lsp/blob/d85e556febcd3e787c48f4558b5f89a34729626d/build.mjs)

Исходники используют обычные Node-модули (`node:url`, `node:fs`, `node:path`, `node:worker_threads`); в просмотренном коде нет очевидного API, доступного только с Node 26.9. Worker стартует при инициализации сервера, и smoke завершился успешным LSP handshake на Node 22.5.1 и 23.11.0. Это доказывает возможность запуска и старта worker, но не работу всех функций на этих версиях. [исходник 0.1.0](https://github.com/don2e4/bend2-lsp/blob/b3547434dbd52450e342dddaa6addf2614906bd1/src/server.ts) · [исходник 0.1.1](https://github.com/don2e4/bend2-lsp/blob/d85e556febcd3e787c48f4558b5f89a34729626d/src/server.ts) · [worker 0.1.1](https://github.com/don2e4/bend2-lsp/blob/d85e556febcd3e787c48f4558b5f89a34729626d/src/analysis-worker.ts)

**Не проверено:** диагностика, форматирование и import go-to-definition на Node 22/23/24; точная версия Node, выбранная `node_binary_path()` в пользовательском Zed; причина `engines.node >=26.9.0`. Пользователь сообщил, что расширение «вроде работает» внутри Zed, но не уточнил, какие LSP-запросы проверял. Поэтому запуск подтверждён отдельно smoke-тестом и пользовательским сообщением, а полная совместимость API — нет.