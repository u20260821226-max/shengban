"""Explicit allowlist: no private originals, credentials, job inputs or local tools."""
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from package_demo import runtime_files


def main():
    target = ROOT / 'dist/shengban-server.tar.gz'
    target.parent.mkdir(exist_ok=True)
    runtime = runtime_files() | {'recognition-config.json'}
    runtime.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'labs').glob('recognition.*'))
    source = {'backend/public_api.py', 'backend/public_limits.py', 'backend/public_requirements.txt'}
    source.update(p.relative_to(ROOT).as_posix() for p in (ROOT / 'backend/omr').glob('*.py'))
    with tarfile.open(target, 'w:gz') as bundle:
        for name in sorted(runtime):
            bundle.add(ROOT / name, arcname='site/' + name)
        for name in sorted(source):
            bundle.add(ROOT / name, arcname='app/' + name)
        for path in (ROOT / 'deploy').iterdir():
            if path.is_file():
                bundle.add(path, arcname='deploy/' + path.name)
    print(f'Created {target.name}: {len(runtime)} web files, {len(source)} source files')


if __name__ == '__main__':
    main()
