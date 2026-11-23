"""OpenCascade solids and frozen STEP assembly hierarchy. Coordinates and distances are mm."""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2,gp_Dir,gp_Pnt,gp_Trsf
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader,STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs,STEPControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_Editor
from OCP.collections import Sequence_TDF_Label


def doc():
    app=XCAFApp_Application.GetApplication_s();name=TCollection_ExtendedString("XmlXCAF")
    d=TDocStd_Document(name);out=app.NewDocument(name,d)
    return out[0] if out else d

def named(label):
    a=TDataStd_Name()
    return a.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(),a) else ""

def pose(x=0,y=0,z=0,deg=0):
    a=math.radians(deg);c,s=math.cos(a),math.sin(a)
    t=gp_Trsf();t.SetValues(c,-s,0,x,s,c,0,y,0,0,1,z);return TopLoc_Location(t)

def bbox(shape):
    b=Bnd_Box();BRepBndLib.AddOptimal_s(shape,b,False,False)
    if b.IsVoid():return None
    a,z=b.CornerMin(),b.CornerMax();return (a.X(),a.Y(),a.Z(),z.X(),z.Y(),z.Z())

@lru_cache(maxsize=64)
def source(path,expected):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError("STEP SHA256 不匹配 "+str(path))
    d=doc();reader=STEPCAFControl_Reader();reader.SetNameMode(True);reader.SetColorMode(True)
    if reader.ReadFile(str(path))!=IFSelect_RetDone or not reader.Transfer(d):raise ValueError("无法读取 STEP "+str(path))
    tool=XCAFDoc_DocumentTool.ShapeTool_s(d.Main());roots=Sequence_TDF_Label();tool.GetFreeShapes(roots);leaves=[]
    def visit(label,parent):
        ref=TDF_Label();target=ref if tool.GetReferredShape_s(label,ref) else label
        loc=parent.Multiplied(tool.GetLocation_s(label));children=Sequence_TDF_Label()
        if tool.GetComponents_s(target,children):
            for j in range(1,children.Length()+1):visit(children.Value(j),loc)
        else:
            sh=tool.GetShape_s(target).Moved(loc)
            if bbox(sh) is not None:leaves.append((named(target),sh))
    for i in range(1,roots.Length()+1):visit(roots.Value(i),TopLoc_Location())
    if not leaves:raise ValueError("空 STEP "+str(path))
    return d,roots,leaves

def rigid(rows):
    if len(rows)!=3 or any(len(row)!=4 for row in rows):raise ValueError("源到套件矩阵应为 3 × 4")
    u,v,w=[r[:3] for r in rows]
    dot=lambda a,b:sum(x*y for x,y in zip(a,b))
    if any(abs(dot(a,b)-float(i==j))>1e-6 for i,a in enumerate((u,v,w)) for j,b in enumerate((u,v,w))):raise ValueError("变换含缩放或剪切")
    det=sum(w[i]*(u[(i+1)%3]*v[(i+2)%3]-u[(i+2)%3]*v[(i+1)%3]) for i in range(3))
    if abs(det-1)>1e-6:raise ValueError("镜像或非法姿态")
    tr=gp_Trsf();tr.SetValues(*[v for line in rows for v in line]);return TopLoc_Location(tr)


