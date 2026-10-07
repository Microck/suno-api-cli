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
succeeded. No song was submitted. Eight local tests cover
status, generation payloads, errors, lyrics, download behavior, and private
credential storage. Backend
TypeScript and scoped ESLint passed. Strict lint reports five inherited errors
and 17 warnings; those upstream issues were not changed.


## Logo

Generated with the built-in image generation tool, then edited to the final
repository name. Saved at .github/assets/logo.png.

Final prompt: preserve the true black background, white chevron and five-bar
waveform mark. Set the text to exact lowercase "suno-api-cli", slightly smaller
with generous horizontal margins. Minimal flat style, crisp edges, no gradients,
shadows, frame, extra text, or official Suno logo.

## Download contract

`suno download ID_OR_SONG_URL ...` downloads selected tracks. `--all` downloads
all completed tracks returned by the authenticated library feed, requesting
pages until an empty page or a page with no new IDs. IDs and --all are mutually
exclusive. Library entries still generating are omitted from --all.
Explicit incomplete or missing IDs are errors. Song links must use HTTPS and
suno.com/song/ID. Duplicate selections are downloaded once.

Audio filenames are a sanitized title followed by the complete track ID,
or only the ID when the title is empty. Files retain the progressive audio format supplied in media_urls, supporting
M4A/Opus, M4A, MP3, and WAV without transcoding. The deprecated audio_url field
is not used for downloads. `--metadata` writes a matching JSON
file with title, ID, lyrics, prompts, tags, duration, and the other returned
track fields. `--jobs` defaults to 4 and accepts 1 through 16.

Downloads refuse to overwrite existing files. --skip-existing skips an existing
nonempty audio file, with a nonempty metadata file also required when metadata
was requested. Its audio header must match the expected container. Empty or incomplete file pairs remain errors. Partial downloads
and newly created metadata files are removed on failure. Empty or truncated
HTTP responses are errors. No account cookies are sent to audio hosts. Audio is streamed through
GET /api/download?id=ID. The backend uses Suno-issued Mango rights to unwrap
AES-GCM keys and decrypt AES-CTR audio, keeping playback keys off the CLI
response and out of metadata files. A refused rights request is an error.
Downloads and existing files must have a matching audio container header.

All downloads return JSON with downloaded, skipped, and errors arrays. The exit
code is 1 if any selected track failed; successful files remain available.
Downloading does not generate songs or spend generation credits.

Version 0.2 changes the old single-download response from {file} to the batch
summary, and filenames now include the sanitized title when available. The
bundled backend preserves media_urls in library responses. Existing backend
installations must add this field or install the new bundled backend into a
fresh directory. Run setup with a new SUNO_BACKEND_DIR as described above.


The Mango protocol was checked against Suno's current web-player chunk:
https://suno.com/_next/static/immutable/chunks/1r54r3aq4-jfn.js
For authenticated playback, SHA-256 of the exact request session token is the
AES-GCM wrapping key. Clip ID is the additional authenticated data. The unwrapped
content key and counter decrypt AES-CTR audio. The backend snapshots the token
and explicitly uses it for the rights request to avoid renewal races. This
client has one authenticated rights flow; it does not retry with guest rights.

The download workflow was informed by these projects without copying their code:
https://github.com/danny-englander/suno-ai-downloader
https://github.com/zarigata/sudodownloader

Live download verification: all eight tracks in the test account library were
downloaded with metadata, and ffprobe parsed every M4A successfully. Repeated
downloads skipped the existing files. Fourteen CLI HTTP/storage tests and three
cryptographic tests pass. The first live test revealed that copying encrypted
CDN bytes was insufficient; those test artifacts were removed before validating
the authenticated decrypted output. No music generation was submitted.
