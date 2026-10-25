"""Audiveris adapter for one-page local tests; no MuseScore process required."""
import json
import os
from pathlib import Path
import signal
import subprocess
import re
import time
from zipfile import ZipFile

from PIL import Image, ImageOps, UnidentifiedImageError

from .musicxml import UnsupportedScore, parse_xml, read_mxl, to_song
from .errors import RecognitionTimeout, RecognitionUncertain
from .pages import MAX_PAGES, page_for_measure, write_book

DEFAULT_BIN = '/Applications/Audiveris.app/Contents/MacOS/Audiveris'
ATTEMPT_TIMEOUT_SECONDS = 150


def prepare_image(source, target, retry=False):
    try:
        with Image.open(source) as image:
            if image.format not in {'JPEG', 'PNG'} or getattr(image, 'n_frames', 1) != 1:
                raise UnsupportedScore('请上传单张 JPG 或 PNG 图片。')
            if image.width * image.height > 20_000_000:
                raise UnsupportedScore('图片过大，请截取一页或较短片段。')
            if min(image.size) < 400:
                raise UnsupportedScore('图片尺寸过小，请上传原图。')
            image = ImageOps.exif_transpose(image)
            # Alpha must composite onto paper, not become black upon conversion.
            if 'A' in image.getbands() or image.mode == 'P':
                rgba = image.convert('RGBA')
                paper = Image.new('RGBA', image.size, 'white')
                image = Image.alpha_composite(paper, rgba).convert('RGB')
            gray = ImageOps.grayscale(image)
            factor = (3 if gray.width < 1600 else 1.5) if retry else (2 if gray.width < 1600 else 1)
            scale = min(factor, (25_000_000 / (gray.width * gray.height)) ** .5)
            if scale != 1:
                gray = gray.resize((round(gray.width * scale), round(gray.height * scale)), Image.Resampling.LANCZOS)
            gray.save(target, 'PNG')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise UnsupportedScore('图片无法读取，请重新上传完整的 JPG 或 PNG。') from exc


