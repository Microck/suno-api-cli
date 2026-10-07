"""Exercise the CLI against a real HTTP fixture server without provider charges."""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import TestCase

spec = importlib.util.spec_from_file_location('suno', Path(__file__).resolve().parents[1] / 'suno.py')
suno = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suno)


class BackendFixture(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, *args):
        pass

    def respond(self, status, value):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(value).encode())

    def do_GET(self):
        if self.path == '/api/get_limit':
            return self.respond(200, {'credits_left': 300})
        if self.path.startswith('/api/get?ids=failed'):
            return self.respond(200, [{'id': 'failed', 'status': 'error'}])
        if self.path.startswith('/api/get?ids=track-1'):
            return self.respond(200, [{'id': 'track-1', 'status': 'complete',
                                      'audio_url': f'http://127.0.0.1:{self.server.server_port}/audio'}])
        if self.path == '/audio':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'real HTTP audio fixture')
            return
        if self.path == '/api/get?ids=unauthorized':
            return self.respond(403, {'error': 'Session expired'})
        return self.respond(200, [])

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.requests.append((self.path, body, self.headers.get('User-Agent')))
        self.respond(200, [{'id': 'track-1', 'status': 'submitted'}])


class CliTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), BackendFixture)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = ['--api-url', f'http://127.0.0.1:{cls.http.server_port}']

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = suno.main(self.base + list(args))
        return status, out.getvalue(), err.getvalue()

    def test_status_checks_account(self):
        code, out, _ = self.call('status')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {'authenticated': True, 'credits': {'credits_left': 300}})

    def test_description_posts_exact_contract_once(self):
        before = len(BackendFixture.requests)
        code, _, _ = self.call('generate', '--prompt', 'rain', '--instrumental', '--model', 'chirp-crow', '--wait')
        self.assertEqual(code, 0)
        self.assertEqual(len(BackendFixture.requests), before + 1)
        route, body, agent = BackendFixture.requests[-1]
        self.assertEqual(route, '/api/generate')
        self.assertEqual(body, {'prompt': 'rain', 'model': 'chirp-crow', 'wait_audio': True, 'make_instrumental': True})
        self.assertEqual(agent, suno.USER_AGENT)

    def test_custom_reads_lyrics_file(self):
        with tempfile.TemporaryDirectory() as folder:
            lyrics = Path(folder) / 'lyrics.txt'
            lyrics.write_text('verse\nchorus')
            code, _, _ = self.call('generate', '--lyrics-file', str(lyrics), '--tags', 'folk', '--title', 'Rain')
        self.assertEqual(code, 0)
        route, body, _ = BackendFixture.requests[-1]
        self.assertEqual(route, '/api/custom_generate')
        self.assertEqual(body['prompt'], 'verse\nchorus')
        self.assertNotIn('model', body)

    def test_invalid_custom_does_not_submit(self):
        before = len(BackendFixture.requests)
        code, out, err = self.call('generate', '--lyrics-file', 'missing.txt')
        self.assertEqual((code, out), (2, ''))
        self.assertIn('--tags', err)
        self.assertEqual(len(BackendFixture.requests), before)

    def test_http_error_uses_stderr_and_fails(self):
        code, out, err = self.call('list', 'unauthorized')
        self.assertEqual((code, out), (1, ''))
        self.assertIn('HTTP 403', err)

    def test_download_and_protect_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.call('download', 'track-1', '--output', folder)
            self.assertEqual(code, 0)
            target = Path(json.loads(out)['file'])
            self.assertEqual(target.read_bytes(), b'real HTTP audio fixture')
            code, _, _ = self.call('download', 'track-1', '--output', folder)
            self.assertEqual(code, 1)
            self.assertEqual(target.read_bytes(), b'real HTTP audio fixture')

    def test_failed_track_not_downloaded(self):
        code, out, err = self.call('download', 'failed')
        self.assertEqual((code, out), (1, ''))
        self.assertIn('not complete', err)


class AuthStorageTests(TestCase):
    def test_auth_saves_private_file_without_restarting_a_service(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parents[1] / 'suno.py'),
                 'auth', '--cookie-stdin'], input='__client=fixture-refresh-cookie',
                text=True, capture_output=True, env={**os.environ, 'HOME': folder},
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertNotIn('fixture-refresh-cookie', process.stdout + process.stderr)
            saved = Path(folder) / '.config/suno-api-cli/credentials.json'
            self.assertEqual(json.loads(saved.read_text()), {'cookie': '__client=fixture-refresh-cookie'})
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
