import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend.omr.errors import RecognitionTimeout
from backend.omr.jobs import Busy, JobStore, RETENTION_SECONDS
from backend.omr.pipeline import run_attempt


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = JobStore(self.root, 'test-version')

    def tearDown(self):
        self.temp.cleanup()

    def complete(self, key):
        (self.root / key / 'score.musicxml').write_text('<score-partwise/>')
        self.store.update(key, status='completed', message='done')

    def test_duplicate_pending_request_returns_original_task(self):
        key, created = self.store.submit(b'image')
        self.assertTrue(created)
        self.assertEqual(self.store.submit(b'image'), (key, False))
        with self.assertRaises(Busy):
            self.store.submit(b'different image')

    def test_completed_input_is_reused_without_recognition(self):
        key, _ = self.store.submit(b'image')
        self.complete(key)
        self.assertEqual(self.store.submit(b'image'), (key, False))
        restored = JobStore(self.root, 'test-version')
        self.assertEqual(restored.submit(b'image'), (key, False))

    def test_new_pipeline_version_does_not_reuse_stale_result(self):
        key, _ = self.store.submit(b'image')
        self.complete(key)
        updated = JobStore(self.root, 'new-version')
        fresh, created = updated.submit(b'image')
        self.assertTrue(created)
        self.assertNotEqual(fresh, key)

    def test_interrupted_job_is_failed_on_restart_and_slot_released(self):
        key, _ = self.store.submit(b'image')
        self.store.update(key, status='recognizing')
        restored = JobStore(self.root, 'test-version')
        self.assertEqual(restored.snapshot(key)['status'], 'failed')
        fresh, created = restored.submit(b'image')
        self.assertTrue(created)
        self.assertNotEqual(fresh, key)

    def test_rejected_input_can_be_retried(self):
        key, _ = self.store.submit(b'image')
        self.store.update(key, status='rejected', message='bad rhythm')
        fresh, created = self.store.submit(b'image')
        self.assertTrue(created)
        self.assertNotEqual(fresh, key)

    def test_expiration_clears_only_expired_registered_jobs(self):
        key, _ = self.store.submit(b'image')
        self.complete(key)
        unrelated = self.root / 'original.txt'
        unrelated.write_text('keep')
        self.store.update(key, createdAt=time.time() - RETENTION_SECONDS - 2)
        self.store.cleanup()
        self.assertIsNone(self.store.snapshot(key))
        self.assertFalse((self.root / key).exists())
        self.assertTrue(unrelated.exists())

    def test_active_job_not_removed_by_retention(self):
        key, _ = self.store.submit(b'image')
        self.store.update(key, createdAt=time.time() - RETENTION_SECONDS - 2)
        self.store.cleanup()
        self.assertEqual(self.store.snapshot(key)['status'], 'queued')

    def test_public_snapshot_does_not_expose_cache_key(self):
        key, _ = self.store.submit(b'image')
        snapshot = self.store.snapshot(key)
        self.assertNotIn('fingerprint', snapshot)
        snapshot['message'] = 'changed'
        self.assertNotEqual(self.store.snapshot(key)['message'], 'changed')

    def test_timeout_terminates_process_group_promptly(self):
        executable = self.root / 'slow-test-engine'
        executable.write_text('#!/bin/sh\nsleep 30 &\nwait\n')
        executable.chmod(0o700)
        started = time.monotonic()
        with patch('backend.omr.pipeline.ATTEMPT_TIMEOUT_SECONDS', .1), \
                patch('backend.omr.pipeline.os.killpg', wraps=os.killpg) as kill:
            with self.assertRaises(RecognitionTimeout):
                run_attempt(executable, self.root / 'unused.png', self.root, 'test', lambda *a: None)
            kill.assert_called_once()
        self.assertLess(time.monotonic() - started, 3)


if __name__ == '__main__':
    unittest.main()
