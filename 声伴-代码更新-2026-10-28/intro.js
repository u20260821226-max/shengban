import { contourMarkup } from './motion.js';
const letters = Array.from('SHENGBAN');
const overlay = document.createElement('section');
overlay.className = 'opening-scene'; overlay.hidden = true;
overlay.setAttribute('aria-label', '声伴开场');
overlay.innerHTML = `<div class="opening-contours" aria-hidden="true">${contourMarkup()}</div><div class="opening-center"><p>声 伴</p><div class="opening-word" aria-label="SHENGBAN">${letters.map((s,i)=>`<span aria-hidden="true" style="--letter:${i}">${s}</span>`).join('')}</div><p class="opening-caption">让旋律响起，让心绪有回声。</p></div><button class="opening-skip">走进声伴 <span aria-hidden="true">→</span></button>`;
document.body.append(overlay);
function close() {
  overlay.hidden = true;
  document.querySelector('.app-shell').inert = false;
  document.querySelector('.brand')?.focus({preventScroll:true});
}
function play() {
  overlay.hidden = false;
  overlay.classList.remove('is-playing'); void overlay.offsetWidth; overlay.classList.add('is-playing');
  document.querySelector('.app-shell').inert = true;
  overlay.querySelector('button').focus({preventScroll:true});
  // Keep the entrance visible after the animation; enter only by explicit action.
}
overlay.querySelector('button').addEventListener('click', close);
overlay.addEventListener('keydown', e => { if(e.key === 'Escape') close(); });

play();
