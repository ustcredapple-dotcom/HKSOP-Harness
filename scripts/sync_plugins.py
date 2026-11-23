#!/usr/bin/env python3
"""Materialize the portable engines and Cordis skill payloads from their canonical sources."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("hksop-step1-optics", "hksop-step2-board", "hksop-custom-part", "hksop-step3-manufacture")
IGNORE = {"__pycache__", ".DS_Store"}


def files(folder):
    return {p.relative_to(folder): p for p in folder.rglob("*")
            if p.is_file() and not IGNORE.intersection(p.parts)
            and not p.name.startswith("._") and p.suffix != ".pyc"}


def reconcile(apply):
    differences = []

    def match(source, dest):
        if dest.is_symlink() or source.is_symlink():
            raise ValueError(f"Link in bundled payload: {dest.relative_to(ROOT)}")
        content = source.read_bytes()
        if dest.is_file() and dest.read_bytes() == content:
            return
        differences.append(dest.relative_to(ROOT))
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
                tmp.write(content)
            os.chmod(tmp.name, 0o644)
            os.replace(tmp.name, dest)

    def mirror(source, dest):
        if not source.is_dir() or source.is_symlink() or dest.is_symlink():
            raise ValueError(f"Invalid managed directory: {source}")
        wanted, existing = files(source), files(dest)
        for name in sorted(wanted):
            match(wanted[name], dest / name)
        for name in sorted(existing.keys() - wanted.keys()):
            differences.append((dest / name).relative_to(ROOT))
            if apply:
                (dest / name).unlink()

    for i, skill in enumerate(("optics-graph-design", "board-auto-layout")):
        base = ROOT / "plugins" / NAMES[i] / "skills" / skill / "scripts"
        mirror(ROOT / "src/optical_graph", base / "optical_graph")
        match(ROOT / "scripts/optical_graph_render.py", base / "optical_graph_render.py")
        if i == 1:
            mirror(ROOT / "src/optical_layout", base / "optical_layout")
            match(ROOT / "scripts/optical_graph_to_board.py", base / "optical_graph_to_board.py")
    runtime = ROOT / "src/optical_layout/hksop_runtime.py"
    for i, sk in ((2, "library-intake"), (3, "json-to-3d-verify")):
        match(runtime, ROOT / "plugins" / NAMES[i] / "skills" / sk / "scripts/hksop_runtime.py")
    for name in NAMES:
        source = ROOT / "plugins" / name
        dest = ROOT / "dsh-plugins" / ("dsh-" + name)
        for folder in ("skills", "rules", "assets"):
            mirror(source / folder, dest / folder)
    return differences


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        changes = reconcile(args.apply)
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")
    if changes and not args.apply:
        sys.exit("Out of sync:\n" + "\n".join(map(str, changes)))
    print(f"{len(changes)} updated" if args.apply else "Embedded engines and all four Cordis payloads match.")
