#!/usr/bin/env python3
"""Exercise the board rules, four optical briefs, native replay and the six handoffs."""
import argparse
from concurrent.futures import ProcessPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from math import dist, isclose, pi
from pathlib import Path
import hashlib
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from layer2_challenges import ALL_FIXTURES,BRIEFS
from optical_graph import Aperture, BeamDump, FiberSource, FiberCoupler, HeightShift, LaserSource, OpticalGraph
from optical_layout import NAMES, STEP_FILES, output_directory, page, run
from optical_layout.bridge_refactored import forbid_extensions,native,save
from optical_layout.folding_planner import State, crosses, linebox, pose
from optical_layout.hole_snapper import FitError, snap, xy
from optical_layout.lowering import bounds, lower
from optical_layout.stage_policy import evaluate

HERE=Path(__file__).resolve().parent
def check(value,reason):
    if not value:raise ValueError(reason)
def read(path):return json.loads(path.read_bytes())
def rules():
    graph=OpticalGraph("tight-aperture")
    graph.add("In",LaserSource(780,1));graph.add("Iris",Aperture(3));graph.add("Stop",BeamDump())
    graph.link("In.front","Iris.a",exact_mm=100,tol_mm=.5);graph.link("Iris.b","Stop.front")
    g=graph.to_dict(True);decision=evaluate(g);row=decision["nodes"]["Iris"]
    check("S3" in row["rules"] and decision["boardAxisHeightMm"]==87.5,"S3/87.5")
    model=lower(g,decision)
    for hand in ("l","r"):
        kit="stage-board-lbtek-ls30-6"+hand+"1-r3"
        for delta,ok in ((-.75,True),(.75,True),(1.1,False)):
            p=pose(model["nodes"]["Iris"],(100+delta,100),0,1,kit,0)
            try: ledger=snap(model,State({"Iris":p},{},[],p.box),250,200,25)
            except FitError:
                check(not ok,"正常初调余量被拒绝");continue
            check(ok and abs(ledger["nodes"]["Iris"]["qMm"]-delta)<1e-6 and min(ledger["nodes"]["Iris"]["remainingTravelMm"])>=2,"q 行程")
    for bad in ("extension-ex25-r1","extension-ed12p5-r1"):
        try:forbid_extensions({"moduleQuantities":[[bad,1]]})
        except ValueError:pass
        else:raise ValueError("EX/ED 反例未拦截")
    for mode,first,last in (("straight",62.5,100),("turn90",100,62.5)):
        g=OpticalGraph("registered-periscope",default_plane_height_mm=first)
        g.add("Launch",FiberSource(780,1.2,power_mw=1));g.add("Relay",HeightShift(first,last,mode))
        g.add("Receive",FiberCoupler(allow_uncompensated_pm=True, design_diameter_mm=1.2,required_pol="S" if mode=="turn90" else "P",steering_mirrors=0))
        g.link("Launch.front","Relay.a",min_mm=95,max_mm=170);g.link("Relay.b","Receive.front",min_mm=105,max_mm=160)
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td);run(g,dest,"450x350",12.5,"fixed")
            native_report=read(dest/"verification.json")
            check(native_report["valid"] and not native_report["pendingCAD"],"标准爬架入射方向或换柱")
            paths=native_report["trace"]["segments"]
            check(any(abs(x.get("from3D",{}).get("z",-1000)-first)<.01 and abs(x.get("to3D",{}).get("z",-1000)-last)<.01 for x in paths),"爬架内部反射高度")
            check(paths[-1]["hitInstanceId"]=="Receive" and abs(paths[-1]["axisHeightMm"]-last)<.01,"爬架出口接收高度")
    from pm_layout_checks import check as pm_check
    return pm_check()+["标准直向反用及 90° 转向爬架的双镜高度、方向、换柱与原生终端复验","S3 独立严格公差与 87.5 mm 自动光高","S4 左右手 ±0.75 mm 初调与 1.1 mm 越限拒绝","EX25/ED12.5 反例被拒绝"]


