#!/usr/bin/env python3
"""Validate plugin contracts and run the isolated optical, board, CAD-task and 3-D handoffs."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parents[1]
TESTS=HERE/"tests"
PLUGINS=("hksop-step1-optics","hksop-step2-board","hksop-custom-part","hksop-step3-manufacture")
SKILLS=[("optics-graph-design",),("board-auto-layout",),("custom-part-cad","library-intake"),("json-to-3d-verify","export-packages")]
FIELDS={"name","displayName","version","description","logo","suggestedPrompts"}
from optical_layout.hksop_runtime import library_root, resolve_node, local_environment

def expect(ok,message):
    if not ok:raise ValueError(message)
def read(f):return json.loads(f.read_bytes())
def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def save(f,d):
    f.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=f.parent,delete=False) as s:
        json.dump(d,s,indent=2,ensure_ascii=False,allow_nan=False);s.write("\n");temp=s.name
    os.replace(temp,f)
def manifests(root):
    expect({d.name for d in root.iterdir() if d.is_dir()}==set(PLUGINS),"插件目录数量或名称")
    rows=[]
    for i,name in enumerate(PLUGINS):
        f=root/name;m=read(f/"plugin.json");mirror=read(f/".codex-plugin/plugin.json")
        expect(set(m)==FIELDS and m==mirror and m["name"]==name,"双端清单 "+name)
        expect(all(isinstance(m[k],str) and m[k].strip() for k in FIELDS-{"suggestedPrompts"}),"清单字段 "+name)
        prompts=m["suggestedPrompts"];expect(len(prompts)==3 and len(set(prompts))==3 and all(re.search(r"[\u3400-\u9fff]",q) for q in prompts),"启动语")
        expect(m["logo"]=="assets/logo.svg","图标路径");icon=ET.parse(f/m["logo"]).getroot()
        expect(icon.tag=="{http://www.w3.org/2000/svg}svg" and list(map(float,icon.attrib["viewBox"].split()))==[0,0,128,128],"矢量图标")
        expect((f/"README.md").stat().st_size>30 and not (f/"rules/AGENTS.md").read_text().lstrip().startswith("---"),"入口规则")
        expect({p.name for p in (f/"skills").iterdir() if p.is_dir()}==set(SKILLS[i]),"技能边界 "+name)
        for sk in SKILLS[i]:
            d=f/"skills"/sk;lines=(d/"SKILL.md").read_text().splitlines()
            expect(len(lines)<250 and lines[0]=="---","技能结构 "+sk)
            end=lines.index("---",1);meta=dict(v.split(": ",1) for v in lines[1:end]);expect(meta.get("name")==sk and meta.get("description","").strip(),"技能元数据")
            expect(all(any((d/s).iterdir()) for s in ("references","scripts")),"引用与可执行程序 "+sk)
            for url in re.findall(r"\]\((references/[^)]+)\)","\n".join(lines)):expect((d/url).exists(),"技能引用缺失 "+url)
        for p in f.rglob("*"):expect(not p.is_symlink(),"插件外部软链 "+str(p))
        rows.append(dict(plugin=name,manifestSha256=sha(f/"plugin.json"),codexManifestSha256=sha(f/".codex-plugin/plugin.json"),skills=list(SKILLS[i]),prompts=3,viewBox=icon.attrib["viewBox"]))
    return rows

def isolation(root, prefix=""):
    result=[]
    for name,patterns in [(PLUGINS[0],[r"C0[.]3","Manrope","Hong Kong Standard Optical Protocol","LS30","catalog-ai-slim","cad-venv"]),
                           (PLUGINS[1],[r"C0[.]3\s*[×xX]\s*45","Manrope","Hong Kong Standard Optical Protocol"])]:
        count=0
        for f in (root/(prefix+name)).rglob("*"):
            if not f.is_file() or f.name.startswith("._") or f.suffix.lower() not in (".md",".txt",".py",".json",".svg",".yaml",".yml",".cjs",".js",".html",".toml",".sh"):continue
            body=f.read_text();count+=1
            for term in patterns:expect(not re.search(term,body,re.I),"隔离扫描命中 "+str(f.relative_to(root))+" "+term)
        result.append(dict(plugin=name,textFiles=count,forbiddenPatterns=patterns,matches=0))
    return result

def command(argv,cwd,env,expected=0,timeout=1800):
    start=time.monotonic();r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
    if r.returncode!=expected:raise ValueError(f"{Path(argv[2] if len(argv)>2 else argv[0]).name} 返回 {r.returncode}，期望 {expected}。"+(r.stderr or r.stdout)[-1300:])
    return dict(exitCode=r.returncode,seconds=round(time.monotonic()-start,2),stdout=r.stdout.strip()[-350:],stderr=r.stderr.strip()[-240:])
def py(script,*args):return [sys.executable,"-B",script,*args]

def runtime_fallback_contract(temp, native):
    """Exercise both independent plugin copies with inaccessible and nonworking Node candidates."""
    from importlib.util import module_from_spec, spec_from_file_location
    from unittest.mock import patch
    root=temp/"resolver-test";config=root/"config";config.mkdir(parents=True)
    paths=[("board",HERE/"plugins"/PLUGINS[1]/"skills/board-auto-layout/scripts/optical_layout/hksop_runtime.py"),
           ("manufacture",HERE/"plugins"/PLUGINS[3]/"skills/json-to-3d-verify/scripts/hksop_runtime.py")]
    denied=root/"no-execute";denied.write_text("unavailable")
    cannot_run=root/"bad-runtime";cannot_run.write_text("#!/nonexistent/hksop-test-interpreter");cannot_run.chmod(0o700)
    rows={}
    for label,source in paths:
        spec=spec_from_file_location("hksop_node_"+label,source);module=module_from_spec(spec);spec.loader.exec_module(module)
        real=Path(module.resolve_node(native))
        fallback=root/"dsh-node";pathbin=root/"bin";pathbin.mkdir(exist_ok=True)
        for link in (fallback,pathbin/"node"):
            if not link.is_symlink():link.symlink_to(real)
        save(config/"local-environment.json",{"node":str(cannot_run)})
        with patch.dict(os.environ,{"HKSOP_NODE":str(denied),"PATH":str(pathbin)}),patch.object(module,"DSH_NODE",fallback):
            expect(module.resolve_node(root)==str(fallback),"不可启动的首选解释器未转用 DSH")
        with patch.dict(os.environ,{"HKSOP_NODE":str(denied),"PATH":str(pathbin)}),patch.object(module,"DSH_NODE",root/"missing"):
            expect(module.resolve_node(root)==str(pathbin/"node"),"未转用系统 PATH")
        rows[label]={"unusableEnv":True,"unstartableConfig":True,"dshFallback":True,"pathFallback":True}
    return rows

def protected(native):
    result={}
    for root in (native,):
        for rel in ("hksop.py","AGENTS.md","library/registry.json","library/curation.json","library/catalog.json","library/catalog-ai-slim.json",
                    "engine/compiler/cli.py","engine/design/design.cjs","runtime/releases/editor-web-current/static/optical-engine.js"):
            f=root/rel
            if f.is_file():result[str(f)]=sha(f)
    for f in (TESTS/"layer2_acceptance.py",TESTS/"optical_graph_acceptance.py"):result[str(f)]=sha(f)
    return result

def smoke(root,out,tmp,native):
    # Each stage runs in a separate process. Only its own plugin is copied into its installation.
    installation=tmp/"installation";env=dict(os.environ,HKSOP_ROOT=str(native),HKSOP_NODE=resolve_node(native),PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1");env.pop("PYTHONPATH",None)
    # Native runs can rebuild the excluded commercial resources in this disposable workspace.
    geometry_source = "registered-assets"
    focus = os.environ.get("HKSOP_FOCUS_ASSETS")
    if not focus:
        for candidate in (native / "optical-assets/pm532", Path(os.environ.get("XDG_CACHE_HOME", Path.home()/".cache")) / "hksop-harness/pm532"):
            if (candidate / "head-registration.json").is_file():
                focus = str(candidate)
                break
    if not focus:
        interpreter = os.environ.get("HKSOP_CAD_PYTHON") or local_environment(native).get("cadPython") or sys.executable
        target = tmp / "focus-assets"
        vendor = os.environ.get("HKSOP_VENDOR_DIR")
        # A migrated installation can already have the four licensed supplier models.
        # Only read model files here. The current checkout rebuilds and verifies the assembly.
        if not vendor:
            legacy = native.parent / "HKSOP harness" / "optical-assets/pm532/vendor"
            source_list = read(HERE / "examples/pm-fiber-1x3-532/asset-sources.json")
            if all((legacy / entry["file"]).is_file() for entry in source_list.values()):
                vendor = str(legacy)
        geometry_source = "rebuilt-from-local-supplier-models" if vendor else "rebuilt-from-supplier-downloads"
        input_args = ["--vendor", vendor] if vendor else ["--fetch"]
        command([interpreter,"-B",HERE/"scripts/prepare_focus_assets.py","--root",native,*input_args,"-o",target], tmp, env)
        focus = str(target)
    env["HKSOP_FOCUS_ASSETS"] = str(Path(focus).resolve())
    home=tmp/"home";home.mkdir();env.update(HOME=str(home),TMPDIR=str(tmp))
    audit={"geometrySource": geometry_source}
    audit["dryRun"]=command(py(HERE/"scripts/install_plugins.py"),tmp,env);expect(not list(home.iterdir()),"dry-run 创建了用户配置")
    preview=tmp/"preview";command(py(HERE/"scripts/install_plugins.py","--dry-run","--target",preview,"--mode","copy"),tmp,env);expect(not preview.exists(),"dry-run 写入目标")
    command(py(HERE/"scripts/install_plugins.py","--target",installation,"--mode","copy","--apply"),tmp,env)
    links=tmp/"links";command(py(HERE/"scripts/install_plugins.py","--target",links,"--mode","symlink","--apply"),tmp,env)
    expect(all((links/s).resolve()==root/s for s in PLUGINS),"软链部署")
    def scripts(i):return installation/PLUGINS[i]/"skills"/SKILLS[i][0]/"scripts"
    a=tmp/"01";audit["step1"]=command(py(scripts(0)/"run_design.py","--example","double-pass","-o",a),tmp,env)
    d=read(a/"trace.json");ET.parse(a/"schematic.svg");expect(d["format"]=="hksop-optical-graph-v1" and d["trace"]["valid"] and
        any(e["bidirectional"] for e in d["links"]) and d["trace"]["terminals"]["PM"]["beams"][0]["freq_shift_mhz"]==200,"双通冒烟未追到 +200 MHz")
    circular = [beam[at] for beam in d["trace"]["beams"] for at in ("start","end")
                if beam[at]["pol"] in ("LHC","RHC")]
    expect(circular and all(state["pol_angle_deg"]==0 for state in circular),
           "理想圆偏振的数值方位应在各 Python 运行时一致")
    intake=installation/PLUGINS[2]/"skills/library-intake/scripts/intake.py"
    example=native/"library/standard/coupling/fiber-coupling-mft-rear-r3"
    audit["libraryIntake"]=command(py(intake,example),tmp,env)
    b=tmp/"02";audit["step2"]=command(py(scripts(1)/"optical_graph_to_board.py",a/"trace.json","--board","450x350","--pitch","12.5","--height-policy","auto","-o",b),tmp,env)
    expect(read(b/"verification.json")["valid"] and read(b/"custom-wishes.json")["wishes"],"第二棒需要真实 WISH 和有效工程")
    ET.parse(b/"step6_board_layout.svg")
    c=tmp/"03";c.mkdir();audit["custom"]=command(py(scripts(2)/"parse_wishes.py",b/"custom-wishes.json","-o",c/"cad-tasks.json"),tmp,env)
    wishes=read(b/"custom-wishes.json")["wishes"];tasks=read(c/"cad-tasks.json")["tasks"]
    expect({v["wishId"] for v in tasks}=={v["wishId"] for v in wishes} and all(v["mountingInterface"] for v in tasks),"定制需求传递")
    end=tmp/"04";end.mkdir();checker=scripts(3)/"check_3d_beam_clearance.py"
    audit["placeholderRejected"]=command(py(checker,b/"project.zzoptics.json","-o",end/"blocked.json"),tmp,env,2)
    expect(read(end/"blocked.json").get("pendingCAD") and not read(end/"blocked.json")["valid"],"制造占位拦截未触发")
    # An independent all-standard handoff permits a positive manufacture test without
    # removing the real placeholders which correctly stopped the double-pass project.
    simple=tmp/"standard.py";simple.write_text('from optical_graph import OpticalGraph,FiberSource,FiberCoupler\n\ndef build_graph():\n    g=OpticalGraph("standard-fiber-link")\n    g.add("Launch",FiberSource(532,1.2,power_mw=1))\n    g.add("Receiver",FiberCoupler(allow_uncompensated_pm=True, design_diameter_mm=1.2,steering_mirrors=0))\n    g.link("Launch.front","Receiver.front",min_mm=85,max_mm=180)\n    return g\n')
    s1=tmp/"standard-optics";s2=tmp/"standard-board"
    command(py(scripts(0)/"run_design.py","--input",simple,"-o",s1),tmp,env)
    audit["standardBoard"]=command(py(scripts(1)/"optical_graph_to_board.py",s1/"trace.json","--board","350x250","--pitch","25","-o",s2),tmp,env)
    std=s2/"project.zzoptics.json";expect(not any(v.get("placeholder") for v in read(std)["layout"]["instances"]),"标准示例含占位")
    audit["step3"]=command(py(checker,std,"--assembly",end/"assembly.step","--board-step",end/"board.step","-o",end/"beam_clearance_3d.json"),tmp,env)
    result=read(end/"beam_clearance_3d.json")
    expect(result["valid"] and result.get("nativeVerify") and result["segments"] and not result["obstructions"] and result["bodyCount"]>2 and
           all(v["minimumClearanceLowerBoundMm"]>0 for v in result["segments"]) and result["projectSha256"]==sha(std),"缺少有效的三维实体净空证据")
    audit["oversizedTubeRejected"]=command(py(checker,std,"--margin","14","-o",end/"oversized-tube.json"),tmp,env,1)
    oversized=read(end/"oversized-tube.json")
    expect(not oversized["valid"] and bool(oversized["obstructions"]),"实际 STEP 实体未拦截加宽的光束管")
    exporter=installation/PLUGINS[3]/"skills"/SKILLS[3][1]/"scripts"
    normalizer=exporter/"normalize_bom.py";mixed=end/"test-bom-raw.json";dst=tmp/"normalized"
    save(mixed,dict(lineItems=[dict(model=model,description=name,quantity=n,source=origin) for model,name,n,origin in [
        ("M4×12 内六角圆柱头螺钉","内六角圆柱头螺钉",4,"base"),("v7-iso4762-m4x12","M4×12 内六角圆柱头螺钉",2,"clamp"),
        ("Ø2×8","定位销",20,"post"),("Ø2×8 圆柱销","圆柱销",8,"adapter"),
        ("A240TM-A","M12 × 0.5 镜座",4,"lens"),("S1TM12","SM1 到 M12 × 0.5 转接环",4,"carrier")]]))
    audit["bomNormalization"]=command(py(normalizer,mixed,"-o",dst),tmp,env)
    items=read(dst/"bom.json")["lineItems"]
    expect({r["model"]:r["quantity"] for r in items}=={"ISO 4762 M4×12":6,"Ø2×8 圆柱销":28,"A240TM-A":4,"S1TM12":4},"紧固件归并或外购件被错误合并")
    expect(result.get("finalAssemblyFiberReadback") and len(result.get("fiberInterfaces",{}))==2,"实际总装调焦/尾套复验缺失")
    ledger=s2/"step5_hole_ledger.json";nodes=read(ledger)["nodes"]
    labels=dict(projectSha256=sha(std),ledgerSha256=sha(ledger),outwardSide="south",labels={
        "Launch":{"zh":"光纤准直头","en":"MFT"},"Receiver":{"zh":"光纤耦合头","en":"MFT"}},
        beamCenterlinesMm=[[ray["a"][:2],ray["b"][:2]] for ray in result["segments"]])
    save(end/"marking-labels.json",labels)
    audit["boardDrawing"]=command(py(exporter/"board_drawing.py",std,ledger,end/"marking-labels.json","-o",end/"board-drawing.svg","--marking-dir",end),tmp,env)
    for name in ("top-marking.svg","side-marking.svg","board-drawing.svg"):ET.parse(end/name)
    shutil.copyfile(std,end/"project.zzoptics.json");command(py(exporter/"normalize_bom.py",s2/"bom.json","-o",end),tmp,env)
    guide=["# 标准双光纤头示例装配","","安装面板 350 × 250 mm，M6 孔距 25 mm，光高 62.5 mm。"]
    for key in ("Launch","Receiver"):
        r=nodes[key]
        guide.append(f'- {key} 使用 {r["kitId"]}，安装转角 {r["rotationDeg"]}°，固定孔 '+ "、".join(p["id"] for p in r["screws"])+"。")
    guide.extend(["","对照定位框安装。沿 Launch 至 Receiver 方向观察并调节对准，复核接口功率。"])
    (end/"assembly-guide.md").write_text("\n".join(guide)+"\n")
    roles={"project.zzoptics.json":("project",["manufacturing","customer"]),"beam_clearance_3d.json":("clearance",["manufacturing"]),
           "assembly.step":("assembly",["manufacturing"]),"board.step":("board-step",["manufacturing"]),
           "board-drawing.svg":("drawing",["manufacturing"]),"top-marking.svg":("marking",["manufacturing"]),"side-marking.svg":("marking",["manufacturing"]),
           "bom.json":("bom",["customer"]),"assembly-guide.md":("assembly-guide",["customer"])}
    frozen=dict(revision=read(std)["catalogVersion"]+" / standard-fiber-link",files=[
        dict(path=name,sha256=sha(end/name),role=role,audiences=audiences) for name,(role,audiences) in roles.items()])
    save(end/"release.json",frozen)
    audit["exportPackages"]=command(py(exporter/"export_packages.py",end/"release.json","-o",end),tmp,env)
    import zipfile
    for audience in ("manufacturing","customer"):
        with zipfile.ZipFile(end/(audience+"_package.zip")) as archive:
            expect(archive.testzip() is None and set(archive.namelist())=={name for name,(_,auds) in roles.items() if audience in auds}|{"release-manifest.json"},"交付包文件")
    expect(not (home/".gemini").exists() and not (home/".codex").exists(),"创建了用户全局配置")
    handoffs={}
    for label,folder,files in [("optics",a,["graph.py","trace.json","schematic.svg"]),("board",b,["project.zzoptics.json","verification.json","custom-wishes.json","step6_board_layout.svg"]),
            ("custom",c,["cad-tasks.json"]),("manufacture",end,["beam_clearance_3d.json","blocked.json","oversized-tube.json","assembly.step","manufacturing_package.zip","customer_package.zip","board-drawing.svg"]),("standard",s2,["project.zzoptics.json","verification.json"])]:
        dest=out/"smoke"/label;dest.mkdir(exist_ok=True,parents=True)
        for name in files:
            src=folder/name;shutil.copyfile(src,dest/name);handoffs[label+"/"+name]=sha(src)
    audit["filesSha256"]=handoffs;audit["opticalShiftMHz"]=200;audit["wishCount"]=len(tasks)
    audit["bodyCount"]=result["bodyCount"];audit["minimumClearanceLowerBoundMm"]=min(v["minimumClearanceLowerBoundMm"] for v in result["segments"])
    return audit

def cordis_contract():
    from sys import path
    path.insert(0,str(HERE/"scripts"))
    from sync_plugins import files
    root=HERE/"dsh-plugins"
    expect({d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".")}=={"dsh-"+n for n in PLUGINS},"Cordis 插件集合")
    for i,name in enumerate(PLUGINS):
        source=HERE/"plugins"/name
        folder=root/("dsh-"+name)
        meta=read(folder/"package.json")
        expect(meta["name"]==folder.name and meta["version"]==read(source/"plugin.json")["version"],"Cordis 版本与身份")
        expect(meta["main"]=="lib/index.js" and meta["dsh"]["bundle"]["patch"]=="./cordis.patch.yml","Cordis 入口")
        patch=(folder/"cordis.patch.yml").read_text().splitlines()
        expect([line.strip() for line in patch]==["- insert:","- id: "+folder.name,"name: "+folder.name],"Cordis 独立入口")
        code=(folder/"lib/index.js").read_text()
        expect(folder.name in code and all('"'+sk+'"' in code for sk in SKILLS[i]) and "ctx.skills.register" in code,"Cordis 技能注册")
        for part in ("skills","rules","assets"):
            left,right=files(source/part),files(folder/part)
            expect(left.keys()==right.keys() and all(sha(f)==sha(right[n]) for n,f in left.items()),"Cordis 同源内容 "+name)
    return isolation(root,"dsh-")


def installer_checks(tmp):
    # Client defaults must confine every write to this temporary home.
    home=tmp/"client-home"
    home.mkdir()
    env=dict(os.environ,HOME=str(home),PYTHONDONTWRITEBYTECODE="1")
    cli=HERE/"scripts/install_plugins.py"
    clients={"antigravity":".gemini/config/plugins","codex":".codex/local-marketplaces/hksop/plugins","dsh":".dsh/local-plugins"}
    receipts={}
    for client,directory in clients.items():
        dest=home/directory
        command(py(cli,"--client",client,"--dry-run"),tmp,env)
        command(py(cli,"--client",client,"--target",dest),tmp,env)
        expect(not dest.exists(),"预演写入了目标")
        command(py(cli,"--client",client,"--apply"),tmp,env)
        first=dest/(("dsh-" if client=="dsh" else "")+PLUGINS[0])
        expect(first.is_dir() and not first.is_symlink(),"实体安装")
        command(py(cli,"--client",client,"--apply"),tmp,env,1)
        command(py(cli,"--client",client,"--update","--mode","symlink","--apply"),tmp,env)
        expect(first.is_symlink(),"从已验来源升级为链接")
        command(py(cli,"--client",client,"--mode","copy","--update","--apply"),tmp,env)
        expect(not first.is_symlink(),"从已验链接换回实体")
        (first/"keep-user-file.txt").write_text("local edits")
        command(py(cli,"--client",client,"--update","--apply"),tmp,env,1)
        expect((first/"keep-user-file.txt").is_file(),"保护本地修改")
        receipts[client]=["dry-run","copy","update-owned","update-symlink","reject-unrelated-edit"]
    return receipts


def offline_smoke(tmp):
    folder=tmp/"offline";home=tmp/"offline-home";home.mkdir()
    env=dict(os.environ,HOME=str(home),PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1")
    for key in ("HKSOP_ROOT","HKSOP_NODE","PYTHONPATH","HKSOP_CAD_PYTHON","HKSOP_FOCUS_ASSETS"):
        env.pop(key,None)
    command(py(HERE/"scripts/install_plugins.py","--target",folder,"--apply"),tmp,env)
    runner=folder/PLUGINS[0]/"skills"/SKILLS[0][0]/"scripts/run_design.py"
    out=tmp/"optical"
    step=command(py(runner,"--example","double-pass","-o",out),tmp,env)
    trace=read(out/"trace.json")
    ET.parse(out/"schematic.svg")
    expect(trace["trace"]["valid"] and trace["trace"]["terminals"]["PM"]["beams"][0]["freq_shift_mhz"]==200,"离线第 1 棒")
    return dict(exitCode=step["exitCode"],shiftMHz=200,outputs=["graph.py","trace.json","schematic.svg","gallery.html"])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--offline",action="store_true")
    p.add_argument("--root",type=Path)
    p.add_argument("-o","--output",type=Path,default=Path(os.environ.get("HKSOP_TEST_OUTPUT", HERE / "results")) / "plugins-acceptance")
    args=p.parse_args(argv)
    root=HERE/"plugins";out=args.output.resolve()
    protected_dirs=[Path.home()/k for k in (".gemini",".codex",".dsh")]
    native=None
    if not args.offline:
        try:native=library_root(args.root)
        except ValueError as exc:p.error(str(exc))
        protected_dirs.extend([native,native.parent/"HKSOP"])
    if any(out==v or v in out.parents for v in protected_dirs):p.error("请选择独立的验收目录")
    report=dict(format="hksop-plugins-acceptance-v2",valid=False,offline=args.offline)
    try:
        report["manifests"]=manifests(root)
        report["isolation"]=isolation(root)+cordis_contract()
        with tempfile.TemporaryDirectory(prefix="hksop-plugins-") as td:
            scratch=Path(td)
            report["installers"]=installer_checks(scratch)
            report["offlineRelay"]=offline_smoke(scratch)
            if native is not None:
                before=protected(native)
                report["runtimeFallback"]=runtime_fallback_contract(scratch,native)
                with ThreadPoolExecutor(2) as pool:
                    env=dict(os.environ,HKSOP_ROOT=str(native),PYTHONDONTWRITEBYTECODE="1")
                    regressions={name:pool.submit(command,py(TESTS/name),HERE,env)
                                 for name in ("optical_graph_acceptance.py","layer2_acceptance.py")}
                    report["relay"]=smoke(root,out,scratch,native)
                    report["regressions"]={k:v.result() for k,v in regressions.items()}
                expect(before==protected(native),"受保护输入发生变化")
        report["valid"]=True
    except (OSError,ValueError,KeyError,RuntimeError) as exc:
        report["error"]=str(exc)
    save(out/"report.json",report)
    print("PASS" if report["valid"] else "FAIL",report.get("error","4 plugins · manifests · isolation · file relay"),out/"report.json")
    return int(not report["valid"])

if __name__=="__main__":
    sys.exit(main())
