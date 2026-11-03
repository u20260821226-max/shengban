"""Partial results must be a validated prefix with explicit coverage and ownership."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from fastapi.testclient import TestClient
from PIL import Image

from backend.omr.errors import RecognitionUncertain, RecognitionTimeout, UnsupportedScore
from backend.omr.jobs import JobStore, RETENTION_SECONDS
from backend.omr.musicxml import to_song
from backend.omr.partial import checked_prefix, partial_coverage
from backend.omr.pipeline import recognize
from backend.public_api import create_app
from test_recognition import score, note


def pages_xml(count, ties=None):
    root = E.fromstring(score())
    for part in root.findall('part'):
        for index in range(1, count):
            measure = E.fromstring(E.tostring(part[0]))
            measure.set('number', str(index + 1))
            measure.remove(measure.find('attributes'))
            part.append(measure)
    if ties:
        for index, kind in ties.items():
            E.SubElement(root.find('part').findall('measure')[index - 1].find('note'), 'tie', type=kind)
    return E.tostring(root)


def write_candidate(folder, count, xml=None):
    xml = xml or pages_xml(count)
    song = to_song(xml, 'test', page_measures=[1] * count)
    song.update(pageMeasures=[1] * count, processing={'attempts': 1, 'pages': count, 'croppedPages': []})
    (folder / 'score.musicxml').write_bytes(xml)
    return song


class PrefixTests(unittest.TestCase):
    def test_preparation_failure_on_later_image_still_keeps_valid_prefix(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);folder = root / 'job';folder.mkdir()
            first, second = root / 'one.png', root / 'two.png'
            Image.new('RGB', (600, 800), 'white').save(first)
            second.write_bytes(b'broken image')
            binary = root / 'engine';binary.touch()
            xml = pages_xml(1)
            song = to_song(xml, 'test');song['pageMeasures'] = [1]
            with patch.dict('os.environ', {'AUDIVERIS_BIN': str(binary)}), \
                    patch('backend.omr.pipeline.run_attempt', return_value=(xml, song)) as engine:
                result = recognize([first, second], folder, 'test')
            self.assertEqual(engine.call_count, 1)
            self.assertEqual(result['coverage']['includedPages'], 1)
            self.assertEqual(result['coverage']['omittedPages'], [2])
            self.assertEqual(result['processing']['attempts'], 1)

    def test_recovery_uses_one_shared_time_budget(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch('backend.omr.pipeline._recognize_complete', side_effect=RecognitionTimeout('超时')) as engine, \
                patch('backend.omr.pipeline.time.monotonic', side_effect=[0, 1000]):
            with self.assertRaises(RecognitionTimeout):
                recognize(list(range(6)), Path(temp), 'test')
            self.assertEqual(engine.call_count, 1)

    def test_processing_counts_full_attempts_and_recovery(self):
        def engine(sources, folder, title, progress, layout='vocal', **options):
            options['on_attempt']()
            if len(sources) == 6:
                options['on_attempt']()
                raise RecognitionUncertain('第 6 页失败')
            return write_candidate(folder, len(sources))
        with tempfile.TemporaryDirectory() as temp, patch('backend.omr.pipeline._recognize_complete', engine):
            song = recognize(list(range(6)), Path(temp), 'test')
        self.assertEqual(song['processing']['attempts'], 3)
        self.assertEqual(song['processing']['recoveryAttempts'], 1)

    def test_last_page_failure_preserves_first_five_with_explicit_warning(self):
        calls = []
        def engine(sources, folder, title, progress, layout='vocal', **options):
            calls.append(len(sources))
            if len(sources) == 6:
                raise RecognitionUncertain('第 6 页未能完整检测谱表。')
            return write_candidate(folder, len(sources))
        with tempfile.TemporaryDirectory() as temp, patch('backend.omr.pipeline._recognize_complete', engine):
            folder = Path(temp)
            song = recognize([Path(str(i)) for i in range(6)], folder, 'test')
            self.assertEqual(calls, [6, 5])
            self.assertEqual(song['coverage']['includedPages'], 5)
            self.assertEqual(song['coverage']['omittedPages'], [6])
            self.assertFalse(song['coverage']['complete'])
            self.assertEqual(song['measures'], 5)
            self.assertEqual(len(song['notes']), 15)
            root = E.fromstring((folder / 'score.musicxml').read_bytes())
            self.assertEqual([len(p.findall('measure')) for p in root.findall('part')], [5, 5])
            self.assertIn('部分乐谱', root.findtext('work/work-title'))

    def test_middle_failure_never_skips_a_page(self):
        calls = []
        def engine(sources, folder, title, progress, layout='vocal', **options):
            calls.append(list(sources))
            if len(sources) > 2:
                raise RecognitionUncertain('第 3 页节拍异常。')
            return write_candidate(folder, len(sources))
        with tempfile.TemporaryDirectory() as temp, patch('backend.omr.pipeline._recognize_complete', engine):
            song = recognize(list(range(6)), Path(temp), 'test')
        self.assertEqual(calls, [list(range(6)), [0, 1]])
        self.assertEqual(song['coverage']['omittedPages'], [3, 4, 5, 6])

    def test_first_page_failure_has_no_recovery_or_false_success(self):
        with tempfile.TemporaryDirectory() as temp, patch('backend.omr.pipeline._recognize_complete', side_effect=RecognitionUncertain('第 1 页失败')) as engine:
            with self.assertRaises(RecognitionUncertain):
                recognize(list(range(6)), Path(temp), 'test')
            self.assertEqual(engine.call_count, 1)
            self.assertFalse((Path(temp) / 'song.json').exists())

    def test_recovery_never_exceeds_two_additional_runs(self):
        calls = []
        def engine(sources, folder, title, progress, layout='vocal', **options):
            calls.append(len(sources))
            raise RecognitionUncertain('无法确认谱表。')
        with tempfile.TemporaryDirectory() as temp, patch('backend.omr.pipeline._recognize_complete', engine):
            with self.assertRaisesRegex(RecognitionUncertain, '未能保留'):
                recognize(list(range(6)), Path(temp), 'test')
        self.assertEqual(calls, [6, 5, 4])

    def test_full_timeout_can_still_recover_a_checked_prefix(self):
        calls = []
        def engine(sources, folder, title, progress, layout='vocal', **options):
            calls.append(options)
            if len(sources) == 3:
                raise RecognitionTimeout('识谱超时')
            return write_candidate(folder, len(sources))
        with tempfile.TemporaryDirectory() as temp, patch('backend.omr.pipeline._recognize_complete', engine):
            result = recognize(list(range(3)), Path(temp), 'test')
        self.assertEqual(result['coverage']['includedPages'], 2)
        self.assertFalse(calls[1]['allow_retry'])
        self.assertGreater(calls[1]['recovery_deadline'], time.monotonic() - 1)

    def test_dangling_boundary_tie_shrinks_to_previous_whole_page(self):
        xml = pages_xml(3, {3: 'start'})
        song = to_song(xml, 'test', page_measures=[1, 1, 1])
        song.update(pageMeasures=[1, 1, 1], processing={'attempts': 1})
        data, result, count = checked_prefix(xml, song, 'test', 'vocal')
        self.assertEqual(count, 2)
        self.assertEqual(result['measures'], 2)
        self.assertNotIn(b'<tie', data)

    def test_tie_chain_crossing_all_boundaries_is_rejected(self):
        root = E.fromstring(pages_xml(2, {1: 'start', 2: 'start'}))
        E.SubElement(root.find('part').findall('measure')[1].find('note'), 'tie', type='stop')
        xml = E.tostring(root)
        song = to_song(xml, 'test', page_measures=[1, 1])
        song.update(pageMeasures=[1, 1], processing={'attempts': 1})
        with self.assertRaisesRegex(RecognitionUncertain, '没有可安全保留'):
            checked_prefix(xml, song, 'test', 'vocal')

    def test_closed_cross_page_tie_is_kept_without_changing_duration(self):
        xml = pages_xml(2, {1: 'start', 2: 'stop'})
        song = to_song(xml, 'test', page_measures=[1, 1])
        song.update(pageMeasures=[1, 1], processing={'attempts': 1})
        _, result, count = checked_prefix(xml, song, 'test', 'vocal')
        melody = [n for n in result['notes'] if n['role'] == 'melody']
        self.assertEqual(count, 2)
        self.assertEqual(len(melody), 1)
        self.assertEqual(melody[0]['duration'], 4)

    def test_bad_prefix_cannot_be_used_as_a_partial_result(self):
        root = E.fromstring(pages_xml(2))
        root.find('part/measure/note/duration').text = '5'
        with self.assertRaisesRegex(RecognitionUncertain, '没有可安全保留'):
            checked_prefix(E.tostring(root), {'pageMeasures': [1, 1], 'processing': {}}, 'test', 'vocal')

    def test_partial_job_is_terminal_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp);store = JobStore(root, 'version');key, _ = store.submit(b'input')
            store.update(key, status='partial', song={'coverage': {'complete': False}})
            self.assertIsNone(store.active)
            restored = JobStore(root, 'version')
            self.assertEqual(restored.snapshot(key)['status'], 'partial')
            self.assertIn('finishedAt', restored.snapshot(key))
            restored.update(key, createdAt=time.time() - RETENTION_SECONDS - 5)
            restored.cleanup()
            self.assertIsNone(restored.snapshot(key))

    def test_partial_result_remains_owner_protected_and_quota_counts_all_pages(self):
        token = 'b' * 64
        def engine(sources, folder, title, progress):
            song = write_candidate(folder, 1)
            return partial_coverage(song, 2, 1, '第 2 页失败')
        with tempfile.TemporaryDirectory() as temp:
            app = create_app(Path(temp), engine)
            with TestClient(app) as client:
                response = client.post('/api/recognition', files=[('images', ('a.png', b'a', 'image/png')), ('images', ('b.png', b'b', 'image/png'))], headers={'X-Recognition-Token': token})
                self.assertEqual(response.status_code, 202)
                key = response.json()['id']
            # Worker shutdown waits for completion before checking stored result.
            state = app.state.store.snapshot(key)
            self.assertEqual(state['status'], 'partial')
            self.assertEqual(state['pageCount'], 2)
            with TestClient(app) as client:
                url = f'/api/recognition/{key}/score.musicxml'
                self.assertEqual(client.get(url, headers={'X-Recognition-Token': token}).status_code, 200)
                self.assertEqual(client.get(url, headers={'X-Recognition-Token': 'c' * 64}).status_code, 404)
                self.assertEqual(client.get(url).status_code, 401)
