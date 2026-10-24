import { MusicPlayer } from './music-player.js';
import { ScoreView } from './score-view.js';
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)];
const songs = [
  { id: 'ai-yong-zai', title: '爱永在', key: '1 个升号', measures: 16, color: 'orange' },
  { id: 'xiao-xing-yun', title: '小幸运', key: '1 个降号', measures: 31, color: 'green' },
  { id: 'you-yi-zhong-bei-shang', title: '有一种悲伤', key: '1 个升号', measures: 37, color: 'blue' },
];
let selected = songs[0], songData, busy = false, ready = false, toastTimer;
let countIn = false, loopStart = null, loopEnd = null;
const scoreView = new ScoreView($('#score-container'));
const player = new MusicPlayer(updatePlayer);
const time = s => `${Math.floor(s / 60).toString().padStart(2, '0')}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
function showToast(message) {
  $('#toast').textContent = message; $('#toast').classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('#toast').classList.remove('show'), 4000);
}
function setView(view) {
  $$('.view').forEach(el => el.classList.toggle('active', el.id === `${view}-view`));
  $$('.nav-item').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  $('.crumb').textContent = view === 'practice' ? `正在练习 / ${selected.title}` : '我的曲目 / 练习曲库';
  if (view === 'library') { player.pause(); $('#backup-audio').pause(); }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
function updatePlayer(p) {
  const duration = p.song?.duration || 0;
  $('#main-play').textContent = busy ? '…' : p.playing ? 'Ⅱ' : '▶';
  $('#main-play').setAttribute('aria-label', p.playing ? '暂停' : '播放');
  $('#main-play').disabled = busy || !ready;
  $('#progress').value = duration ? p.position / duration * 100 : 0;
  $('#elapsed').textContent = time(p.position / p.rate); $('#duration').textContent = time(Math.ceil(duration / p.rate));
  $('#position-label').textContent = duration ? `第 ${Math.max(1, p.song.measureTimes.filter(t => t <= p.position + .001).length)} / ${selected.measures} 小节` : '准备乐谱';
  $('#key-down').disabled = p.semitone <= -6 || !ready || busy;
  $('#key-up').disabled = p.semitone >= 6 || !ready || busy;
}
function renderLibrary() {
  $('.library-count').textContent = `${songs.length} 首演示曲目`;
  const filter = $('#song-search').value.trim(); $('#songs').replaceChildren();
  songs.filter(s => s.title.includes(filter)).forEach(song => {
    const row = document.createElement('article'); row.className = 'score-row';
    row.innerHTML = `<div class="score-art art-${song.color}"><span>♬</span><i></i><i></i><i></i></div><div class="score-main"><p class="score-kicker">比赛演示曲目</p><h2>${song.title}</h2><p>纯伴奏 / 三行钢琴 · ${song.measures} 小节</p></div><div class="score-meta"><span>${song.key}</span><b>♩ = 120</b></div><div class="row-actions"><button class="play-mini" aria-label="播放${song.title}">▶</button></div>`;
    row.addEventListener('click', event => openSong(song, Boolean(event.target.closest('button'))));
    $('#songs').append(row);
  });
  $('#empty-library').hidden = $('#songs').childElementCount > 0;
}
async function openSong(song, autoplay = false) {
  if (busy) return;
  busy = true; player.pause(); ready = false; selected = song; setView('practice');
  $('#practice-title').textContent = song.title;
  $('#practice-subtitle').textContent = `${song.measures} 小节 · 比赛演示曲目`;
  $('.piece-index').textContent = String(songs.indexOf(song) + 1).padStart(2, '0');
  $('#score-title').textContent = song.title;
  $('#score-message').textContent = '正在打开乐谱…'; $('#score-message').hidden = false;
  $('#score-container').hidden = true;
  $('#tempo').value = 120; $('#tempo-readout').textContent = '120 BPM';
  $('#semitone').textContent = '0'; $('#key-readout').textContent = '原调'; $('#score-key-label').textContent = song.key;
  loopStart = loopEnd = null; player.loop = null; updateLoop(); setBackup(); updatePlayer(player);
  try {
    const response = await fetch(`assets/scores/${song.id}.json`);
    if (!response.ok) throw new Error('曲目文件未找到');
    songData = await response.json(); await player.load(songData);
    const firstMelody = songData.notes.find(note => note.role === 'melody');
    if (firstMelody) {
      const entryMeasure = songData.measureTimes.filter(t => t <= firstMelody.time + .001).length;
      $('#practice-subtitle').textContent = `${song.measures} 小节 · 主旋律从第 ${entryMeasure} 小节进入`;
    }
    player.mode = $('.track-tab.active').dataset.track;
    $('#score-container').hidden = false;
    await scoreView.load(`assets/scores/${song.id}.musicxml`);
    $('#score-message').hidden = true; ready = true;
  } catch (error) {
    $('#score-message').textContent = `${error.message}。请返回曲库重试，或使用备用音频。`;
    $('#score-message').hidden = false;
  } finally { busy = false; updatePlayer(player); }
  if (autoplay && ready) togglePlay();
}
async function togglePlay() {
  if (busy || !ready) return;
  $('#backup-audio').pause();
  if (player.playing) { player.pause(); return; }
  busy = true; updatePlayer(player);
  try { await player.play(countIn); } catch (e) { showToast(e.message || '播放失败，请使用备用音频'); }
  finally { busy = false; updatePlayer(player); }
}
function setBackup() {
  $('#backup-audio').src = `assets/audio/${selected.id}-${$('.track-tab.active').dataset.track}.mp3`;
}
async function configure(values) {
  try { await player.configure(values); } catch (e) { player.pause(); showToast(e.message); }
}
$$('.track-tab').forEach(tab => tab.addEventListener('click', async () => {
  if (busy) return;
  $$('.track-tab').forEach(el => { el.classList.toggle('active', el === tab); el.setAttribute('aria-selected', String(el === tab)); });
  $('#track-description').textContent = tab.dataset.track === 'melody' ? '三行全部用钢琴演奏：主旋律 + 双手伴奏。' : '只播放下面两行钢琴伴奏，关闭最上方主旋律。';
  setBackup(); await configure({ mode: tab.dataset.track });
}));
async function transpose(change) {
  if (!ready || busy) return;
  const semitone = Math.max(-6, Math.min(6, player.semitone + change)); busy = true; updatePlayer(player);
  try {
    await configure({ semitone }); scoreView.transpose(semitone);
    $('#semitone').textContent = semitone > 0 ? `+${semitone}` : semitone;
    const label = semitone ? `${semitone > 0 ? '升' : '降'} ${Math.abs(semitone)} 半音` : '原调';
    $('#key-readout').textContent = label; $('#score-key-label').textContent = semitone ? label : selected.key;
  } catch { player.pause(); showToast('谱面移调失败，请返回曲库重试'); }
  finally { busy = false; updatePlayer(player); }
}
function updateLoop() {
  $('#loop-a').textContent = loopStart === null ? '设置 A 点' : `A ${time(loopStart)}`;
  $('#loop-b').textContent = loopEnd === null ? '设置 B 点' : `B ${time(loopEnd)}`;
  $('#loop-b').disabled = loopStart === null; $('#loop-clear').hidden = loopStart === null;
  $('#loop-status').textContent = player.loop ? 'A–B 循环已开启' : loopStart !== null ? '移动进度到结束位置，再设置 B 点' : '选择播放位置，设置循环起止点';
}
$('#loop-a').addEventListener('click', () => { if (!ready) return; loopStart = player.currentPosition(); loopEnd = null; player.loop = null; updateLoop(); });
$('#loop-b').addEventListener('click', () => {
  const end = player.currentPosition(); if (end <= loopStart + .25) return showToast('B 点需要在 A 点之后，请先移动播放进度');
  loopEnd = end; player.loop = { start: loopStart, end }; updateLoop();
});
$('#loop-clear').addEventListener('click', () => { loopStart = loopEnd = null; player.loop = null; updateLoop(); });
$('#count-toggle').addEventListener('click', () => { countIn = !countIn; $('#count-toggle').classList.toggle('active', countIn); $('#count-toggle').setAttribute('aria-pressed', String(countIn)); });
$('#main-play').addEventListener('click', togglePlay);
$('#key-up').addEventListener('click', () => transpose(1)); $('#key-down').addEventListener('click', () => transpose(-1));
$('#tempo').addEventListener('change', event => { if (!busy) configure({ rate: Number(event.target.value) / (songData?.bpm || 120) }); });
$('#tempo').addEventListener('input', event => { $('#tempo-readout').textContent = `${event.target.value} BPM`; });
$('#progress').addEventListener('input', event => { if (ready) player.seek(Number(event.target.value) / 100 * songData.duration).catch(() => showToast('跳转失败，请重新播放')); });
$('#restart').addEventListener('click', () => { if (ready) player.seek(player.loop?.start || 0); });
for (const [id, direction] of [['prev', -1], ['next', 1]]) $(`#${id}`).addEventListener('click', () => {
  if (!ready) return; const positions = songData.measureTimes, now = player.currentPosition();
  const target = direction < 0 ? [...positions].reverse().find(t => t < now - .15) ?? 0 : positions.find(t => t > now + .15) ?? songData.duration;
  player.seek(target).catch(() => showToast('跳转失败，请重新播放'));
});
$('#backup-audio').addEventListener('play', () => player.pause());
$$('[data-view]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.view === 'practice' && !songData) openSong(selected); else setView(button.dataset.view);
}));
$('#song-search').addEventListener('input', renderLibrary);
$('#show-rights').addEventListener('click', () => $('#rights-dialog').showModal());
$$('[data-close]').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$$('[data-import]').forEach(button => button.addEventListener('click', () => $('#import-dialog').showModal()));
renderLibrary();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => showToast('离线缓存未启用，联网时仍可播放'));
