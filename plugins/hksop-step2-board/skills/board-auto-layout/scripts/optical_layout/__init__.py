"""OpticalGraph to a constrained M6 optical board, with an auditable native verification."""
from collections import Counter
from html import escape
from pathlib import Path
from pprint import pformat
import json
import math

from optical_graph import OpticalGraph
from optical_graph.renderer import render_svg
from .board_renderer import board_svg
from .bridge_refactored import finish_native, forbid_extensions, save, verify_project
from .folding_planner import State, linebox, plans, spliced_plans, translations
from .hole_snapper import FitError, fitted_states, snap
from .hksop_runtime import library_root
from .lowering import STANDARD_BOARDS, lower, rigid_runs
from .stage_policy import evaluate

STEP_FILES=[
 ["step1_design_rationale.md"],
 ["step2_graph.py","step2_trace.json","step2_schematic.svg"],
 ["step3_stages_and_runs.json"],
 ["step4_folding_plan.json","step4_folding_sketch.svg"],
 ["step5_hole_ledger.json","custom-wishes.json","custom-wishes.md"],
 ["step6_board_layout.svg","project.zzoptics.json","verification.json","bom.json","board-optical-verification.json","native-coverage.json","compose-recipe.json","native-preview.svg","native-design.zip"]]
NAMES=["实验需求与参数选择","光学图与第一层体检","滑台选择与刚性光段","选板与折转","逐孔装配与定制件","工程图与闭环复验"]
CSS="""*{box-sizing:border-box}body{margin:0;background:#eff3f1;color:#203c40;font:16px/1.65 system-ui,'PingFang SC',sans-serif}main{max-width:1120px;margin:auto;padding:42px 32px 72px}header{border-bottom:2px solid #145e55;padding:0 0 15px}h1{font-size:clamp(25px,4vw,42px);line-height:1.2;margin:8px 0 18px;overflow-wrap:anywhere}h2{font-size:21px}h3{font-size:16px}a{color:#08675b;text-underline-offset:3px}nav,.files{display:flex;flex-wrap:wrap;gap:6px 18px}section{background:white;border:1px solid #cfdbd5;border-radius:6px;padding:18px 24px;margin:16px 0}section p{max-width:88ch;margin:9px 0}img{display:block;width:100%;height:auto;border:1px solid #d7e0dc;margin:16px 0}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}td,th{padding:6px 9px;border-bottom:1px solid #dbe5df;text-align:left}small{color:#446961}table,pre{font-size:14px}ol{padding-left:23px}li{margin:4px 0}@media(max-width:640px){main{padding:20px 10px}section{padding:12px}.scroll{overflow:auto}}"""


def output_directory(folder):
    f=Path(folder).resolve()
    root = library_root()
    for forbidden in (root, root.parent/"HKSOP", root.parent/"HKSOP-refactored"):
        if f==forbidden or forbidden in f.parents:raise ValueError("输出目录位于受保护的库内")
    f.mkdir(parents=True,exist_ok=True)
    return f


def realized_graph(graph,state,z):
    data=graph.to_dict();old=data["default_plane_height_mm"];data["default_plane_height_mm"]=z
    for n in data["nodes"]:
        if n["type"] in ("LaserSource","FiberSource") and n["params"].get("height_mm")==old:
            n["params"]["height_mm"]=z
    for e in data["links"]:
        if e["id"] in state.paths and e["exact_mm"] is None:
            e["min_mm"]=e["max_mm"]=state.paths[e["id"]]["airMm"]
    return OpticalGraph.from_dict(data).to_dict(True)


