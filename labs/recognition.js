import { MusicPlayer } from '/music-player.js';
import { ScoreView } from '/score-view.js';
import { lastTask, rememberTask, requestJson, requestScore, watchTask } from './recognition.task.js';
import { PagePicker } from './recognition.pages.js';

export function initRecognition(root = document, initialLayout = 'vocal') {
  const $ = selector => root.querySelector(selector);
  if (['localhost', '127.0.0.1'].includes(location.hostname)) {
    if ($('.lab-header span')) $('.lab-header span').textContent = '自动识谱 · 本机测试';
    $('#privacy-note').textContent = '本机测试入口：图片由本机识谱服务处理，临时文件约 24 小时后清理。公网服务另有使用次数限制。';
  }
  const formatTime = n => `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(Math.floor(n % 60)).padStart(2, '0')}`;
  const player = new MusicPlayer(state => {
    $('#play').textContent = state.playing ? '暂停' : '播放';
    $('#position').textContent = formatTime(state.position / state.rate);
  });
  const score = new ScoreView($('#score'));
  let working = false;

  function processingStage(stage) {
    const steps = $('#processing-steps');
    steps.hidden = false;
    const current = ['queued', 'preparing'].includes(stage) ? 'recognizing' : stage;
    for (const step of steps.children) {
      if (step.dataset.step === current) step.setAttribute('aria-current', 'step');
      else step.removeAttribute('aria-current');
    }
  }

  function status(message, error = false) {
    if ($('#status').textContent !== message) $('#status').textContent = message;
    $('#status').dataset.error = String(error);
  }

  async function generate(images = null, resumeId = null) {
    if (working) return;
    working = true; player.pause(); $('#submit').disabled = true; picker.setDisabled(true); $('#layout').disabled = true;
    $('#result').hidden = true; $('#reconnect').hidden = true; $('#elapsed').hidden = true;
    processingStage(resumeId ? 'recognizing' : 'uploading');
    status(resumeId ? '正在恢复上次任务，不会重新生成…' : images?.[0]?.type === 'application/pdf' ? '正在上传 PDF、检查页数并自动转页，请稍候…' : '正在上传谱图，请稍候…');
    let id = resumeId;
    try {
      if (images) {
        rememberTask(null, $('#layout').value);
        const form = new FormData();
        form.append('layout', $('#layout').value);
        for (const image of images) form.append('images', image, image.name);
        const created = await requestJson('/api/recognition', { method: 'POST', body: form }, 90000);
        id = created.id;
      }
      rememberTask(id, $('#layout').value);
      const result = await watchTask(id, state => {
        processingStage(state.status);
        status(state.message);
        if (state.elapsedSeconds !== undefined) {
          $('#elapsed').hidden = false;
          $('#elapsed').textContent = `${state.status === 'completed' ? '本次处理耗时' : '已等待'}约 ${state.elapsedSeconds} 秒${state.status === 'completed' ? '' : '；正在自动处理，无需重新提交。'}`;
        }
      });
      await player.load(result.song);
      applyLayout(result.song.layout || 'vocal');
      await player.configure({ mode: 'accompaniment' });
      $('#details').textContent = `${result.pageCount || 1} 页 · ${result.song.measures} 小节 · ${result.song.bpm} BPM${result.song.tempoDefaulted ? '（默认速度）' : ''}${result.song.processing.attempts > 1 ? ' · 已自动重试' : ''}`;
      $('#notice').textContent = result.song.notice;
      const affected = new Set(result.song.rhythmChecks.filter(check => check.gapBeats !== 0).map(check => check.measure));
      $('#rhythm-summary').textContent = `节拍检查：检查了 ${result.song.rhythmChecks.length} 组谱表时值及各声部的重叠、超拍；${affected.size ? `${affected.size} 个小节有空缺，见下方提示。` : '未发现谱表时值空缺或超拍。'}这不能排除等时值的错音或误识别。`;
      $('#warnings').replaceChildren(...result.song.warnings.map(message => {
        const item = document.createElement('li'); item.textContent = message; return item;
      }));
      $('#result').hidden = false;
      $('#tempo').value = result.song.bpm;
      $('#tempo-label').textContent = `${result.song.bpm} BPM`;
      status(result.song.layout === 'piano' ? '识别完成，可以试听完整钢琴；请留意错音、节奏与连线。' : '识别完成，可以试听两种模式；请留意错音、节奏与连线。');
      try { await score.load(await requestScore(result.scoreUrl)); }
      catch {
        $('#score').textContent = '谱面暂未显示，可先试听，或刷新页面恢复结果。';
        status('试听已生成，谱面暂未显示；刷新后可恢复，不需要重新上传。', true);
      }
    } catch (error) {
      $('#result').hidden = true; status(error.message, true);
      if (error.resumable && id) $('#reconnect').hidden = false;
      else rememberTask(null, $('#layout').value);
    } finally { working = false; $('#submit').disabled = false; picker.setDisabled(false); $('#layout').disabled = false; }
  }

  $('#upload-form').addEventListener('submit', event => {
    event.preventDefault();
    if (!picker.files.length) { status('请先选择 1 至 6 张图片，或一份最多 6 页的 PDF。', true); return; }
    generate([...picker.files]);
  });
  $('#reconnect').addEventListener('click', () => { const id = lastTask($('#layout').value); if (id) generate(null, id); });

  $('#play').addEventListener('click', async () => {
    if (player.playing) { player.pause(); return; }
    $('#play').disabled = true;
    try { await player.play(); } catch (error) { status(error.message, true); }
    finally { $('#play').disabled = false; }
  });
  $('#restart').addEventListener('click', () => player.seek(0).catch(error => status(error.message, true)));
  for (const button of root.querySelectorAll('[data-mode]')) button.addEventListener('click', async () => {
    for (const tab of root.querySelectorAll('[data-mode]')) tab.setAttribute('aria-selected', String(tab === button));
    $('#mode-description').textContent = player.song?.layout === 'piano' ? '完整播放右手和左手的两行钢琴谱。' : button.dataset.mode === 'melody' ? '人声旋律与钢琴伴奏全部用钢琴演奏。' : '只播放下方钢琴双手伴奏。';
    try { await player.configure({ mode: button.dataset.mode }); } catch (error) { status(error.message, true); }
  });
  $('#tempo').addEventListener('input', event => { $('#tempo-label').textContent = `${event.target.value} BPM`; });
  $('#tempo').addEventListener('change', async event => {
    try { await player.configure({ rate: Number(event.target.value) / player.song.bpm }); }
    catch (error) { status(error.message, true); }
  });
  function applyLayout(layout) {
    $('#layout').value = layout;
    const piano = layout === 'piano';
    const full = $('[data-mode="accompaniment"]'), melody = $('[data-mode="melody"]');
    full.textContent = piano ? '完整钢琴' : '纯伴奏';
    full.setAttribute('aria-selected', 'true'); melody.setAttribute('aria-selected', 'false');
    melody.hidden = piano;
    $('#mode-description').textContent = piano ? '完整播放右手和左手的两行钢琴谱。' : '只播放下方钢琴双手伴奏。';
  }
  const picker = new PagePicker($('#image'), $('#page-list'), status);
  $('#layout').value = initialLayout;
  $('#layout').addEventListener('change', () => {
    player.pause(); $('#result').hidden = true;
    status('请选择该类型的谱图，核对页序后生成。');
  });
  if (lastTask(initialLayout)) generate(null, lastTask(initialLayout));
  return {
    pause: () => player.pause(),
    setLayout(layout) {
      if (working) { status('当前任务仍在处理，完成后可更换乐谱类型。'); return; }
      if ($('#layout').value === layout) return;
      player.pause(); $('#layout').value = layout; $('#result').hidden = true;
    },
  };
}
if (document.body.dataset.page === 'recognition') initRecognition();
