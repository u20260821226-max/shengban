"""Failed retries retain evidence; successful retries still produce validated output."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from backend.omr.errors import RecognitionAttemptsFailed, RecognitionUncertain
from backend.omr.pipeline import _recognize_complete, recognize
from backend.omr.partial import preceding_pages
from backend.omr.musicxml import to_song
from test_recognition import score


class RetryDiagnosticsTests(unittest.TestCase):
    def test_missing_left_hand_is_identified_as_recognition_failure(self):
        with self.assertRaisesRegex(RecognitionUncertain, '第 1 小节识别结果未读出钢琴下行.*不代表原谱'):
            to_song(score(left=''), 'test')

    def test_overflow_identifies_the_affected_staff(self):
        from test_recognition import note
        upper = score(right=note(5, staff=1)).replace(
            b'<backup><duration>4</duration>', b'<backup><duration>5</duration>')
        lower = score(left=note(5, staff=2, voice='5'))
        for xml, label, other in [(upper, '钢琴上行', '钢琴下行'),
                                  (lower, '钢琴下行', '钢琴上行')]:
            with self.subTest(label=label), self.assertRaises(RecognitionUncertain) as caught:
                to_song(xml, 'test')
            message = str(caught.exception)
            self.assertIn(f'第 1 小节{label}识别结果超出 4 拍', message)
            self.assertNotIn(other, message)
            self.assertIn('不代表原谱', message)

    def run_with_attempts(self, root, outcomes):
        source = root / 'input.png'
        Image.new('RGB', (600, 800), 'white').save(source)
        binary = root / 'engine'
        binary.touch()
        folder = root / 'job'
        folder.mkdir()
        with patch.dict('os.environ', {'AUDIVERIS_BIN': str(binary)}), \
                patch('backend.omr.pipeline.run_attempt', side_effect=outcomes) as engine:
            result = _recognize_complete(source, folder, 'test', lambda *args: None)
            self.assertEqual(engine.call_count, 2)
        return folder, result

    def test_retry_failure_does_not_replace_initial_diagnostic_or_create_score(self):
        initial = RecognitionUncertain('第 5 小节识别结果超出 4 拍。')
        retry = RecognitionUncertain('第 4 小节识别结果未读出钢琴下行。')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(RecognitionAttemptsFailed) as caught:
                self.run_with_attempts(root, [initial, retry])
            self.assertIn(str(initial), str(caught.exception))
            self.assertIn(str(retry), str(caught.exception))
            self.assertFalse((root / 'job/score.musicxml').exists())
            self.assertFalse((root / 'job/song.json').exists())

    def test_successful_retry_keeps_normal_result(self):
        xml = score()
        song = to_song(xml, 'test')
        with tempfile.TemporaryDirectory() as temp:
            folder, result = self.run_with_attempts(Path(temp), [RecognitionUncertain('首次失败'), (xml, song)])
            self.assertEqual(result['processing']['attempts'], 2)
            self.assertEqual((folder / 'score.musicxml').read_bytes(), xml)

    def test_context_wrapper_can_preserve_combined_failure(self):
        failure = RecognitionAttemptsFailed(RecognitionUncertain('第 3 页首次失败'),
                                            RecognitionUncertain('第 2 页重试失败'))
        wrapped = type(failure)(f'前段检查：{failure}')
        self.assertIn('第 3 页首次失败', str(wrapped))
        self.assertIn('第 2 页重试失败', str(wrapped))
        self.assertEqual(preceding_pages(wrapped, 3), 1)

    def test_first_page_retry_failure_skips_recovery_and_preserves_reason(self):
        failure = RecognitionAttemptsFailed(RecognitionUncertain('跨页小节未完整衔接'),
                                            RecognitionUncertain('第 1 页：第 4 小节识别结果未读出钢琴下行'))
        with tempfile.TemporaryDirectory() as temp, \
                patch('backend.omr.pipeline._recognize_complete', side_effect=failure) as engine:
            with self.assertRaises(RecognitionAttemptsFailed) as caught:
                recognize([Path('1'), Path('2'), Path('3')], Path(temp), 'test')
            self.assertEqual(engine.call_count, 1)
            self.assertIs(caught.exception, failure)

    def test_failed_prefix_preserves_combined_failure_without_internal_error(self):
        failure = RecognitionAttemptsFailed(RecognitionUncertain('第 3 页首次失败'),
                                            RecognitionUncertain('第 3 页重试失败'))
        with tempfile.TemporaryDirectory() as temp, patch(
                'backend.omr.pipeline._recognize_complete',
                side_effect=[failure, RecognitionUncertain('第 1 页恢复失败')]):
            with self.assertRaisesRegex(RecognitionAttemptsFailed, '未能保留可用的连续前段.*恢复失败'):
                recognize([Path('1'), Path('2'), Path('3')], Path(temp), 'test')


if __name__ == '__main__':
    unittest.main()