def graph_code(graph):
    d=graph.to_dict()
    rows=["from optical_graph import OpticalGraph, "+", ".join(sorted({n["type"] for n in d["nodes"]})),"",
          "def build_graph():",f'    g = OpticalGraph({graph.name!r}, default_plane_height_mm={d["default_plane_height_mm"]!r})']
    for n in d["nodes"]:
        args=", ".join(k+"="+repr(v) for k,v in n["params"].items())
        rows.append(f'    g.add({n["id"]!r}, {n["type"]}({args}))')
    if any(n["id"]!=f"L{i+1}" for i,n in enumerate(d["links"])):
        return "from optical_graph import OpticalGraph\n\n\ndef build_graph():\n    return OpticalGraph.from_dict("+pformat(d,sort_dicts=False)+")\n"
    for e in d["links"]:
        args=", ".join(k+"="+repr(e[k]) for k in ("exact_mm","tol_mm","min_mm","max_mm","can_fold","note"))
        rows.append(f'    g.link({e["u"]!r}, {e["v"]!r}, {args})')
    for s in d["spans"]:
        rows.append(f'    g.span({s["start"]!r}, {s["end"]!r}, exact_mm={s["exact_mm"]!r}, tol_mm={s["tol_mm"]!r}, note={s["note"]!r})')
    return "\n".join(rows+["    return g",""])


def power_summary(trace):
    return "；".join(f"{n} {r['power_mw']:.3g} mW"+("（"+"/".join(sorted({f'{b["freq_shift_mhz"]:+g} MHz，{b["pol"]}' for b in r["beams"]}))+"）" if r["beams"] else "") for n,r in trace["terminals"].items())


def wish_text(wishes):
    a=["# 定制件加工交接","","坐标单位 mm，行列以面包板左下角为起点。制造前须复核实物接口。",""]
    for w in wishes:
        a += ["## "+w["wishId"]+" · "+w["node"],"",f'- 触发条件 {w["trigger"]}，硬件 {w["hardware"]}。',
              "- 光心 "+str(w["opticalDatum"])+"，加工包络 "+str(w["envelopeBudgetMm"])+"。",
              "- 固定孔 "+", ".join(v["id"] for v in w["lowerM6"])+f'，最远借孔 {w["borrowRadiusMm"]:.2f} mm。',
              "- 相邻包络 "+", ".join(r["id"] for r in w["keepoutNeighbors"])+"。",""]
        if "heightShift" in w:a += [f'- 入口 {w["heightShift"]["inputHeightMm"]} mm，出口 {w["heightShift"]["outputHeightMm"]} mm，模式 {w["heightShift"]["mode"]}。',""]
        if "riserThicknessMm" in w:a += [f'- 裸机增高 {w["riserThicknessMm"]:.2f} mm。',""]
        if "availableHeadroomMm" in w:a += [f'- 滑台上板 Z={w["stageTopZ"]}，可用高度 {w["availableHeadroomMm"]}。',""]
        if "spatialAssembly" in w:a+=[w["verticalStageMount"],""]
    return "\n".join(a)


def page(title,content):
    return '<!doctype html><html lang="zh-Hans"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escape(title)+'</title><style>'+CSS+'</style><main>'+content+'</main></html>\n'


def walkthrough(out,name,summaries,data):
    nav='<nav>'+''.join(f'<a href="#s{i}">Step {i}</a>' for i in range(1,7))+'</nav>'
    html='<header><small>HKSOP　/　光路设计审阅</small><h1>'+escape(name)+'</h1>'+nav+'</header>'
    md=["# "+name,""]
    for i,(title,summary,files) in enumerate(zip(NAMES,summaries,STEP_FILES),1):
        html+=f'<section id="s{i}"><h2>Step {i}　{title}</h2><p>'+escape(summary)+'</p>'
        if i==2:
            table='<div class="scroll"><table><thead><tr><th>终端</th><th>波长 nm</th><th>功率 mW</th><th>2w mm</th><th>zR mm</th><th>频移 MHz</th><th>偏振</th></tr></thead><tbody>'
            for key,t in data["trace"]["terminals"].items():
                for b in t["beams"]:
                    vals=[key,f'{b["wavelength_nm"]:g}',f'{b["power_mw"]:.3f}',f'{b["diameter_mm"]:.4f}',f'{b["q_mm"][1]:.3f}',f'{b["freq_shift_mhz"]:+g}',b["pol"]]
                    table+='<tr>'+''.join('<td>'+escape(v)+'</td>' for v in vals)+'</tr>'
            html+=table+'</tbody></table></div>'
        if i in (2,4,6):
            img={2:"step2_schematic.svg",4:"step4_folding_sketch.svg",6:"step6_board_layout.svg"}[i]
            html+=f'<a href="{img}"><img src="{img}" alt="{title}" loading="lazy"></a>'
        html+='<div class="files">'+''.join(f'<a href="{f}">{f}</a>' for f in files)+'</div></section>'
        md.extend([f"## Step {i}　{title}","",summary,""," · ".join(f"[{f}]({f})" for f in files),""])
    save(out/"step_by_step_walkthrough.html",page(name,html));save(out/"walkthrough.md","\n".join(md))


