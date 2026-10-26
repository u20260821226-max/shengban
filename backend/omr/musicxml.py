"""Convert the supported voice + grand piano subset into playback events.

No notation is repaired: uncertain structure is rejected, not silently rewritten.
MusicXML remains intact for display; only explicit same-pitch ties merge in audio.
"""
from fractions import Fraction
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from .errors import RecognitionUncertain, UnsupportedScore
from .rhythm import check_measure
from .pages import page_for_measure


def parse_xml(data):
    if len(data) > 20_000_000 or b'<!ENTITY' in data.upper():
        raise UnsupportedScore('识谱结果文件过大或格式不受支持。')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise UnsupportedScore('识谱结果无法读取，请更换谱图。') from exc
    for node in root.iter():
        node.tag = node.tag.rsplit('}', 1)[-1]
    return root


def read_mxl(path):
    with ZipFile(path) as bundle:
        container = parse_xml(bundle.read('META-INF/container.xml'))
        files = [e.get('full-path') for e in container.iter('rootfile')
                 if e.get('media-type') == 'application/vnd.recordare.musicxml+xml']
        if len(files) != 1 or bundle.getinfo(files[0]).file_size > 20_000_000:
            raise UnsupportedScore('暂不支持一张图导出多个乐章。')
        return bundle.read(files[0])


def _part_events(part, role):
    divisions, meter = None, None
    events, lengths, pending, warnings, checks = [], [], {}, [], []
    staff_count = max([int(e.text) for e in part.findall('.//staves')] or [1])
    absolute = Fraction(0)
    for index, measure in enumerate(part.findall('measure')):
        cursor = furthest = last_onset = Fraction(0)
        lanes, forwards, previous = {}, [], None
        attr = measure.find('attributes')
        if attr is not None:
            value = attr.findtext('divisions')
            if value is not None:
                divisions = int(value)
            time = attr.find('time')
            if time is not None:
                candidate = (time.findtext('beats'), time.findtext('beat-type'))
                if candidate not in {('2', '4'), ('3', '4'), ('4', '4')}:
                    raise UnsupportedScore('试用版仅支持固定的 2/4、3/4、4/4 拍。')
                if meter is not None and candidate != meter:
                    raise UnsupportedScore('暂不支持中途换拍。')
                meter = candidate
            for fifths in attr.findall('key/fifths'):
                if abs(int(fifths.text)) > 3:
                    raise UnsupportedScore('试用版暂限最多三个升降号。')
        if not divisions or divisions < 0 or meter is None:
            raise UnsupportedScore('未能读出完整拍号或时值信息。')
        expected = Fraction(int(meter[0]))
        for element in measure:
            if element.tag in {'backup', 'forward'}:
                delta = Fraction(element.findtext('duration', '0')) / divisions
                cursor += delta if element.tag == 'forward' else -delta
                if cursor < 0:
                    raise UnsupportedScore('检测到小节声部错位，请更换谱图。')
                furthest = max(cursor, furthest)
                if element.tag == 'forward':
                    forwards.append((cursor - delta, cursor, element.findtext('voice'), element.findtext('staff')))
                previous = None
            elif element.tag == 'note':
                if element.find('grace') is not None or element.find('time-modification') is not None:
                    raise UnsupportedScore(f'第 {index + 1} 小节的识别结果包含装饰音或连音组，试用版暂不支持。')
                duration = Fraction(element.findtext('duration', '0')) / divisions
                if duration <= 0:
                    raise UnsupportedScore('有音符缺少可用时值。')
                onset = last_onset if element.find('chord') is not None else cursor
                lane = (element.findtext('voice', '1'), element.findtext('staff', '1'))
                if lane[1] not in {str(i) for i in range(1, staff_count + 1)}:
                    raise UnsupportedScore('音符谱表编号与钢琴声部结构不一致。')
                intervals = lanes.setdefault(lane, [])
                if element.find('chord') is not None:
                    if previous != (lane, onset) or not intervals:
                        raise UnsupportedScore('和弦音符的时序不完整。')
                    intervals[-1] = (onset, max(intervals[-1][1], onset + duration))
                else:
                    if intervals and onset < intervals[-1][1]:
                        raise UnsupportedScore(f'第 {index + 1} 小节同一声部音符重叠。')
                    intervals.append((onset, onset + duration))
                previous = (lane, onset)
                if element.find('chord') is None:
                    last_onset, cursor = onset, cursor + duration
                furthest = max(furthest, onset + duration)
                if element.find('rest') is not None:
                    continue
                pitch = element.find('pitch')
                if pitch is None:
                    raise UnsupportedScore('暂不支持无固定音高声部。')
                step = pitch.findtext('step')
                if step is None or len(step) != 1 or step not in 'CDEFGAB':
                    raise UnsupportedScore('音高信息不完整。')
                alter = Fraction(pitch.findtext('alter', '0'))
                if alter.denominator != 1:
                    raise UnsupportedScore('暂不支持微分音。')
                midi = 12 * (int(pitch.findtext('octave')) + 1) + {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}[step] + int(alter)
                if not 21 <= midi <= 108:
                    raise UnsupportedScore('识别到超出钢琴范围的音高。')
                key = (element.findtext('voice', '1'), element.findtext('staff', '1'), midi)
                ties = {e.get('type') for e in element.findall('tie') + element.findall('notations/tied')}
                at = absolute + onset
                if 'stop' in ties:
                    prior = pending.pop(key, None)
                    if prior is None or prior['beat'] + prior['beats'] != at:
                        raise RecognitionUncertain('延音线连接不完整，暂不能生成可靠试听。')
                    prior['beats'] += duration
                    event = prior
                else:
                    if key in pending:
                        raise UnsupportedScore('延音线与音符时序不一致。')
                    event = {'beat': at, 'beats': duration, 'midi': midi, 'role': role,
                             'velocity': .65 if role == 'melody' else .6}
                    events.append(event)
                if 'start' in ties:
                    pending[key] = event
        bar_checks, bar_warnings = check_measure(lanes, forwards, expected, role,
                                                 index + 1, staff_count, furthest)
        checks.extend(bar_checks)
        warnings.extend(bar_warnings)
        lengths.append(expected)
        absolute += expected
    if any(e['beat'] + e['beats'] != absolute for e in pending.values()):
        raise RecognitionUncertain('检测到未闭合的延音线。')
    return events, lengths, warnings, checks


