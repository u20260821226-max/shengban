import { contourMarkup } from '/motion.js';

// Animation is decoration. Stage/page messages and elapsed time come from the job.
export function mountTaskWaiting(root) {
  const scene = root.querySelector('#waiting-scene');
  scene.className = 'waiting-scene';
  scene.innerHTML = `<div class="waiting-atmosphere">${contourMarkup()}</div><p class="waiting-label">声伴 · 正在处理乐谱</p><h2>正在把乐谱变成声音</h2><p class="waiting-message" role="status"></p><div class="waiting-meta"><span class="waiting-stage"></span><span>已等待 <strong class="waiting-seconds">0</strong><small>秒</small></span></div><div class="wave-tray" aria-hidden="true">${Array.from({length:39},(_,i)=>`<i style="--wave-h:${7+Math.round(Math.abs(Math.sin(i*.62))*(21+Math.sin(i*.21)*14))}px;--wave-delay:${-i*.087}s"></i>`).join('')}</div><ol class="waiting-steps" aria-label="处理阶段">${['上传与转页','识别音符','检查节拍','准备试听'].map((s,i)=>`<li data-number="0${i+1}">${s}</li>`).join('')}</ol><div class="waiting-actions"><button type="button" class="wait-pause" aria-pressed="false">暂停动画</button></div><p class="waiting-footnote">多页乐谱可能需要数分钟。波形表示任务正在处理，不代表完成比例；无需重复提交。</p>`;
  const $ = selector => scene.querySelector(selector);
  const labels = {uploading:'上传与转页',queued:'等待处理',preparing:'整理谱图',recognizing:'识别音符',checking:'检查节拍',completed:'准备试听'};
  let timer = null, started = 0, serverSeconds = 0, stage = 'uploading', pageCount = 0;
  function tick() { $('.waiting-seconds').textContent = String(Math.max(serverSeconds, Math.floor((Date.now()-started)/1000))); }
  function update(state) {
    if(state.status) stage = state.status;
    if(Number.isFinite(state.elapsedSeconds)) serverSeconds = Math.max(serverSeconds,state.elapsedSeconds);
    if(state.pageCount) pageCount = state.pageCount;
    if(state.message) $('.waiting-message').textContent = state.message;
    $('.waiting-stage').textContent = `${labels[stage] || '正在处理'}${pageCount ? ` · 共 ${pageCount} 页` : ''}`;
    const index = {uploading:0,queued:0,preparing:0,recognizing:1,checking:2,completed:3}[stage] ?? 0;
    scene.querySelectorAll('.waiting-steps li').forEach((li,i)=>{
      li.classList.toggle('finished',i<index);
      if(i===index) li.setAttribute('aria-current','step'); else li.removeAttribute('aria-current');
    });
    tick();
    if(['completed','failed','rejected'].includes(stage)) stop();
  }
  function stop() { clearInterval(timer); timer=null; scene.classList.add('is-done'); $('.wait-pause').disabled=true; }
  function start(message) {
    clearInterval(timer); started=Date.now(); serverSeconds=0; stage='uploading'; pageCount=0;
    scene.hidden=false; scene.classList.remove('is-done','is-paused'); $('.wait-pause').disabled=false;
    $('.wait-pause').textContent='暂停动画'; $('.wait-pause').setAttribute('aria-pressed','false');
    update({status:'uploading',message}); timer=setInterval(tick,1000);
  }
  function fail(message) { stop(); $('.waiting-message').textContent=message; $('.waiting-stage').textContent='处理暂未完成'; }
  function pauseAnimation() { scene.classList.add('is-paused'); $('.wait-pause').textContent='继续动画'; $('.wait-pause').setAttribute('aria-pressed','true'); }
  $('.wait-pause').addEventListener('click',()=>{
    if(scene.classList.contains('is-paused')) { scene.classList.remove('is-paused'); $('.wait-pause').textContent='暂停动画'; $('.wait-pause').setAttribute('aria-pressed','false'); }
    else pauseAnimation();
  });
  return {start,update,fail,pauseAnimation,hide:()=>{stop();scene.hidden=true;}};
}
