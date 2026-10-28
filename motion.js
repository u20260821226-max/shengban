// Independent enhancements: visual motion never changes playback or task data.
const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

export function contourMarkup() {
  const shape = 'M-80 110C-10 20 100 50 145 5S275-10 300 70 435 45 460 150 385 220 285 235 180 325 85 270-140 220-80 110Z';
  const colors = ['#263d36','#345346','#446a54','#65886a','#93ab83','#bbca9b'];
  return `<svg class="contour-field" viewBox="0 0 440 290" fill="none" aria-hidden="true"><g class="contour-group">${colors.map((color, i) => `<path d="${shape}" fill="${color}" transform="translate(${220 * (i * .105)} ${145 * (i * .105)}) scale(${1 - i * .105})"/>`).join('')}</g><g class="contour-group contour-secondary" opacity=".35"><path d="M300 170C280 130 360 95 400 125S460 180 410 210 325 220 300 170Z" fill="#a9bd91"/></g></svg>`;
}

export function decorateSpeed(root = document) {
  const input = root.querySelector('#tempo');
  const source = root.querySelector('#tempo-readout, #tempo-label');
  if (!input || !source || input.dataset.motionReady) return;
  input.dataset.motionReady = 'true'; input.classList.add('tempo-slider');
  const output = document.createElement('span');
  output.className = 'tempo-roller'; output.setAttribute('aria-hidden', 'true');
  const digits = document.createElement('span'); digits.className = 'digit-strip';
  const unit = document.createElement('small'); unit.textContent = 'BPM'; output.append(digits, unit);
  source.classList.add('visually-hidden'); source.after(output);
  let previous = '';
  function refresh() {
    const value = String(parseInt(source.textContent) || Number(input.value));
    input.style.setProperty('--range-fill', `${(Number(input.value) - Number(input.min)) / (Number(input.max) - Number(input.min)) * 100}%`);
    input.setAttribute('aria-valuetext', `${input.value} BPM`);
    if (previous === value) return;
    const direction = Number(value) < Number(previous) ? -1 : 1;
    digits.style.setProperty('--digit-enter', `${direction * 100}%`);
    digits.style.setProperty('--digit-exit', `${direction * -100}%`);
    digits.replaceChildren(...Array.from(value, (digit, index) => {
      const cell = document.createElement('span'); cell.className = 'digit';
      const current = document.createElement('span'); current.textContent = digit;
      const old = previous.padStart(value.length, ' ')[index];
      if (previous && old !== digit && !reduceMotion()) {
        const leaving = document.createElement('span'); leaving.className = 'digit-old'; leaving.textContent = old;
        current.className = 'digit-new'; cell.append(leaving);
        leaving.addEventListener('animationend', () => leaving.remove(), { once: true });
      }
      cell.append(current); return cell;
    }));
    previous = value;
  }
  new MutationObserver(refresh).observe(source, { childList: true, characterData: true, subtree: true });
  input.addEventListener('input', refresh); refresh();
}

if (document.querySelector('#tempo-readout')) {
  decorateSpeed();
  const art = document.querySelector('.library-art'); if (art) art.innerHTML = contourMarkup();
}