def to_song(xml, title, page_measures=None, layout='vocal'):
    root = parse_xml(xml)
    if root.tag != 'score-partwise':
        raise UnsupportedScore('暂不支持此种乐谱格式。')
    if root.find('.//repeat') is not None or root.find('.//ending') is not None or root.find('.//transpose') is not None:
        raise UnsupportedScore('试用版暂不支持反复跳房子或移调乐器。')
    parts = root.findall('part')
    staff_counts = [max([int(e.text) for e in p.findall('.//staves')] or [1]) for p in parts]
    expected = [2] if layout == 'piano' else [1, 2]
    if layout not in {'piano', 'vocal'} or staff_counts != expected:
        raise RecognitionUncertain('未能确认钢琴双行结构，请上传右手和左手的两行五线谱。' if layout == 'piano' else '未能确认上方人声、下方钢琴双行的结构，请换一张三行声乐谱。')
    measures = [len(p.findall('measure')) for p in parts]
    limit = sum(page_measures) if page_measures else 16
    if len(set(measures)) != 1 or not 1 <= measures[0] <= limit:
        raise UnsupportedScore('声部小节数不一致，或超过试用版的 16 小节限制。')
    if page_measures and measures[0] != sum(page_measures):
        raise RecognitionUncertain('跨页小节未完整衔接，暂不能生成连续伴奏。')
    tempos = {float(e.get('tempo')) for e in root.findall('.//sound') if e.get('tempo')}
    if len(tempos) > 1 or any(not 30 <= bpm <= 220 for bpm in tempos):
        raise UnsupportedScore('暂不支持曲中变速或异常速度标记。')
    bpm = next(iter(tempos), 120)
    notes, lengths, warnings, checks = [], None, [], []
    roles = ['accompaniment'] if layout == 'piano' else ['melody', 'accompaniment']
    for part, role in zip(parts, roles):
        events, sizes, issues, part_checks = _part_events(part, role)
        if not events or (lengths is not None and lengths != sizes):
            raise UnsupportedScore('声部为空或小节无法对齐。')
        lengths = sizes
        notes.extend(events)
        warnings.extend(issues)
        checks.extend(part_checks)
    pages_with_gaps = [0] * (len(page_measures) if page_measures else 1)
    for check in checks:
        if check['gapBeats']:
            page = page_for_measure(check['measure'], page_measures) if page_measures else 1
            pages_with_gaps[page - 1] += 1
    if any(count > 1 for count in pages_with_gaps):
        raise RecognitionUncertain('多处谱表存在时值空缺，暂不能生成试听。')
    quarter = 60 / bpm
    starts, total = [], Fraction(0)
    for size in lengths:
        starts.append(float(total) * quarter)
        total += size
    for note in notes:
        note['time'] = float(note.pop('beat')) * quarter
        note['duration'] = float(note.pop('beats')) * quarter
    return {'id': 'recognized', 'title': title, 'layout': layout, 'bpm': bpm, 'duration': float(total) * quarter,
            'measureTimes': starts, 'measures': len(lengths),
            'notes': sorted(notes, key=lambda n: (n['time'], n['midi'])),
            'tempoDefaulted': not bool(tempos),
            'warnings': warnings,
            'rhythmChecks': checks,
            'notice': '自动识别结果，可能有错音、节奏或连线遗漏。结构检查通过不代表逐音准确。'}
