"""Small persistent local job registry; one worker, bounded input retention."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from threading import RLock
import time
from uuid import uuid4

TERMINAL = {'completed', 'failed', 'rejected'}
RETENTION_SECONDS = 24 * 60 * 60


def pipeline_version():
    folder = Path(__file__).parent
    return sha256(b''.join((folder / name).read_bytes() for name in
                           ['pipeline.py', 'musicxml.py', 'rhythm.py', 'errors.py', 'pages.py', 'images.py'])).hexdigest()


class Busy(RuntimeError):
    pass


class JobStore:
    def __init__(self, root, version=None):
        self.root, self.version = root, version or pipeline_version()
        self.lock, self.jobs, self.active = RLock(), {}, None
        root.mkdir(parents=True, exist_ok=True)
        for folder in root.iterdir():
            if folder.is_symlink() or not re.fullmatch('[a-f0-9]{32}', folder.name):
                continue
            try:
                data = json.loads((folder / 'state.json').read_text())
                if data.get('id') != folder.name:
                    continue
                self.jobs[folder.name] = data
                if data['status'] not in TERMINAL:
                    self.update(folder.name, status='failed', message='识谱服务曾中断，请重新上传重试。')
            except (OSError, ValueError, KeyError):
                continue
        self.cleanup()

    def persist(self, data):
        folder = self.root / data['id']
        temporary = folder / 'state.tmp'
        temporary.write_text(json.dumps(data, ensure_ascii=False))
        temporary.replace(folder / 'state.json')

    def cleanup(self):
        with self.lock:
            now = time.time()
            for key, data in list(self.jobs.items()):
                if key != self.active and now - data['createdAt'] > RETENTION_SECONDS:
                    shutil.rmtree(self.root / key)
                    del self.jobs[key]

    def submit(self, raw, owner=None):
        return self.submit_pages([raw], owner)

    def fingerprint(self, pages, owner, layout):
        fingerprint = sha256(self.version.encode() + (owner or '').encode())
        if layout != 'vocal':
            fingerprint.update(layout.encode())
        if len(pages) > 1:
            fingerprint.update(b'ordered-pages-v1')
        for raw in pages:
            if len(pages) > 1:
                fingerprint.update(len(raw).to_bytes(8, 'big'))
            fingerprint.update(raw)
        return fingerprint.hexdigest()

    def find_reusable(self, pages, owner=None, layout='vocal'):
        with self.lock:
            digest = self.fingerprint(pages, owner, layout)
            for data in self.jobs.values():
                if data['fingerprint'] == digest and (data['status'] not in TERMINAL or
                        (data['status'] == 'completed' and (self.root / data['id'] / 'score.musicxml').is_file())):
                    return data['id']
        return None

    def submit_pages(self, pages, owner=None, layout='vocal'):
        with self.lock:
            self.cleanup()
            if not 1 <= len(pages) <= 6:
                raise ValueError('invalid page count')
            reusable = self.find_reusable(pages, owner, layout)
            if reusable:
                return reusable, False
            digest = self.fingerprint(pages, owner, layout)
            if self.active:
                raise Busy('本机正在处理另一张谱图，请稍后重试；同一张图再次提交会继续原任务。')
            key = uuid4().hex
            folder = self.root / key
            folder.mkdir()
            for index, raw in enumerate(pages, 1):
                name = 'source' if len(pages) == 1 else f'page-{index:02d}.source'
                (folder / name).write_bytes(raw)
            data = {'id': key, 'status': 'queued', 'message': '正在等待识谱',
                    'fingerprint': digest, 'createdAt': time.time(), 'pageCount': len(pages), 'layout': layout}
            if owner:
                data['owner'] = owner
            self.persist(data)
            self.jobs[key], self.active = data, key
            return key, True

    def update(self, key, **fields):
        with self.lock:
            data = self.jobs[key]
            data.update(fields)
            if data['status'] in TERMINAL:
                data['finishedAt'] = time.time()
                if self.active == key:
                    self.active = None
            self.persist(data)

    def snapshot(self, key):
        with self.lock:
            self.cleanup()
            data = deepcopy(self.jobs.get(key))
            if data is not None:
                data.pop('fingerprint', None)
                data.pop('owner', None)
                data['elapsedSeconds'] = max(0, round(data.get('finishedAt', time.time()) - data['createdAt']))
            return data
