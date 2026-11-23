#!/usr/bin/env python3
"""Generate a six-step optical board design using only the Python standard library."""
import argparse
import os
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from optical_graph_render import read_graphs
from optical_layout import run_layer2_pipeline
from optical_layout.hksop_runtime import library_root


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("input",type=Path)
    p.add_argument("--func");p.add_argument("--board",default="auto");p.add_argument("--pitch",choices=(25.,12.5),type=float,default=None)
    p.add_argument("--height-policy",choices=("fixed","auto"),default="auto")
    p.add_argument("--mounting-holes",choices=(4,8),type=int,default=4);p.add_argument("-o","--output",required=True,type=Path)
    p.add_argument("--root", type=Path, help="HKSOP core checkout")
    a=p.parse_args(argv)
    try:
        if a.root is not None:
            os.environ["HKSOP_ROOT"] = str(library_root(a.root))
        path=a.input.resolve(strict=True)
        if path.suffix.lower()==".json":
            supplied=json.loads(path.read_bytes())
            if "trace" in supplied and supplied["trace"].get("valid") is not True:raise ValueError("上游 trace 未通过体检")
        _,graph=read_graphs(path,a.func,False)[0]
        rationale="";hardware={}
        if path==Path(__file__).resolve().parents[1] / "tests/layer2_challenges.py":
            sys.path.insert(0,str(path.parent))
            from layer2_challenges import ALL_FIXTURES,BRIEFS
            idx=next(i for i,fn in enumerate(ALL_FIXTURES) if fn.__name__==a.func)
            rationale,hardware=BRIEFS[idx][3:]
        q=run_layer2_pipeline(graph,a.output,a.board,a.pitch,a.height_policy,rationale,hardware,a.mounting_holes)
        print(f'{q["name"]} · {q["board"]} mm · {q["stages"]} LS30 · verify 0 · {a.output.resolve()/"step_by_step_walkthrough.html"}')
    except (RuntimeError,ValueError,KeyError,OSError,AttributeError) as exc:
        print(str(exc),file=sys.stderr);return 1
    return 0


if __name__=="__main__":
    sys.exit(main())
