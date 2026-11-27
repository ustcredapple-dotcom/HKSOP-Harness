#!/usr/bin/env python3
"""Adversarial checks for dedup gates, isolated resources, cache protection and DSH builds."""
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from unittest.mock import patch
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from sync_plugins import NAMES, distribution_map, files
from build_dist import build_dsh
from install_plugins import sync_codex_plugin_cache, signature
from redundancy_audit import audit_files, long_overlap, self_repetition, dsh_prompt_contract


def rejected(call, label):
    try:call()
    except ValueError:return
    raise AssertionError('Gate accepted '+label)


def main():
    rejected(lambda:audit_files({'a/item.md':b'evidence','b/copy.md':b'evidence'},{},{}),'an unregistered byte copy')
    rejected(lambda:audit_files({'a/rule.md':b'one','b/rule.md':b'two'},{},{}),'same-name semantic drift')
    source=bytes(range(200))
    assert audit_files({'src/engine.py':source,'plugin/engine.py':source},{Path('plugin/engine.py'):Path('src/engine.py')},{})['redundantCopies']==1
    paragraph='This controlled instruction specifies optical datums, verified mechanical coordinates and the exact handoff evidence for manufacturing. '
    assert long_overlap('rules\n'+paragraph,'skill\n'+paragraph) and self_repetition(paragraph+'\n'+paragraph)
    assert not long_overlap('short common heading','short common heading')
    assert not self_repetition(paragraph)
    # Every installed Markdown reference resolves inside the same plugin; no sibling plugin dependency.
    links=0
    for name in NAMES:
        root=(ROOT/'plugins'/name).resolve()
        for p in root.rglob('*.md'):
            for url in re.findall(r'\]\(([^)]+)\)',p.read_text()):
                if re.match(r'[a-z]+:|#',url):continue
                target=(p.parent/url.split('#')[0]).resolve()
                assert target.exists(),(p,url)
                assert target==root or root in target.parents,(p,'external installed reference',url)
                links+=1
    with tempfile.TemporaryDirectory(prefix='hksop-packaging-') as td:
        base=Path(td).resolve()
        dest=build_dsh(base/'payload')
        first=dest/('dsh-'+NAMES[0]);(first/'stale.txt').write_text('obsolete')
        build_dsh(dest);assert not (first/'stale.txt').exists()
        prompts=dsh_prompt_contract(dest);assert prompts==6
        unrelated=base/'unrelated';unrelated.mkdir();(unrelated/'precious').write_text('keep')
        rejected(lambda:build_dsh(unrelated),'an unowned populated directory')
        assert (unrelated/'precious').read_text()=='keep'
        link=base/'linked';link.symlink_to(unrelated,target_is_directory=True)
        rejected(lambda:build_dsh(link),'a linked distribution target')
        home=base/'home';home.mkdir()
        with patch.object(Path,'home',return_value=home):
            sync_codex_plugin_cache(ROOT/'plugins',{},False,False)
            assert not list(home.iterdir()),'cache dry-run wrote files'
            sync_codex_plugin_cache(ROOT/'plugins',{},True,False)
            for name in NAMES:
                version=json.loads((ROOT/'plugins'/name/'plugin.json').read_bytes())['version']
                assert signature(home/'.codex/plugins/cache/hksop-local'/name/version)==signature(ROOT/'plugins'/name)
            cache=home/'.codex/plugins/cache/hksop-local'/NAMES[0]/version
            edited=cache/'keep-user-edit.txt';edited.write_text('uncommitted user work')
            rejected(lambda:sync_codex_plugin_cache(ROOT/'plugins',{},True,True),'locally edited Codex cache')
            assert edited.read_text()=='uncommitted user work'
    print(f'PASS packaging adversarial gates, {links} isolated reference links, {prompts} runtime prompts, Codex cache dry-run/copy/edit protection')


if __name__=='__main__':main()
