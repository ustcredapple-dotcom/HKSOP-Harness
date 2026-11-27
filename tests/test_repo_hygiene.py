#!/usr/bin/env python3
"""Check staged blobs and working files, package synchronization, isolation and resolver behavior."""
import hashlib
import base64
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from optical_layout.hksop_runtime import library_root
from plugins_acceptance import manifests, isolation, cordis_contract
sys.path.insert(0, str(ROOT / "scripts"))
from redundancy_audit import run_audit, dsh_prompt_contract
from build_dist import build_dsh


def patterns():
    # Construct detection patterns from parts so that this test can examine its own bytes.
    personal = ["/" + "Volumes" + "/", "/" + "Users" + "/", "volisle" + "-write-mounts",
                "GPT" + "成果", "ZZLab" + "_001", "w" + "jj", "Wang" + " Junjie", "cad.onshape.com/" + "documents/"]
    tokens = [r"\bgh[pousr]_[A-Za-z0-9]{24,}", r"\bgithub_pat_[A-Za-z0-9_]{30,}",
              r"\bAKIA[A-Z0-9]{16}\b", r"\bASIA[A-Z0-9]{16}\b", r"\bAIza[0-9A-Za-z_-]{35}",
              r"\bsk[-_](?:proj-|ant-)?[A-Za-z0-9_-]{24,}", r"\bxox[baprs]-[0-9A-Za-z-]{15,}",
              r"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----",
              r"(?i)\b(?:password|api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\x22][A-Za-z0-9_+/=-]{16,}"]
    return [re.compile(re.escape(v).encode(), re.I) for v in personal]+[re.compile(v.encode()) for v in tokens]


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def hygiene():
    tracked = [row.split(b"\t", 1) for row in git("ls-files", "--stage", "-z").split(b"\0") if row]
    if not tracked:
        raise ValueError("No tracked files. Stage the release before running the audit.")
    forbidden_dirs = {"results","backups","__pycache__","optical-assets",".git","project-logs"}
    forbidden_names = {".DS_Store","PROJECT_LOG.md","restore-copy-links.py","package-moves.json",
                       "mirror-request.json","hksop-gpt-handoff-spec.md"}
    rules = patterns()
    ids = sorted({header.split()[1] for header, _ in tracked})
    request = b"".join(oid + b"\n" for oid in ids)
    def batch(option):
        return subprocess.check_output(["git", "-C", str(ROOT), "cat-file", option], input=request)
    for row in batch("--batch-check").splitlines():
        oid, kind, length = row.split()
        if kind != b"blob" or int(length) >= 2_000_000:
            raise ValueError("Unexpected tracked object or size: " + oid.decode())
    stream = io.BytesIO(batch("--batch"))
    blobs = {}
    for wanted in ids:
        oid, kind, length = stream.readline().split()
        if oid != wanted or kind != b"blob":
            raise ValueError("Unexpected Git object")
        blobs[oid.decode()] = stream.read(int(length))
        if stream.read(1) != b"\n":
            raise ValueError("Incomplete Git object")
    scanned = set()
    def check_bytes(content, name):
        if len(content) >= 2_000_000:
            raise ValueError("File exceeds size limit: " + name)
        key = hashlib.sha256(content).digest()
        if key not in scanned:
            # Scan embedded assets as decoded bytes, then scan the surrounding text.
            # Base64's random letters are not prose; hiding a credential in it still fails.
            embedded = re.compile(rb"data:(?:image/[a-zA-Z0-9+.-]+|font/[a-zA-Z0-9+.-]+);base64,([A-Za-z0-9+/=]+)")
            def decode_asset(match):
                payload = base64.b64decode(match.group(1), validate=True)
                check_bytes(payload, name + " [embedded asset]")
                return b"data:decoded-and-scanned"
            readable = embedded.sub(decode_asset, content)
            if any(rule.search(readable) for rule in rules):
                raise ValueError("Private path or credential pattern in " + name)
            scanned.add(key)
    for header, raw_name in tracked:
        mode, oid, stage = header.decode().split()
        name = os.fsdecode(raw_name)
        p = Path(name)
        if (mode not in {"100644","100755"} or stage != "0" or forbidden_dirs.intersection(p.parts)
                or p.name in forbidden_names or p.name.startswith(("._","gpt-prompt-"))
                or p.suffix.lower() in {".step",".stp",".zip",".pdf",".pyc",".pem",".key"}):
            raise ValueError("Excluded tracked file: " + name)
        check_bytes(raw_name, name)
        check_bytes(blobs[oid], name)
        working = ROOT / p
        if not working.is_file() or working.is_symlink():
            raise ValueError("Missing or linked tracked file: " + name)
        check_bytes(working.read_bytes(), name)
    return len(tracked)


def root_contract():
    from optical_layout import hksop_runtime as resolver
    with tempfile.TemporaryDirectory() as work:
        base = Path(work).resolve()
        siblings = [base / "HKSOP", base / "HKSOP-refactored"]
        for p in siblings:
            (p / "library").mkdir(parents=True)
            (p / "library/catalog.json").write_text("{}")
        with patch.object(resolver, "sibling_libraries", return_value=siblings), patch.dict(os.environ,clear=True):
            assert library_root() == siblings[0]
            os.environ["HKSOP_ROOT"] = str(siblings[1])
            assert library_root() == siblings[1] and library_root(siblings[0]) == siblings[0]
            try:
                library_root(base/"not-a-core")
            except ValueError as exc:
                assert "HKSOP_ROOT" in str(exc)
            else:
                raise AssertionError("Invalid explicit root accepted")


def main():
    count = hygiene()
    subprocess.run([sys.executable,"-B",str(ROOT/"scripts/sync_plugins.py"),"--check"],check=True)
    manifests(ROOT/"plugins")
    rows = isolation(ROOT/"plugins")+cordis_contract()
    root_contract()
    metrics = run_audit([Path(os.fsdecode(p)) for p in git("ls-files", "-z").split(b"\0") if p])
    prompts = dsh_prompt_contract(build_dsh())
    print(f"PASS redundancy gates: {metrics}; {prompts} live Cordis prompts")
    print(f"PASS {count} tracked files, staged and on disk; 8 client packages; {sum(x['matches'] for x in rows)} isolation matches")


if __name__ == "__main__":
    try:
        main()
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