def exam(job):
    i,folder=job;f=Path(folder)/f"challenge_{i}"
    board,pitch,policy,why,hardware=BRIEFS[i-1];graph=ALL_FIXTURES[i-1]()
    summary=run(graph,f,board,pitch,policy,why,hardware)
    for name in ["walkthrough.md","step_by_step_walkthrough.html",*(s for group in STEP_FILES for s in group)]:
        check((f/name).stat().st_size>0,name)
    spec=spec_from_file_location("exam_graph",f/"step2_graph.py");module=module_from_spec(spec);spec.loader.exec_module(module)
    check(module.build_graph().to_dict()==graph.to_dict(),"独立 graph.py 往返不一致")
    graph_data=read(f/"board-optical-verification.json");t=graph_data["trace"]["terminals"]
    stage=read(f/"step3_stages_and_runs.json");l=read(f/"step5_hole_ledger.json");fold=read(f/"step4_folding_plan.json")
    check(graph_data["trace"]["valid"],"板长追迹");check(l["zeroEXED"],"EX/ED")
    forbid_extensions(read(f/"project.zzoptics.json"),read(f/"bom.json"))
    with tempfile.TemporaryDirectory() as td:
        receipt=Path(td)/"receipt.json";rc=native("verify",f/"project.zzoptics.json",receipt)
        check(rc==0 and read(receipt)==read(f/"verification.json"),"交付文件原生复验回执不一致")
    xml=ET.parse(f/"step6_board_layout.svg")
    layers={n.get("id") for n in xml.getroot() if n.tag.endswith("}g")}
    check(len(layers)==7,"工程图七层")
    used={v["id"] for v in l["board"]["mountingHoles"]};check(len(used)==4,"沉孔")
    for k,r in l["nodes"].items():
        holes={v["id"] for v in r["screws"]};check(bool(holes) and not used&holes,"螺孔所有权 "+k);used|=holes
        if r["mode"]=="stage":check(len(holes)==4 and abs(r["qMm"])<=1 and min(r["remainingTravelMm"])>=2,"滑台 "+k)
        for region in r["operatorKeepout"]:
            corners=list(map(xy,region["polygon"]));check(sorted(round(dist(corners[i],corners[(i+1)%4]),4) for i in range(4))==[25.,25.,30.,30.],"25×30 mm")
            from optical_layout.footprints import overlaps
            box=bounds(corners);check(all(not overlaps(corners,list(map(xy,poly))) for n,rr in l["nodes"].items() if k!=n for poly in rr["collisionPolygonsMm"]),"手部与安装件相交")
            for e in fold["paths"].values():
                check(all(not overlaps(corners,[(a[0]-.0001,a[1]-.0001),(b[0]+.0001,b[1]+.0001),(b[0]+.0002,b[1]+.0002)]) for a,b in zip(e["points"],e["points"][1:])),"手部与光束相交")
    for wish in l["wishes"]:
        check(2<=len(wish["lowerM6"])<=4 and wish["borrowRadiusMm"]<=50.001,"WISH 借孔 "+wish["wishId"])
    req={k for k,v in stage["nodes"].items() if v["required"]}
    check(stage["boardAxisHeightMm"]==[62.5,100,100,62.5][i-1],"光高")
    checks={}
    if i==1:
        b=t["PM"]["beams"][0]
        check(req=={"Lshort"} and "S2" in stage["nodes"]["Lshort"]["rules"] and stage["nodes"]["PM"]["coveredBy"]=="MFT","扩束镜组 / MFT")
        check(any(w["trigger"]=="low_profile_stage_mount" and w["availableHeadroomMm"]==25 for w in l["wishes"]),"固定高度低剖面座")
        check(abs(b["diameter_mm"]/2.1-1)<=.05 and abs(b["waist_diameter_mm"]-2.1)<.001,"PM 入口实算 2w 与目标 2.1 mm")
        check(abs(t["Monitor"]["power_mw"]-1.2)<1e-5 and abs(b["power_mw"]-28.8)<1e-5,"监测比例")
        waist=1.05;w=b["diameter_mm"]/2;wave=b["wavelength_nm"]*1e-6
        eta=4/((waist/w+w/waist)**2+(pi*w*waist/(wave*b["radius_mm"]))**2)
        checks=dict(fiberActualDiameterMm=b["diameter_mm"],designWaistDiameterMm=b["waist_diameter_mm"],idealGaussianOverlap=eta,
                    openBoardEntry=l["externalInputs"]);check(eta>.9 and l["externalInputs"],"入口及高斯模式")
    if i==2:
        check(req=={"End","Camera"} and all("S1" in stage["nodes"][k]["rules"] for k in req),"猫眼 / 焦面相机")
        check(all(b["freq_shift_mhz"]==200 for v in t.values() for b in v["beams"]),"双通频移")
        check(abs(t["Camera"]["power_mw"]-.8)<1e-7 and abs(t["PM"]["power_mw"]-39.2)<1e-7,"2% 取样")
        air=next(e["resolved_air_mm"] for e in graph_data["links"] if {e["u"],e["v"]}=={"AO.b","Cat.a"})
        drift=next(s["resolved_mm"] for s in graph_data["spans"] if s["start"]=="Cat.b")
        fcat=next(n["params"]["f_mm"] for n in graph_data["nodes"] if n["id"]=="Cat")
        scan=[]
        for kick in (-.003,0,.003):
            x=0.;a=kick
            for length,lens in [(air,True),(2*drift,True),(air,False)]:
                x+=length*a
                if lens:a-=x/fcat
            scan.append(dict(inputMrad=kick*1000,residualMrad=1000*(a+kick),walkoffMm=x))
        check(all(abs(v["residualMrad"])<1e-7 and abs(v["walkoffMm"])<1e-7 for v in scan),"扫频猫眼指向")
        checks=dict(paraxialScan=scan,frequencyShiftMHz=200)
    if i==3:
        check(req=={"Obj"} and stage["nodes"]["Camera"]["coveredBy"]=="collimated_monitor","准直相机豁免")
        cut=l["boardCutouts"][0];check(cut["diameterMm"]>=max(25,3*cut["beamDiameterMm"]),"穿板孔径")
        below={v["id"]:v for v in l["spatialAssemblies"]["Down"]}
        check(below["Obj"]["stageAxisXYZ"][2] in (-1,1) and min(below["Obj"]["remainingTravelMm"])>=2 and below["Obj"]["clearanceToPlateUndersideMm"]>0,"板下滑台")
        check(isclose(below["Win"]["axisXYZmm"][2]-3-below["Atoms"]["axisXYZmm"][2],48,abs_tol=1e-6),"窗背 48")
        check({b["wavelength_nm"] for b in t["Atoms"]["beams"]}=={399,532} and all(b["pol"]=="RHC" and abs(abs(b["stokes"][2])-1)<1e-7 and abs(b["defocus_mm"])<.15 for b in t["Atoms"]["beams"]),"双色焦点")
        checks=dict(cutoutDiameterMm=cut["diameterMm"],focusResidualMm={b["wavelength_nm"]:b["defocus_mm"] for b in t["Atoms"]["beams"]})
    if i==4:
        check(not req and t["PD"]["power_mw"]>4.499 and t["Dump"]["beams"][0]["freq_shift_mhz"]==80,"对射锁频")
        check(all(isclose(t[k]["power_mw"],25.5,abs_tol=1e-6) for k in ("PM_A","PM_B")),"纤路分配")
        check(sum(r["type"]=="Steer" for r in l["nodes"].values())==4 and l["externalInputs"],"四面调节镜与入口")
        checks={"ratioSweep":[]}
        for ratio in (.01,.25,.5,.75,.99):
            d=graph.to_dict();next(n for n in d["nodes"] if n["id"]=="Ratio")["params"]["split_reflect_ratio"]=ratio
            tt=OpticalGraph.from_dict(d).to_dict(True)["trace"]["terminals"]
            actual=tt["PM_B"]["power_mw"]/51
            check(abs(actual-ratio)<1e-7,"连续可调分束器");checks["ratioSweep"].append([ratio,actual])
    summary["physics"]=checks;summary["verificationSha256"]=hashlib.sha256((f/"verification.json").read_bytes()).hexdigest()
    return summary


