#!/usr/bin/env python3
"""Reject unregistered copies, ambiguous same-name documents and prompt double injection."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import os
from sync_plugins import ROOT, NAMES, distribution_map


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized(text):
    return re.sub(r'\s+', '', text)


def long_overlap(a, b, width=120):
    a, b = normalized(a), normalized(b)
    windows = {a[i:i+width] for i in range(max(0, len(a)-width+1))}
    return any(b[i:i+width] in windows for i in range(max(0, len(b)-width+1)))


def self_repetition(text, width=120):
    text = normalized(text)
    seen = {}
    for i in range(max(0, len(text)-width+1)):
        window = text[i:i+width]
        if window in seen and i-seen[window] >= width:return True
        seen.setdefault(window, i)
    return False


def audit_files(contents, mapping, exceptions):
    groups, basenames = defaultdict(list), defaultdict(list)
    for path, content in contents.items():
        groups[sha(content)].append(path)
        basenames[Path(path).name].append(path)
    canonical = lambda name: str(mapping.get(Path(name), Path(name)))
    for names in groups.values():
        if len(names) > 1 and len({canonical(p) for p in names}) != 1:
            raise ValueError('Unregistered identical files: ' + ', '.join(sorted(names)))
    for basename, paths in basenames.items():
        if len(paths) < 2 or len({sha(contents[p]) for p in paths}) == 1:continue
        origins = {canonical(p) for p in paths}
        if len(origins) == 1:continue
        exception = exceptions.get(basename, {})
        if not exception.get('reason') or origins != set(exception.get('sources', [])):
            raise ValueError('Same-name semantic drift; merge or rename: ' + basename + ': ' + ', '.join(sorted(origins)))
    return dict(files=len(contents), bytes=sum(map(len, contents.values())),
                duplicateGroups=sum(len(v)>1 for v in groups.values()),
                redundantCopies=sum(len(v)-1 for v in groups.values()),
                duplicateBytes=sum((len(v)-1)*len(contents[v[0]]) for v in groups.values()))


def instruction_contract():
    for name in NAMES:
        root = ROOT / 'plugins' / name
        rules = (root / 'rules/AGENTS.md').read_text()
        for skill in (root / 'skills').glob('*/SKILL.md'):
            if long_overlap(rules, skill.read_text()):
                raise ValueError('Rules injected twice: ' + str(skill.relative_to(ROOT)))


def dsh_prompt_contract(root):
    node = os.environ.get('HKSOP_NODE') or shutil.which('node')
    if not node:raise ValueError('Node is required for the Cordis runtime prompt gate')
    code = '''import {pathToFileURL} from 'node:url';
const rows=[];const plugin=await import(pathToFileURL(process.argv[1]).href);
plugin.apply({skills:{register(definition){rows.push(definition)}}});
console.log(JSON.stringify({name:plugin.name,inject:plugin.inject,rows}));'''
    count=0
    for name in NAMES:
        folder = root / ('dsh-' + name)
        result = subprocess.run([node, '--input-type=module', '-e', code, str(folder/'lib/index.js')],
                                check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        skills = {p.name for p in (folder/'skills').iterdir() if p.is_dir()}
        if data['name'] != folder.name or data['inject'] != ['skills'] or {r['name'] for r in data['rows']} != skills:
            raise ValueError('Cordis runtime registration differs from package contract')
        if len(data['rows']) != len(skills):raise ValueError('Duplicate skill registration')
        rules = (folder/'rules/AGENTS.md').read_text().strip()
        for row in data['rows']:
            base = folder/'skills'/row['name']
            if Path(row['resourceBase']['path']) != base or Path(row['path']) != base/'SKILL.md':
                raise ValueError('Cordis resources escape their isolated skill')
            if row['content'].count(rules) != 1 or self_repetition(row['content']):
                raise ValueError('Cordis prompt contains repeated long instructions: ' + row['name'])
            count+=1
    return count


def run_audit(paths):
    contents={str(p): (ROOT/p).read_bytes() for p in paths}
    exceptions=json.loads((ROOT/'packaging/semantic-names.json').read_bytes())
    metrics=audit_files(contents, distribution_map(), exceptions)
    instruction_contract()
    return metrics
