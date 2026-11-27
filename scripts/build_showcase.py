#!/usr/bin/env python3
"""Build the offline showcase; optional outlined covers need fontTools and a CJK font."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
LOGO=Path('plugins/hksop-step3-manufacture/skills/export-packages/references/logo/hksop-logo-mono.svg')
NAMES=('hksop-step1-optics','hksop-step2-board','hksop-custom-part','hksop-step3-manufacture')
SCHEMATIC=Path('examples/pm-fiber-1x3-532/schematic.svg')
ASSEMBLY=Path('examples/pm-fiber-1x3-532/assembly-preview.png')

def data(path,mime):
    return 'data:'+mime+';base64,'+base64.b64encode((ROOT/path).read_bytes()).decode()

def page():
    content=(ROOT/'docs/showcase.template.html').read_text()
    version=json.loads((ROOT/'packaging/release.json').read_bytes())['version']
    translations=json.loads((ROOT/'docs/showcase.i18n.json').read_bytes())
    if set(translations['zh'])!=set(translations['en']):raise ValueError('Incomplete translation keys')
    outputs=('schematic.svg / trace.json','.zzoptics.json / custom-wishes.json','cad-tasks.json / STEP / 2D','assembly.step / 2 ZIPs')
    cards=[]
    for i,name in enumerate(NAMES):
        cards.append(f'''<details class="stage{' custom' if i==2 else ''}"><summary><div class="stage-head"><img src="{data(Path('plugins')/name/'assets/logo.svg','image/svg+xml')}" width="128" height="128" data-i18n-alt="stage{i}_alt"><span class="step mono" data-i18n="stage{i}_badge"></span></div><h3 data-i18n="stage{i}_title"></h3><span class="package mono">{name}</span><p data-i18n="stage{i}_description"></p><div class="outputs mono">{outputs[i]}</div><div class="gate" data-i18n="stage{i}_gate"></div></summary><div class="detail" data-i18n="stage{i}_detail"></div></details>''')
    tokens={'VERSION':version,'STAGES':'\n'.join(cards),'I18N':json.dumps(translations,ensure_ascii=False,separators=(',',':')),'LOGO':data(LOGO,'image/svg+xml'),'SCHEMATIC':data(SCHEMATIC,'image/svg+xml'),'ASSEMBLY':data(ASSEMBLY,'image/png')}
    for weight in (400,800):tokens['FONT'+str(weight)]=data(Path(f'docs/assets/manrope-{weight}.woff'),'font/woff')
    for key,value in tokens.items():content=content.replace('@@'+key+'@@',value)
    if re.search(r'@@[A-Z0-9]+@@',content):raise ValueError('Unresolved template token')
    # Each asset is embedded once. The standalone page makes no resource requests.
    return content


def covers(cjk_font, cjk_index=0):
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    fonts={w:TTFont(ROOT/f'docs/assets/manrope-{w}.woff') for w in (400,800)}
    cjk=TTFont(cjk_font,fontNumber=cjk_index)
    inputs=[LOGO,SCHEMATIC,ASSEMBLY,Path('docs/showcase.i18n.json'),Path('packaging/release.json')]+[Path(f'docs/assets/manrope-{w}.woff') for w in (400,800)]
    version=json.loads((ROOT/'packaging/release.json').read_bytes())['version']
    rows={}
    for lang in ('zh','en'):
        bits=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1280" height="640" viewBox="0 0 1280 640" role="img" aria-labelledby="cover-title cover-desc">',
        '<title id="cover-title">HKSOP Harness — '+('从光路图到制造交付' if lang=='zh' else 'Optical Graph to Manufacturing')+'</title>',
        '<desc id="cover-desc">Four isolated plugins. PM-532 1×3 R2 digital engineering example; 2.727 mm minimum clearance lower bound. Physical power and PER remain to be measured.</desc>',
        '<defs><pattern id="grid" width="25" height="25" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".85" fill="#152C36" opacity=".07"/></pattern><clipPath id="canvas"><rect x="1" y="1" width="1278" height="638" rx="24"/></clipPath><clipPath id="assembly"><rect x="671" y="76" width="555" height="391" rx="7"/></clipPath></defs>',
        '<rect x="1" y="1" width="1278" height="638" rx="24" fill="#FCFBF7" stroke="#CBD5E1"/>',
        '<rect width="1280" height="640" fill="url(#grid)" clip-path="url(#canvas)"/>',
        f'<image x="56" y="51" width="260" height="61.5543" preserveAspectRatio="xMidYMid meet" xlink:href="{data(LOGO,"image/svg+xml")}"/>']
        def rect(x,y,w,h,fill,stroke=None,rx=4):bits.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"'+(f' stroke="{stroke}"' if stroke else '')+'/>')
        def text(value,x,y,size,weight=400,color='#152C36',spacing=0):
            # Outlines make PNG/SVG exports independent of the viewer's installed fonts.
            start=x;paths=[]
            for char in value:
                font=fonts[weight] if ord(char) in fonts[weight].getBestCmap() else cjk
                cmap=font.getBestCmap();glyph_name=cmap.get(ord(char))
                if glyph_name is None:raise ValueError('Missing cover glyph: '+char)
                glyph=font.getGlyphSet()[glyph_name];scale=size/font['head'].unitsPerEm
                pen=SVGPathPen(font.getGlyphSet());glyph.draw(pen);path=pen.getCommands()
                if path:paths.append(f'<path transform="translate({x:.4f} {y}) scale({scale:.6f} {-scale:.6f})" d="{path}"/>')
                x+=glyph.width*scale+spacing
            bits.append('<g fill="'+color+'" aria-label="'+html.escape(value,quote=True)+'">'+''.join(paths)+'</g>')
            return x-start
        text('HARNESS  /  v'+version,57,143,12,800,'#47636D',1)
        if lang=='zh':
            for n,line in enumerate(['写一张光路图，','交付整套可加工','光机总装。']):text(line,54,230+n*54,45,800)
            text('从偏振光路追迹、面包板排板与定制 CAD，',57,398,15,400,'#47636D')
            text('到三维净空复核与加工、采购交付。',57,423,15,400,'#47636D')
            labels=['01 光路','02 排板','定制支线','03 三维交付']
        else:
            for n,line in enumerate(['Write One','Optical Graph.','Ship a Machined','3D Assembly.']):text(line,54,216+n*48,42,800)
            text('Polarization-aware design. Verified CAD.',57,405,15,400,'#47636D')
            text('Manufacturing and procurement handoffs.',57,430,15,400,'#47636D')
            labels=['01 Optics','02 Layout','Custom CAD','03 Release']
        bits.append('<path d="M80 494H595" stroke="#168148" stroke-width="1.5"/>')
        for i,(x,w,label) in enumerate(zip([56,188,320,452],[118,118,118,148],labels)):
            rect(x,478,w,32,'#ECE4F6' if i==2 else '#F5F8F7','#c8d9d0')
            text(label,x+11,499,11,800,'#6D4C9E' if i==2 else '#152C36')
        text('按需定制，完成后返回排板复验。' if lang=='zh' else 'Custom branch returns to layout verification.',57,535,10,400,'#47636D')
        text('v'+version+'    /    Python 3.11+    /    All Rights Reserved',57,586,11,400,'#47636D')
        rect(671,76,555,391,'#F5F8F7','#bbcfc7',7)
        bits.append(f'<image x="675" y="83" width="547" height="368" preserveAspectRatio="xMidYMid meet" clip-path="url(#assembly)" xlink:href="{data(ASSEMBLY,"image/png")}"/>')
        # Technical inset has its own border; the official logo never gets a box or shadow.
        rect(648,408,344,145,'#152c36',None,6);bits[-1]=bits[-1].replace('/>',' opacity=".08"/>')
        rect(643,402,344,145,'#FCFBF7','#168148',5)
        text('01 / '+('逻辑原理图' if lang=='zh' else 'LOGICAL SCHEMATIC'),656,422,9,800,'#168148',.5)
        bits.append(f'<image x="651" y="431" width="328" height="109" preserveAspectRatio="xMidYMid meet" xlink:href="{data(SCHEMATIC,"image/svg+xml")}"/>')
        bits.append('<path d="M994 523H1179V476" stroke="#168148" stroke-width="1.5" fill="none"/><circle cx="1179" cy="476" r="4" fill="#22C55E"/>')
        text('PM-532 · 1×3 R2 · 450×300 mm',670,582,12,800,'#152C36')
        text('2.727 mm '+('三维净空下界 · 数字总装核验' if lang=='zh' else '3D clearance lower bound · CAD verified'),670,605,10,400,'#47636D')
        bits.append('</svg>')
        dest=ROOT/f'docs/assets/cover-{lang}.svg';dest.write_text('\n'.join(bits)+'\n')
        rows[dest.name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    manifest={'format':'hksop-showcase-assets-v1','version':version,'canvas':[1280,640],'pngCanvas':[2560,1280],'originalLogoUnmodified':True,'cjkOutlines':cjk['name'].getDebugName(1)+' '+cjk['name'].getDebugName(2)+'; document glyph outlines only, no font file distributed.','inputs':{str(p):hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},'svg':rows}
    (ROOT/'docs/assets/cover-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--covers',action='store_true');p.add_argument('--cjk-font',type=Path);p.add_argument('--cjk-index',type=int,default=0);a=p.parse_args()
    result=page();dest=ROOT/'docs/index.html'
    if a.check:
        if not dest.exists() or dest.read_text()!=result:p.exit(1,'Showcase is stale. Run scripts/build_showcase.py\n')
        print('PASS self-contained showcase matches its sources')
    else:dest.write_text(result);print(dest.relative_to(ROOT),len(result.encode()),'bytes')
    if a.covers:
        if not a.cjk_font:p.error('--covers requires --cjk-font')
        covers(a.cjk_font,a.cjk_index)

if __name__=='__main__':main()
