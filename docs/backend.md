# Backend

The bundled backend is gcui-art/suno-api at upstream commit a2e6a823.
Source: https://github.com/gcui-art/suno-api
License: LGPL-3.0-or-later. See backend/LICENSE and backend/COPYING.

Local modifications select the CAPTCHA provider returned by Suno, solve
Turnstile with the existing 2Captcha SDK, and retain upstream's hCaptcha
screenshot solver. Android impersonation headers were removed in favor of web
requests. CAPTCHA tokens are redacted from generation payload logs. A new
GET /api/captcha checks the gate; POST tests a solve without submitting music.
Strict Oxlint rules and a lint:anti-slop script accompany the source.

The npm package includes editable backend source. `suno setup` copies it into
~/.local/share/suno-api-cli/backend, installs its pinned dependency tree with
npm ci --ignore-scripts, and downloads the matching Playwright Chromium headless
shell. It skips Electron and unrelated install hooks. Existing backend source
is retained when setup is rerun so local modifications are not overwritten.
To use a fresh bundled revision, select a new empty SUNO_BACKEND_DIR and run
setup again. Use the same variable when starting the server.

On Linux, missing Chromium system libraries can be installed from the backend
directory with `node node_modules/rebrowser-playwright-core/cli.js install-deps
chromium`. This needs administrator access. Background management uses user
systemd; macOS and Windows use `suno server run`. Windows needs Python available
as `python`, or an explicit SUNO_PYTHON path. These platforms have not been
verified live.

CLI responses are JSON. Exit codes are 0 for success, 1 for runtime failure,
2 for invalid input, and 130 for Ctrl-C. The default request timeout is 300
seconds. Generation requests are never automatically retried.

Live evidence before packaging: renewable session authentication succeeded,
the account credits endpoint responded, and one paid Turnstile diagnostic
succeeded. No song was submitted. Seven local HTTP fixture tests cover
status, generation payloads, errors, lyrics, and download behavior. Backend
TypeScript and scoped ESLint passed. Strict lint reports five inherited errors
and 17 warnings; those upstream issues were not changed.
