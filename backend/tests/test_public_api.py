"""Public boundary tests: ownership, recovery, upload bounds and quota persistence."""
from pathlib import Path
import tempfile
import threading
import time
import unittest

from fastapi.testclient import TestClient

from backend.public_api import create_app, MAX_UPLOAD
from backend.public_limits import owner_digest

A = {'X-Recognition-Token': 'a' * 64, 'Content-Type': 'image/png'}
B = {'X-Recognition-Token': 'b' * 64, 'Content-Type': 'image/png'}


def fake_recognizer(source, folder, title, progress):
    (folder / 'score.musicxml').write_text('<score-partwise/>')
    return {'title': title, 'notes': []}


class PublicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = create_app(self.root, fake_recognizer)
        self.client = TestClient(self.app).__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def submit(self, raw=b'image', headers=A):
        return self.client.post('/api/recognition', headers=headers, content=raw)

    def wait(self, key):
        for _ in range(100):
            data = self.client.get('/api/recognition/' + key, headers=A).json()
            if data['status'] == 'completed':
                return data
            time.sleep(.01)
        self.fail('worker did not complete')

    def test_missing_token_and_cross_origin_rejected(self):
        self.assertEqual(self.submit(headers={'Content-Type': 'image/png'}).status_code, 401)
        self.assertEqual(self.submit(headers={**A, 'Origin': 'https://other.example'}).status_code, 403)

    def test_owner_only_can_read_status_and_score(self):
        key = self.submit().json()['id']
        result = self.wait(key)
        self.assertNotIn('owner', result)
        self.assertNotIn('fingerprint', result)
        for suffix in ['', '/score.musicxml']:
            self.assertEqual(self.client.get('/api/recognition/' + key + suffix, headers=B).status_code, 404)
            response = self.client.get('/api/recognition/' + key + suffix, headers=A)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_completed_reused_only_by_same_browser(self):
        key = self.submit().json()['id']
        self.wait(key)
        self.assertEqual(self.submit().json(), {'id': key, 'reused': True})
        self.assertNotEqual(self.submit(headers=B).json()['id'], key)

    def test_recovery_preserves_owner_and_quota(self):
        key = self.submit().json()['id']
        self.wait(key)
        with TestClient(create_app(self.root, fake_recognizer)) as recovered:
            self.assertEqual(recovered.get('/api/recognition/' + key, headers=A).status_code, 200)
            self.assertEqual(recovered.get('/api/recognition/' + key, headers=B).status_code, 404)
            self.assertEqual(recovered.post('/api/recognition', headers=A, content=b'image').json()['id'], key)

    def test_large_empty_and_wrong_type_upload_rejected(self):
        self.assertEqual(self.submit(b'').status_code, 400)
        self.assertEqual(self.submit(b'x' * (MAX_UPLOAD + 1)).status_code, 413)
        self.assertEqual(self.submit(headers={**A, 'Content-Type': 'text/plain'}).status_code, 415)

    def test_browser_quota(self):
        for i in range(5):
            key = self.submit(str(i).encode()).json()['id']
            self.wait(key)
        self.assertEqual(self.submit(b'sixth').status_code, 429)

    def test_no_unbounded_recognition_queue(self):
        gate = threading.Event()
        def blocked(*args):
            gate.wait(3)
            return fake_recognizer(*args)
        with TestClient(create_app(self.root / 'busy', blocked)) as client:
            try:
                first = client.post('/api/recognition', headers=A, content=b'first')
                self.assertEqual(first.status_code, 202)
                self.assertEqual(client.post('/api/recognition', headers=A, content=b'first').json()['id'], first.json()['id'])
                self.assertEqual(client.post('/api/recognition', headers=B, content=b'second').status_code, 429)
            finally:
                gate.set()

    def test_total_quota(self):
        store = self.app.state.store
        for i in range(30):
            key, _ = store.submit(str(i).encode(), owner=owner_digest('c' * 64))
            store.update(key, status='rejected')
        self.assertEqual(self.submit().status_code, 429)