def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument("-o","--output",type=Path,default=Path(os.environ.get("HKSOP_TEST_OUTPUT", HERE.parent / "results")) / "layer2-exam");a=ap.parse_args(argv)
    out=output_directory(a.output);checks=rules();result=[];errors=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(exam,(i,str(out))) for i in range(1,5)]
        for i,j in enumerate(jobs,1):
            try:result.append(j.result());print(f"PASS challenge_{i}",flush=True)
            except Exception as ex:errors.append({"challenge":i,"error":str(ex)});print(f"FAIL challenge_{i}: {ex}",file=sys.stderr,flush=True)
    save(out/"acceptance.json",dict(valid=len(result)==4 and not errors,rules=checks,challenges=result,failures=errors))
    html="<header><small>HKSOP　/　第二层验收</small><h1>四道光路设计实战</h1><p>"+f"{len(result)}/4 项完成原生复验。每题含六步记录、工程图与螺孔账本。"+'</p><a href="acceptance.json">验收数据</a></header>'
    for row in result:
        n=next(i for i,fn in enumerate(ALL_FIXTURES,1) if fn().name==row["name"])
        html+=f'<section><h2><a href="challenge_{n}/step_by_step_walkthrough.html">第 {n} 题 · {row["name"]}</a></h2><p>{row["steps"][0]}</p><p>{row["steps"][3]} {row["steps"][4]}</p></section>'
    save(out/"index.html",page("HKSOP · 四道光路设计实战",html))
    return int(bool(errors) or len(result)!=4)


if __name__=="__main__":sys.exit(main())
