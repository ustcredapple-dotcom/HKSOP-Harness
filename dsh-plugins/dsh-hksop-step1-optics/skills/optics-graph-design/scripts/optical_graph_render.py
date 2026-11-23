#!/usr/bin/env python3
"""Render OpticalGraph Python builders or a v1 graph JSON to offline HTML / SVG."""
import argparse
from hashlib import sha256
import importlib.util
import inspect
import json
from pathlib import Path
import re
import sys

source = Path(__file__).resolve().parents[1] / "src"
if (source / "optical_graph").is_dir():
    sys.path.insert(0, str(source))

from optical_graph import OpticalGraph
from optical_graph.renderer import json_text, render_gallery, render_svg, write_output

DEFAULT = Path("results/optical-graph")


def _load_py(path):
    module_name = "_optical_graph_input_" + sha256(str(path).encode()).hexdigest()[:16]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    sys.path.insert(0,str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


def read_graphs(path, name, batch):
    if path.suffix.lower() == ".json":
        if batch:
            raise ValueError("--all requires a Python input file")
        with path.open(encoding="utf-8") as f:
            graph = OpticalGraph.from_dict(json.load(f))
        if name and name.replace("_","-") != graph.name.replace("_","-"):
            raise ValueError(f"graph {name!r} not present in JSON")
        return [(name or graph.name,graph)]
    if path.suffix.lower() != ".py":
        raise ValueError("expected a .py or .json input file")
    if not batch and not name:
        raise ValueError("--func is required for a single Python builder")
    module = _load_py(path)
    if batch:
        if hasattr(module, "ALL_FIXTURES"):
            builders = module.ALL_FIXTURES
        else:
            builders = [fn for k,fn in vars(module).items() if not k.startswith("_") and inspect.isfunction(fn)
                        and fn.__module__ == module.__name__ and not inspect.signature(fn).parameters]
    else:
        builders = [getattr(module,name,None)]
    result, used = [], set()
    for fn in builders:
        if not callable(fn):
            raise ValueError(f"missing graph builder: {name or fn}")
        key = fn.__name__
        if key in used or not re.fullmatch(r"[A-Za-z_]\w*",key,re.ASCII):
            raise ValueError(f"duplicate or invalid builder name: {key}")
        graph = fn()
        if not isinstance(graph,OpticalGraph):
            if batch and not hasattr(module,"ALL_FIXTURES"):
                continue
            raise ValueError(f"{key} did not return an OpticalGraph")
        result.append((key,graph))
        used.add(key)
    if not result:
        raise ValueError("no graph builders found")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input",type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--func")
    mode.add_argument("--all",action="store_true")
    parser.add_argument("-o","--output",type=Path)
    parser.add_argument("--svg",type=Path)
    parser.add_argument("--svg-dir",type=Path)
    parser.add_argument("--json",type=Path)
    parser.add_argument("--allow-invalid",action="store_true")
    args = parser.parse_args(argv)
    if args.all and args.svg or not args.all and args.svg_dir:
        parser.error("use --svg-dir with --all, or --svg for a single graph")
    if not args.all and not args.output:
        parser.error("single graph mode needs -o FILE")
    try:
        source = args.input.resolve(strict=True)
        entries = []
        for i,(key,graph) in enumerate(read_graphs(source,args.func,args.all)):
            data = graph.to_dict(include_trace=True)
            entries.append((key,graph,data,render_svg(graph,data,prefix=f"og{i}")))
        outputs = [(args.output or DEFAULT/"gallery.html", render_gallery(entries))]
        if args.all:
            svg_dir = args.svg_dir or DEFAULT/"svg"
            outputs.extend((svg_dir/(key+".svg"),svg+"\n") for key,_,_,svg in entries)
            results = [{"fixture":key,**data} for key,_,data,_ in entries]
            summary = dict(format="hksop-optical-graph-gallery-v1",count=len(results),
                           valid_count=sum(row["trace"]["valid"] for row in results),graphs=results)
            outputs.append((args.json or DEFAULT/"summary.json",json_text(summary)))
        else:
            if args.svg:
                outputs.append((args.svg,entries[0][3]+"\n"))
            if args.json:
                outputs.append((args.json,json_text(entries[0][2])))
        paths = {source}
        for dest,_ in outputs:
            if dest.resolve() in paths:
                raise ValueError(f"output path collision: {dest}")
            paths.add(dest.resolve())
        for dest,content in outputs:
            write_output(dest,content)
        valid = sum(data["trace"]["valid"] for _,_,data,_ in entries)
        print(f"{len(entries)} graphs rendered; {valid} valid, {len(entries)-valid} invalid. {outputs[0][0]}")
        return 0 if valid == len(entries) or args.allow_invalid else 1
    except Exception as exc:
        print(f"optical_graph_render: {type(exc).__name__}: {exc}",file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
