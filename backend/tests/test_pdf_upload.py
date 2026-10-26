"""PDF input acceptance: real rasterization, page bounds, order and HTTP routing."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from backend.omr.pdf_input import PDFInputError, render_pdf
from backend.omr.uploads import UploadError, decode_upload
from backend.public_api import create_app


def pdf_bytes(colors=('white',)):
    images = [Image.new('RGB', (400, 600), color) for color in colors]
    output = BytesIO()
    images[0].save(output, 'PDF', save_all=True, append_images=images[1:], resolution=72)
    for image in images:
        image.close()
    return output.getvalue()


class PDFTests(unittest.TestCase):
    def test_real_pdf_renders_in_original_page_order(self):
        pages = render_pdf(pdf_bytes(('red', 'blue')))
        self.assertEqual(len(pages), 2)
        for raw, color in zip(pages, (0, 2)):
            with Image.open(BytesIO(raw)) as image:
                self.assertEqual(image.format, 'PNG')
                self.assertLessEqual(image.width * image.height, 10_000_000)
                self.assertGreater(image.getpixel((20, 20))[color], 240)

    def test_six_page_pdf_is_accepted_without_dropping_last_page(self):
        self.assertEqual(len(render_pdf(pdf_bytes(('white',) * 6))), 6)

    def test_seven_page_pdf_rejected_before_any_rendering(self):
        with self.assertRaisesRegex(PDFInputError, '6 页'):
            render_pdf(pdf_bytes(('white',) * 7))

    def test_corrupt_pdf_returns_human_readable_error(self):
        with self.assertRaisesRegex(PDFInputError, 'PDF'):
            render_pdf(b'%PDF-1.4\nbroken')

    def test_conversion_has_a_timeout(self):
        import subprocess
        with patch('backend.omr.pdf_input.subprocess.run', side_effect=subprocess.TimeoutExpired('pdf', 30)):
            with self.assertRaisesRegex(PDFInputError, '超时'):
                render_pdf(b'%PDF-1.4\n')

    def test_raw_pdf_adapter_uses_same_conversion(self):
        pages, layout = decode_upload(pdf_bytes(), 'application/pdf')
        self.assertEqual(len(pages), 1)
        self.assertEqual(layout, 'vocal')

    def test_pdf_http_preserves_selected_layout_and_page_count(self):
        seen = []
        def recognize(sources, folder, title, progress, layout='vocal'):
            seen.extend(sources)
            self.assertEqual(layout, 'piano')
            for source in sources:
                with Image.open(source) as image:
                    self.assertEqual(image.format, 'PNG')
            (folder / 'score.musicxml').write_text('<score-partwise/>')
            return {'notes': [], 'layout': layout}
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(Path(folder), recognize)) as client:
                response = client.post('/api/recognition', data={'layout': 'piano'},
                                       files={'images': ('score.pdf', pdf_bytes(('red', 'blue')), 'application/pdf')},
                                       headers={'X-Recognition-Token': 'f' * 64})
                self.assertEqual(response.status_code, 202)
            self.assertEqual(len(seen), 2)

    def test_pdf_cannot_be_mixed_with_images_or_other_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(Path(folder))) as client:
                headers = {'X-Recognition-Token': 'f' * 64}
                pdf = ('images', ('score.pdf', pdf_bytes(), 'application/pdf'))
                image = ('images', ('page.png', b'png', 'image/png'))
                self.assertEqual(client.post('/api/recognition', files=[pdf, image], headers=headers).status_code, 400)
                self.assertEqual(client.post('/api/recognition', files=[pdf, pdf], headers=headers).status_code, 415)

    def test_failed_conversion_does_not_create_job_or_consume_quota(self):
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder))
            with TestClient(app) as client:
                response = client.post('/api/recognition', data={'layout': 'vocal'},
                                       files={'images': ('bad.pdf', b'%PDF-1.4 broken', 'application/pdf')},
                                       headers={'X-Recognition-Token': 'f' * 64})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(app.state.store.jobs, {})


if __name__ == '__main__':
    unittest.main()