class PendingHeightShift(RuntimeError):
    """The candidate reaches its hardware handoff before native optical certification."""


def run_layer2_pipeline(graph,out,board="auto",pitch=None,height_policy="auto",rationale="",hardware=None,counter_count=4):
    if isinstance(graph,dict):
        if "trace" in graph and graph["trace"].get("valid") is not True:raise ValueError("上游 trace 未通过体检")
        graph=OpticalGraph.from_dict(graph)
    out=output_directory(out)
    from .comb_planner import topology,candidates
    requested_pitch=pitch
    pitch=pitch or (12.5 if any(type(n).__name__=="PBS" for n in graph.nodes.values()) else 25.)
    if pitch not in (12.5,25) or counter_count not in (4,8):raise ValueError("M6 接口允许 12.5 / 25 mm 孔距与 4 / 8 颗沉孔")
    d=graph.to_dict(True)
    if not d["trace"]["valid"]:raise ValueError("第一层光学检查失败 "+str(d["trace"]["diagnostics"]))
    if board=="auto":sizes=STANDARD_BOARDS
    else:
        try:w,h=map(float,board.lower().split("x"))
        except (ValueError,AttributeError):raise ValueError("板型应为 auto 或 宽x高") from None
        if not all(math.isfinite(v) and 50<=v<=2000 for v in (w,h)):raise ValueError("板型超出设计尺寸范围")
        sizes=[(w,h)]
    stages=evaluate(d,height_policy);m=lower(d,stages,hardware);z=stages["boardAxisHeightMm"]
    rationale=rationale or f'{graph.name}。原始光学设计的输入、端口、机制及工作点见 Step 2。名义光高 {z:g} mm，板型 {board}，孔距 {pitch:g} mm。'
    save(out/"step1_design_rationale.md","# "+graph.name+"\n\n"+rationale+"\n")
    save(out/"step2_graph.py",graph_code(graph));save(out/"step2_trace.json",d);save(out/"step2_schematic.svg",render_svg(graph,d))
    logs=[];chosen=None
    unknown_shifts={k for k,n in m["nodes"].items() if n["type"]=="HeightShift" and not n["kit"]}
    # Alternative root/branch orders sample distinct topology families before refining.
    seeds=list(dict.fromkeys([0,4,1,5,3,126,131,129,2,7,19,51,83,95,118,143]+list(range(160))))
    pattern=topology(m)
    if pattern and board=="auto":
        sizes=sorted(set(STANDARD_BOARDS+[(w,h) for w in (400,425,450,475,500) for h in (225,250,275,300,325)]),key=lambda wh:(wh[0]*wh[1],wh))
    for w,h,pitch in [(w,h,p) for p in ([pitch,25.] if requested_pitch is None and pitch==12.5 else [pitch]) for w,h in sizes]:
        for ordinal,seed in enumerate([0] if pattern else seeds[:8]+seeds):
            direct_only=ordinal<8
            beam=38 if len(m["edges"])>=12 else (30 if len(m["edges"])<9 else 18)
            if pattern:states,info=candidates(m,pattern,w,h,pitch),dict(strategy="bus-and-comb")
            else:states,info=plans(m,w,h,pitch,seed,beam,36 if beam>=24 else 28)
            log=dict(boardMm=[w,h],seed=seed,beamWidth=beam,preferAllDirect=direct_only,**info);logs.append(log);fail=Counter()
            if not states and ordinal in (5,11) and len(m["edges"])<=12:
                from itertools import islice
                joined=list(islice(spliced_plans(m,w,h,pitch,ordinal//3),12))
                states=[s for s,edge in joined];log["joinedChannels"]=[edge for s,edge in joined]
            if not pattern and ordinal==0:
                from itertools import chain
                from .reference_routes import registered
                states=chain(registered(m,w,h,pitch),states)
            for s in states:
                if pattern:
                    from .footprints import conflicts
                    blocked=conflicts(s)
                    if blocked:fail[blocked]+=1;continue
                for trial in ((s,) if pattern else (fit for moved in translations(s,w,h,pitch) for fit in fitted_states(m,moved,w,h,pitch))):
                    if direct_only and ordinal!=0 and any(abs(v-round(v/pitch)*pitch)>.001 for q in trial.poses.values()
                                           if q.kit and not q.stage for v in q.base):
                        fail["优先寻找全部标准基座直接锁孔的可行解"]+=1;continue
                    try:
                        actual=realized_graph(graph,trial,z)
                        if not actual["trace"]["valid"]:
                            raise FitError("实际板长的光学追迹失败 "+str([v["code"] for v in actual["trace"]["diagnostics"] if v["level"]=="ERROR"]))
                        live=lower(actual,stages,hardware)
                        lines=[]
                        for link,path in trial.paths.items():
                            radius=max((max(b["start"]["diameter_mm"],b["end"]["diameter_mm"])/2 for b in live["beams"][link]),default=.25)
                            for j,(a,b) in enumerate(zip(path["points"],path["points"][1:])):
                                lines.append((path["ids"][j],path["ids"][j+1],linebox(a,b,radius)))
                        trial=State(trial.poses,trial.paths,lines,trial.box,trial.folds)
                        ledger=snap(live,trial,w,h,pitch,counter_count)
                        if direct_only and ordinal!=0 and any(wish["trigger"]=="off_grid_adapter" for wish in ledger["wishes"]):
                            raise FitError("刚性安装相位待调整")
                        if unknown_shifts:
                            # A provisional 2-D datum cannot deflect a native ray between distinct heights.
                            # Hand off the exact mount and both port axes as soon as a mechanical layout fits.
                            save(out/"step3_stages_and_runs.json",{**stages,"rigidRuns":rigid_runs(live),"steering":live["steering"]})
                            save(out/"step4_folding_plan.json",dict(valid=False,selectedBoard=[w,h],reason="待入库定制爬架",paths=trial.paths,trials=logs))
                            save(out/"step4_folding_sketch.svg",board_svg(actual,live,trial,ledger,sketch=True))
                            save(out/"step5_hole_ledger.json",ledger);save(out/"custom-wishes.json",dict(wishes=ledger["wishes"]))
                            save(out/"custom-wishes.md",wish_text(ledger["wishes"]));save(out/"board-optical-verification.json",actual)
                            try:
                                report,coverage=verify_project(actual,live,trial,ledger,out)
                            except (ValueError,FitError) as error:
                                coverage={"nativeExitCode":None,"reason":str(error),"pendingHeightShift":sorted(unknown_shifts)}
                            save(out/"native-coverage.json",coverage)
                            raise PendingHeightShift("爬架端口高度未登记："+", ".join(sorted(unknown_shifts))+"。已输出带 2–4 个 M6 孔及双端光高的 custom-wishes.json，待入库后复验。")
                        report,coverage=verify_project(actual,live,trial,ledger,out)
                        if not report["valid"]:
                            raise FitError("原生复验 "+",".join(sorted({v["code"] for v in report["issues"]})))
                    except (FitError,ValueError) as exc:
                        fail[str(exc)[:320]]+=1;continue
                    chosen=trial,live,ledger,report,coverage,actual
                    break
                if chosen:break
            if fail:log["rejected"]=dict(fail)
            if chosen:log["accepted"]=True;break
            if board=="auto" and ordinal>=32:break
        if chosen:break
    if not chosen:
        save(out/"step4_folding_plan.json",dict(valid=False,trials=logs))
        raise FitError("在登记的板型和搜索预算内未取得可验证的方案；详见 "+str(out/"step4_folding_plan.json"))
    state,live,ledger,report,coverage,actual=chosen
    for node,decision in stages["nodes"].items():
        row=ledger["nodes"].get(node,{})
        for line in ledger["spatialAssemblies"].values():
            row=next((r for r in line if r["id"]==node),row)
        for field in ("stageKitId","stageRotationDeg","qMm","remainingTravelMm","stageAxisXYZ","operatorKeepout","operatorKeepoutXYZmm"):
            if field in row:decision[field]=row[field]
    runs=rigid_runs(live);save(out/"step3_stages_and_runs.json",{**stages,"steering":live["steering"],"rigidRuns":runs})
    mirrors=[dict(id=k,opticalCenter=list(q.point),role="光纤位置和指向独立可调" if q.kind=="Steer" else "活距离中插入 90° 折转以腾出装配空间") for k,q in state.poses.items() if q.kind in ("Fold","Steer")]
    plan=dict(selectedBoard=[w,h],pitchMm=pitch,paths=state.paths,folds=mirrors,trials=logs,
              search="有限候选搜索；较小标准板逐档搜索，失败表示此预算下未找到可行解。")
    save(out/"step4_folding_plan.json",plan);save(out/"step4_folding_sketch.svg",board_svg(actual,live,state,ledger,True))
    save(out/"step5_hole_ledger.json",ledger);save(out/"custom-wishes.json",{"wishes":ledger["wishes"]});save(out/"custom-wishes.md",wish_text(ledger["wishes"]))
    save(out/"step6_board_layout.svg",board_svg(actual,live,state,ledger))
    save(out/"board-optical-verification.json",actual);save(out/"native-coverage.json",coverage);bill=finish_native(out)
    required=[(k,r) for k,r in stages["nodes"].items() if r["required"]]
    stage_summary="、".join(k+" "+",".join(r["rules"])+" "+r["stageKitId"].split("-")[-2].upper() for k,r in required) or "无"
    # Keep clause endings ASCII-neutral in the JSON and the Markdown presentation.
    summaries=[rationale,power_summary(d["trace"]),f"LS30 {stage_summary}。板级光高 {z:g} mm，{len(runs)} 组刚性直杆。",
               f"选定 {w:g} × {h:g} mm，孔距 {pitch:g} mm。{len(logs)} 轮排布，加入 {len(mirrors)} 面折转及调节镜。",
               f"锁紧 {ledger['mainBoardScrewCount']} 个板孔，保留 {counter_count} 颗固定沉孔。{len(ledger['wishes'])} 项定制件，手部净空深 25 mm，EX/ED 挂载数为 0。",
               f"原生 verify 返回 0，{len(report['issues'])} 项冲突，{len(coverage['requestedConnections'])} 段定向连接。{len(report['pendingCAD'])} 项原生待确认记录（含光学基准）。按实际板长复算的终端为 "+power_summary(actual["trace"])+"。"]
    walkthrough(out,graph.name,summaries,d)
    return dict(name=graph.name,board=[w,h],pitchMm=pitch,heightMm=z,stages=len(required),mirrors=len(mirrors),wishes=len(ledger["wishes"]),
                pendingCAD=report["pendingCAD"],nativeConnections=len(coverage["requestedConnections"]),nativeIssues=len(report["issues"]),steps=summaries,
                direct=sum(v["mode"] in ("stage","direct") for v in ledger["nodes"].values()),mounts=len(ledger["nodes"]),nativeBOMLines=len(bill["components"]))


run = run_layer2_pipeline
