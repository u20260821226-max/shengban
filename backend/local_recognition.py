"""Loopback-only upload playground. Not a production/public upload server.

Run from project root: python3 -m backend.local_recognition
One Audiveris process at a time; private inputs stay outside static routes.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import time
from urllib.parse import unquote, urlsplit

from .omr.musicxml import UnsupportedScore
from .omr.pipeline import recognize
from .omr.errors import RecognitionTimeout
from .omr.jobs import Busy, JobStore
from .omr.uploads import MAX_REQUEST, UploadError, decode_upload

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / 'work' / 'recognition-jobs'
STORE = JobStore(STORAGE)
WORKER = ThreadPoolExecutor(max_workers=1)
MAX_UPLOAD = MAX_REQUEST
JOB_PATH = re.compile(r'/api/recognition/([a-f0-9]{32})(/score.musicxml)?$')
STATIC = {'/labs/recognition.html', '/labs/recognition.css', '/labs/recognition.js',
          '/labs/recognition.task.js',
          '/labs/recognition.pages.js',
          '/music-player.js', '/score-view.js', '/icon.svg', '/styles.css',
          '/vendor/opensheetmusicdisplay.min.js'}


def process(job_id, folder):
    try:
        data = STORE.snapshot(job_id)
        count = data.get('pageCount', 1)
        source = folder / 'source' if count == 1 else [folder / f'page-{i:02d}.source' for i in range(1, count + 1)]
        song = recognize(source, folder, '上传乐谱',
                         lambda status, message: STORE.update(job_id, status=status, message=message), layout=data.get('layout', 'vocal'))
        STORE.update(job_id, status='completed', message='试听已生成，请检查效果', song=song,
               scoreUrl=f'/api/recognition/{job_id}/score.musicxml')
    except UnsupportedScore as exc:
        STORE.update(job_id, status='rejected', message=str(exc))
    except RecognitionTimeout as exc:
        STORE.update(job_id, status='failed', message=str(exc))
    except Exception:
        # Keep technical details local; no process paths or stack traces in the UI.
        import traceback
        (folder / 'error.log').write_text(traceback.format_exc())
        STORE.update(job_id, status='failed', message='处理未完成，请重试；若重复失败，请保留本机日志。')


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def valid_host(self):
        return self.headers.get('Host') in {'localhost:4175', '127.0.0.1:4175'}

    def reply(self, status, data):
        raw = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_HEAD(self):
        self.send_error(405)

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {'message': '仅支持本机访问'})
        path = unquote(urlsplit(self.path).path)
        match = JOB_PATH.fullmatch(path)
        if match:
            result = STORE.snapshot(match[1])
            if not result:
                return self.reply(404, {'message': '任务不存在或已过期，请重新上传'})
            if match[2]:
                if result['status'] != 'completed':
                    return self.reply(409, {'message': '乐谱尚未生成'})
                data = (STORAGE / match[1] / 'score.musicxml').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.recordare.musicxml+xml')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(data)
                return
            return self.reply(200, result)
        if path == '/':
            self.send_response(302)
            self.send_header('Location', '/labs/recognition.html')
            self.end_headers()
            return
        if path not in STATIC and not re.fullmatch(r'/assets/piano/(?:A[0-7]|C[1-8]|Ds[1-7]|Fs[1-7])\.mp3', path):
            return self.reply(404, {'message': '文件不可访问'})
        self.path = path
        super().do_GET()

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') not in {
                'http://localhost:4175', 'http://127.0.0.1:4175'}:
            return self.reply(403, {'message': '请从本机测试页面提交'})
        if self.path != '/api/recognition':
            return self.reply(404, {'message': '接口不存在'})
        content_type = self.headers.get('Content-Type', '')
        if content_type not in {'image/jpeg', 'image/png'} and not content_type.startswith('multipart/form-data;'):
            return self.reply(415, {'message': '仅支持 JPG、PNG 图片'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_UPLOAD:
            return self.reply(413, {'message': '请选择不超过 10 MB 的谱图'})
        job_id = None
        try:
            self.connection.settimeout(90)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('incomplete body')
            images, layout = decode_upload(raw, content_type)
            job_id, created = STORE.submit_pages(images, layout=layout)
            if created:
                WORKER.submit(process, job_id, STORAGE / job_id)
        except Busy as exc:
            return self.reply(429, {'message': str(exc)})
        except UploadError as exc:
            return self.reply(exc.status, {'message': str(exc)})
        except Exception:
            if job_id and STORE.snapshot(job_id):
                STORE.update(job_id, status='failed', message='识谱任务未能启动，请重新上传。')
            return self.reply(400, {'message': '文件没有上传完整，请重试'})
        self.reply(202, {'id': job_id, 'reused': not created})


class LocalServer(ThreadingHTTPServer):
    last_cleanup = 0

    def service_actions(self):
        if time.monotonic() - self.last_cleanup > 60:
            STORE.cleanup()
            self.last_cleanup = time.monotonic()


if __name__ == '__main__':
    STORAGE.mkdir(parents=True, exist_ok=True)
    server = LocalServer(('127.0.0.1', 4175), Handler)
    print('声伴本机识谱测试：http://localhost:4175/ （仅本机可访问）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        WORKER.shutdown(wait=True)
