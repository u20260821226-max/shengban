"""校验运行资源，并生成网页发布包和代码提交包。仅使用 Python 标准库。"""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'


def runtime_files():
    entries = json.loads((ROOT / 'asset-list.json').read_text())
    names = {'index.html', 'sw.js', 'asset-list.json',
             'assets/ATTRIBUTION.md', 'assets/piano/LICENSE.txt',
             'vendor/OSMD-LICENSE.txt'}
    for entry in entries:
        if entry == './':
            continue
        path = (ROOT / entry).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError(f'资源不存在或路径越界：{entry}')
        names.add(path.relative_to(ROOT).as_posix())
    for name in names:
        if not (ROOT / name).is_file():
            raise ValueError(f'缺少文件：{name}')
    for path in (ROOT / 'assets/scores').glob('*.json'):
        data = json.loads(path.read_text())
        assert data['notes'] and data['measureTimes'], f'空乐谱：{path.name}'
        assert all(n['role'] in {'melody', 'accompaniment'} for n in data['notes'])
    return names


def write_zip(filename, names):
    with ZipFile(DIST / filename, 'w', ZIP_DEFLATED) as bundle:
        for name in sorted(names):
            bundle.write(ROOT / name, name)


def main():
    runtime = runtime_files()
    source = runtime | {'README.md', 'DEMO_GUIDE.md', '启动声伴.command', '.gitignore',
                        'scripts/package_demo.py', 'scripts/整理代码.command'}
    source.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'docs').glob('*.md'))
    # 后端仅打包源文件和配置模板；排除真实环境配置、数据库和上传文件。
    source.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'backend/app').glob('*.py'))
    source.update({'backend/README.md', 'backend/requirements.txt', 'backend/.env.example',
                   'PROVIDER_CONFIRMATION.md'})
    DIST.mkdir(exist_ok=True)
    write_zip('声伴-网页发布包.zip', runtime)
    write_zip('声伴-代码提交包.zip', source)
    checksums = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                 for name in sorted(runtime)}
    (DIST / '资源校验清单.json').write_text(json.dumps(checksums, ensure_ascii=False, indent=2))
    print(f'校验通过：{len(runtime)} 个运行文件；已生成网页发布包、代码提交包及校验清单。')


if __name__ == '__main__':
    main()
