"""Public API, behind Caddy; single process with one bounded recognition worker."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path
import re

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .omr.errors import RecognitionTimeout
from .omr.jobs import Busy, JobStore
from .omr.musicxml import UnsupportedScore
from .omr.pipeline import recognize
from .public_limits import UploadLimiter, check_quota, owner_digest, require_owner
from .omr.uploads import MAX_IMAGE, MAX_REQUEST, UploadError, decode_upload

MAX_UPLOAD = MAX_IMAGE
LOG = logging.getLogger(__name__)


def create_app(storage=None, recognizer=recognize):
    root = Path(storage or os.environ.get('RECOGNITION_STORAGE', '/var/lib/shengban/jobs'))
    store, worker, limiter = JobStore(root), ThreadPoolExecutor(max_workers=1), UploadLimiter()
    upload_lock = asyncio.Lock()

    async def cleanup():
        while True:
            await asyncio.sleep(60)
            store.cleanup()

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(cleanup())
        yield
        task.cancel()
        worker.shutdown(wait=True)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(HTTPException)
    async def public_error(request, error):
        return JSONResponse({'message': error.detail}, status_code=error.status_code,
                            headers={'Cache-Control': 'no-store'})

    @app.middleware('http')
    async def private_responses(request, call_next):
        result = await call_next(request)
        result.headers['Cache-Control'] = 'no-store'
        result.headers['X-Content-Type-Options'] = 'nosniff'
        return result

    def process(key):
        folder = root / key
        try:
            data = store.snapshot(key)
            pages = data.get('pageCount', 1)
            source = folder / 'source' if pages == 1 else [folder / f'page-{i:02d}.source' for i in range(1, pages + 1)]
            args = {} if data.get('layout', 'vocal') == 'vocal' else {'layout': 'piano'}
            song = recognizer(source, folder, '上传乐谱',
                              lambda status, message: store.update(key, status=status, message=message), **args)
            store.update(key, status='completed', message='试听已生成，请检查效果', song=song,
                         scoreUrl=f'/api/recognition/{key}/score.musicxml')
        except UnsupportedScore as error:
            store.update(key, status='rejected', message=str(error))
        except RecognitionTimeout as error:
            store.update(key, status='failed', message=str(error))
        except Exception:
            LOG.exception('Recognition failed: %s', key)
            store.update(key, status='failed', message='识谱暂未完成，请换一张简单谱图重试。')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'mode': 'competition-demo'}

    @app.post('/api/recognition', status_code=202)
    async def submit(request: Request, x_recognition_token: str = Header(default='')):
        owner = owner_digest(x_recognition_token)
        # Same-origin frontend and API; CORS is intentionally not enabled.
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, '请从识谱页面提交。')
        content_type = request.headers.get('content-type', '')
        if content_type not in {'image/jpeg', 'image/png', 'application/pdf'} and not content_type.startswith('multipart/form-data;'):
            raise HTTPException(415, '仅支持 JPG、PNG 图片或 PDF。')
        limiter.check(request.client.host if request.client else 'unknown')
        if upload_lock.locked():
            raise HTTPException(429, '有人正在上传，请稍后重试。')
        async with upload_lock:
            raw = bytearray()
            async def read_body():
                async for chunk in request.stream():
                    raw.extend(chunk)
                    limit = MAX_REQUEST if content_type.startswith('multipart/form-data;') else MAX_UPLOAD
                    if len(raw) > limit:
                        raise HTTPException(413, '一次最多 6 页，每页不超过 10 MB。')
            try:
                await asyncio.wait_for(read_body(), timeout=90)
            except asyncio.TimeoutError:
                raise HTTPException(408, '上传超时，请重试。')
            if not raw:
                raise HTTPException(400, '图片为空，请重新选择。')
            try:
                images, layout = await run_in_threadpool(decode_upload, bytes(raw), content_type)
            except UploadError as error:
                raise HTTPException(error.status, str(error))
            with store.lock:
                store.cleanup()
                reusable = store.find_reusable(images, owner=owner, layout=layout)
                if reusable:
                    return {'id': reusable, 'reused': True}
                check_quota(store, owner, pages=len(images))
                try:
                    key, created = store.submit_pages(images, owner=owner, layout=layout)
                except Busy:
                    raise HTTPException(429, '识谱服务正在处理另一张谱图，请稍后重试。')
                if created:
                    try:
                        worker.submit(process, key)
                    except Exception:
                        store.update(key, status='failed', message='任务未能启动，请重试。')
                        raise HTTPException(503, '识谱服务暂时不可用。')
        return {'id': key, 'reused': not created}

    def authorized(key, token):
        if not re.fullmatch('[a-f0-9]{32}', key):
            raise HTTPException(404, '任务不存在。')
        store.cleanup()
        require_owner(store, key, owner_digest(token))
        return store.snapshot(key)

    @app.get('/api/recognition/{key}')
    def state(key: str, x_recognition_token: str = Header(default='')):
        return authorized(key, x_recognition_token)

    @app.get('/api/recognition/{key}/score.musicxml')
    def score(key: str, x_recognition_token: str = Header(default='')):
        data = authorized(key, x_recognition_token)
        if data['status'] != 'completed':
            raise HTTPException(409, '乐谱尚未生成。')
        return Response((root / key / 'score.musicxml').read_bytes(),
                        media_type='application/vnd.recordare.musicxml+xml')

    return app
