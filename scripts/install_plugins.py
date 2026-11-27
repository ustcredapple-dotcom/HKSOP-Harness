#!/usr/bin/env python3
"""Preview or atomically install the four independent HKSOP plugins for a client."""
import argparse
from datetime import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from sync_plugins import NAMES, ROOT, files
from build_dist import build_dsh

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


def sync_codex_plugin_cache(store, legacy, apply, update):
    cache_root = Path.home() / ".codex/plugins/cache/hksop-local"
    stamp_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = Path.home() / ".codex/backups" / f"hksop-cache-{stamp_ts}"
    for name in NAMES:
        source = store / name
        identity = json.loads((source / "plugin.json").read_bytes())
        version = identity["version"]
        wanted = signature(source)
        plugin_cache = cache_root / name
        dest = plugin_cache / version
        stale_dirs = [p for p in sorted(plugin_cache.iterdir()) if p.name != version] if plugin_cache.is_dir() else []
        need_copy = True
        if os.path.lexists(dest):
            if not dest.is_symlink() and dest.is_dir() and signature(dest) == wanted:
                need_copy = False
            else:
                if not update:
                    raise ValueError(f"Already cached: {name}/{version}. Use --update for a verified replacement.")
                actual = None if dest.is_symlink() else signature(dest)
                if actual is not None and actual not in legacy.get(name, []) and actual != wanted:
                    raise ValueError(f"Unrecognized or locally edited cache installation: {dest}")
        if not apply:
            if need_copy or stale_dirs:
                print("DRY-RUN cache-sync", name, "→", dest)
            continue
        plugin_cache.mkdir(parents=True, exist_ok=True)
        if need_copy:
            with tempfile.TemporaryDirectory(prefix=".hksop-cache-", dir=plugin_cache) as temp:
                slot = Path(temp) / version
                shutil.copytree(source, slot, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", "._*"))
                if signature(slot) != wanted:
                    raise ValueError(f"Incomplete cache copy: {name}/{version}")
                if os.path.lexists(dest):
                    dst_backup = backup_root / name / (version + "-replaced")
                    dst_backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(dest), str(dst_backup))
                slot.rename(dest)
            print("CACHE-SYNC", name, "→", dest)
        for old in stale_dirs:
            old_backup = backup_root / name / old.name
            old_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(old_backup))
            print("CACHE-BACKUP", old, "→", old_backup)


def _install(client, target, mode, apply, update, sync_codex_cache=False, store=None):
    if sync_codex_cache and client != "codex":
        raise ValueError("--sync-codex-cache 仅适用于 --client codex")
    root = validate_target(target or (Path.home() / CLIENTS[client]))
    store = store or ROOT / "plugins"
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
        if sync_codex_cache:
            sync_codex_plugin_cache(store, legacy, False, update)
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
    if sync_codex_cache:
        sync_codex_plugin_cache(store, legacy, True, update)


def install(client, target, mode, apply, update, sync_codex_cache=False):
    if client != "dsh":
        return _install(client, target, mode, apply, update, sync_codex_cache)
    if apply:
        # A persistent generated path also keeps developer symlink installations valid.
        return _install(client, target, mode, apply, update, sync_codex_cache, build_dsh())
    with tempfile.TemporaryDirectory(prefix="hksop-dsh-preview-") as temp:
        return _install(client, target, mode, apply, update, sync_codex_cache, build_dsh(Path(temp)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", choices=tuple(CLIENTS), default="codex")
    p.add_argument("--target", type=Path)
    p.add_argument("--mode", choices=("copy", "symlink"), default="copy")
    p.add_argument("--update", action="store_true")
    p.add_argument("--sync-codex-cache", action="store_true")
    choice = p.add_mutually_exclusive_group()
    choice.add_argument("--apply", action="store_true")
    choice.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    try:
        install(a.client, a.target, a.mode, a.apply, a.update, a.sync_codex_cache)
    except (OSError, ValueError, KeyError) as exc:
        p.exit(1, str(exc) + "\n")
