#!/usr/bin/env python3
"""Lay out the approved sidewall logo, M6 pattern, component frames and bilingual markings."""
import argparse
from html import escape
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

def drawing(project,ledger,labels,logo,filename,marking_dir=None):
    p=json.loads(project.read_bytes());l=json.loads(ledger.read_bytes());text=json.loads(labels.read_bytes())
    if text["projectSha256"]!=hashlib.sha256(project.read_bytes()).hexdigest():raise ValueError("刻字表未绑定当前工程")
    if any(i.get("placeholder") for i in p["layout"]["instances"]):raise ValueError("未解决的 WISH 不能制作加工标记")
    b=p["layout"]["board"];w,h,t=b["widthMm"],b["heightMm"],b["thicknessMm"];pitch=b["pitchMm"];edge=b["edgeOffsetMm"]
    if any(b[k]!=l["board"][k] for k in ("widthMm","heightMm","pitchMm","edgeOffsetMm")):raise ValueError("孔图与工程板型不符")
    ids={i["id"] for i in p["layout"]["instances"]}
    if ids!=set(l["nodes"]) or ids!=set(text["labels"]):raise ValueError("器件框及双语铭牌数量不匹配")
    side=text["outwardSide"];length=w if side in ("south","north") else h if side in ("west","east") else None
    if length is None or t<=3:raise ValueError("外侧面或壁高无效")
    sign=ET.parse(logo).getroot()
    m=json.loads((logo.parent/"manifest.json").read_bytes())
    expected=next(v["sha256"] for v in m["files"] if v["path"]==logo.name)
    if hashlib.sha256(logo.read_bytes()).hexdigest()!=expected:raise ValueError("Logo 哈希不符")
    ink=json.loads((logo.parent/"ink-bounds.json").read_bytes())["bounds"]
    if text.get("ledgerSha256")!=hashlib.sha256(ledger.read_bytes()).hexdigest():raise ValueError("刻字表未绑定孔位账本")
    ix,iy,iw,ih=ink;scale=(t-3)/ih
    if scale*iw>length-3:raise ValueError("完整标识超过外侧壁")
    s=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w+28}mm" height="{h+t+65}mm" viewBox="-14 -16 {w+28} {h+t+65}"><g font-family="sans-serif" font-size="3.3" fill="#111"><text x="0" y="-6">{escape(p["metadata"]["name"])} · {w:g} × {h:g} × {t:g} mm · 孔距 {pitch:g} mm</text><rect width="{w}" height="{h}" fill="none" stroke="#111" stroke-width=".25"/>']
    fixed={(v["columnIndex"],v["rowIndex"]) for v in b["mountingHoles"]}
    for i in range(int((w-2*edge)//pitch)+1):
        for j in range(int((h-2*edge)//pitch)+1):
            x,y=edge+i*pitch,h-edge-j*pitch;f=(i,j) in fixed
            s.append(f'<circle cx="{x}" cy="{y}" r="{3.3 if f else 2.5}" stroke="#898989" stroke-width=".2" fill="none"/>')
            if f:s.append(f'<circle cx="{x}" cy="{y}" r="5.5" stroke="#111" stroke-width=".25" fill="none"/>')
    for v in l.get("boardCutouts",[]):
        x,y=v["center"];s.append(f'<circle cx="{x}" cy="{h-y}" r="{v["diameterMm"]/2}" fill="none" stroke="#111" stroke-width=".3"/>')
    start_marks=len(s)
    for k,r in l["nodes"].items():
        x0,y0,x1,y1=r["supportBoundsMm"];v=text["labels"][k]
        if not re.search(r"[\u3400-\u9fff]",v["zh"]) or not re.search(r"[a-z]",v["en"],re.I):raise ValueError("需核实中英文刻字 "+k)
        s.append(f'<rect x="{x0}" y="{h-y1}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="#111" stroke-width=".2"/>')
        for j,title in enumerate((k,v["zh"],v["en"])):
            size=min(3.1,(x1-x0-1)/max(1,len(title)))
            s.append(f'<text x="{x0+1}" y="{h-y1+4+j*4}" font-size="{size:.2f}">{escape(title)}</text>')
        import math
        angle=math.radians(r["rotationDeg"]);s.append(f'<circle cx="{(x0+x1)/2+math.cos(angle)*(x1-x0-3)/2:g}" cy="{h-(y0+y1)/2-math.sin(angle)*(y1-y0-3)/2:g}" r="1"/>')
    for a,b_ in text["beamCenterlinesMm"]:
        s.append(f'<line x1="{a[0]}" y1="{h-a[1]}" x2="{b_[0]}" y2="{h-b_[1]}" stroke="#444" stroke-width=".18" stroke-dasharray="2 1"/>')
    top_marks=s[start_marks:]
    wall=h+12;tx=length-3-scale*(ix+iw);ty=wall+1.5-scale*iy
    s.append(f'<rect x="0" y="{wall}" width="{length}" height="{t}" stroke="#111" fill="none" stroke-width=".25"/><g transform="translate({tx} {ty}) scale({scale})">')
    artwork="".join(ET.tostring(n,encoding="unicode") for n in sign if n.tag.rsplit("}",1)[-1] not in ("title","desc"))
    s.append(artwork)
    s+=['</g>',f'<text x="0" y="{wall+t+7}">外侧 {side} 正视 · 标识距右 3 mm，上下各 1.5 mm。固定孔 Ø6.6 / Ø11 深 6.5。其余孔 M6×1。</text></g></svg>']
    filename.write_text("".join(s))
    if marking_dir:
        marking_dir.mkdir(parents=True,exist_ok=True)
        def svg(width,height,contents):
            return f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}"><g fill="#111" font-family="sans-serif">{contents}</g></svg>'
        (marking_dir/"top-marking.svg").write_text(svg(w,h,"".join(top_marks)))
        (marking_dir/"side-marking.svg").write_text(svg(length,t,f'<g transform="translate({tx} {ty-wall}) scale({scale})">{artwork}</g>'))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("project",type=Path);p.add_argument("ledger",type=Path);p.add_argument("labels",type=Path);p.add_argument("-o",type=Path,required=True);p.add_argument("--marking-dir",type=Path);a=p.parse_args()
    try:drawing(a.project,a.ledger,a.labels,Path(__file__).resolve().parents[1]/"references/logo/hksop-logo-mono.svg",a.o,a.marking_dir)
    except (KeyError,OSError,ValueError) as e:sys.exit(str(e))
