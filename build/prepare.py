#!/usr/bin/env python3
"""Apply the reviewed patch only to the exact uploaded upstream revision."""
from __future__ import annotations

import base64
import hashlib
import lzma
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
REVISION = "4d5933c9914ab5c5efc4ff4124bdf255f6ba619d"
PATCH_SHA256 = "5ef0f6020474039270af123ee8f17ba000b563eeab63cfe50acbbe8c42b5d469"


def run(*args: str) -> None:
    subprocess.run(args, cwd=SOURCE, check=True)


def main() -> None:
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=SOURCE, text=True
    ).strip()
    if revision != REVISION:
        raise RuntimeError(f"Unexpected source revision: {revision}")
    parts = [ROOT / "build" / f"patch.b64.{index:02d}" for index in range(4)]
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    patch = lzma.decompress(
        base64.b64decode(encoded, validate=True), memlimit=256 * 1024 * 1024
    )
    digest = hashlib.sha256(patch).hexdigest()
    if digest != PATCH_SHA256:
        raise RuntimeError(f"Patch checksum mismatch: {digest}")
    patch_path = ROOT / "build" / "custom.patch"
    patch_path.write_bytes(patch)
    run("git", "apply", "--check", "--unidiff-zero", str(patch_path))
    run("git", "apply", "--unidiff-zero", str(patch_path))
    # Native compiler fixes remain readable and separate from the reviewed payload.
    for fix in sorted((ROOT / "build" / "fixes").glob("*.patch")):
        run("git", "apply", "--check", str(fix))
        run("git", "apply", str(fix))
    print(f"Verified and applied patch {digest}", flush=True)
    destination = ROOT / "build-source"
    destination.mkdir(exist_ok=True)
    archive_path = destination / "OxideTerm-2.0.31-custom-source.tar.gz"
    def source_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
        if any(part in {".git", "target", "dist", "__pycache__"} for part in Path(member.name).parts):
            return None
        return member
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(SOURCE, arcname="oxideterm-custom", filter=source_filter)
    print(f"Corresponding source: {archive_path.name}", flush=True)


if __name__ == "__main__":
    main()
