"""Page order, piano routing and cross-page musical continuity."""
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from fastapi.testclient import TestClient
from PIL import Image

from backend.omr.jobs import JobStore
from backend.omr.musicxml import UnsupportedScore, to_song
from backend.omr.pages import write_book
from backend.public_api import create_app
from test_recognition import score, note


class PageTests(unittest.TestCase):
    def test_two_staff_piano_plays_both_hands_without_melody(self):
        root = E.fromstring(score())
        root.remove(root.findall('part')[0])
        result = to_song(E.tostring(root), 'piano', layout='piano')
        self.assertEqual(result['layout'], 'piano')
        self.assertEqual(len(result['notes']), 2)
        self.assertEqual({n['role'] for n in result['notes']}, {'accompaniment'})
        with self.assertRaises(UnsupportedScore):
            to_song(E.tostring(root), 'wrong type')

    def test_cross_page_tie_remains_one_continuous_note(self):
        root = E.fromstring(score(melody=note(extra='<tie type="start"/>')))
        for index, part in enumerate(root.findall('part')):
            second = E.fromstring(score(melody=note(extra='<tie type="stop"/>'))).findall('part')[index][0]
            second.set('number', '2');second.remove(second.find('attributes'));part.append(second)
        song = to_song(E.tostring(root), 'two pages', page_measures=[1, 1])
        melody = [n for n in song['notes'] if n['role'] == 'melody']
        self.assertEqual(len(melody), 1)
        self.assertEqual(melody[0]['duration'], 4)
        self.assertEqual(song['measureTimes'], [0, 2])
        self.assertEqual(song['duration'], 4)

    def test_page_loss_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedScore, '跨页'):
            to_song(score(), 'lost page', page_measures=[1, 1])

    def test_six_pages_preserve_measure_order(self):
        root = E.fromstring(score())
        for index, part in enumerate(root.findall('part')):
            for page in range(1, 6):
                measure = E.fromstring(score()).findall('part')[index][0]
                measure.set('number', str(page + 1));measure.remove(measure.find('attributes'));part.append(measure)
        song = to_song(E.tostring(root), 'six pages', page_measures=[1] * 6)
        self.assertEqual(song['measures'], 6)
        self.assertEqual(song['duration'], 12)
        self.assertEqual(song['measureTimes'], [0, 2, 4, 6, 8, 10])

    def test_tiff_is_lossless_and_keeps_six_distinct_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); paths = []
            for i in range(6):
                path = root / f'{i}.png';Image.new('L', (400, 500), i * 30).save(path);paths.append(path)
            output = write_book(paths, root / 'book.tif')
            with Image.open(output) as book:
                self.assertEqual(book.n_frames, 6)
                for i in range(6):
                    book.seek(i);self.assertEqual(book.getpixel((100, 100)), i * 30)

    def test_order_and_layout_are_part_of_reuse_key(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JobStore(Path(folder), 'pages')
            first, _ = store.submit_pages([b'a', b'b']);store.update(first, status='rejected')
            second, _ = store.submit_pages([b'b', b'a']);store.update(second, status='rejected')
            third, _ = store.submit_pages([b'a', b'b'], layout='piano')
            self.assertEqual(len({first, second, third}), 3)
            self.assertEqual((Path(folder) / first / 'page-01.source').read_bytes(), b'a')

    def test_public_six_images_reach_worker_in_display_order(self):
        seen = []
        def recognize(sources, folder, title, progress, layout='vocal'):
            seen.extend(p.read_bytes() for p in sources)
            self.assertEqual(layout, 'piano')
            (folder / 'score.musicxml').write_text('<score-partwise/>')
            return {'layout': layout, 'notes': []}
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder), recognize)
            with TestClient(app) as client:
                files = [('images', (f'{i}.png', bytes([i]), 'image/png')) for i in [6, 5, 4, 3, 2, 1]]
                response = client.post('/api/recognition', files=files, data={'layout': 'piano'}, headers={'X-Recognition-Token': 'd' * 64})
                self.assertEqual(response.status_code, 202)
            self.assertEqual(seen, [bytes([i]) for i in [6, 5, 4, 3, 2, 1]])

    def test_seventh_page_and_invalid_layout_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with TestClient(create_app(Path(folder))) as client:
                headers = {'X-Recognition-Token': 'd' * 64}
                files = [('images', ('a.png', b'a', 'image/png'))] * 7
                self.assertIn(client.post('/api/recognition', files=files, headers=headers).status_code, [400, 413])
                self.assertEqual(client.post('/api/recognition', files=files[:1], data={'layout': 'guitar'}, headers=headers).status_code, 400)
