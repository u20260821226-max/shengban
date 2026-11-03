"""Keep only a checked, contiguous prefix; never patch notes or skip a page."""
import re
import xml.etree.ElementTree as ET

from .errors import RecognitionUncertain, UnsupportedScore
from .musicxml import parse_xml, to_song


def preceding_pages(error, count):
    """Page hints only choose a new input; they never certify its correctness."""
    pages = [int(page) for page in re.findall(r'第 (\d+) 页', str(error))]
    return min(count - 1, max(0, min(pages) - 1)) if pages else count - 1


def checked_prefix(xml, song, title, layout):
    """Revalidate each whole-page boundary, including every outstanding tie."""
    counts = song['pageMeasures']
    original = parse_xml(xml)
    measures = [len(part.findall('measure')) for part in original.findall('part')]
    if not measures or any(size != sum(counts) for size in measures):
        raise RecognitionUncertain('无法确认前段的页面与小节对应关系。')
    last_error = None
    for pages in range(len(counts), 0, -1):
        root = parse_xml(xml)
        keep = sum(counts[:pages])
        for part in root.findall('part'):
            for measure in part.findall('measure')[keep:]:
                part.remove(measure)
        data = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        try:
            result = to_song(data, title, page_measures=counts[:pages], layout=layout,
                             require_closed_ties=True)
        except UnsupportedScore as error:
            last_error = error
            continue
        result['pageMeasures'] = counts[:pages]
        result['processing'] = song['processing']
        return data, result, pages
    raise RecognitionUncertain(f'前段没有可安全保留的完整页面：{last_error}')


def partial_coverage(song, total, included, reason, boundary_reason=None):
    summary = f'仅生成前 {included} 页，共上传 {total} 页；第 {included + 1} 至 {total} 页未包含在结果中。'
    if included + 1 == total:
        summary = f'仅生成前 {included} 页，共上传 {total} 页；第 {total} 页未包含在结果中。'
    if boundary_reason:
        summary += boundary_reason
    song['coverage'] = {'complete': False, 'totalPages': total, 'includedPages': included,
                        'omittedPages': list(range(included + 1, total + 1)),
                        'reason': str(reason), 'message': summary}
    song['notice'] = '当前是部分乐谱，不含全曲结尾。' + song['notice']
    return song


def label_partial_xml(xml, included, total):
    """The exported file itself must retain the incompleteness warning."""
    root = parse_xml(xml)
    title = f'部分乐谱：仅前 {included} / 共 {total} 页'
    work = root.find('work')
    if work is None:
        work = ET.Element('work')
        root.insert(0, work)
    node = work.find('work-title')
    if node is None:
        node = ET.SubElement(work, 'work-title')
    node.text = title
    movement = root.find('movement-title')
    if movement is not None:
        movement.text = title
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