def solids(root,layout,catalog,geometry,project):
    kits={x["id"]:x for x in catalog["kits"]}
    annex=json.loads(geometry.read_bytes()) if geometry else {}
    if annex and annex.get("projectSha256")!=hashlib.sha256(project.read_bytes()).hexdigest():raise ValueError("附加 CAD 登记与工程哈希不匹配")
    records=annex.get("instances",{});plates={};rows=[];assemblies=[];evidence=[]
    def add(key,path,sha,location,media):
        _,_,parts=source(path,sha);assemblies.append((key,path,sha,location))
        optical={}
        for entry in media:
            if not isinstance(entry,dict):raise ValueError("光学介质须提供 STEP 子件编号、有效口径和厚度 "+key)
            index=entry["index"]
            if not isinstance(index,int) or not 0<=index<len(parts) or parts[index][0]!=entry["name"] or index in optical:
                raise ValueError("光学介质子件身份无效 "+key)
            width,depth=entry["clearRadiusMm"],entry["halfThicknessMm"]
            if not all(math.isfinite(v) and v>0 for v in (width,depth)):raise ValueError("介质有效口径或厚度无效 "+key)
            center=gp_Pnt(*entry["centerSourceMm"]).Transformed(location.Transformation())
            normal=gp_Dir(*entry["normalSourceXYZ"]).Transformed(location.Transformation())
            optical[index]=dict(center=center.Coord(),normal=normal.Coord(),radius=width,depth=depth)
            if "additionalPortNormalsSourceXYZ" in entry:
                directions = [normal.Coord()]
                for direction in entry["additionalPortNormalsSourceXYZ"]:
                    world_direction = gp_Dir(*direction).Transformed(location.Transformation()).Coord()
                    if any(abs(sum(a*b for a,b in zip(world_direction, old))) > 1e-7 for old in directions):
                        raise ValueError("PBS port axes must be mutually orthogonal")
                    directions.append(world_direction)
                optical[index]["portAxes"] = directions
        for j,(name,shape) in enumerate(parts):
            transformed=shape.Moved(location);limit=bbox(transformed)
            rows.append((f"{key}/{j}:{name}",(transformed,limit),optical.get(j)))
        evidence.append(dict(id=key,sourceSha256=sha,leafCount=len(parts)))
    def frozen(key,rec,loc):
        f=Path(rec["step"]);f=f if f.is_absolute() else geometry.parent/f
        if not rec.get("datumEvidence"):raise ValueError("缺少定位基准 "+key)
        add(key,f,rec["sha256"],loc.Multiplied(rigid(rec["sourceToKit3x4"])),rec.get("transmissiveOpticalLeaves",[]))
    for p in layout.get("subBoards",[]):
        r=p["rotationDeg"];stage=p.get("stageMotion",{});base=pose(p["xMm"],p["yMm"],p.get("elevationMm",0),r)
        if stage:
            m=next(v for v in catalog["stageModules"] if v["id"]==stage["moduleId"] and v["revision"]==stage["revision"])
            z=m["stackHeightMm"] if "stackHeightMm" in m else 37.5
            plates[p["id"]]=base.Multiplied(pose(z=z))
            if p["id"] in records:frozen(p["id"],records[p["id"]],base);continue
            if abs(stage["qMm"])>1e-8:raise ValueError("非零滑台位移需要绑定行程的实体登记 "+p["id"])
            off=m["centerTopOriginMm"];fixed=base.Multiplied(pose(-off["xMm"],-off["yMm"]))
            asset=next(a for a in m["assemblyAssets"] if a["role"]=="reference-assembly")
            add(p["id"],root/"library/assets"/asset["path"],asset["sha256"],fixed,[])
        else:
            if p["id"] not in records:raise ValueError("缺少子板实体及支撑高度 "+p["id"])
            rec=records[p["id"]];frozen(p["id"],rec,base);plates[p["id"]]=base.Multiplied(pose(z=rec["topHeightMm"]))
    for inst in layout["instances"]:
        key=inst["id"];kit=kits[inst["kitId"]];g=kit["layout"];world=pose(inst["xMm"],inst["yMm"],inst.get("elevationMm",0),inst.get("rotationDeg",0))
        if inst.get("boardId"):world=plates[inst["boardId"]].Multiplied(world)
        if key in records:frozen(key,records[key],world);continue
        if inst.get("laserAdapter",{}).get("enabled") or any(old!=new for old,new in inst.get("universalPostSelection",{}).items()):
            raise ValueError("需登记已换柱或带转接件的实际 STEP "+key)
        a=kit.get("assemblyReference") or {};ev=g.get("geometryEvidence",{});tr=ev.get("sourceToKit")
        if not a.get("stepPath") or not a.get("sourceStepSha256"):raise ValueError("缺少冻结总装 "+key)
        f=root/"library/assets"/a["stepPath"];sha=a["sourceStepSha256"]
        if tr:
            origin=tr["originSourceMm"];rotation=tr["rotationRows"]
            world=world.Multiplied(rigid([line+[-sum(x*y for x,y in zip(line,origin))] for line in rotation]))
        else:
            _,_,leaf=source(f,sha);boxes=[bbox(v) for _,v in leaf];b=g["collisionBoundsMm"]
            vals=[min(v[0] for v in boxes),min(v[1] for v in boxes),max(v[3] for v in boxes),max(v[4] for v in boxes)]
            if any(abs(x-b[k])>.65 for x,k in zip(vals,("xMin","yMin","xMax","yMax"))) or abs(min(v[2] for v in boxes))>.65:
                raise ValueError("CAD 坐标未与登记基面/轮廓吻合，需要 sourceToKit "+key)
        add(key,f,sha,world,[])
    for hardware in annex.get("supportFasteners", []):
        point = hardware["centerMm"]
        fastener = geometry.parent / hardware["step"]
        add(hardware["id"], fastener, hardware["sha256"], pose(*point), [])
    main=None
    if annex.get("mainBoard"):
        rec=annex["mainBoard"]
        if not rec.get("datumEvidence"):raise ValueError("主板缺少板面及安装基准")
        path=geometry.parent/rec["step"];location=rigid(rec["sourceToBoard3x4"])
        _,_,leaves=source(path,rec["sha256"])
        shape=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(shape)
        for _,leaf in leaves:builder.Add(shape,leaf.Moved(location))
        main=(shape,bbox(shape));evidence.append(dict(id="main-board",sourceSha256=rec["sha256"],leafCount=len(leaves)))
    return rows,dict(assets=evidence,cutouts=annex.get("cutouts",[]),additionalSegments=annex.get("spatialSegments",[])),assemblies,main

