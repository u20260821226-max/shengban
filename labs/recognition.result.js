import { requestScore } from './recognition.task.js';

// Result coverage and export stay separate from task submission and playback.
export function mountResult(root, onError) {
  const $ = selector => root.querySelector(selector);
  const button = $('#download-score');
  let current = null;
  button.addEventListener('click', async () => {
    if (!current) return;
    const result = current;
    button.disabled = true;
    try {
      const xml = await requestScore(result.scoreUrl);
      const partial = result.song.coverage?.complete === false;
      const label = partial ? `声伴-仅前${result.song.coverage.includedPages}页-共${result.song.coverage.totalPages}页` : '声伴-识别乐谱';
      const url = URL.createObjectURL(new Blob([xml], { type: 'application/vnd.recordare.musicxml+xml' }));
      const link = document.createElement('a');
      link.href = url; link.download = `${label}.musicxml`;
      document.body.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { onError('乐谱下载暂未完成，请重试；无需重新识别。', true); }
    finally { button.disabled = !current; }
  });
  function reset() {
    current = null; button.disabled = true;
    $('#partial-result').hidden = true;
  }
  function render(result) {
    current = result; button.disabled = false;
    const coverage = result.song.coverage;
    const partial = coverage?.complete === false;
    $('#result-title').textContent = partial ? '部分乐谱已生成' : '自动识别试听';
    $('#partial-result').hidden = !partial;
    if (partial) {
      $('#partial-summary').textContent = coverage.message;
      $('#partial-reason').textContent = `完整生成未成功：${coverage.reason}`;
      $('#partial-next').textContent = `可试听、下载这 ${coverage.includedPages} 页。请重新选择未包含的谱页单独识别，或更换问题页后重新提交全曲；不会自动拼接到本次结果。`;
      if (result.song.layout !== 'vocal') $('[data-mode="accompaniment"]').textContent = '钢琴试听';
      describeMode($('#mode-description').textContent);
    }
    const pages = partial ? `仅前 ${coverage.includedPages} / 共 ${coverage.totalPages} 页` : `${result.pageCount || 1} 页`;
    $('#details').textContent = `${pages} · ${result.song.measures} 小节 · ${result.song.bpm} BPM${result.song.tempoDefaulted ? '（默认速度）' : ''}${result.song.processing?.attempts > 1 ? ' · 已自动重试' : ''}`;
    button.textContent = partial ? `下载前 ${coverage.includedPages} 页乐谱（MusicXML）` : '下载识别乐谱（MusicXML）';
    $('#reading-note').textContent = partial ? `下方仅为原上传乐谱的前 ${coverage.includedPages} 页内容，未经人工校正，不含剩余页面。重新排版后的显示页数可能不同。` : '向下滑动查看完整乐谱；播放与谱面均来自本次上传，未经人工校正。';
    return partial ? coverage.message : null;
  }
  reset();
  function describeMode(text) {
    const coverage = current?.song.coverage;
    $('#mode-description').textContent = coverage?.complete === false ? `仅播放已生成的前 ${coverage.includedPages} 页。${text}` : text;
  }
  return {reset, render, describeMode};
}
