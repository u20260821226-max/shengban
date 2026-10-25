// Explicit order is visible before submission; never trust a file picker's order.
export class PagePicker {
  constructor(input, list, message) {
    this.input = input; this.list = list; this.message = message; this.files = [];
    input.addEventListener('change', () => {
      const files = [...input.files].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN', { numeric: true }));
      if (files.length > 6 || files.some(f => !['image/jpeg', 'image/png'].includes(f.type) || f.size > 10 * 1024 * 1024)) {
        this.files = []; input.value = ''; this.render();
        message('请选择 1 至 6 张 JPG / PNG，每张不超过 10 MB。', true); return;
      }
      this.files = files; this.render();
      message('请核对下方页序，可用“上移／下移”调整，再开始生成。');
    });
  }
  setDisabled(value) {
    this.input.disabled = value;
    for (const button of this.list.querySelectorAll('button')) button.disabled = value || button.dataset.edge === 'true';
  }
  render() {
    this.list.replaceChildren(...this.files.map((file, index) => {
      const item = document.createElement('li'), label = document.createElement('span');
      label.textContent = `第 ${index + 1} 页 · ${file.name}`;
      item.append(label);
      for (const [text, delta] of [['上移', -1], ['下移', 1], ['移除', 0]]) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = text;
        button.setAttribute('aria-label', `${text}第 ${index + 1} 页`);
        button.dataset.edge = String(delta !== 0 && (index + delta < 0 || index + delta >= this.files.length));
        button.disabled = button.dataset.edge === 'true';
        button.addEventListener('click', () => {
          if (delta) [this.files[index], this.files[index + delta]] = [this.files[index + delta], this.files[index]];
          else this.files.splice(index, 1);
          if (!this.files.length) this.input.value = '';
          this.render();
        });
        item.append(button);
      }
      return item;
    }));
  }
}
