// Preserve the chosen page order; sort only each newly selected batch.
export class PagePicker {
  constructor(input, list, message, onChange = () => {}, { appendInput, appendButton } = {}) {
    Object.assign(this, { input, list, message, onChange, appendInput, appendButton });
    this.files = []; this.disabled = false;
    input.addEventListener('change', () => this.select(input, false));
    appendInput?.addEventListener('change', () => this.select(appendInput, true));
    appendButton?.addEventListener('click', () => {
      if (!this.disabled) appendInput.click();
    });
  }
  select(input, append) {
    const selected = [...input.files];
    input.value = ''; // Selecting a removed file again must trigger change.
    if (this.disabled || !selected.length) return;
    const pdfs = selected.filter(file => file.type === 'application/pdf');
    if (pdfs.length && (append || selected.length !== 1) || append && this.files[0]?.type === 'application/pdf') {
      this.message('PDF 和图片不能混传。请用“重新选择全部”改选一份 PDF，或选择图片。已选文件已保留。', true); return;
    }
    if (selected.some(file => !['image/jpeg', 'image/png', 'application/pdf'].includes(file.type) || file.size > 10 * 1024 * 1024 || !file.size)) {
      this.message('请选择非空的 JPG / PNG 或 PDF，每个文件不超过 10 MB。已选文件已保留。', true); return;
    }
    const files = append ? [...this.files] : [];
    const identity = file => JSON.stringify([file.name, file.type, file.size, file.lastModified]);
    const seen = new Set(files.map(identity));
    let added = 0;
    for (const file of selected.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }))) {
      const key = identity(file);
      if (seen.has(key)) continue;
      seen.add(key); files.push(file); added++;
    }
    if (files.length > 6) {
      this.message(`一次最多 6 页，当前已选 ${this.files.length} 页。本次选择未加入，原先文件已保留。`, true); return;
    }
    if (!added) { this.message('这些文件已经选过，未重复添加。'); return; }
    this.files = files; this.render();
    this.message(pdfs.length ? 'PDF 将按文档页序自动转页，最多 6 页；请确认是同一首歌。' : `${append ? `已追加 ${added} 页，` : ''}共已添加 ${files.length} 页。${files.length < 6 ? '可继续添加，' : '已达 6 页上限，'}请用“上移／下移”核对页序后生成。`);
  }
  updateControls() {
    this.input.disabled = this.disabled;
    if (this.appendInput) this.appendInput.disabled = this.disabled;
    if (this.appendButton) this.appendButton.disabled = this.disabled || this.files.length >= 6 || this.files[0]?.type === 'application/pdf';
    for (const button of this.list.querySelectorAll('button')) button.disabled = this.disabled || button.dataset.edge === 'true';
  }
  setDisabled(value) { this.disabled = value; this.updateControls(); }
  render() {
    this.list.replaceChildren(...this.files.map((file, index) => {
      const item = document.createElement('li'), label = document.createElement('span');
      const pdf = file.type === 'application/pdf';
      label.textContent = pdf ? `PDF · ${file.name}（自动按文档页序读取）` : `第 ${index + 1} 页 · ${file.name}`;
      item.append(label);
      for (const [text, delta] of [['上移', -1], ['下移', 1], ['移除', 0]]) {
        if (pdf && delta) continue;
        const button = document.createElement('button'); button.type = 'button'; button.textContent = text;
        button.setAttribute('aria-label', `${text}第 ${index + 1} 页`);
        button.dataset.edge = String(delta !== 0 && (index + delta < 0 || index + delta >= this.files.length));
        button.addEventListener('click', () => {
          if (this.disabled) return;
          if (delta) [this.files[index], this.files[index + delta]] = [this.files[index + delta], this.files[index]];
          else this.files.splice(index, 1);
          this.render();
        });
        item.append(button);
      }
      return item;
    }));
    this.updateControls();
    this.onChange(this.files);
  }
}
