"""Resolve the read-only HKSOP installation and a working Node for this process."""
import json
import os
from pathlib import Path
import shutil
import subprocess

DSH_NODE = Path.home() / ".dsh/dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node"


def sibling_libraries():
    anchors = [Path.cwd()]
    for parent in Path(__file__).resolve().parents:
        if (parent / "compatibility.json").is_file() or (parent / "plugin.json").is_file() or (parent / "cordis.patch.yml").is_file():
            anchors.append(parent)
    for anchor in anchors:
        for name in ("HKSOP", "HKSOP-refactored"):
            yield anchor.parent / name


def library_root(override=None):
    """Explicit choices are validated before looking for a neighbouring checkout."""
    selected = override or os.environ.get("HKSOP_ROOT")
    candidates = [Path(selected)] if selected else sibling_libraries()
    for candidate in candidates:
        root = candidate.expanduser().resolve()
        if (root / "library/catalog.json").is_file():
            return root
    raise ValueError("找不到 library/catalog.json。请先克隆并构建 HKSOP 本体，"
                     "再指定 --root 或 export HKSOP_ROOT=/path/to/HKSOP")


def local_environment(root):
    try:
        data = json.loads((root / "config/local-environment.json").read_bytes())
    except (FileNotFoundError, PermissionError):
        return {}
    if not isinstance(data, dict):
        raise ValueError("HKSOP 本机环境配置应为 JSON 对象")
    return data


def resolve_node(root):
    """Check actual execution as well as permissions. Never alter the environment on disk."""
    configured = local_environment(root).get("node")
    candidates = (os.environ.get("HKSOP_NODE"), configured, DSH_NODE, shutil.which("node"))
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        try:
            expanded = os.path.expanduser(os.fspath(candidate))
            path = Path(expanded) if os.sep in expanded else Path(shutil.which(expanded) or expanded)
            if not path.is_absolute():
                continue
            if path in seen or not path.is_file() or not os.access(path, os.R_OK | os.X_OK):
                continue
            seen.add(path)
            check = subprocess.run([str(path), "-p", "process.versions.node"],
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=5, check=False)
            if check.returncode == 0 and check.stdout.strip().split(".")[0].isdigit():
                return str(path)
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            continue
    raise ValueError("找不到可读取并执行的 Node。已检查 HKSOP_NODE、本机配置、DeepSeek Harness 运行时和 PATH。")
