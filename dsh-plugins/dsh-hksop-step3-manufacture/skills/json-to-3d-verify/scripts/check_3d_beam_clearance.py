#!/usr/bin/env python3
"""Check a frozen project's Gaussian tubes against the registered 3-D solids."""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from hksop_runtime import library_root, local_environment, resolve_node

HERE=Path(__file__).resolve().parent
def digest(f):
    with f.open("rb") as stream:
        h=hashlib.sha256()
        for chunk in iter(lambda:stream.read(1<<20),b""):h.update(chunk)
        return h.hexdigest()
def in_clear_aperture(start,end,tube,medium):
    """Require the swept beam to fit inside the measured clear cylinder through the optic."""
    # registered cubic splitter has two orthogonal, manufacturer-specified clear port pairs. Select
    # the measured port parallel to this segment. The original bounded-cylinder
    # test still checks both ends of the entire clipped Gaussian tube.
    if "portAxes" in medium:
        length = math.dist(start, end)
        if length == 0:
            return False
        direction = [(b-a)/length for a,b in zip(start,end)]
        for axis in medium["portAxes"]:
            if abs(sum(a*b for a,b in zip(direction,axis))) < 1-1e-8:
                continue
            aperture = {k:v for k,v in medium.items() if k != "portAxes"}
            aperture["normal"] = axis
            return in_clear_aperture(start,end,tube,aperture)
        return False
    normal,center=medium["normal"],medium["center"]
    dot=lambda a,b:sum(x*y for x,y in zip(a,b))
    delta=[y-x for x,y in zip(start,end)]
    offset=[x-y for x,y in zip(start,center)]
    z0,dz=dot(offset,normal),dot(delta,normal)
    depth=medium["depth"]+tube
    if abs(dz)<1e-10:
        if abs(z0)>depth:return False
        lo,hi=0.,1.
    else:
        lo,hi=sorted(((-depth-z0)/dz,(depth-z0)/dz))
        lo,hi=max(0.,lo),min(1.,hi)
        if lo>hi:return False
    for t in (lo,hi):
        axial=z0+t*dz
        radial=[v+t*d-axial*n for v,d,n in zip(offset,delta,normal)]
        if math.sqrt(dot(radial,radial))+tube>medium["radius"]:return False
    return True

def report(f,obj):
    f.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=f.parent,delete=False,encoding="utf8") as fd:
        json.dump(obj,fd,ensure_ascii=False,indent=2,allow_nan=False);fd.write("\n");name=fd.name
    os.replace(name,f)
