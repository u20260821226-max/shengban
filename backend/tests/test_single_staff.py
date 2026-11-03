"""Single-staff input, explicit flat pitches and public worker routing."""
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from fastapi.testclient import TestClient

from backend.omr.jobs import JobStore
from backend.omr.musicxml import UnsupportedScore, to_song
from backend.public_api import create_app
from test_recognition import score


def single_score(fifths=-4):
    root = E.fromstring(score())
    root.remove(root.findall('part')[1])
    part = root.find('part')
    key = E.SubElement(part.find('measure/attributes'), 'key')
    E.SubElement(key, 'fifths').text = str(fifths)
    measure = part.find('measure')
    measure.remove(measure.find('note'))
    # MusicXML pitches already include the key signature; do not apply it twice.
    for step in ('B', 'E', 'A', 'D'):
        alter = -1 if step != 'D' or fifths == -4 else 0
        measure.append(E.fromstring(f'<note><pitch><step>{step}</step><alter>{alter}</alter>'
                                   '<octave>4</octave></pitch><duration>1</duration>'
                                   '<voice>1</voice><type>quarter</type></note>'))
    return E.tostring(root)


class SingleStaffTests(unittest.TestCase):
    def test_three_and_four_flats_preserve_actual_pitches(self):
        for fifths, pitches in [(-3, [70, 63, 68, 62]), (-4, [70, 63, 68, 61])]:
            with self.subTest(fifths=fifths):
                song = to_song(single_score(fifths), '单行谱', layout='single')
                self.assertEqual([n['midi'] for n in song['notes']], pitches)
                self.assertEqual({n['role'] for n in song['notes']}, {'accompaniment'})
                self.assertEqual(song['layout'], 'single')
                self.assertEqual(song['duration'], 2)
                self.assertEqual(len(song['rhythmChecks']), 1)

    def test_explicit_natural_is_not_flattened_again(self):
        root = E.fromstring(single_score())
        root.find('.//note/pitch/alter').text = '0'
        song = to_song(E.tostring(root), '还原音', layout='single')
        self.assertEqual(song['notes'][0]['midi'], 71)

    def test_out_of_range_keys_rejected(self):
        for fifths in (-5, 4):
            with self.subTest(fifths=fifths), self.assertRaisesRegex(UnsupportedScore, '四个降号'):
                to_song(single_score(fifths), '超范围', layout='single')

    def test_other_layouts_still_reject_single_staff(self):
        for layout in ('piano', 'vocal'):
            with self.subTest(layout=layout), self.assertRaises(UnsupportedScore):
                to_song(single_score(), '错误谱型', layout=layout)
        with self.assertRaisesRegex(UnsupportedScore, '单行钢琴'):
            to_song(score(), '错误谱型', layout='single')

    def test_overfull_bar_is_still_rejected(self):
        root = E.fromstring(single_score())
        root.find('.//note/duration').text = '2'
        with self.assertRaisesRegex(UnsupportedScore, '超出'):
            to_song(E.tostring(root), '超拍', layout='single')

    def test_cross_page_tie_preserves_flat_pitch_and_duration(self):
        root = E.fromstring(single_score())
        part = root.find('part')
        for index in range(2):
            measure = part[0] if index == 0 else E.SubElement(part, 'measure', number='2')
            for node in list(measure.findall('note')):
                measure.remove(node)
            measure.append(E.fromstring('<note><pitch><step>D</step><alter>-1</alter>'
                                       '<octave>4</octave></pitch><duration>4</duration>'
                                       f'<tie type="{"start" if index == 0 else "stop"}"/></note>'))
        song = to_song(E.tostring(root), '跨页', page_measures=[1, 1], layout='single')
        self.assertEqual([(n['midi'], n['duration']) for n in song['notes']], [(61, 4)])

    def test_single_staff_tasks_do_not_reuse_other_layouts(self):
        with tempfile.TemporaryDirectory() as folder:
            store = JobStore(Path(folder))
            for layout in ('vocal', 'piano'):
                key, _ = store.submit_pages([b'same'], layout=layout)
                store.update(key, status='completed')
            self.assertIsNone(store.find_reusable([b'same'], layout='single'))

    def test_public_upload_keeps_single_layout_through_worker(self):
        seen = []
        def recognize(source, folder, title, progress, layout='vocal'):
            seen.append(layout)
            song = to_song(single_score(), title, layout=layout)
            (folder / 'score.musicxml').write_bytes(single_score())
            return song
        with tempfile.TemporaryDirectory() as folder:
            app = create_app(Path(folder), recognize)
            with TestClient(app) as client:
                response = client.post('/api/recognition', data={'layout': 'single'},
                                       files={'images': ('single.png', b'image', 'image/png')},
                                       headers={'X-Recognition-Token': 'e' * 64})
                self.assertEqual(response.status_code, 202)
                key = response.json()['id']
            self.assertEqual(seen, ['single'])
            result = app.state.store.snapshot(key)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['song']['layout'], 'single')
