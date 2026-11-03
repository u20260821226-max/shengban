"""Supported score structures shared by upload, recognition and conversion."""
from .errors import UnsupportedScore

# Part staff counts, playback roles, lowest supported key signature.
LAYOUTS = {
    'vocal': ((1, 2), ('melody', 'accompaniment'), -3),
    'piano': ((2,), ('accompaniment',), -3),
    'single': ((1,), ('accompaniment',), -4),
}


def score_layout(name):
    if name not in LAYOUTS:
        raise UnsupportedScore('请选择单行钢琴谱、两行钢琴谱或三行声乐谱。')
    return LAYOUTS[name]
