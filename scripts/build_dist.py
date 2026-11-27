#!/usr/bin/env python3
"""Assemble Cordis payloads from four small wrappers and isolated native plugins."""
import argparse
from pathlib import Path
import shutil
import tempfile
from sync_plugins import ROOT, NAMES, files, atomic_write, reconcile


def payload_files(name):
    wrapper = ROOT / 'packaging/dsh' / ('dsh-' + name)
    result = files(wrapper)
    for folder in ('skills', 'rules', 'assets', 'shared'):
        base = ROOT / 'plugins' / name / folder
        result.update({Path(folder) / rel: p for rel, p in files(base).items()})
    for p in result.values():
        if p.is_symlink() or any(x.is_symlink() for x in p.parents if ROOT in x.parents):
            raise ValueError(f'Linked build input: {p}')
    return result


def build_dsh(output=None):
    differences = reconcile(False)
    if differences:raise ValueError('Run scripts/sync_plugins.py --apply before packaging: ' + str(differences))
    output = Path(output) if output is not None else ROOT / 'dist/dsh-plugins'
    if output.is_symlink():raise ValueError('Linked distribution target')
    output = output.resolve()
    # Output is controlled: refuse arbitrary populated directories without our marker.
    marker = output / '.hksop-generated'
    if output.exists() and any(output.iterdir()) and (not marker.is_file() or marker.read_text() != 'hksop-dsh-dist-v1\n'):
        raise ValueError('Unowned distribution directory: ' + str(output))
    output.mkdir(parents=True, exist_ok=True)
    if not marker.exists():atomic_write(marker, b'hksop-dsh-dist-v1\n')
    for name in NAMES:
        destination = output / ('dsh-' + name)
        wanted = payload_files(name)
        if destination.is_symlink():raise ValueError('Linked generated plugin')
        present = files(destination)
        for rel, source in wanted.items():
            dest = destination / rel
            content = source.read_bytes()
            if not dest.is_file() or dest.read_bytes() != content:atomic_write(dest, content)
            elif dest.is_symlink():raise ValueError('Linked generated file')
        for rel in present.keys() - wanted.keys():
            stale = destination / rel
            if stale.is_symlink():raise ValueError('Linked stale file')
            stale.unlink()
        if files(destination).keys() != wanted.keys():raise ValueError('Incomplete distribution')
    if not marker.exists():atomic_write(marker, b'hksop-dsh-dist-v1\n')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:print(build_dsh(args.output))
    except (OSError, ValueError) as exc:parser.exit(1, str(exc) + '\n')
