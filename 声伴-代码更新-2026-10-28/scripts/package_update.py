"""Small GitHub web-upload update: source/docs only, no keys or music originals."""
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def main():
    source = DIST / '声伴-代码提交包.zip'
    target = DIST / '声伴-本次更新'
    with ZipFile(source) as bundle:
        # Include the new visual assets; original score/audio/vendor assets stay in the repository.
        names = [name for name in bundle.namelist()
                 if (not name.startswith(('assets/', 'vendor/'))
                     or name.startswith('assets/visuals/') or name == 'assets/ATTRIBUTION.md')
                 and not Path(name).name.startswith('.')]
        if len(names) > 100:
            raise ValueError('网页上传文件数超过 100，应拆分提交')
        for name in names:
            path = target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(bundle.read(name))
    with ZipFile(DIST / '声伴-本次更新.zip', 'w', ZIP_DEFLATED) as bundle:
        for name in names:
            bundle.write(target / name, name)
    print(f'更新文件夹已生成：{len(names)} 个文件，不含密钥、上传图片或歌曲原件。')


if __name__ == '__main__':
    main()
