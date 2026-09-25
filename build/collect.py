#!/usr/bin/env python3
"""Deliver only the writable bundle variant, never the ordinary installer."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source_archive = ROOT / "source/dist/OxideTerm_2.0.31_macos_arm64_portable.tar.gz"
    if not source_archive.is_file():
        raise FileNotFoundError(source_archive)
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
        if (contents / "UserData").exists():
            raise RuntimeError("A release must never ship user data")
        for name in ("oxideterm-native", "oxideterm-update-helper"):
            binary = contents / "MacOS" / name
            architecture = subprocess.check_output(["lipo", "-archs", str(binary)], text=True).strip()
            if architecture != "arm64":
                raise RuntimeError(f"Unexpected architecture for {name}: {architecture}")
            if not os.access(binary, os.X_OK):
                raise RuntimeError(f"Not executable: {name}")
            subprocess.run(["codesign", "--verify", "--strict", str(binary)], check=True)
        destination = output / "OxideTerm-2.0.31-Mac-ARM64-Bundle.zip"
        subprocess.run([
            "ditto", "-c", "-k", "--keepParent", app.name, str(destination)
        ], cwd=stage, check=True)
    shutil.copy2(ROOT / "source/docs/MACOS_BUNDLE_PORTABLE.md", output / "使用与升级说明.md")
    with destination.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (output / "SHA256.txt").write_text(f"{digest}  {destination.name}\n", encoding="utf-8")
    print(f"Verified ARM64 application: {destination.name}; SHA256: {digest}", flush=True)
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
