// Network and recovery state are separate from score rendering and playback.
const STORAGE_KEY = 'shengban.recognition.last-task';
const TOKEN_KEY = 'shengban.recognition.browser-token';

function browserToken() {
  let token = localStorage.getItem(TOKEN_KEY);
  if (!/^[a-f0-9]{64}$/.test(token || '')) {
    token = [...crypto.getRandomValues(new Uint8Array(32))].map(n => n.toString(16).padStart(2, '0')).join('');
    localStorage.setItem(TOKEN_KEY, token);
  }
  return token;
}

export async function requestScore(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(url, { headers: { 'X-Recognition-Token': browserToken() }, cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error('谱面暂未取得');
    return await response.text();
  } finally { clearTimeout(timer); }
}

export function rememberTask(id, layout = 'vocal') {
  const key = layout === 'piano' ? STORAGE_KEY + '.piano' : STORAGE_KEY;
  try { id ? localStorage.setItem(key, id) : localStorage.removeItem(key); } catch {}
}

export function lastTask(layout = 'vocal') {
  try {
    const id = localStorage.getItem(layout === 'piano' ? STORAGE_KEY + '.piano' : STORAGE_KEY);
    return /^[a-f0-9]{32}$/.test(id || '') ? id : null;
  } catch { return null; }
}

export async function requestJson(url, options = {}, timeout = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, headers: { ...options.headers, 'X-Recognition-Token': browserToken() }, cache: 'no-store', signal: controller.signal });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.message || '请求未完成，请重试。');
      error.httpStatus = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error.httpStatus) throw error;
    const failure = new Error('暂时无法连接识谱服务，任务可能仍在处理。可继续查看或稍后重试。');
    failure.resumable = true;
    throw failure;
  } finally { clearTimeout(timer); }
}

export async function watchTask(id, onUpdate) {
  const started = Date.now();
  let deadline = started + 360000;
  let networkFailures = 0;
  while (Date.now() < deadline) {
    let result;
    try {
      result = await requestJson(`/api/recognition/${id}`);
      deadline = started + Math.max(360000, Math.min(6, result.pageCount || 1) * 330000 + 60000);
      networkFailures = 0;
    } catch (error) {
      if (error.resumable && ++networkFailures < 4) {
        onUpdate({ message: '连接暂时中断，正在重新连接原任务…' });
        await new Promise(resolve => setTimeout(resolve, 1500));
        continue;
      }
      throw error;
    }
    onUpdate(result);
    if (result.status === 'completed') return result;
    if (['failed', 'rejected'].includes(result.status)) throw new Error(result.message);
    await new Promise(resolve => setTimeout(resolve, 900));
  }
  const error = new Error('页面等待已超时，可点击“继续查看任务”获取最终状态，不必重复生成。');
  error.resumable = true;
  throw error;
}
