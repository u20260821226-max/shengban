"""Check staff coverage without requiring partial polyphonic voices to fill a bar."""
from fractions import Fraction

from .errors import RecognitionUncertain


def coverage(spans):
    covered, end = Fraction(0), Fraction(0)
    for start, stop in sorted(spans):
        covered += max(Fraction(0), stop - max(start, end))
        end = max(end, stop)
    return covered


def staff_label(role, staff_count, staff):
    if role == 'melody':
        return '旋律'
    if staff_count == 1:
        return '钢琴谱'
    return '钢琴上行' if str(staff) == '1' else '钢琴下行'


def check_measure(lanes, forwards, expected, role, number, staff_count, furthest):
    if furthest > expected:
        overflowing = {staff for (_, staff), spans in lanes.items()
                       if any(end > expected for _, end in spans)}
        overflowing.update(staff for _, end, _, staff in forwards
                           if end > expected and staff is not None)
        label = '、'.join(staff_label(role, staff_count, staff) for staff in sorted(overflowing))
        raise RecognitionUncertain(
            f'第 {number} 小节{label}识别结果超出 {float(expected):g} 拍，暂不能生成试听。'
            '可能存在音符时值误识别，不代表原谱拍数有误。')
    present = {staff for _, staff in lanes}
    expected_staves = {str(i) for i in range(1, staff_count + 1)}
    if present - expected_staves:
        raise RecognitionUncertain(f'第 {number} 小节识别结果的谱表编号异常，请尝试清晰原图。')
    checks, warnings = [], []
    for staff in range(1, staff_count + 1):
        label = staff_label(role, staff_count, staff)
        if str(staff) not in present:
            raise RecognitionUncertain(
                f'第 {number} 小节识别结果未读出{label}的音符或休止符，无法核对时值。'
                '这不代表原谱拍数有误，请尝试清晰原图或较短片段。')
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
            warnings.append(f'第 {number} 小节{label}识别结果有 {float(gap):g} 拍空缺，试听中保留为空白。')
        elif gap != 0:
            raise RecognitionUncertain(
                f'第 {number} 小节{label}应为 {float(expected):g} 拍，'
                f'识别结果仅覆盖 {float(covered):g} 拍（缺 {float(gap):g} 拍），暂不能生成试听。')
    return checks, warnings
