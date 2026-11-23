#!/usr/bin/env python3
"""Normalize native and board-design WishSpecs to a dimensional CAD task list."""
import argparse
import json
import math
from pathlib import Path
import sys


def parse(doc):
    rows=doc if isinstance(doc,list) else doc.get("wishes")
    if not isinstance(rows,list):raise ValueError("缺少 wishes 数组")
    output=[];seen=set()
    def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
    for row in rows:
        wid=row["wishId"]
        if not isinstance(wid,str) or not wid.startswith("WISH-") or wid in seen:raise ValueError("无效或重复的 WISH 编号")
        seen.add(wid);datum=row["opticalDatum"];base=row.get("lowerM6");b=row["envelopeBudgetMm"]
        if isinstance(b,list):
            x,y,xx,yy=b;center=[datum[k] for k in ("xMm","yMm","zMm")];frame="board"
        else:
            x,y,xx,yy=(b[k] for k in ("xMin","yMin","xMax","yMax"));pos=datum["worldCenterMm"]
            center=[pos[k] for k in ("x","y","z")];frame="component-local"
        if not all(finite(v) for v in [x,y,xx,yy,*center]) or xx<=x or yy<=y:raise ValueError(wid+" 基准或包络无效")
        if base is not None:
            if not 2<=len(base)<=4 or len({h["id"] for h in base})!=len(base):raise ValueError(wid+" 借孔数量或编号无效")
            if any(not all(finite(h[k]) for k in ("xMm","yMm")) for h in base):raise ValueError(wid+" 非法板孔")
            if not finite(row["borrowRadiusMm"]) or row["borrowRadiusMm"]>50.001:raise ValueError(wid+" 借孔超出 50 mm")
            mount={"frame":"main-board","holes":base,"upperInterface":row.get("upperInterface",{}),"borrowRadiusMm":row["borrowRadiusMm"]}
        else:
            mount=row["mountingInterface"]
            if not mount.get("holeOffsetsMm") or any(not all(finite(h[k]) for k in ("xMm","yMm")) for h in mount["holeOffsetsMm"]):raise ValueError(wid+" 下接口缺少真实孔位")
        output.append(dict(wishId=wid,node=row.get("node",row.get("title")),trigger=row["trigger"],datumXYZmm=center,
            envelope={"frame":frame,"xyxyMm":[x,y,xx,yy]},mountingInterface=mount,
            keepoutNeighbors=row.get("keepoutNeighbors",b.get("keepoutNeighbors",[]) if isinstance(b,dict) else []),
            commercialHardware=row.get("commercialHardware",[row.get("hardware")]),requirements={k:row[k] for k in
                ("stageTopZ","targetOpticalZ","availableHeadroomMm","riserThicknessMm","heightShift","spatialAssembly","boardCutouts","frontThread","rearThread","axialTravelMm","workingDistanceMm","keyWidthMm") if k in row},
            status="待核实上接口和实物尺寸后建模"))
    return {"format":"hksop-cad-tasks-v1","count":len(output),"tasks":output}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("wishes",type=Path);p.add_argument("-o","--output",type=Path,required=True)
    a=p.parse_args()
    try:
        result=parse(json.loads(a.wishes.read_bytes()));a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n");print(result["count"],"CAD tasks")
    except (OSError,KeyError,TypeError,ValueError) as e:print(str(e),file=sys.stderr);return 1
    return 0
if __name__=="__main__":sys.exit(main())
