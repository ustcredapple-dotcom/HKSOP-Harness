#!/usr/bin/env python3
"""Build a dimensioned eccentric adapter from an approved rectangular machining definition."""
import argparse
from html import escape
import json
import math
from pathlib import Path
import sys


def build(task,drawing,out):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.gp import gp_Ax2,gp_Dir,gp_Pnt
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    if drawing["wishId"]!=task["wishId"] or not drawing.get("upperDrawingReference") or not drawing.get("material"):raise ValueError("须提供对应需求、上接口原图及材料")
    if task["envelope"]["frame"]!="board":raise ValueError("先将包络与接口注册到同一坐标系")
    x0,y0,x1,y1=drawing["boundsXYmm"];a,b,c,d=task["envelope"]["xyxyMm"]
    if not (a<=x0<x1<=c and b<=y0<y1<=d):raise ValueError("超出已批准加工包络")
    w,h,t=x1-x0,y1-y0,drawing["thicknessMm"]
    if not all(math.isfinite(n) and n>.6 for n in (w,h,t)):raise ValueError("坯料尺寸无效")
    holes=[dict(xMm=p["xMm"],yMm=p["yMm"],diameterMm=6.6,role="lower "+p["id"]) for p in task["mountingInterface"]["holes"]]+drawing["upperHoles"]
    initial=BRepPrimAPI_MakeBox(w,h,t).Shape();ch=BRepFilletAPI_MakeChamfer(initial);edges=TopExp_Explorer(initial,TopAbs_EDGE)
    cast=getattr(TopoDS,"Edge_s",None) or TopoDS.Edge
    while edges.More():ch.Add(.3,cast(edges.Current()));edges.Next()
    ch.Build()
    if not ch.IsDone():raise ValueError("外棱倒角失败")
    solid=ch.Shape();positions=[]
    for entry in holes:
        x,y,r=entry["xMm"]-x0,entry["yMm"]-y0,entry["diameterMm"]/2
        if not (r>0 and r+.3<x<w-r-.3 and r+.3<y<h-r-.3):raise ValueError("孔与外棱相交")
        if any(math.hypot(x-px,y-py)<=r+pr for px,py,pr in positions):raise ValueError("孔组相交")
        positions.append((x,y,r))
        solid=BRepAlgoAPI_Cut(solid,BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,-1),gp_Dir(0,0,1)),r,t+2).Shape()).Shape()
    if not BRepCheck_Analyzer(solid).IsValid():raise ValueError("实体无效")
    out.mkdir(parents=True,exist_ok=True);writer=STEPControl_Writer();writer.Transfer(solid,STEPControl_AsIs)
    if writer.Write(str(out/"adapter.step"))!=IFSelect_RetDone:raise ValueError("STEP 写入失败")
    rows=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {max(w+42,150)} {h+65+len(holes)*6}"><g font-family="sans-serif" font-size="4" fill="#19313c">',
          f'<text x="8" y="8">{escape(task["wishId"])} · {escape(drawing["material"])} · mm</text>',
          f'<rect x="15" y="18" width="{w}" height="{h}" fill="none" stroke="#182e38" stroke-width=".6"/>']
    for i,(x,y,r) in enumerate(positions,1):
        rows.append(f'<circle cx="{15+x}" cy="{18+h-y}" r="{r}" fill="none" stroke="#182e38" stroke-width=".4"/><text x="{16+x+r}" y="{19+h-y}">{i}</text>')
    rows+= [f'<text x="8" y="{h+28}">基准为左下角。外形 {w:g} × {h:g} × {t:g} mm。外棱 C0.3×45°。</text>',
            f'<text x="8" y="{h+35}">上接口依据 {escape(drawing["upperDrawingReference"])}。</text>']
    for i,((x,y,r),entry) in enumerate(zip(positions,holes),1):
        rows.append(f'<text x="8" y="{h+38+6*i}">{i}　X {x:.3f}　Y {y:.3f}　Ø{2*r:g} 通孔　{escape(entry["role"])}</text>')
    (out/"machining.svg").write_text("".join(rows)+"</g></svg>\n")

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("tasks",type=Path);p.add_argument("dimensions",type=Path);p.add_argument("-o",type=Path,required=True);a=p.parse_args()
    try:
        d=json.loads(a.dimensions.read_bytes());row=next(t for t in json.loads(a.tasks.read_bytes())["tasks"] if t["wishId"]==d["wishId"]);build(row,d,a.o)
    except (ImportError,StopIteration,ValueError,KeyError,OSError) as e:print(str(e),file=sys.stderr);return 1
    return 0
if __name__=="__main__":sys.exit(main())
