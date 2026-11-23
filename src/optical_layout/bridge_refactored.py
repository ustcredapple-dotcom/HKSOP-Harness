"""Compose the registered project and ask the unmodified HKSOP executable to verify it."""
from collections import Counter
from pathlib import Path
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

from .lowering import FOUR, SOURCES, bounds, catalog, offset, rectangle, rot, xy
from .hole_snapper import aspoint
from .hksop_runtime import library_root, resolve_node


def save(path, data):
    path=Path(path)
    value=data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    if path.exists() and path.read_bytes()==value.encode():return
    with tempfile.NamedTemporaryFile("w",dir=path.parent,encoding="utf-8",delete=False) as f:
        f.write(value); name=f.name
    os.replace(name,path)


def native(action,source,target):
    root = library_root()
    cmd=[sys.executable,"-B",str(root/"hksop.py"),"design",action,str(source),"-o",str(target),"--node",resolve_node(root)]
    result=subprocess.run(cmd,cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,
                          env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1",HKSOP_PYTHON=sys.executable))
    if result.returncode and not (action=="verify" and result.returncode==1 and target.is_file()):
        raise ValueError("HKSOP "+action+" "+(result.stderr or result.stdout)[-2500:])
    return result.returncode


def forbid_extensions(project,bill=None):
    def walk(v):
        if isinstance(v,dict):
            for key,val in v.items():yield key;yield from walk(val)
        elif isinstance(v,(list,tuple)):
            for val in v:yield from walk(val)
        elif isinstance(v,str):yield v
    bad=sorted({v for v in walk([project,bill]) if re.search(r"(?:^|[-_/])(?:extension[-_])?(?:ex|ed)[-_]?\d+(?:p\d+)?(?:$|[-_/ .])",v,re.I)})
    if bad:raise ValueError("禁止安装 EX/ED "+", ".join(bad))
    if project.get("supportSpans"):raise ValueError("禁止启用 supportSpans")
    return True


def connections(model,state):
    result=[]
    for e in model["edges"]:
        ids=state.paths[e["id"]]["ids"]
        for beam in model["beams"][e["id"]]:
            seq=ids if beam["from"].split(".")[0]==e["a"] else ids[::-1]
            for a,b in zip(seq,seq[1:]):
                edge=dict(from_=a,to=b);edge["from"]=edge.pop("from_")
                if edge not in result:result.append(edge)
    return result


def optical_settings(n,q,rotation,waves):
    t,p=n["type"],n["params"];c=n.get("computed",{})
    heading=q.head*90-rotation
    ap=c.get("clear_aperture_mm") or p.get("active_aperture_mm") or p.get("clear_aperture_mm") or p.get("aperture_inch",1)*25.4
    optics=dict(inserted=True,configured=True,clearApertureMm=ap,surfaceAngleDeg=(heading+90)%360)
    if t in SOURCES:
        st=n["launch"]
        optics.update(elementType="source" if t=="LaserSource" else "coupler",
            source=dict(enabled=True,directionAngleDeg=heading,wavelengthNm=st["wavelength_nm"],powerMw=st["power_mw"],
                beamDiameterMm=st["diameter_mm"],beamQualityM2=st["m2"],wavefrontRadiusMm=st["radius_mm"],
                polarizationType={"P":"linear","S":"linear","LHC":"circular-left","RHC":"circular-right","unpolarized":"unpolarized"}.get(st["pol"],"elliptical" if st["pol"]=="elliptical" else "linear"),
                polarizationAngleDeg=st["pol_angle_deg"] or 0,ellipticityDeg=-math.degrees(math.asin(max(-1,min(1,st["stokes"][2]))))/2))
    elif t in ("FiberCoupler","Camera","Photodiode","BeamDump","TargetPlane","VerticalFold","SpatialFold"):
        optics.update(elementType="coupler",source={"enabled":False,"directionAngleDeg":(heading+180)%360})
    elif t in ("Fold","Steer","RetroMirror"):
        normal=(q.head*90+(180 if t=="RetroMirror" else 135*q.hand))%360
        optics.update(elementType="mirror",surfaceAngleDeg=(normal-90-rotation)%360,mirror=dict(mode="ideal",samples=[]))
    elif t in FOUR:
        optics.update(elementType="pbs" if t=="PBS" else "dichroic",surfaceAngleDeg=(heading+45*q.hand)%180)
        if t!="PBS":
            samples=[]
            for wl in waves:
                ratio=(float(wl in p["reflect_wavelengths_nm"]) if t=="Dichroic" else p.get("reflect_ratio",.5))
                samples.append(dict(wavelengthNm=wl,incidenceAngleDeg=45,reflectanceP=ratio,reflectanceS=ratio,
                    transmittanceP=1-ratio,transmittanceS=1-ratio,reflectionPhaseDifferenceDeg=0,transmissionPhaseDifferenceDeg=0))
            optics["dichroic"]=dict(mode="data",samples=samples)
    elif "Waveplate" in t:
        vals=([(c["resolved_qwp_deg"],90),(c["resolved_hwp_deg"],180)] if t=="DualWaveplate" else
              [(c["resolved_fast_axis_deg"],90 if t=="QuarterWaveplate" else 180)])
        if t=="DualWaveplate" and p.get("order")=="HWP_QWP":vals.reverse()
        optics.update(elementType="waveplate",waveplates=[dict(inserted=True,fastAxisDeg=a,retardanceDeg=d,designWavelengthNm=waves[0]) for a,d in vals])
    elif t=="Lens":optics.update(elementType="lens",focalLengthMm=p["f_mm"])
    else:optics.update(elementType="empty",inserted=False)
    return optics


def rectangle_dict(points):
    a,b,c,d=bounds(points)
    return dict(xMin=a,yMin=b,xMax=c,yMax=d)


def detailed_recipe(graph,model,state,ledger):
    kits,slim,_=catalog();z=model["stages"]["boardAxisHeightMm"]
    nodes=[];modes={};quantities=Counter()
    waves=sorted({r["start"]["wavelength_nm"] for rays in model["beams"].values() for r in rays})
    for k,q in state.poses.items():
        row=ledger["nodes"][k];kit=q.kit;layout=kits[kit]["layout"] if kit else {}
        n=dict(model["nodes"].get(k,dict(type=q.kind,params={})))
        if q.kind in SOURCES:
            n["launch"]=next(b["start"] for bs in model["beams"].values() for b in bs if b["from"].split(".")[0]==k)
        typ=layout.get("opticalType","unsupported")
        custom=bool(row["wishIds"]) or typ=="unsupported" or layout.get("opticalDatumVerified") is False or q.kind in ("AOM","Isolator","Window","CustomTwoPort","Aperture")
        relative_z=row.get("axisHeightMm",z)-(37.5 if q.stage else 0)
        phys_rotation=q.rotation*90
        settings=optical_settings(n,q,0 if custom else phys_rotation,waves)
        primitive=slim[kit]["primitive"] if kit else ("source" if q.kind in SOURCES else "terminal" if q.kind in ("VerticalFold","SpatialFold","TargetPlane") else "lens_filter")
        node=dict(id=k,primitive=primitive,xMm=q.point[0],yMm=q.point[1],nominalAxisHeightMm=relative_z,optics=settings)
        if q.kind=="HeightShift":
            p=n["params"];node.update(mode=p["mode"],inputHeightMm=p["in_height_mm"],outputHeightMm=p["out_height_mm"],
                                     inDirDeg=q.head*90,outDirDeg=((q.head+q.hand)%4)*90 if p["mode"]=="turn90" else q.head*90)
            if not custom:
                node["internalOptics"]={v["id"]:dict(elementType="mirror",inserted=True,configured=True,coatingFaceIndex=0,
                        clearApertureMm=min(v["radiusMm"]*2,p["aperture_inch"]*25.4),mirror=dict(mode="ideal",samples=[]))
                        for v in layout["opticalAssembly"]["nodes"] if v["type"]=="mirror"}
        if custom:
            if primitive=="mirror":
                node.update(inDirDeg=q.head*90,outDirDeg=(q.head+q.hand)*90)
            if primitive=="beamsplitter":node.update(inDirDeg=q.head*90,worldDiagonalAngleDeg=(q.head*90+45*q.hand)%180)
            datum_type=settings["elementType"] if settings["elementType"]!="dichroic" else "empty"
            datum=dict(opticalType=datum_type,clearApertureMm=settings["clearApertureMm"],portDirectionsDeg=[q.head*90,(q.head*90+180)%360])
            if datum_type=="mirror":datum["worldFrontNormalDeg"]=(settings["surfaceAngleDeg"]+90)%360
            if datum_type=="pbs":datum.update(worldDiagonalAngleDeg=(q.head*90+45*q.hand)%180,portDirectionsDeg=[0,90,180,270])
            if q.stage:
                # The native placeholder has just one outline. Supply the load's real mounting
                # interface on the top plate; the full overhanging body is checked in Step 5.
                b=layout.get("baseBoundsMm",dict(xMin=-17.5,xMax=17.5,yMin=-17.5,yMax=17.5))
                poly=[offset(rot(p,q.rotation),q.base) for p in rectangle(b["xMin"],b["yMin"],b["xMax"],b["yMax"])]
                screws=[offset(q.base,rot((i,j),q.rotation)) for i in (-12.5,12.5) for j in (-12.5,12.5)]
            else:
                # The native placeholder exposes one polygon for both support and collision.
                # Test the mounted interface here; Step 5 independently uses the complete CAD outline.
                interface=row.get("adapterBoundsMm") or row["supportBoundsMm"]
                poly=rectangle(*interface);screws=[xy(v) for v in row["screws"]]
            delta=lambda p:(p[0]-q.point[0],p[1]-q.point[1])
            node.update(customBoard={"specialMount":True},wishId=(row["wishIds"] or ["WISH-DATUM-"+k])[0],
                title=k+" · "+q.kind,commercialHardware=[kit] if kit else [],opticalDatum=datum,
                mountingInterface=dict(holeOffsetsMm=[aspoint(delta(p)) for p in screws],degreesOfFreedom=[]),
                envelopeBudgetMm=rectangle_dict([delta(p) for p in poly]))
            if kit and model["stages"]["nodes"].get(k,{}).get("mount")!="low_profile_stage_mount":quantities[kit]+=1
        else:
            node["kitId"]=kit
            if primitive=="mirror":
                node["kind"]=slim[kit]["parameters"]["kind"];node["inDirDeg"]=q.head*90
                node["outDirDeg"]=(q.head*90+(180 if q.kind=="RetroMirror" else q.hand*90))%360
            if primitive=="beamsplitter":
                node.update(inDirDeg=q.head*90,worldDiagonalAngleDeg=(q.head*90+q.hand*45)%180)
            if primitive=="fiber_port":node["outDirDeg" if q.kind in SOURCES else "inDirDeg"]=q.head*90
            if primitive in ("lens_filter","waveplate"):node["inDirDeg"]=q.head*90
        modes[k]=dict(provisional=custom,nominalAxisHeightMm=relative_z,kit=kit,type=q.kind)
        nodes.append(node)
        if q.stage:
            nodes.append(dict(id="LS30-"+k,kitId=q.stage,primitive="stage",**row["baseOrigin"]))
    for chain in ledger["spatialAssemblies"].values():
        for item in chain:
            key=item["id"];kit=model["nodes"][key]["kit"]
            if kit:quantities[kit]+=1
            if item.get("stageKitId"):quantities[item["stageKitId"]]+=1
    # Heights in the compose step refer to the supporting surface. Attach the top-board
    # children before submitting world-space optical connections to the native verifier.
    return dict(name=graph["name"],notes="Layer 2 nominal design. See native-coverage.json and the preliminary mechanical wishes.",
                board={**ledger["board"],"mountingHoles":[{k:h[k] for k in ("rowIndex","columnIndex")} for h in ledger["board"]["mountingHoles"]]},nodes=nodes),modes,quantities


def verify_project(graph,model,state,ledger,out):
    out=Path(out);recipe,modes,modules=detailed_recipe(graph,model,state,ledger)
    save(out/"compose-recipe.json",recipe);native("compose",out/"compose-recipe.json",out/"project.zzoptics.json")
    p=json.loads((out/"project.zzoptics.json").read_bytes());layout=p["layout"]
    stages={b["id"]:b for b in layout.get("subBoards",[])}
    source={n["id"]:n for n in recipe["nodes"]}
    for item in layout["instances"]:
        k=item["id"];q=state.poses[k];row=ledger["nodes"][k];n=source[k];provisional=modes[k]["provisional"]
        if not provisional and item.get("placeholder"):
            # Resolve the payload alone so temporary on-board staging cannot reject its
            # final child-board position. A different catalog selection is never substituted.
            with tempfile.TemporaryDirectory() as td:
                f=Path(td); template={**n,"xMm":100.,"yMm":100.}
                save(f/"in.json",dict(nodes=[template],board=dict(widthMm=250,heightMm=250,pitchMm=12.5)))
                native("compose",f/"in.json",f/"out.json")
                body=json.loads((f/"out.json").read_bytes())["layout"]["instances"][0]
                if body.get("kitId")!=q.kit:raise ValueError(k+" 无已注册顶板负载 "+str(body.get("wishSpec",{}))[:450])
                item.clear();item.update(body)
        if provisional:
            wish=item["wishSpec"];wid=wish["wishId"]
            w=next((a for a in ledger["wishes"] if a["wishId"]==wid),None)
            wish["trigger"]={"off_grid_adapter":"collision","low_profile_stage_mount":"nonstandard_height","vertical_carrier":"custom_board"}.get(w["trigger"],w["trigger"]) if w else "standard_gap"
            wish["whyStandardFailed"]=w or {"kitId":q.kit,"scope":"Registered mechanical carrier has no confirmed native optical transfer for this role. Confirm the project-local ideal datum before fabrication."}
            if q.kit:wish["commercialHardware"]=[q.kit]
        anchor=q.point if provisional else q.base
        rotation=0 if provisional else q.rotation*90
        if q.stage:
            plate=stages["LS30-"+k];r=q.stage_rot;module=next(m for m in catalog()[2]["stageModules"] if m["id"]==q.stage)
            center=xy(module["centerTopOriginMm"]);origin=offset(xy(row["baseOrigin"]),rot((center[0]+row["qMm"],center[1]),r))
            plate.update(aspoint(origin),rotationDeg=r*90);plate["stageMotion"]["qMm"]=row["qMm"]
            item["boardId"]=plate["id"]
            anchor=rot((anchor[0]-origin[0],anchor[1]-origin[1]),-r)
            rotation=(rotation-r*90)%360
        item.update(aspoint(anchor),rotationDeg=rotation,optics=n["optics"])
        if provisional:
            item["datumRotationDeg"]=rotation
        if q.kind=="PBS":item["worldDiagonalAngleDeg"]=(q.head*90+q.hand*45)%180
    layout["planningConnections"]=connections(model,state)
    p["moduleQuantities"]=[]
    for kit,qty in sorted(modules.items()):
        record=catalog()[0][kit]
        if record["layout"].get("placementAllowed") is False:p["moduleQuantities"].append([kit,qty])
        else:p["extras"].append(dict(id="hardware-"+kit,kitId=kit,kind="standard",name=record["name"],model=kit,quantity=qty,unit="套",
                    notes="Project-local optical datum or spatial carrier. Procure this registered assembly once per unit."))
    p["metadata"]["notes"]+=" Board holes, carrier poses and all spatial coordinates are recorded in step5_hole_ledger.json and the vertical carrier WishSpec."
    forbid_extensions(p);save(out/"project.zzoptics.json",p)
    code=native("verify",out/"project.zzoptics.json",out/"verification.json")
    report=json.loads((out/"verification.json").read_bytes())
    return report,dict(nativeExitCode=code,requestedConnections=layout["planningConnections"],hardware=modes,
           modelBoundary={"AOM":"选定衍射级名义中心线。频移与双通由第一层计算。",
                          "Isolator":"正向名义中心线。通轴和反向阻断由第一层计算。",
                          "terminal":"相机、PD、光阱以接受面终止原生平面射线。",
                          "vertical":"原生平面追迹止于穿板转折口，后续空间轴线、焦点及开孔见三维账本。",
                          "coatings":"分光系数与镜面数据为设计值，须实测标定。"})


def finish_native(out):
    f=Path(out);project=f/"project.zzoptics.json"
    native("preview",project,f/"native-preview.svg")
    with tempfile.TemporaryDirectory() as td:
        temp=Path(td);native("export",project,temp)
        for remote,local in (("bom.json","bom.json"),("design.zip","native-design.zip")):
            shutil.copyfile(temp/remote,f/local)
    bill=json.loads((f/"bom.json").read_bytes());forbid_extensions(json.loads(project.read_bytes()),bill)
    return bill
