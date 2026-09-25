#!/usr/bin/env python3
"""Deliver only the writable bundle variant, never the ordinary installer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "source/scripts/release"))
from install_macos_bundle import verify_macho_signature
from verify_native_package import verify_portable_archive

MACHO_MAGICS = {
    b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}


def main() -> None:
    source_archive = ROOT / "source/dist/OxideTerm_2.0.31_macos_arm64_portable.tar.gz"
    if not source_archive.is_file():
        raise FileNotFoundError(source_archive)
    verify_portable_archive(source_archive, "aarch64-apple-darwin", "2.0.31")
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="oxideterm-verify-") as temporary:
        stage = Path(temporary)
        with tarfile.open(source_archive, "r:gz") as archive:
            names = {Path(member.name).parts[0] for member in archive.getmembers()}
            if names != {"OxideTerm.app"}:
                raise RuntimeError(f"Expected one application, got {names}")
            archive.extractall(stage, filter="data")
        app = stage / "OxideTerm.app"
        contents = app / "Contents"
        manifest = json.loads((contents / "portable-update.json").read_text())
        if manifest != {
            "formatVersion": 2,
            "appExecutable": "MacOS/oxideterm-native",
            "updateHelper": "MacOS/oxideterm-update-helper",
            "managedEntries": ["Info.plist", "MacOS", "Resources", "portable-update.json"],
        }:
            raise RuntimeError("Unexpected portable layout or update replacement scope")
        if (contents / "UserData").exists() or (contents / "_CodeSignature").exists():
            raise RuntimeError("A portable release must not ship user data or an outer resource seal")
        required = {contents / "MacOS" / name for name in ("oxideterm-native", "oxideterm-update-helper")}
        verified = set()
        for binary in sorted(contents.rglob("*")):
            if binary.is_symlink():
                raise RuntimeError(f"Unexpected symlink: {binary.relative_to(contents)}")
            if not binary.is_file():
                continue
            with binary.open("rb") as stream:
                magic = stream.read(4)
            if magic not in MACHO_MAGICS:
                continue
            architecture = subprocess.check_output(["lipo", "-archs", str(binary)], text=True).strip()
            if architecture != "arm64":
                raise RuntimeError(f"Unexpected architecture for {binary.name}: {architecture}")
            if binary in required and not os.access(binary, os.X_OK):
                raise RuntimeError(f"Not executable: {binary.name}")
            # Verify the exact embedded Mach-O signature on a standalone copy;
            # codesign would otherwise promote the main file to the outer app.
            verify_macho_signature(binary)
            verified.add(binary)
        if not required.issubset(verified):
            raise RuntimeError("Required executable is missing or is not signed Mach-O code")
        destination = output / "OxideTerm-2.0.31-Mac-ARM64-Bundle.zip"
        subprocess.run([
            "ditto", "-c", "-k", "--keepParent", app.name, str(destination)
        ], cwd=stage, check=True)
    shutil.copy2(ROOT / "source/docs/MACOS_BUNDLE_PORTABLE.md", output / "使用与升级说明.md")
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (output / "SHA256.txt").write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    print(f"Verified {len(verified)} ARM64 Mach-O files; application: {destination.name}; SHA256: {digest}", flush=True)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write("## Mac ARM64 包内便携版\n\n")
            file.write("下载下方 **OxideTerm-Mac-ARM64-Bundle** 产物，再解压其中的应用 ZIP。\n\n")
            file.write("包含活动会话右键菜单、独立字号及 Contents/UserData 包内存储。\n\n")
            file.write("这是自用构建，内部程序已做签名校验；外层应用未公证，未进行交互式 SSH/SFTP 测试。\n\n")
            file.write("升级须使用包内安装脚本；不能用 Finder 整包替换含数据的旧应用。\n")


if __name__ == "__main__":
    main()
