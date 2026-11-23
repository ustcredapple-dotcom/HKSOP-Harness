#!/usr/bin/env python3
"""Deliver a replayable optical graph, trace and schematic to one folder."""
import argparse
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
from optical_graph_render import main as render

def main():
    p=argparse.ArgumentParser();group=p.add_mutually_exclusive_group(required=True);group.add_argument("--example",choices=["double-pass"]);group.add_argument("--input",type=Path)
    p.add_argument("--func",default="build_graph");p.add_argument("-o","--output",type=Path,required=True);a=p.parse_args()
    src=Path(__file__).resolve().parent/"examples/double_pass.py" if a.example else a.input.resolve(strict=True)
    a.output.mkdir(exist_ok=True,parents=True);dst=a.output/"graph.py"
    if src.resolve()!=dst.resolve():shutil.copyfile(src,dst)
    return render([str(dst),"--func",a.func,"-o",str(a.output/"gallery.html"),"--svg",str(a.output/"schematic.svg"),"--json",str(a.output/"trace.json")])
if __name__=="__main__":sys.exit(main())
