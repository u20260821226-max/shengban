"""Screenshot margins and three-flat pitch support, without altering score content."""
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from PIL import Image, ImageDraw

from backend.omr.images import paper_bounds
from backend.omr.musicxml import to_song, UnsupportedScore
from backend.omr.pipeline import prepare_image
from test_recognition import score


class InputTests(unittest.TestCase):
    def test_dark_screenshot_bands_removed_without_cutting_staff(self):
        image = Image.new('L', (600, 1200), 0)
        draw = ImageDraw.Draw(image);draw.rectangle((0, 200, 599, 999), fill=220)
        for y in [300, 310, 320, 330, 340]:
            draw.line((30, y, 570, y), fill=0, width=2)
        bounds = paper_bounds(image)
        self.assertIsNotNone(bounds)
        self.assertLessEqual(bounds[1], 205)
        self.assertGreaterEqual(bounds[3], 995)
        self.assertEqual((bounds[0], bounds[2]), (0, 600))

    def test_white_scan_margins_and_normal_paper_are_not_cropped(self):
        image = Image.new('L', (600, 1000), 255)
        ImageDraw.Draw(image).rectangle((60, 250, 540, 700), fill=20)
        self.assertIsNone(paper_bounds(image))

    def test_preparation_reports_crop_and_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder) / 'source.png', Path(folder) / 'normalized.png'
            image = Image.new('L', (600, 1200), 0)
            ImageDraw.Draw(image).rectangle((0, 200, 599, 999), fill=255);image.save(source)
            before = source.read_bytes()
            self.assertTrue(prepare_image(source, target)['cropped'])
            self.assertEqual(source.read_bytes(), before)

    def test_three_flats_keep_explicit_pitch_without_transposing(self):
        root = E.fromstring(score())
        for attributes in root.findall('.//attributes'):
            key = E.SubElement(attributes, 'key');E.SubElement(key, 'fifths').text = '-3'
        melody = root.find('part/measure/note/pitch')
        melody.find('step').text = 'E';E.SubElement(melody, 'alter').text = '-1'
        song = to_song(E.tostring(root), 'three flats')
        self.assertEqual([n['midi'] for n in song['notes'] if n['role'] == 'melody'], [63])
        self.assertEqual({n['midi'] for n in song['notes'] if n['role'] == 'accompaniment'}, {60})

    def test_four_accidentals_remain_out_of_range(self):
        root = E.fromstring(score())
        key = E.SubElement(root.find('.//attributes'), 'key');E.SubElement(key, 'fifths').text = '4'
        with self.assertRaisesRegex(UnsupportedScore, '三个'):
            to_song(E.tostring(root), 'four sharps')

    def test_unsupported_tuplet_names_the_affected_measure(self):
        root = E.fromstring(score())
        modification = E.SubElement(root.find('part/measure/note'), 'time-modification')
        E.SubElement(modification, 'actual-notes').text = '6'
        E.SubElement(modification, 'normal-notes').text = '4'
        with self.assertRaisesRegex(UnsupportedScore, '第 1 小节.*连音组'):
            to_song(E.tostring(root), 'unsupported tuplet')