def board_solid(layout,cutouts,threaded=False):
    b=layout["board"]
    if b.get("registeredBoardId"):raise ValueError("登记异形主板需其真实外形 CAD")
    w,h,t=b["widthMm"],b["heightMm"],b.get("thicknessMm",12.5);ax=gp_Dir(0,0,1)
    board=BRepPrimAPI_MakeBox(gp_Pnt(0,0,-t),w,h,t).Shape();tools=TopoDS_Compound();builder=BRep_Builder();builder.MakeCompound(tools);count=0
    if threaded:
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeChamfer
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS
        chamfer = BRepFilletAPI_MakeChamfer(board)
        outer = TopExp_Explorer(board, TopAbs_EDGE)
        while outer.More():
            chamfer.Add(.3, TopoDS.Edge(outer.Current()))
            outer.Next()
        chamfer.Build()
        if not chamfer.IsDone():
            raise ValueError("主板十二条外棱 C0.3 建模失败")
        board = chamfer.Shape()
    def hole(x,y,z,r,depth):
        nonlocal count
        builder.Add(tools,BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),ax),r,depth).Shape());count+=1
    for c in cutouts:
        x,y=c["center"];hole(x,y,-t-1,c["diameterMm"]/2,t+2)
    if threaded:
        p=b["pitchMm"];e=b["edgeOffsetMm"];fixed={(v["columnIndex"],v["rowIndex"]) for v in b["mountingHoles"]}
        for i in range(math.floor((w-2*e)/p)+1):
            for j in range(math.floor((h-2*e)/p)+1):
                x=e+i*p;y=e+j*p;isfixed=(i,j) in fixed
                hole(x,y,-t-1,3.3 if isfixed else 2.5,t+2)
    if count:board=BRepAlgoAPI_Cut(board,tools).Shape()
    if threaded:
        # Subtract the counterbores after the drills. A compound containing two
        # intersecting cutters at each corner can silently retain the smaller bore.
        counterbores = TopoDS_Compound()
        builder.MakeCompound(counterbores)
        for i, j in sorted(fixed):
            point = gp_Pnt(e + i*p, e + j*p, -6.5)
            tool = BRepPrimAPI_MakeCylinder(gp_Ax2(point, ax), 5.5, 7).Shape()
            builder.Add(counterbores, tool)
        board = BRepAlgoAPI_Cut(board, counterbores).Shape()
    return (board,bbox(board))

def edge_distance(a,b,body,tube_radius):
    shape,box=body
    separation=math.sqrt(sum(max(0,box[i]-max(a[i],b[i]),min(a[i],b[i])-box[i+3])**2 for i in (0,1,2)))
    if separation>max(12.,tube_radius+1.e-5):return separation
    edge=BRepBuilderAPI_MakeEdge(gp_Pnt(*a),gp_Pnt(*b)).Edge()
    algorithm=BRepExtrema_DistShapeShape(edge,shape);algorithm.Perform()
    if not algorithm.IsDone():raise ValueError("实体距离运算未收敛")
    return algorithm.Value()

def write_board(file,board):
    writer=STEPControl_Writer()
    if writer.Transfer(board[0],STEPControl_AsIs)!=IFSelect_RetDone or writer.Write(str(file))!=IFSelect_RetDone:
        raise ValueError("底板 STEP 导出失败")

def write_assembly(file,subassemblies,board):
    d=doc();tool=XCAFDoc_DocumentTool.ShapeTool_s(d.Main());root=tool.NewShape();TDataStd_Name.Set_s(root,TCollection_ExtendedString("HKSOP"))
    base=tool.AddShape(board[0],False);TDataStd_Name.Set_s(base,TCollection_ExtendedString("Breadboard"));tool.AddComponent(root,base,TopLoc_Location())
    for name,path,sha,location in subassemblies:
        _,roots,_=source(path,sha);child=tool.NewShape()
        if not XCAFDoc_Editor.Extract_s(roots,child):raise ValueError("源装配层级复制失败 "+name)
        inst=tool.AddComponent(root,child,location);TDataStd_Name.Set_s(inst,TCollection_ExtendedString(name))
    tool.UpdateAssemblies();writer=STEPCAFControl_Writer();writer.SetNameMode(True);writer.SetColorMode(True)
    if not writer.Transfer(d,STEPControl_AsIs) or writer.Write(str(file))!=IFSelect_RetDone:raise ValueError("总装 STEP 导出失败")
