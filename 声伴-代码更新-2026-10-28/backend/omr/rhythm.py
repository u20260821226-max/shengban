"""Check staff coverage without requiring partial polyphonic voices to fill a bar."""
from fractions import Fraction

from .errors import RecognitionUncertain


def coverage(spans):
    covered, end = Fraction(0), Fraction(0)
    for start, stop in sorted(spans):
        covered += max(Fraction(0), stop - max(start, end))
        end = max(end, stop)
    return covered


def check_measure(lanes, forwards, expected, role, number, staff_count, furthest):
    if furthest > expected:
        raise RecognitionUncertain(f'第 {number} 小节识别结果超出 {float(expected):g} 拍，暂不能生成试听。')
    if {staff for _, staff in lanes} != {str(i) for i in range(1, staff_count + 1)}:
        raise RecognitionUncertain(f'第 {number} 小节有谱表缺少时值信息。')
    checks, warnings = [], []
    for staff in range(1, staff_count + 1):
        label = '旋律' if role == 'melody' else ('钢琴右手' if staff == 1 else '钢琴左手')
        spans, voices = [], []
        for (voice, lane_staff), notes in lanes.items():
            if lane_staff != str(staff):
                continue
            voice_spans = notes + [(start, end) for start, end, v, s in forwards
                                   if (v is None or v == voice) and (s is None or s == lane_staff)]
            spans.extend(voice_spans)
            voices.append({'voice': voice, 'coveredBeats': float(coverage(voice_spans))})
        # Partial voices can legitimately appear only during part of a bar.
        # Check their overlaps/overflow separately in the parser, then union the
        # staff timeline. Never use one hand to fill gaps in the other hand.
        covered = coverage(spans)
        gap = expected - covered
        checks.append({'measure': number, 'role': role, 'staff': staff, 'voices': voices,
                       'expectedBeats': float(expected), 'coveredBeats': float(covered),
                       'gapBeats': float(gap)})
        if 0 < gap <= Fraction(1, 2):
            warnings.append(f'第 {number} 小节{label}有 {float(gap):g} 拍空缺，试听中保留为空白。')
        elif gap != 0:
            raise RecognitionUncertain(
                f'第 {number} 小节{label}应为 {float(expected):g} 拍，'
                f'识别结果仅覆盖 {float(covered):g} 拍（缺 {float(gap):g} 拍），暂不能生成试听。')
    return checks, warnings
