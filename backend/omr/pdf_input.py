"""Rasterize one bounded PDF in an isolated, time-limited process."""
import json
import math
from contextlib import closing
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

MAX_PDF = 10 * 1024 * 1024
MAX_PAGES = 6


class PDFInputError(ValueError):
    pass


def render_pdf(raw):
    if not raw.startswith(b'%PDF-') or len(raw) > MAX_PDF:
        raise PDFInputError('请上传完整的 PDF，文件不超过 10 MB。')
    with TemporaryDirectory(prefix='shengban-pdf-') as temporary:
        folder = Path(temporary)
        source = folder / 'source.pdf'
        source.write_bytes(raw)
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(source), str(folder)],
                                    capture_output=True, timeout=30, check=False)
        except subprocess.TimeoutExpired as error:
            raise PDFInputError('PDF 转页超时，请尝试较短的 PDF 或改传图片。') from error
        try:
            info = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            raise PDFInputError('PDF 暂时无法转页，请换一份 PDF 或改传图片。')
        if result.returncode or 'error' in info:
            raise PDFInputError(info.get('error', 'PDF 无法读取，请检查文件是否完整或有密码。'))
        count = info.get('pages', 0)
        if not isinstance(count, int) or not 1 <= count <= MAX_PAGES:
            raise PDFInputError('一次只支持 1 至 6 页同一首歌的 PDF。')
        return [(folder / f'page-{index:02d}.png').read_bytes() for index in range(1, count + 1)]


def rasterize(source, folder):
    # Native PDF decoding cannot hold the API event loop or recognition worker forever.
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
    if sys.platform == 'linux':
        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
    import pypdfium2 as pdfium
    try:
        with closing(pdfium.PdfDocument(source)) as document:
            count = len(document)
            if not 1 <= count <= MAX_PAGES:
                raise PDFInputError('PDF 超过 6 页或没有页面，请先导出需要的 1 至 6 页。')
            # Check every page's dimensions before allocating any page bitmap.
            scales = []
            for index in range(count):
                width, height = document.get_page_size(index)
                if not all(math.isfinite(n) and 72 <= n <= 14400 for n in (width, height)):
                    raise PDFInputError('PDF 页面尺寸异常，请改传标准页面的 PDF。')
                scales.append(min(300 / 72, 2600 / width, 4000 / height,
                                  math.sqrt(10_000_000 / (width * height))))
            total = 0
            for index, scale in enumerate(scales):
                with closing(document[index]) as page:
                    bitmap = page.render(scale=scale)
                    try:
                        image = bitmap.to_pil().convert('RGB')
                        output = Path(folder) / f'page-{index + 1:02d}.png'
                        image.save(output, 'PNG')
                        image.close()
                    finally:
                        bitmap.close()
                size = output.stat().st_size
                total += size
                if size > MAX_PDF or total > 60 * 1024 * 1024:
                    raise PDFInputError('PDF 转页后的图片过大，请拆短 PDF 或改传压缩后的图片。')
            return {'pages': count}
    except PDFInputError:
        raise
    except Exception as error:
        raise PDFInputError('PDF 无法读取，可能已损坏或需要密码；请换一份无密码 PDF。') from error


if __name__ == '__main__':
    try:
        print(json.dumps(rasterize(sys.argv[1], sys.argv[2]), ensure_ascii=False))
    except Exception as error:
        message = str(error) if isinstance(error, PDFInputError) else 'PDF 转页暂未完成，请改传图片。'
        print(json.dumps({'error': message}, ensure_ascii=False))
        sys.exit(1)
