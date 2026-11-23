"""Final solid-model tests for the adjustable fibre interface, travel and edge conditions."""
from functools import lru_cache
from pathlib import Path
import hashlib,json,math
import numpy as np
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane,GeomAbs_Cylinder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from solid_scene import bbox,source,pose

def bounds_gap(a,b):
    return math.sqrt(sum(max(0,a[i]-b[i+3],b[i]-a[i+3])**2 for i in range(3)))
def distance(a,b):
    solver=BRepExtrema_DistShapeShape(a,b);solver.Perform()
    if not solver.IsDone():raise ValueError("OCC distance failed")
    return solver.Value()
def apex(ferrule):
    cylinder=plane=None;ex=TopExp_Explorer(ferrule,TopAbs_FACE)
    while ex.More():
        face=(getattr(TopoDS,'Face_s',None) or TopoDS.Face)(ex.Current())
        ad=BRepAdaptor_Surface(face)
        if ad.GetType()==GeomAbs_Cylinder and abs(ad.Cylinder().Radius()-1.2495)<.001:cylinder=ad.Cylinder().Axis()
        if ad.GetType()==GeomAbs_Plane:
            n=np.array(ad.Plane().Axis().Direction().Coord())
            if abs(n[2])>.15 and abs(n[1])>.9:plane=ad.Plane()
        ex.Next()
    if cylinder is None or plane is None:raise ValueError("缺少陶瓷插芯圆柱或 8° 抛光面")
    v=np.array(cylinder.Direction().Coord());c=np.array(cylinder.Location().Coord());normal=np.array(plane.Axis().Direction().Coord())
    if abs(math.degrees(math.acos(min(1,abs(v@normal))))-8)>.05:raise ValueError("APC 端面角无效")
    return c+v*((np.array(plane.Location().Coord())-c)@normal/(v@normal))
def sweep(a,b,lo,hi):
    # Distance to a solid is 1-Lipschitz under translation: a midpoint lower bound
    # proves an entire interval. Recurse only if the conservative interval touches.
    axis=(lo+hi)/2;s=a.Moved(pose(0,axis,0))
    lower=bounds_gap(bbox(s),bbox(b))
    if lower<=(hi-lo)/2+.0005:lower=distance(s,b)
    if lower>(hi-lo)/2+.0002:return lower-(hi-lo)/2
    if hi-lo<.002 or lower<.00005:raise ValueError("全行程发现接触，位移 "+str(round(axis,4))+" mm")
    return min(sweep(a,b,lo,axis),sweep(a,b,axis,hi))
@lru_cache(maxsize=8)
def local_check(path,digest,design_bfl):
    leaves=dict(source(path,digest)[2])
    for name in ("front lens glass","moving APC ferrule","moving keyed plug","moving rigid boot","moving FC APC flange"):
        if name not in leaves:raise ValueError("调焦头实装缺少 "+name)
    point=apex(leaves["moving APC ferrule"]);glass=bbox(leaves["front lens glass"])
    spacing=point[1]-glass[4];offset=spacing-design_bfl
    if abs(offset)>.1:raise ValueError("名义 BFL 未居中 "+str(offset))
    moving=[(n,s) for n,s in leaves.items() if n.startswith("moving ")]
    stat=[(n,s) for n,s in leaves.items() if not n.startswith("moving ")]
    results=[];threads=[]
    for a,sh in moving:
        for b,obj in stat:
            if b.startswith("stock-64 ") and a=="moving FC APC flange":
                threads.append([a,b,"1.035-40 SM1 externally threaded flange engages moving inner ring"]);continue
            if b.startswith("stock-64 "):continue # co-moving original carriage
            bb=bbox(sh);br=bbox(obj);min_gap=bounds_gap(bb,br)
            if min_gap>1.5:continue
            try:g=sweep(sh,obj,-.5,.5)
            except ValueError as exc:raise ValueError(a+" / "+b+" "+str(exc)) from exc
            results.append(dict(moving=a,stationary=b,clearanceBoundMm=g))
    carriage=next(s for n,s in stat if n.startswith("stock-64 "))
    for b,obj in stat:
        if b.startswith("front "):results.append(dict(moving="MFT carriage",stationary=b,clearanceBoundMm=sweep(carriage,obj,-.5,.5)))
    return dict(measuredFacetXYZmm=point.tolist(),measuredLensRearYmm=glass[4],measuredBFLmm=spacing,designBFLmm=design_bfl,
                focusOffsetMm=offset,travelToNegativeStopMm=.5+offset,travelToPositiveStopMm=.5-offset,
                strokeMm=1.,continuousTravelVerified=True,nearPairs=results,mating=threads,stockMechanism="厂家原装、未修改 MFT 导向副按厂家 1.0 mm 总行程；新增零件与原装固定组连续扫程。")
