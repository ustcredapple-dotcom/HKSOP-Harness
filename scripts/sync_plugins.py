#!/usr/bin/env python3
"""Check or refresh the explicit, zero-build runtime distribution map (strategy B)."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('hksop-step1-optics', 'hksop-step2-board', 'hksop-custom-part', 'hksop-step3-manufacture')
IGNORE = {'__pycache__', '.DS_Store'}


def files(folder):
    return {p.relative_to(folder): p for p in folder.rglob('*')
            if p.is_file() and not IGNORE.intersection(p.parts)
            and not p.name.startswith('._') and p.suffix != '.pyc'}


def distribution_map():
    """Destination -> authoring source; this is also the duplicate-file allowlist."""
    result = {}
    for i, skill in enumerate(('optics-graph-design', 'board-auto-layout')):
        base = Path('plugins') / NAMES[i] / 'skills' / skill / 'scripts'
        for package in ('optical_graph', 'optical_layout') if i == 1 else ('optical_graph',):
            for rel in files(ROOT / 'src' / package):
                result[base / package / rel] = Path('src') / package / rel
        result[base / 'optical_graph_render.py'] = Path('scripts/optical_graph_render.py')
        if i == 1:
            result[base / 'optical_graph_to_board.py'] = Path('scripts/optical_graph_to_board.py')
    for i, skill in ((2, 'library-intake'), (3, 'json-to-3d-verify')):
        result[Path('plugins') / NAMES[i] / 'skills' / skill / 'scripts/hksop_runtime.py'] = Path('src/optical_layout/hksop_runtime.py')
    for name in NAMES:
        result[Path('plugins') / name / '.codex-plugin/plugin.json'] = Path('plugins') / name / 'plugin.json'
    for name in NAMES[2:]:
        result[Path('plugins') / name / 'shared/library-policy.md'] = Path('docs/library-policy.md')
    result[Path('plugins/hksop-custom-part/skills/custom-part-cad/references/drawing-standard.md')] = Path('plugins/hksop-step3-manufacture/skills/export-packages/references/drawing-standard.md')
    return result


def atomic_write(dest, content):
    if dest.is_symlink() or any(p.is_symlink() for p in dest.parents if p != ROOT.parent):
        raise ValueError(f'Link in managed payload: {dest}')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
        tmp.write(content)
    os.chmod(tmp.name, 0o644)
    os.replace(tmp.name, dest)


def reconcile(apply):
    differences = []
    def match(dest, content):
        if dest.is_symlink():
            raise ValueError(f'Link in bundled payload: {dest.relative_to(ROOT)}')
        if dest.is_file() and dest.read_bytes() == content:
            return
        differences.append(dest.relative_to(ROOT))
        if apply:
            atomic_write(dest, content)
    def encoded(value):
        return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    version = json.loads((ROOT / 'packaging/release.json').read_bytes())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid release version')
    expected = {}
    for name in NAMES:
        p = ROOT / 'plugins' / name / 'plugin.json'
        meta = json.loads(p.read_bytes()); meta['version'] = version
        expected[p.relative_to(ROOT)] = encoded(meta)
        match(p, expected[p.relative_to(ROOT)])
        p = ROOT / 'packaging/dsh' / ('dsh-' + name) / 'package.json'
        package = json.loads(p.read_bytes()); package['version'] = version
        package['description'] = meta['description']
        if name in NAMES[2:] and 'shared' not in package['files']:
            package['files'].append('shared')
        match(p, encoded(package))
    p = ROOT / 'compatibility.json'; compatibility = json.loads(p.read_bytes()); compatibility['version'] = version
    match(p, encoded(compatibility))
    p = ROOT / 'pyproject.toml'
    match(p, re.sub(r'(?m)^version = "[^"]+"$', f'version = "{version}"', p.read_text()).encode())
    mapping = distribution_map()
    for dest, source in mapping.items():
        src = ROOT / source
        if src.is_symlink():raise ValueError(f'Linked authoring source: {source}')
        match(ROOT / dest, expected.get(source, src.read_bytes()))
    # Extra engine files are drift too. Never silently delete a developer's file.
    for base in (ROOT / 'plugins').glob('*/skills/*/scripts'):
        for package in ('optical_graph', 'optical_layout'):
            for rel in files(base / package):
                dest = (base / package / rel).relative_to(ROOT)
                if dest not in mapping:raise ValueError(f'Unregistered runtime file: {dest}')
    return differences


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true'); mode.add_argument('--apply', action='store_true')
    args = p.parse_args()
    try:
        changes = reconcile(args.apply)
    except (OSError, ValueError) as exc:
        p.exit(1, str(exc) + '\n')
    if changes and not args.apply:
        sys.exit('Out of sync:\n' + '\n'.join(map(str, changes)))
    print(f'{len(changes)} updated' if args.apply else 'Controlled runtimes, derived manifests and release versions match.')
