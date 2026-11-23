#!/usr/bin/env python3
"""Preview or atomically install the four independent HKSOP plugins for a client."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from sync_plugins import NAMES, ROOT, files

CLIENTS = {"antigravity": ".gemini/config/plugins", "codex": ".codex/local-marketplaces/hksop/plugins",
           "dsh": ".dsh/local-plugins"}
ORIGIN = "HKSOP-Harness/plugins"


def signature(folder):
    digest = hashlib.sha256()
    for rel, path in sorted(files(folder).items()):
        if path.is_symlink():
            raise ValueError(f"Unexpected link in plugin: {rel}")
        digest.update(rel.as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def validate_target(target):
    root = target.expanduser().resolve()
    protected = {ROOT, ROOT.parent / "HKSOP", ROOT.parent / "HKSOP-refactored"}
    if os.environ.get("HKSOP_ROOT"):
        protected.add(Path(os.environ["HKSOP_ROOT"]).expanduser().resolve())
    if root == Path(root.anchor) or root == Path.home() or any(p == root or p in root.parents for p in protected):
        raise ValueError("请选择 HKSOP 本体和源码树之外的独立插件目录")
    if any((p / "library/catalog.json").is_file() for p in (root, *root.parents)):
        raise ValueError("目标位于 HKSOP 元件库中")
    for name, valid in CLIENTS.items():
        standard = (Path.home() / valid).resolve()
        base = (Path.home() / Path(valid).parts[0]).resolve()
        if (root == base or base in root.parents) and root != standard:
            if name == "codex" and root.name == "plugins" and (base / "local-marketplaces") in root.parents:
                continue
            raise ValueError("请选择客户端的插件子目录")
    return root


def install(client, target, mode, apply, update):
    root = validate_target(target or (Path.home() / CLIENTS[client]))
    store = ROOT / ("dsh-plugins" if client == "dsh" else "plugins")
    legacy = json.loads((ROOT / "compatibility.json").read_bytes()).get("previousPackageFingerprints", {})
    manifest = "package.json" if client == "dsh" else "plugin.json"

    def plan():
        rows = []
        for plugin in NAMES:
            name = "dsh-" + plugin if client == "dsh" else plugin
            source, dest = store / name, root / name
            identity = json.loads((source / manifest).read_bytes())
            if identity["name"] != name:
                raise ValueError(f"Invalid package identity: {name}")
            wanted = signature(source)
            stamp = root / ("." + name + ".hksop-install.json")
            if stamp.is_symlink():
                raise ValueError(f"Unexpected linked receipt: {stamp}")
            receipt = json.loads(stamp.read_bytes()) if stamp.exists() else {}
            owned = receipt.get("origin") == ORIGIN and receipt.get("name") == name
            if stamp.exists() and not owned:
                raise ValueError(f"Foreign installation receipt: {stamp}")
            present = os.path.lexists(dest)
            if present:
                linked = dest.is_symlink()
                if linked and dest.resolve() == source.resolve() and mode == "symlink":
                    continue
                if not update:
                    raise ValueError(f"Already installed: {name}. Use --update for a verified replacement.")
                if linked and not dest.exists():
                    trusted = owned and receipt.get("link") == os.readlink(dest)
                else:
                    if not (dest / manifest).is_file() or json.loads((dest / manifest).read_bytes()).get("name") != name:
                        raise ValueError(f"Unrecognized destination: {dest}")
                    actual = signature(dest)
                    trusted = (actual == wanted or actual in legacy.get(name, []) or
                               (owned and actual == receipt.get("sha256")) or
                               (linked and dest.resolve() == source.resolve()))
                    if trusted and actual == wanted and not linked and mode == "copy":
                        continue
                if not trusted:
                    raise ValueError(f"Unrecognized or locally edited installation: {dest}")
            rows.append((source, dest, stamp, dict(origin=ORIGIN, name=name, version=identity["version"],
                                                   sha256=wanted, link=str(source) if mode=="symlink" else None)))
        return rows

    if not apply:
        for src, dst, _, _ in plan():
            print("DRY-RUN", mode, src.name, "→", dst)
        return
    root.mkdir(exist_ok=True, parents=True)
    handle = os.open(root, os.O_RDONLY)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        rows = plan()
        with tempfile.TemporaryDirectory(prefix=".hksop-update-", dir=root) as temp:
            stage = Path(temp)
            moves = []
            for source, dest, stamp, record in rows:
                slot = stage / dest.name
                if mode == "copy":
                    shutil.copytree(source, slot, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "._*"))
                    if signature(slot) != record["sha256"]:
                        raise ValueError(f"Incomplete copy: {dest.name}")
                else:
                    slot.symlink_to(source, target_is_directory=True)
                (stage / stamp.name).write_text(json.dumps(record, ensure_ascii=False) + "\n")
            try:
                for _, dest, stamp, _ in rows:
                    for item in (dest, stamp):
                        if os.path.lexists(item):
                            backup = stage / ("previous-" + item.name)
                            item.rename(backup)
                            moves.append((backup, item))
                        slot = stage / item.name
                        slot.rename(item)
                        moves.append((item, slot))
                    print("INSTALL", mode, dest)
            except BaseException:
                for moved, original in reversed(moves):
                    moved.rename(original)
                raise
    finally:
        os.close(handle)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", choices=tuple(CLIENTS), default="codex")
    p.add_argument("--target", type=Path)
    p.add_argument("--mode", choices=("copy", "symlink"), default="copy")
    p.add_argument("--update", action="store_true")
    choice = p.add_mutually_exclusive_group()
    choice.add_argument("--apply", action="store_true")
    choice.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    try:
        install(a.client, a.target, a.mode, a.apply, a.update)
    except (OSError, ValueError, KeyError) as exc:
        p.exit(1, str(exc) + "\n")
