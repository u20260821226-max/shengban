// Immediate native clicks; subtle feedback never delays playback or transposition.
for (const [id, label] of [['main-play',null],['key-down','降半音'],['key-up','升半音']]) {
  const button = document.querySelector(`#${id}`);
  if (!button) continue;
  if (label) button.setAttribute('aria-label',label);
  button.classList.add('instant-action');
  button.addEventListener('click',()=>{
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    button.getAnimations().forEach(a=>a.cancel());
    button.animate([{transform:'scale(.95)'},{transform:'scale(1)'}],{duration:160,easing:'ease-out'});
  });
}
