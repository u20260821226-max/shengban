"""Focused regression tests for rhythm errors and explicit tie behavior."""
import unittest
from xml.etree import ElementTree as E

from backend.omr.musicxml import UnsupportedScore, to_song


def note(duration=4, step='C', staff=None, voice='1', extra=''):
    return f'<note>{extra}<pitch><step>{step}</step><octave>4</octave></pitch><duration>{duration}</duration><voice>{voice}</voice>{f"<staff>{staff}</staff>" if staff else ""}</note>'


def score(melody=None, right=None, left=None):
    melody = melody if melody is not None else note()
    right = right if right is not None else note(staff=1)
    left = left if left is not None else note(staff=2, voice='5')
    return f'''<score-partwise><part id="V"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time></attributes>{melody}</measure></part><part id="P"><measure number="1"><attributes><divisions>1</divisions><time><beats>4</beats><beat-type>4</beat-type></time><staves>2</staves></attributes>{right}<backup><duration>4</duration></backup>{left}</measure></part></score-partwise>'''.encode()


class RhythmTests(unittest.TestCase):
    def test_three_staff_measure_and_chord_not_double_counted(self):
        data = to_song(score(right=note(staff=1) + note(step='E', staff=1, extra='<chord/>')), 'test')
        self.assertEqual(len(data['notes']), 4)
        self.assertEqual(len(data['rhythmChecks']), 3)
        self.assertFalse(data['warnings'])

    def test_overfull_voice_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedScore, '第 1 小节'):
            to_song(score(melody=note(5)), 'test')

    def test_underfull_bass_is_not_hidden_by_complete_right_hand(self):
        with self.assertRaisesRegex(UnsupportedScore, '第 1 小节'):
            to_song(score(left=note(3, staff=2, voice='5')), 'test')

    def test_small_gap_is_reported_not_filled_with_notes(self):
        data = to_song(score(melody=note('7/2')), 'test')
        self.assertEqual(len(data['warnings']), 1)
        self.assertEqual(data['notes'][0]['duration'], 1.75)
        self.assertEqual(data['duration'], 2)
        self.assertEqual(data['rhythmChecks'][0]['gapBeats'], .5)

    def test_multiple_small_gaps_are_rejected(self):
        with self.assertRaisesRegex(UnsupportedScore, '多处谱表'):
            to_song(score(melody=note('7/2'), left=note('7/2', staff=2, voice='5')), 'test')

    def test_rest_counts_as_time(self):
        rest = '<note><rest/><duration>2</duration><voice>1</voice></note>'
        data = to_song(score(melody=note(2) + rest), 'test')
        self.assertFalse(data['warnings'])
        self.assertEqual(len(data['notes']), 3)

    def test_tie_merges_same_pitch(self):
        melody = note(2, extra='<tie type="start"/>') + note(2, extra='<tie type="stop"/>')
        data = to_song(score(melody=melody), 'test')
        self.assertEqual(sum(n['role'] == 'melody' for n in data['notes']), 1)
        self.assertEqual(data['notes'][0]['duration'], 2)

    def test_broken_tie_is_rejected(self):
        with self.assertRaisesRegex(UnsupportedScore, '延音线'):
            to_song(score(melody=note(extra='<tie type="stop"/>')), 'test')

    def test_partial_second_voice_is_valid_when_staff_timeline_is_complete(self):
        melody = note() + '<backup><duration>4</duration></backup>' + note(2, voice='2')
        data = to_song(score(melody=melody), 'test')
        self.assertFalse(data['warnings'])
        self.assertEqual(data['rhythmChecks'][0]['coveredBeats'], 4)
        self.assertEqual(len(data['rhythmChecks'][0]['voices']), 2)

    def test_multiple_complete_voices_are_not_summed_into_eight_beats(self):
        melody = note() + '<backup><duration>4</duration></backup>' + note(4, voice='2')
        data = to_song(score(melody=melody), 'test')
        self.assertEqual(len(data['rhythmChecks']), 3)
        self.assertFalse(data['warnings'])

    def test_complementary_partial_voices_cover_a_full_staff(self):
        melody = note(2) + note(2, voice='2')
        data = to_song(score(melody=melody), 'test')
        self.assertFalse(data['warnings'])

    def test_midbar_voice_entry_with_forward_is_valid(self):
        left = (note(4, staff=2, voice='5') + '<backup><duration>4</duration></backup>'
                '<forward><duration>2</duration><voice>7</voice><staff>2</staff></forward>'
                + note(2, staff=2, voice='7'))
        data = to_song(score(left=left), 'test')
        self.assertFalse(data['warnings'])

    def test_polyphonic_staff_with_real_gap_is_rejected(self):
        left = (note(2, staff=2, voice='5') + '<backup><duration>2</duration></backup>'
                '<forward><duration>2</duration><voice>7</voice><staff>2</staff></forward>'
                + note(1, staff=2, voice='7'))
        with self.assertRaisesRegex(UnsupportedScore, '钢琴左手.*缺 1 拍'):
            to_song(score(left=left), 'test')

    def test_wrong_staff_structure_rejected(self):
        root = E.fromstring(score())
        root.find('.//staves').text = '1'
        with self.assertRaisesRegex(UnsupportedScore, '三行声乐谱'):
            to_song(E.tostring(root), 'test')

    def test_repeat_is_not_silently_ignored(self):
        with self.assertRaisesRegex(UnsupportedScore, '反复'):
            to_song(score(melody=note() + '<barline><repeat direction="backward"/></barline>'), 'test')


if __name__ == '__main__':
    unittest.main()
