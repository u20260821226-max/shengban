"""Anonymous browser ownership and small competition-demo quotas."""
from hashlib import sha256
import re
import time

from fastapi import HTTPException


def owner_digest(token):
    if not re.fullmatch(r'[a-f0-9]{64}', token or ''):
        raise HTTPException(401, '浏览器身份失效，请刷新页面。')
    return sha256(token.encode()).hexdigest()


def require_owner(store, key, owner):
    with store.lock:
        data = store.jobs.get(key)
        if not data or data.get('owner') != owner:
            raise HTTPException(404, '任务不存在或已过期，请重新上传。')


def check_quota(store, owner, pages=1):
    # Persisted jobs keep quotas across process restarts; one worker/one process.
    now = time.time()
    recent = [d for d in store.jobs.values() if now - d['createdAt'] < 86400]
    if sum(d.get('pageCount', 1) for d in recent) + pages > 30:
        raise HTTPException(429, '今天的演示识谱额度已用完，请明天再试；预置曲目仍可播放。')
    if sum(d.get('owner') == owner for d in recent) >= 5:
        raise HTTPException(429, '本浏览器今天已提交 5 次，请明天再试。')


class UploadLimiter:
    def __init__(self):
        self.recent = {}

    def check(self, address):
        now = time.monotonic()
        self.recent = {key: [t for t in times if now - t < 3600]
                       for key, times in self.recent.items() if times and now - times[-1] < 3600}
        times = self.recent.setdefault(address, [])
        if len(times) >= 20 or len(self.recent) > 1000:
            raise HTTPException(429, '提交过于频繁，请稍后重试。')
        times.append(now)
