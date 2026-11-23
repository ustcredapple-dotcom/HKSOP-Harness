"""Register matched supplier assemblies, optic subsolids and four-bolt feet to a native project."""
import argparse,copy,hashlib,json,math,os,shutil,subprocess
from pathlib import Path
from hksop_runtime import library_root,resolve_node

def sha(f):return hashlib.sha256(f.read_bytes()).hexdigest()
def read(f):return json.loads(f.read_bytes())
def asset_root(root):
    configured = os.environ.get("HKSOP_FOCUS_ASSETS")
    base = Path(configured).expanduser() if configured else root / "optical-assets/pm532"
    if not (base / "head-registration.json").is_file() or not (base / "kit-datums.json").is_file():
        raise ValueError("请设置 HKSOP_FOCUS_ASSETS，指向已获授权的调焦头几何与登记目录。")
    return base.resolve()
def prepare(project,root,out,segments,ledger=None,copy_assets=False):
    data=read(project);base=asset_root(root);out.mkdir(parents=True,exist_ok=True)
    if copy_assets:
        for f in base.rglob('*'):
            if f.is_file() and not f.name.startswith('._'):
                dest=out/f.relative_to(base);dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.exists() or sha(dest)!=sha(f):shutil.copy2(f,dest)
        base=out
    def name(f):return os.path.relpath(f,out) if copy_assets else str(f)
    reg=read(base/'head-registration.json');rules=read(base/'kit-datums.json')
    insts={};spatial=[];heads={};supp=[]
    for n in data["layout"]["instances"]:
        k=n['id'];kit=n.get('kitId')
        if kit in rules:
            entry=dict(rules[kit]);entry['step']=str(root/'library/assets'/entry['step']);insts[k]=entry
        if kit!='fiber-coupling-mft-rear-r3':continue
        rays=[r for r in segments if k in (r.get('hit'),r.get('source'))]
        if not rays or any(abs(r['wavelengthNm']-532)>.01 for r in rays):raise ValueError(k+' 需为此波长登记独立透镜与裸纤法兰实模')
        entry=dict(reg);entry["step"]=name(base/reg["step"]);insts[k]=entry;heads[k]=reg['focus']
        r=rays[0];emit=n["optics"].get("source",{}).get("enabled",False)
        a=math.radians(n['rotationDeg']);unit=(-math.sin(a),math.cos(a),0)
        p0=list(r['a'] if emit else r['b']);length=reg['focus']['lensFrontYmm']-9.55
        p1=[v+length*u for v,u in zip(p0,unit)];u,v=(p1,p0) if emit else (p0,p1)
        par=r['q'];q=[par[0]-length if emit else par[0]+r['rangeMm'],par[1]]
        spatial.append(dict(id='lens-'+k,a=u,b=v,q=q,qSagittal=q,wavelengthNm=532,index=1,m2=1,source=k,hit=k,interactionIds=[k],rangeMm=length))
    screw=base/'M6x12-ISO4762.step'
    if ledger:
        holes=read(ledger)
        for k,row in holes['nodes'].items():
            if row.get("mode")!="direct":continue
            for f in row['screws']:
                supp.append(dict(id='M6x12-'+f['id'],carrier=k,step=name(screw),sha256=sha(screw),centerMm=[f['xMm'],f['yMm'],6.0],seatHeightMm=6))
    dst=out/'geometry.json';dst.write_text(json.dumps(dict(projectSha256=sha(project),instances=insts,spatialSegments=spatial,supportFasteners=supp,focusModels=heads),ensure_ascii=False,indent=2))
    return dst
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('-o',type=Path,required=True);p.add_argument('--ledger',type=Path);p.add_argument('--copy-assets',action='store_true');p.add_argument('--root',type=Path);a=p.parse_args()
    rt=library_root(a.root);run=subprocess.run([resolve_node(rt),str(Path(__file__).with_name('native_segments.cjs')),str(rt),str(a.project.resolve())],check=True,capture_output=True,text=True)
    print(prepare(a.project,rt,a.o,json.loads(run.stdout)['segments'],a.ledger,a.copy_assets))
