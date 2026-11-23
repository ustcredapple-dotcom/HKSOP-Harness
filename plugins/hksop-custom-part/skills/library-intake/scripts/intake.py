#!/usr/bin/env python3
"""Validate assets and use the native stage/adopt transaction in an authorized working copy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from hksop_runtime import library_root, sibling_libraries


def atomic(path,data):
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        stream.write(data);name=stream.name
    os.replace(name,path)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("package",type=Path);p.add_argument("--root",type=Path)
    p.add_argument("--collection",choices=("custom","standard"),default="custom");p.add_argument("--history",choices=("retain","discard"))
    p.add_argument("--curation-file",type=Path,help="经审核的选型配置");p.add_argument("--apply",action="store_true");a=p.parse_args()
    try: root=library_root(a.root)
    except ValueError as exc: p.error(str(exc))
    entry=a.package.resolve();entry=entry/"package.json" if entry.is_dir() else entry
    def command(*argv):
        cp=subprocess.run([sys.executable,"-B",str(root/"hksop.py"),*map(str,argv)],env=dict(os.environ,PYTHONDONTWRITEBYTECODE="1"),capture_output=True,text=True)
        if cp.returncode:raise ValueError(cp.stderr[-1800:])
        return json.loads(cp.stdout)
    try:
        meta=json.loads(entry.read_bytes());mapped=entry.parent/"resource-map.json";verified=[]
        if mapped.is_file():
            for r in json.loads(mapped.read_bytes())["files"]:
                relative = Path(r["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("包内资源应使用相对路径")
                f = (entry.parent / relative).resolve()
                stored = None
                if r.get("stored"):
                    stored_relative = Path(r["stored"])
                    if stored_relative.is_absolute() or ".." in stored_relative.parts:
                        raise ValueError("资源索引应使用相对路径")
                    stored = (root / stored_relative).resolve()
                    if (root / "library/assets").resolve() not in stored.parents:
                        raise ValueError("资源索引越界")
                if entry.parent not in f.parents and f != stored:
                    raise ValueError("资源位于包目录及登记资产之外")
                if not f.is_file() and stored is not None:
                    f = stored
                if hashlib.sha256(f.read_bytes()).hexdigest()!=r["sha256"]:raise ValueError("资源哈希不符 "+r["path"])
                verified.append(r["sha256"])
        checked=command("package","check",entry);out=dict(packageId=meta["packageId"],resourceHashes=verified,checked=checked,applied=False)
        if a.apply:
            protected = set(sibling_libraries())
            if os.environ.get("HKSOP_ROOT"):
                protected.add(Path(os.environ["HKSOP_ROOT"]))
            if a.root is None or any(root == v.resolve() or v.resolve() in root.parents for v in protected):
                raise ValueError("写入时请用 --root 明确指定独立的可写工作副本")
            existing=any(r.get("packageId")==meta["packageId"] for r in json.loads((root/"library/package-index.json").read_bytes()))
            if existing and not a.history:raise ValueError("更新已有版本前须选择 --history retain 或 discard")
            hist=["--history",a.history] if a.history else []
            stage=command("package","stage",entry,"--collection",a.collection,*hist)
            out["adopt"]=command("package","adopt",stage["stage"],*hist);out["applied"]=True
            if a.curation_file:
                target=root/"library/curation.json";new=a.curation_file.read_bytes();old=target.read_bytes()
                candidate=json.loads(new)
                if candidate.get("format")!=json.loads(old)["format"]:raise ValueError("选型配置格式错误")
                atomic(target,new)
                try:command("catalog","build")
                except Exception:atomic(target,old);command("catalog","build");raise
            slim=root/"library/catalog-ai-slim.json"
            out["slimSha256"]=hashlib.sha256(slim.read_bytes()).hexdigest()
        print(json.dumps(out,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:print(str(e),file=sys.stderr);return 1
if __name__=="__main__":sys.exit(main())