def check(args,receipt):
    project=json.loads(args.project.read_bytes());layout=project["layout"];root=args.root.resolve()
    if root in args.output.resolve().parents:raise ValueError("输出必须在元件库之外")
    pending=[x.get("wishId",x["id"]) for x in layout["instances"] if x.get("placeholder")]
    if pending:receipt["pendingCAD"]=pending;raise ValueError("仍有黄色占位件；请到 hksop-custom-part 完成定制件及复验")
    config=local_environment(root)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1")
    if importlib.util.find_spec("OCP") is None:
        cad=Path(os.environ.get("HKSOP_CAD_PYTHON") or config.get("cadPython") or sys.executable)
        if not cad.is_file() or cad.resolve()==Path(sys.executable).resolve():raise ValueError("缺少可用的 CAD Python / OCP")
        return subprocess.run([str(cad),"-B",str(Path(__file__).resolve()),*sys.argv[1:]],env=env).returncode
    node=resolve_node(root)
    receipt["nodeExecutable"]=node
    receipt["portModel"]="Only the registered surface normals, physical subsolids and bounded clear apertures are admitted."
    receipt["cadPython"]=sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        verify=Path(tmp)/"native.json"
        cp=subprocess.run([sys.executable,"-B",str(root/"hksop.py"),"design","verify",str(args.project.resolve()),"-o",str(verify),"--node",node],env=env,capture_output=True,text=True)
        if cp.returncode:raise ValueError("原生 verify 未通过 "+(verify.read_text()[:450] if verify.exists() else cp.stderr[-450:]))
    cmd=subprocess.run([node,str(HERE/"native_segments.cjs"),str(root),str(args.project.resolve())],env=env,capture_output=True,text=True)
    if cmd.returncode:raise ValueError("未取得原生光束 "+cmd.stderr[-500:])
    optics=json.loads(cmd.stdout);segments=optics["segments"]
    if not segments:raise ValueError("工程没有可复验的光束")
    from solid_scene import solids,edge_distance,write_assembly,write_board,board_solid
    catalog=json.loads((root/"library/catalog.json").read_bytes())
    requires_focus=[r["id"] for r in layout["instances"] if r.get("kitId")=="fiber-coupling-mft-rear-r3"]
    generated=None
    if requires_focus and not args.geometry:
        from prepare_geometry import prepare
        generated=tempfile.TemporaryDirectory()
        args.geometry=prepare(args.project,root,Path(generated.name),segments)
    heads={}
    if requires_focus:
        from fiber_audit import local_check,bounds_from_world,final_bounds
        from solid_scene import source,pose,bbox
        aux=json.loads(args.geometry.read_bytes())
        for key in requires_focus:
            rec=aux.get("instances",{}).get(key,{})
            focus=rec.get("focus")
            if not focus:raise ValueError(key+" 的前镜后纤缺少实模调焦登记")
            f=(args.geometry.parent/rec["step"]).resolve()
            heads[key]=dict(local_check(f,rec["sha256"],focus["bflMm"]))
            inst=next(n for n in layout["instances"] if n["id"]==key)
            loc=pose(inst["xMm"],inst["yMm"],0,inst["rotationDeg"])
            parts=[(name,bbox(s.Moved(loc))) for name,s in source(f,rec["sha256"])[2] if name.startswith("moving ")]
            bounds_from_world(key,parts,heads[key],project)
        receipt["fiberInterfaces"]=heads
    items,proofs,assembly,registered_board=solids(root,layout,catalog,args.geometry,args.project)
    registered={v["id"]:v for v in catalog["kits"]}
    for row in layout["instances"]:
        geom=registered[row["kitId"]]["layout"]
        if geom.get("opticalAssembly",{}).get("version")==2 and not any(r.get("source")==row["id"] or r.get("hit")==row["id"] for r in segments):
            raise ValueError("复合件无可核验三维追迹 "+row["id"])
    segments.extend(proofs.get("additionalSegments",[]))
    board=registered_board or board_solid(layout,proofs.get("cutouts",[]),threaded=bool(args.assembly));items.append(("main-board",board,None))
    blocked=[];rows=[];seen=set()
    for r in segments:
        start,end=r["a"],r["b"]
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in start+end):raise ValueError("光束高度或坐标缺失")
        length=math.dist(start,end)
        if len(start)!=3 or len(end)!=3 or length<=0 or r["id"] in seen:raise ValueError("空间段长度、端点维数或身份无效")
        seen.add(r["id"])
        if not all(math.isfinite(v) and v>0 for v in (r["m2"],r["index"],r["rangeMm"],r["wavelengthNm"])):raise ValueError("空间段的传播参数无效")
        if any(len(q)!=2 or not all(map(math.isfinite,q)) or q[1]<=0 for q in (r["q"],r["qSagittal"])):raise ValueError("空间段的高斯 q 无效")
        if abs(length-r["rangeMm"])>max(.01,.0001*length):raise ValueError("实际三维长度与光程传播距离不一致")
        endpoints=r.get("interactionIds",[r.get("hit"),r.get("source")])
        count=max(1,math.ceil(length/20));minimum=math.inf;interactions=0;max_radius=0
        def radius(distance):
            def w(q):
                if q[1]<=0:raise ValueError("非法高斯 q")
                return math.sqrt(r["m2"]*r["wavelengthNm"]*1e-6/(math.pi*r["index"])*((q[0]+distance)**2+q[1]**2)/q[1])
            return args.factor*max(w(r["q"]),w(r["qSagittal"]))+args.margin
        for j in range(count):
            lo,hi=j/count,(j+1)/count
            a=[x+(y-x)*lo for x,y in zip(start,end)];b=[x+(y-x)*hi for x,y in zip(start,end)]
            radius_mm=max(radius(r["rangeMm"]*lo),radius(r["rangeMm"]*hi));max_radius=max(max_radius,radius_mm)
            for key,solid,aperture in items:
                if (aperture is not None and key.split("/")[0] in endpoints
                        and in_clear_aperture(a,b,radius_mm,aperture)):
                    interactions+=1;continue
                gap=edge_distance(a,b,solid,radius_mm)-radius_mm
                minimum=min(minimum,gap)
                if gap<=1e-5:
                    blocked.append(dict(segment=r["id"],solid=key,rangeMm=[lo*length,hi*length],clearanceMm=round(gap,5)))
        rows.append(dict(id=r["id"],a=start,b=end,source=r["source"],hit=r["hit"],wavelengthNm=r["wavelengthNm"],
                         maxTubeRadiusMm=max_radius,minimumClearanceLowerBoundMm=minimum,segmentsTested=count,intendedMedia=interactions))
    if not rows:raise ValueError("无可检查的有限长度光束")
    receipt.update(valid=not blocked,method="Exact OpenCascade point-set distance near the beam, conservative interval bounds elsewhere. Tube radius includes Gaussian 1/e² radius, multiplier and radial margin.",
                   geometry=proofs,nativeVerify=True,segments=rows,obstructions=blocked,bodyCount=len(items),
                   catalogVersion=optics["catalogVersion"])
    if args.assembly and not blocked:
        args.assembly.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=args.assembly.parent) as tmp:
            draft=Path(tmp)/"assembly.step";write_assembly(draft,assembly,board)
            if heads:final_bounds(draft,project,heads);receipt["finalAssemblyFiberReadback"]=True
            receipt["assemblySha256"]=digest(draft);os.replace(draft,args.assembly)
        if args.board_step:
            args.board_step.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(dir=args.board_step.parent) as tmp:
                draft=Path(tmp)/"board.step";write_board(draft,board)
                receipt["boardStepSha256"]=digest(draft);os.replace(draft,args.board_step)
    report(args.output,receipt);print(f"{len(rows)} rays, {len(items)} bodies, {len(blocked)} intersections")
    return int(bool(blocked))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("project",type=Path);p.add_argument("-o","--output",type=Path,default=Path("beam_clearance_3d.json"))
    p.add_argument("--root",type=Path)
    p.add_argument("--geometry",type=Path,help="经核实且绑定项目 SHA256 的附加 CAD 登记");p.add_argument("--assembly",type=Path);p.add_argument("--board-step",type=Path)
    p.add_argument("--factor",type=float,default=1.5);p.add_argument("--margin",type=float,default=.1);args=p.parse_args()
    if not math.isfinite(args.factor) or args.factor<1 or not math.isfinite(args.margin) or args.margin<0:p.error("光束因子至少 1，径向余量须非负")
    try:
        args.root = library_root(args.root)
    except ValueError as exc:
        p.error(str(exc))
    if args.board_step and not args.assembly:p.error("--board-step 随 --assembly 生成")
    destinations=[p.resolve() for p in (args.output,args.assembly,args.board_step) if p is not None]
    if len(set(destinations))!=len(destinations) or args.project.resolve() in destinations:p.error("输入和各输出须使用不同路径")
    for dest in destinations:
        if any(root in dest.resolve().parents for root in (args.root.resolve(),args.root.resolve().parent/"HKSOP")):p.error("输出目录必须在受保护库外")
    receipt=dict(format="hksop-beam-clearance-3d-v1",projectSha256=digest(args.project),valid=False,radiusMultiplier=args.factor,marginMm=args.margin)
    try:return check(args,receipt)
    except (ValueError,KeyError,TypeError,OSError,RuntimeError,ImportError) as e:receipt["valid"]=False;receipt["error"]=str(e);report(args.output,receipt);print(str(e),file=sys.stderr);return 2
if __name__=="__main__":sys.exit(main())
