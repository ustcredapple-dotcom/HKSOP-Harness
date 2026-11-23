#!/usr/bin/env python3
"""Export integrity-checked manufacturing and customer ZIPs from a frozen release manifest."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

def sha(b):return hashlib.sha256(b).hexdigest()
def packages(manifest,out):
    data=json.loads(manifest.read_bytes());base=manifest.resolve().parent;rev=data["revision"]
    if not isinstance(rev,str) or not rev.strip():raise ValueError("缺少冻结修订")
    files={};roles={}
    for r in data["files"]:
        label=r["path"];p=(base/label).resolve()
        if Path(label).is_absolute() or base not in p.parents or ".." in Path(label).parts or label in files:raise ValueError("非法或重复的包内路径")
        raw=p.read_bytes()
        if not raw or sha(raw)!=r["sha256"]:raise ValueError("文件哈希不符 "+label)
        if not set(r["audiences"])<= {"manufacturing","customer"}:raise ValueError("交付对象无效")
        files[label]=(raw,r);roles.setdefault(r["role"],[]).append(label)
    needed={"manufacturing":{"project","clearance","assembly","board-step","drawing","marking"},"customer":{"project","bom","assembly-guide"}}
    for recipient,kinds in needed.items():
        if kinds-{r["role"] for _,r in files.values() if recipient in r["audiences"]}:raise ValueError(recipient+" 的必需文件缺失")
    if any(len(roles.get(k,[]))!=1 for k in ("project","clearance","assembly","board-step")):raise ValueError("冻结工程、总装与三维回执必须各有一份")
    project=files[roles["project"][0]][0];receipt=json.loads(files[roles["clearance"][0]][0])
    if not receipt.get("valid") or not receipt.get("segments") or receipt.get("projectSha256")!=sha(project):raise ValueError("缺少本工程的三维放行回执")
    if receipt.get("assemblySha256")!=sha(files[roles["assembly"][0]][0]):raise ValueError("总装须与三维回执的 STEP 哈希一致")
    if receipt.get("boardStepSha256")!=sha(files[roles["board-step"][0]][0]):raise ValueError("底板须与三维回执的 STEP 哈希一致")
    if any(i.get("placeholder") for i in json.loads(project)["layout"]["instances"]):raise ValueError("有待解决的占位件")
    from normalize_bom import audit
    import csv,io
    bills=[(f,r) for f,r in files.values() if r["role"]=="bom"]
    parsed=next((json.loads(f) for f,r in bills if r["path"].endswith(".json")),None)
    if not parsed or not parsed.get("lineItems"):raise ValueError("缺少公开采购 BOM")
    clean=audit(parsed["lineItems"])
    if not clean["valid"]:raise ValueError("采购清单归并或来源校验失败 "+str(clean))
    for f,r in bills:
        if r["path"].endswith(".csv"):
            tab=list(csv.DictReader(io.StringIO(f.decode("utf-8-sig"))))
            if [(v["型号"],float(v["数量"])) for v in tab]!=[(v["model"],v["quantity"]) for v in parsed["lineItems"]]:
                raise ValueError("BOM CSV 与冻结数据不一致")
    out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as td:
        for target in needed:
            dst=Path(td)/(target+"_package.zip");selected=[]
            with zipfile.ZipFile(dst,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for label,(raw,r) in sorted(files.items()):
                    if target in r["audiences"]:z.writestr(label,raw);selected.append(r)
                z.writestr("release-manifest.json",json.dumps(dict(revision=rev,projectSha256=sha(project),files=selected),ensure_ascii=False,indent=2))
            with zipfile.ZipFile(dst) as z:
                if z.testzip() is not None:raise ValueError("坏的交付压缩包")
        signed={}
        for dest in sorted(Path(td).glob("*.zip")):
            with zipfile.ZipFile(dest) as archive:
                manifest=json.loads(archive.read("release-manifest.json"))
                for row in manifest["files"]:
                    if sha(archive.read(row["path"]))!=row["sha256"]:raise ValueError("ZIP 中的文件不匹配")
            signed[dest.name]=sha(dest.read_bytes())
        (Path(td)/"delivery-check.json").write_text(json.dumps(dict(valid=True,revision=rev,projectSha256=sha(project),bomAudit=clean,archives=signed),ensure_ascii=False,indent=2))
        for f in Path(td).iterdir():os.replace(f,out/f.name)
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("manifest",type=Path);p.add_argument("-o",type=Path,required=True);a=p.parse_args()
    try:packages(a.manifest,a.o)
    except (ValueError,KeyError,OSError) as e:p.exit(1,str(e)+"\n")
