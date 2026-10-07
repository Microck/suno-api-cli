#!/usr/bin/env python3
"""Small command-line client for gcui-art/suno-api."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

VERSION = '0.1.0'
BACKEND = Path(os.environ.get('SUNO_BACKEND_DIR', Path.home() / '.local/share/suno-api-cli/backend'))
BUNDLED_BACKEND = Path(__file__).resolve().parent / 'backend'
CREDENTIALS = Path.home() / '.config/suno-api-cli/credentials.json'
USER_AGENT = 'OpenAI File Downloader, XaiImageApiFetch/1.0'


def credentials():
    return json.loads(CREDENTIALS.read_text()) if CREDENTIALS.exists() else {}


def save_secret(field, value):
    saved = credentials()
    saved[field] = value
    CREDENTIALS.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(CREDENTIALS.parent, 0o700)
    with tempfile.NamedTemporaryFile(mode='w', dir=CREDENTIALS.parent, delete=False) as stream:
        json.dump(saved, stream)
        private_path = Path(stream.name)
    os.chmod(private_path, 0o600)
    private_path.replace(CREDENTIALS)


def api(args, route, body=None):
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        args.api_url.rstrip('/') + route, data=payload,
        headers={'User-Agent': USER_AGENT, 'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get('error', 'Backend request failed')
        except (ValueError, AttributeError):
            detail = 'Backend request failed'
        # Upstream can put credentials in error objects. Never echo them.
        for secret in credentials().values():
            if isinstance(secret, str) and secret:
                detail = str(detail).replace(secret, '[redacted]')
        raise RuntimeError(f'Backend HTTP {error.code}: {detail}') from None
    except urllib.error.URLError:
        raise RuntimeError('Cannot reach suno-api. Run `suno server start`. If generation timed out, check `suno list` before retrying.') from None


def server(action):
    if action == 'run':
        return serve()
    if not shutil.which('systemctl'):
        raise RuntimeError('Background services require Linux systemd. Use `suno server run` in a terminal.')
    if action == 'install':
        node = shutil.which('node')
        if not node:
            raise RuntimeError('Install Node.js 20+ first.')
        unit = Path.home() / '.config/systemd/user/suno-api.service'
        if unit.exists():
            raise RuntimeError('suno-api.service already exists. Keep it or remove it explicitly before installing this service.')
        unit.parent.mkdir(parents=True, exist_ok=True)
        # Quote executable paths for systemd, not for a shell.
        def quoted(value):
            return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
        unit.write_text(
            '[Unit]\nDescription=Private Suno API backend\nAfter=network.target\n'
            '[Service]\nType=simple\n'
            f'ExecStart={quoted(sys.executable)} {quoted(Path(__file__).resolve())} server run\n'
            f'Environment={quoted("SUNO_BACKEND_DIR=" + str(BACKEND))}\n'
            f'Environment={quoted("SUNO_NODE=" + node)}\n'
            'Environment=NODE_OPTIONS=--max-old-space-size=512\n'
            'Restart=on-failure\nRestartSec=5\nUMask=0077\n'
            '[Install]\nWantedBy=default.target\n'
        )
        subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
        subprocess.run(['systemctl', '--user', 'enable', '--now', 'suno-api.service'], check=True)
        return
    subprocess.run(['systemctl', '--user', action, 'suno-api.service'], check=True)


def serve():
    saved = credentials()
    environment = {
        **os.environ, 'SUNO_COOKIE': saved.get('cookie', ''),
        'TWOCAPTCHA_KEY': saved.get('captcha_key', ''),
        'BROWSER': 'chromium', 'BROWSER_HEADLESS': 'true',
        'BROWSER_DISABLE_GPU': 'true', 'BROWSER_GHOST_CURSOR': 'false',
        'BROWSER_LOCALE': 'en', 'NEXT_TELEMETRY_DISABLED': '1',
    }
    node = os.environ.get('SUNO_NODE') or shutil.which('node')
    if not node or not (BACKEND / 'node_modules/next/dist/bin/next').is_file():
        raise RuntimeError('Backend is not installed. Install Node.js 20+ and run `suno setup`.')
    os.chdir(BACKEND)
    subprocess.run([node, str(BACKEND / 'node_modules/next/dist/bin/next'),
                    'dev', '--hostname', '127.0.0.1', '--port', '3791'], env=environment, check=True)


def parser():
    cli = argparse.ArgumentParser(description='Generate and download music through suno-api.')
    cli.add_argument('--version', action='version', version=VERSION)
    cli.add_argument('--api-url', default=os.environ.get('SUNO_API_URL', 'http://127.0.0.1:3791'))
    cli.add_argument('--timeout', type=float, default=300)
    commands = cli.add_subparsers(dest='command', required=True)
    commands.add_parser('setup', help='Install the bundled backend and Chromium')
    commands.add_parser('status', help='Check backend and account authentication')
    commands.add_parser('credits', help='Show account credits')
    captcha = commands.add_parser('captcha', help='Check CAPTCHA requirements')
    captcha.add_argument('--solve', action='store_true', help='Test solving; spends 2Captcha balance, creates no song')
    auth = commands.add_parser('auth', help='Store secrets read from stdin')
    secret = auth.add_mutually_exclusive_group(required=True)
    secret.add_argument('--cookie-stdin', action='store_true')
    secret.add_argument('--captcha-key-stdin', action='store_true')
    generate = commands.add_parser('generate', help='Generate music; spends credits')
    content = generate.add_mutually_exclusive_group(required=True)
    content.add_argument('--prompt')
    content.add_argument('--lyrics-file', type=Path)
    generate.add_argument('--tags')
    generate.add_argument('--title')
    generate.add_argument('--model', help='Suno model ID; omitted uses backend default')
    generate.add_argument('--instrumental', action='store_true')
    generate.add_argument('--wait', action='store_true', help='Wait for audio before returning')
    listing = commands.add_parser('list', help='List songs, optionally by ID')
    listing.add_argument('ids', nargs='*')
    download = commands.add_parser('download', help='Download a completed song')
    download.add_argument('id')
    download.add_argument('--output', type=Path, default=Path.cwd())
    backend = commands.add_parser('server', help='Manage the local backend')
    backend.add_argument('action', choices=['run', 'install', 'start', 'stop', 'restart'])
    return cli


def run(args):
    if args.command == 'setup':
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        node = shutil.which('node')
        if not npm or not node:
            raise RuntimeError('Install Node.js 20+ and npm first.')
        if not BACKEND.exists():
            shutil.copytree(BUNDLED_BACKEND, BACKEND)
        # Skip Electron/browser install hooks; install only the matching Chromium below.
        subprocess.run([npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], cwd=BACKEND, check=True, stdout=sys.stderr)
        subprocess.run([node, str(BACKEND / 'node_modules/rebrowser-playwright-core/cli.js'),
                        'install', 'chromium', '--only-shell'], check=True, stdout=sys.stderr)
        return {'backend': str(BACKEND), 'installed': True}
    if args.command == 'auth':
        value = sys.stdin.read().strip()
        if not value or '\n' in value or '\r' in value:
            raise ValueError('Provide one nonempty secret through stdin.')
        if args.cookie_stdin:
            value = value.removeprefix('Cookie:').strip()
            if not re.search(r'(?:^|;\s*)__client=[^;\s]+', value):
                raise ValueError('suno-api requires the renewable __client cookie. Copy the Cookie request header from auth.suno.com/v1/client in your logged-in browser.')
            field = 'cookie'
        else:
            field = 'captcha_key'
        save_secret(field, value)
        return {'saved': field, 'next': 'Restart your backend to load the new credential.'}
    if args.command == 'server':
        server(args.action)
        return {'backend': args.action}
    if args.command == 'captcha':
        return api(args, '/api/captcha', {} if args.solve else None)
    if args.command in ('credits', 'status'):
        result = api(args, '/api/get_limit')
        return {'authenticated': True, 'credits': result} if args.command == 'status' else result
    if args.command == 'generate':
        body = {'make_instrumental': args.instrumental, 'wait_audio': args.wait}
        if args.model:
            body['model'] = args.model
        if args.lyrics_file is not None:
            if not args.tags or not args.title:
                raise ValueError('--lyrics-file requires --tags and --title.')
            body.update(prompt=sys.stdin.read() if str(args.lyrics_file) == '-' else args.lyrics_file.read_text(),
                        tags=args.tags, title=args.title)
            route = '/api/custom_generate'
        else:
            if args.tags or args.title:
                raise ValueError('--tags and --title require --lyrics-file.')
            body['prompt'] = args.prompt
            route = '/api/generate'
        if not body['prompt'].strip():
            raise ValueError('The prompt or lyrics must not be empty.')
        print('Generating through suno-api. This may spend Suno credits and 2Captcha balance.', file=sys.stderr)
        return api(args, route, body)
    if args.command == 'list':
        query = urllib.parse.urlencode({'ids': ','.join(args.ids)}) if args.ids else ''
        return api(args, '/api/get' + ('?' + query if query else ''))
    if args.command == 'download':
        if not re.fullmatch(r'[A-Za-z0-9-]+', args.id):
            raise ValueError('Invalid track ID.')
        tracks = api(args, '/api/get?' + urllib.parse.urlencode({'ids': args.id}))
        track = next((track for track in tracks if track['id'] == args.id), None)
        if not track or track.get('status') != 'complete' or not track.get('audio_url'):
            raise RuntimeError('Track is not complete or has no audio URL. Check `suno list`.')
        url = track['audio_url']
        if urllib.parse.urlsplit(url).scheme not in ('http', 'https'):
            raise RuntimeError('Backend returned an invalid audio URL.')
        args.output.mkdir(parents=True, exist_ok=True)
        destination = args.output / (args.id + '.mp3')
        # Exclusive creation protects existing downloads. Delete only this partial file on failure.
        with destination.open('xb') as stream:
            try:
                request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
                with urllib.request.urlopen(request, timeout=args.timeout) as response:
                    while block := response.read(65536):
                        stream.write(block)
            except Exception:
                destination.unlink()
                raise
        return {'file': str(destination)}


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.timeout <= 0:
        cli.error('--timeout must be positive')
    try:
        print(json.dumps(run(args), indent=2))
        return 0
    except ValueError as error:
        print(f'error: {error}', file=sys.stderr)
        return 2
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'error: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
