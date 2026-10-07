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
        if self.path == '/api/get?page=0':
            return self.respond(200, [self.track('track-1'), {'id': 'waiting', 'status': 'submitted'}])
        if self.path == '/api/get?page=1':
            return self.respond(200, [self.track('track-2')])
        if self.path.startswith('/api/get?ids=track-'):
            ids = self.path.split('ids=', 1)[1].replace('%2C', ',').split(',')
            return self.respond(200, [self.track(track_id) for track_id in ids if track_id in ('track-1', 'track-2')])
        if self.path == '/api/get?ids=empty':
            track = self.track('empty')
            track['media_urls'][0]['url'] += '-empty'
            return self.respond(200, [track])
        if self.path == '/api/get?ids=truncated':
            track = self.track('truncated')
            track['media_urls'][0]['url'] += '-truncated'
            return self.respond(200, [track])
        if self.path == '/api/get?ids=encrypted':
            return self.respond(200, [self.track('encrypted')])
        if self.path == '/api/download?id=encrypted':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'opaque ciphertext without an audio header')
            return
        if self.path in ('/api/download?id=empty', '/api/download?id=truncated'):
            self.send_response(200)
            self.send_header('Content-Length', '100' if self.path.endswith('truncated') else '0')
            self.end_headers()
            if self.path.endswith('truncated'):
                self.wfile.write(b'partial')
            self.close_connection = True
            return
        if self.path.startswith('/api/download?id=track-'):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'\x00\x00\x00\x18ftypM4A fixture audio')
            return
        if self.path == '/api/get?ids=unauthorized':
            return self.respond(403, {'error': 'Session expired'})
        return self.respond(200, [])

    def track(self, track_id):
        return {'id': track_id, 'title': '../../Rain: song?', 'status': 'complete',
                'prompt': 'verse\nchorus', 'tags': 'folk',
                'audio_url': 'https://studio-api.prod.suno.com/api/forbidden',
                'media_urls': [{'url': f'http://127.0.0.1:{self.server.server_port}/audio',
                                'content_type': 'm4a-opus', 'delivery': 'progressive'}]}

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
            target = Path(json.loads(out)['downloaded'][0]['file'])
            self.assertEqual(target.read_bytes(), b'\x00\x00\x00\x18ftypM4A fixture audio')
            code, _, _ = self.call('download', 'track-1', '--output', folder)
            self.assertEqual(code, 1)
            self.assertEqual(target.read_bytes(), b'\x00\x00\x00\x18ftypM4A fixture audio')

    def test_multiple_song_links_preserve_metadata_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.call('download', 'https://suno.com/song/track-1?share=1',
                                    'track-1', 'track-2', '--metadata', '--output', folder)
            self.assertEqual(code, 0)
            downloaded = json.loads(out)['downloaded']
            self.assertEqual(len(downloaded), 2)
            for entry in downloaded:
                audio = Path(entry['file'])
                self.assertEqual(audio.parent, Path(folder))
                self.assertEqual(audio.read_bytes(), b'\x00\x00\x00\x18ftypM4A fixture audio')
                metadata = json.loads(Path(entry['metadata']).read_text())
                self.assertEqual(metadata['prompt'], 'verse\nchorus')
                self.assertIn(metadata['id'], audio.name)
                self.assertEqual(audio.suffix, '.m4a')

    def test_library_paginates_and_skip_existing_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.call('download', '--all', '--output', folder)
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(out)['downloaded']), 2)
            code, out, _ = self.call('download', '--all', '--skip-existing', '--output', folder)
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(out)['skipped']), 2)
            self.assertEqual(json.loads(out)['downloaded'], [])

    def test_empty_and_truncated_transfers_leave_no_files(self):
        for track_id in ('empty', 'truncated', 'encrypted'):
            with self.subTest(track_id=track_id), tempfile.TemporaryDirectory() as folder:
                code, out, _ = self.call('download', track_id, '--metadata', '--output', folder)
                self.assertEqual(code, 1)
                self.assertEqual(len(json.loads(out)['errors']), 1)
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_batch_keeps_successes_and_reports_missing_tracks(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.call('download', 'track-1', 'missing', '--output', folder)
            self.assertEqual(code, 1)
            summary = json.loads(out)
            self.assertEqual(len(summary['downloaded']), 1)
            self.assertEqual(summary['errors'][0]['id'], 'missing')

    def test_partial_existing_pair_and_empty_file_are_not_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            code, out, _ = self.call('download', 'track-1', '--output', folder)
            self.assertEqual(code, 0)
            audio = Path(json.loads(out)['downloaded'][0]['file'])
            code, _, _ = self.call('download', 'track-1', '--metadata', '--skip-existing', '--output', folder)
            self.assertEqual(code, 1)
            self.assertEqual(audio.read_bytes(), b'\x00\x00\x00\x18ftypM4A fixture audio')
            audio.write_bytes(b'')
            code, _, _ = self.call('download', 'track-1', '--skip-existing', '--output', folder)
            self.assertEqual(code, 1)
            self.assertEqual(audio.read_bytes(), b'')

    def test_invalid_selection_and_urls_fail_before_creating_files(self):
        selections = [[], ['--all', 'track-1'], ['track-1', '--jobs', '0'],
                      ['https://example.com/song/track-1'], ['../track-1'],
                      ['https://suno.com/playlist/track-1']]
        for selection in selections:
            with self.subTest(selection=selection), tempfile.TemporaryDirectory() as folder:
                code, out, _ = self.call('download', *selection, '--output', folder)
                self.assertEqual((code, out), (2, ''))
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_failed_track_not_downloaded(self):
        code, out, err = self.call('download', 'failed')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)['errors'][0]['id'], 'failed')
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
