#!/usr/bin/env python3
"""Validate standalone assets, bilingual completeness, branding and export dimensions."""
import base64
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_showcase import page,LOGO,SCHEMATIC,SCHEMATIC_COVER,ASSEMBLY,NAMES

class Document(HTMLParser):
    def __init__(self):super().__init__();self.tags=[]
    def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))

def main():
    source=(ROOT/'docs/index.html').read_text();assert source==page(),'Generated HTML differs from sources'
    doc=Document();doc.feed(source)
    d=json.loads((ROOT/'docs/showcase.i18n.json').read_bytes());assert set(d)=={'zh','en'} and set(d['zh'])==set(d['en'])
    keys=[]
    for tag,attrs in doc.tags:
        for attribute in ('data-i18n','data-i18n-alt','data-i18n-aria'):
            if attribute in attrs:keys.append(attrs[attribute])
        if tag=='img':assert attrs.get('src','').startswith('data:image/'),'External image dependency'
        if tag=='script':assert 'src' not in attrs,'External script dependency'
        if tag=='link':assert attrs.get('rel')!='stylesheet','External stylesheet dependency'
    assert all(d[lang].get(key) for lang in d for key in keys),'Incomplete UI translation'
    # English UI prose contains no leftover Chinese, except the language selector itself.
    assert not any(re.search('[\u3400-\u9fff]',v) for v in d['en'].values())
    expected=[LOGO,SCHEMATIC,ASSEMBLY]+[Path('plugins')/name/'assets/logo.svg' for name in NAMES]+[Path(f'docs/assets/manrope-{w}.woff') for w in (400,800)]
    embedded=re.findall(r'data:(?:image/[a-zA-Z0-9+.-]+|font/[a-zA-Z0-9+.-]+);base64,([A-Za-z0-9+/=]+)',source)
    digest=lambda b:hashlib.sha256(b).hexdigest()
    assert len(embedded)==len(expected) and {digest(base64.b64decode(v,validate=True)) for v in embedded}=={digest((ROOT/p).read_bytes()) for p in expected},'Unregistered or modified embedded asset'
    brand=json.loads((ROOT/LOGO.parent/'manifest.json').read_bytes())
    assert next(f['sha256'] for f in brand['files'] if f['path']==LOGO.name)==digest((ROOT/LOGO).read_bytes())
    logo=ET.parse(ROOT/LOGO).getroot();assert logo.attrib['viewBox']=='0 0 1943 460'
    manifest=json.loads((ROOT/'docs/assets/cover-manifest.json').read_bytes())
    for p,h in manifest['inputs'].items():assert digest((ROOT/p).read_bytes())==h,('Stale cover input',p)
    for lang in ('zh','en'):
        path=ROOT/f'docs/assets/cover-{lang}.svg';svg=ET.parse(path).getroot();assert svg.attrib['viewBox']=='0 0 1280 640'
        assert manifest['svg'][path.name]==digest(path.read_bytes())
        image_hashes=[]
        for image in svg.iter('{http://www.w3.org/2000/svg}image'):
            url=image.attrib['{http://www.w3.org/1999/xlink}href'];assert url.startswith('data:image/')
            image_hashes.append(digest(base64.b64decode(url.split(',',1)[1],validate=True)))
        assert set(image_hashes)=={digest((ROOT/p).read_bytes()) for p in (LOGO,SCHEMATIC_COVER,ASSEMBLY)}
        png=path.with_suffix('.png').read_bytes();assert png[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',png[16:24])==(2560,1280)
        assert manifest['png'][path.with_suffix('.png').name]==digest(png)
    derivative=manifest['schematicDerivative']
    assert derivative['source']==str(SCHEMATIC) and derivative['output']==str(SCHEMATIC_COVER)
    assert struct.unpack('>I',(ROOT/SCHEMATIC_COVER).read_bytes()[16:20])[0]==1640
    for filename,lang in [('README.md','zh'),('README.en.md','en')]:
        text=(ROOT/filename).read_text();assert f'docs/assets/cover-{lang}.png' in text
        assert ('README.en.md' if lang=='zh' else 'README.md') in text
    print(f'PASS {len(set(keys))} bilingual UI keys, {len(expected)} embedded canonical assets, original logo, two 1280×640 SVGs and two 2560×1280 PNGs')

if __name__=='__main__':main()
