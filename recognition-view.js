// Mount the upload tool in the app; Shadow DOM isolates its controls and CSS.
export async function mountRecognition(container, layout) {
  const response = await fetch('/labs/recognition.html', { cache: 'no-store' });
  if (!response.ok) throw new Error('上传界面暂未加载，请重试。');
  const document = new DOMParser().parseFromString(await response.text(), 'text/html');
  const main = document.querySelector('.lab-main');
  if (!main) throw new Error('上传界面暂未加载，请重试。');
  const { initRecognition } = await import('/labs/recognition.js');
  const shadow = container.shadowRoot || container.attachShadow({ mode: 'open' });
  shadow.replaceChildren();
  for (const href of ['/styles.css', '/labs/recognition.css']) {
    const link = window.document.createElement('link'); link.rel = 'stylesheet'; link.href = href;
    shadow.append(link);
  }
  shadow.append(main);
  return initRecognition(shadow, layout);
}