def run_attempt(executable, normalized, folder, title, progress, retry=False, page_count=1, layout='vocal'):
    destination = folder / ('audiveris-retry' if retry else 'audiveris')
    destination.mkdir()
    stage = '自动重试（第 2 次，最多 2 次）' if retry else '识别音符、节奏与声部'
    progress('recognizing', f'正在{stage}，第 1 / {page_count} 页，请稍候')
    log_path = folder / ('recognition-retry.log' if retry else 'recognition.log')
    with log_path.open('w') as log:
        options = ['-swap', '-constant', 'org.audiveris.omr.sheet.Book.processAllStubsInParallel=false'] if page_count > 1 else []
        process = subprocess.Popen([str(executable), '-batch', '-transcribe', '-export',
                                    '-save', *options, '-output', str(destination), '--', str(normalized)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + ATTEMPT_TIMEOUT_SECONDS * page_count
        current_page = 1
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(process.args, ATTEMPT_TIMEOUT_SECONDS * page_count)
                try:
                    returncode = process.wait(timeout=min(1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    if page_count > 1:
                        text = log_path.read_text(errors='replace')
                        seen = [int(n) for n in re.findall(r'(?:sheet#|\[normalized(?:-retry)?#)(\d+)', text)]
                        page = min(page_count, max(seen or [1]))
                        if page > current_page:
                            current_page = page
                            progress('recognizing', f'正在{stage}，第 {page} / {page_count} 页，请稍候')
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise RecognitionTimeout(f'本次识谱超过 {ATTEMPT_TIMEOUT_SECONDS * page_count:g} 秒，任务已停止；请尝试更短的谱面片段。') from exc
    exports = list(destination.glob('*.mxl'))
    if returncode or len(exports) != 1:
        message = log_path.read_text(errors='replace')
        if 'too low interline' in message:
            raise RecognitionUncertain('未能可靠检测谱线间距，请上传更高分辨率原图或较短片段。')
        if 'No system found' in message or 'Error in reaching step' in message:
            seen = re.findall(r'\[normalized(?:-retry)?#(\d+)\]', message)
            page = min(page_count, int(seen[-1])) if seen else 1
            raise RecognitionUncertain(f'第 {page} 页未能完整检测谱表，请更换清晰原图。')
        raise UnsupportedScore('未能将全部页面识别为同一首曲目，请检查页序、清晰度及三行声部是否一致。' if page_count > 1 else '暂未能完成这张谱图的识别，请换一张清晰、简单的三行声乐谱。')
    progress('checking', '正在检查声部、小节与跨页延音线')
    books = list(destination.glob('*.omr'))
    if len(books) != 1:
        raise UnsupportedScore('缺少谱表结构信息，暂不能自动接受结果。')
    counts = []
    with ZipFile(books[0]) as book:
        for page in range(1, page_count + 1):
            name = f'sheet#{page}/sheet#{page}.xml'
            if name not in book.namelist():
                raise RecognitionUncertain(f'第 {page} 页未能完成识别，不会跳过该页。')
            sheet = parse_xml(book.read(name))
            systems = sheet.findall('page/system')
            staff_count = 2 if layout == 'piano' else 3
            if not systems or any(len(s.findall('part/staff')) != staff_count for s in systems):
                raise RecognitionUncertain(f'第 {page} 页未识出完整的 {staff_count} 行谱表，请检查谱型或更换该页图片。')
            count = len(sheet.findall('page/system/stack'))
            if not 1 <= count <= 16:
                raise UnsupportedScore(f'第 {page} 页超出每页最多 16 小节的试用范围。')
            counts.append(count)
    xml = read_mxl(exports[0])
    try:
        song = to_song(xml, title, page_measures=counts if page_count > 1 else None, layout=layout)
    except UnsupportedScore as error:
        match = re.search(r'第 (\d+) 小节', str(error))
        if page_count > 1 and match:
            raise type(error)(f'第 {page_for_measure(int(match[1]), counts)} 页：{error}') from error
        raise
    song['pageMeasures'] = counts
    return xml, song


def recognize(source, folder, title, progress=lambda status, message: None, layout='vocal'):
    sources = list(source) if isinstance(source, (list, tuple)) else [source]
    if not 1 <= len(sources) <= MAX_PAGES:
        raise UnsupportedScore('一次最多上传 6 页同一首歌的谱图。')
    executable = Path(os.environ.get('AUDIVERIS_BIN', DEFAULT_BIN))
    if not executable.is_file():
        raise RuntimeError('本机未找到 Audiveris，尚不能执行识谱。')
    progress('preparing', '正在检查图片并调整识谱输入')
    def prepare(retry=False):
        images = []
        for index, path in enumerate(sources, 1):
            target = folder / (f'page-{index:02d}' + ('-retry' if retry else '') + '.png')
            progress('preparing', f'正在检查第 {index} / {len(sources)} 页并调整图片')
            try:
                prepare_image(path, target, retry=retry)
            except UnsupportedScore as error:
                raise type(error)(f'第 {index} 页：{error}') from error
            images.append(target)
        if len(images) == 1:
            return images[0], images
        return write_book(images, folder / ('normalized-retry.tif' if retry else 'normalized.tif')), images
    normalized, first_images = prepare()
    attempts = 1
    try:
        xml, song = run_attempt(executable, normalized, folder, title, progress, page_count=len(sources), layout=layout)
    except RecognitionUncertain as initial:
        progress('preparing', '首次结果存在结构或节拍疑点，正在调整图片尺度并自动重试一次')
        retry_image, retry_images = prepare(retry=True)
        sizes = []
        for a, b in zip(first_images, retry_images):
            with Image.open(a) as first, Image.open(b) as second:
                sizes.append(first.size == second.size)
        if all(sizes):
            raise initial
        attempts = 2
        xml, song = run_attempt(executable, retry_image, folder, title, progress, retry=True, page_count=len(sources), layout=layout)
    song['processing'] = {'attempts': attempts, 'pages': len(sources)}
    (folder / 'score.musicxml').write_bytes(xml)
    (folder / 'song.json').write_text(json.dumps(song, ensure_ascii=False))
    return song
