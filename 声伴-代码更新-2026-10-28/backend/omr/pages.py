"""Lossless, ordered multi-image book input; page processing stays sequential."""
from pathlib import Path

from PIL import Image

from .errors import UnsupportedScore

MAX_PAGES = 6


def write_book(images, target):
    """TIFF preserves pixels and page order; no JPEG re-encoding or manual XML join."""
    if not 1 <= len(images) <= MAX_PAGES:
        raise UnsupportedScore('请上传同一首歌的 1 至 6 页谱图。')
    frames = []
    try:
        for path in images:
            with Image.open(path) as image:
                frames.append(image.convert('L'))
        frames[0].save(target, format='TIFF', save_all=True, append_images=frames[1:],
                       compression='tiff_deflate')
    finally:
        for frame in frames:
            frame.close()
    return Path(target)


def page_for_measure(number, counts):
    total = 0
    for index, count in enumerate(counts, 1):
        total += count
        if number <= total:
            return index
    return len(counts)