def final_bounds(path,project,heads):
    # Reopen the actual exported assembly. Obtain the world leaf instances through named top subassemblies.
    from solid_scene import doc,STEPCAFControl_Reader,IFSelect_RetDone,XCAFDoc_DocumentTool,Sequence_TDF_Label,TDF_Label,named,TopLoc_Location
    reader=STEPCAFControl_Reader();reader.SetNameMode(True);d=doc()
    if reader.ReadFile(str(path))!=IFSelect_RetDone or not reader.Transfer(d):raise ValueError("总装回读失败")
    tool=XCAFDoc_DocumentTool.ShapeTool_s(d.Main());roots=Sequence_TDF_Label();tool.GetFreeShapes(roots);found={k:[] for k in heads}
    def visit(lab,par,owner):
        inst=named(lab);owner=inst if inst in found else owner
        ref=TDF_Label();dst=ref if tool.GetReferredShape_s(lab,ref) else lab
        location=par.Multiplied(tool.GetLocation_s(lab));children=Sequence_TDF_Label()
        if tool.GetComponents_s(dst,children):
            for i in range(1,children.Length()+1):visit(children.Value(i),location,owner)
        elif owner and named(dst).startswith("moving "):found[owner].append((named(dst),bbox(tool.GetShape_s(dst).Moved(location))))
    for i in range(1,roots.Length()+1):visit(roots.Value(i),TopLoc_Location(),None)
    for k,shapes in found.items():
        if len(shapes)!=11 or not any(n=="moving rigid boot" for n,b in shapes):raise ValueError(k+" 总装中未找到完整插头与尾套 "+str(len(shapes)))
        bounds_from_world(k,shapes,heads[k],project)
def bounds_from_world(k,shapes,record,project):
    board=project["layout"]["board"];width,height=board["widthMm"],board["heightMm"]
    inst=next(r for r in project["layout"]["instances"] if r["id"]==k)
    angle=math.radians(inst.get("rotationDeg",0));d=(-math.sin(angle),math.cos(angle));ds=[d[0],-d[0],d[1],-d[1]]
    ix=max(range(4),key=lambda i:ds[i])
    if ds[ix]<.9999:raise ValueError(k+" 异形出纤方向需要明确板缘")
    bb=[min(b[i] for _,b in shapes) if i<3 else max(b[i] for _,b in shapes) for i in range(6)]
    end=next(b for n,b in shapes if n=="moving rigid boot")
    xy=[(end[i]+end[i+3])/2 for i in (0,1)]
    xy[ix//2]=(end[3] if ix==0 else end[0] if ix==1 else end[4] if ix==2 else end[1])
    dst=[width-xy[0],xy[0],height-xy[1],xy[1]]
    # Center at mid-travel; the moving accessories travel along the mechanical optical axis.
    over=max(0,-bb[0]+.5*abs(d[0]),-bb[1]+.5*abs(d[1]),bb[3]-width+.5*abs(d[0]),bb[4]-height+.5*abs(d[1]))
    if over>.001 or dst[ix]>min(dst)+.001:raise ValueError(k+" 实模尾套越界或朝向板内 "+str((over,dst)))
    record.update(realRigidBoundsMm=bb,worstOverhangMm=over,exitSide=("east","west","north","south")[ix],remainingToEdgeAtMidMm=dst[ix],exitVector=d,straightToEdge=True)
