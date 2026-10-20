"""Export the current RT-Spark changes without writing to its working checkout.

Run from the project root. This is a maintainer tool, not part of firmware build.
It refuses to overwrite an existing export; review and remove an old export
manually before repeating it.
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "firmware/rt-thread"
BSP = Path("bsp/stm32/stm32f407-rt-spark")
OUT = Path(__file__).resolve().parent
OVERLAY = OUT / "overlays/rt-thread"
PATCHES = OUT / "patches"


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def main() -> None:
    inventory = OUT / "inventory.csv"
    rt_patch = PATCHES / "0001-rt-thread-project-changes.patch"
    rw_patch = PATCHES / "0002-rw007-stm32-port-startup.patch"
    if any(p.exists() for p in (inventory, rt_patch, rw_patch, OVERLAY)):
        raise SystemExit("Export already exists; refusing to overwrite it")
    if git(WORK, "rev-parse", "HEAD").decode().strip() != "99428a1e7f7447955aa860f7c969273a12095b8f":
        raise SystemExit("RT-Thread revision differs from audited baseline")

    PATCHES.mkdir(parents=True)
    rt_patch.write_bytes(git(WORK, "-c", "core.autocrlf=false", "diff", "--binary", "--no-ext-diff"))
    tracked = git(WORK, "diff", "--name-only", "-z").decode().split("\0")[:-1]
    untracked = git(WORK, "ls-files", "--others", "--exclude-standard", "-z", "--", str(BSP).replace("\\", "/")).decode().split("\0")[:-1]
    ignored_required = [str(BSP / "packages/Kconfig").replace("\\", "/")]
    rows: list[dict[str, str]] = []
    for rel in tracked:
        source = WORK / rel
        rows.append(dict(source=str(source.relative_to(ROOT)).replace("\\", "/"), destination=rel,
                         representation=str(rt_patch.relative_to(OUT)).replace("\\", "/"),
                         purpose="RT-Thread/BSP integration and application change", upstream="RT-Thread",
                         sensitive_configuration="network feature flags; no credentials found" if rel.endswith(".config") else "none found",
                         sha256=sha(source), normalized_sha256=normalized_sha(source)))
    for rel in untracked + ignored_required:
        source = WORK / rel
        dest = OVERLAY / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        rows.append(dict(source=str(source.relative_to(ROOT)).replace("\\", "/"),
                         destination=str(dest.relative_to(OUT)).replace("\\", "/"),
                         representation="copy overlay", purpose="RT-Spark application, notes, or package Kconfig",
                         upstream="RT-Thread", sensitive_configuration="private LAN default only" if rel.endswith("mqtt_config.h") else "none found",
                         sha256=sha(source), normalized_sha256=normalized_sha(source)))

    package = WORK / BSP / "packages"
    for name, rels in {
        "icm20608-latest": ["icm20608.c"],
        "rw007-latest": ["src/spi_wifi_rw007.c", "example/rw007_stm32_port.c"],
    }.items():
        for rel in rels:
            source = package / name / rel
            rows.append(dict(source=str(source.relative_to(ROOT)).replace("\\", "/"),
                             destination=f"packages/{name}/{rel}",
                             representation="package patch; see dependency-manifest.json",
                             purpose="sensor or Wi-Fi package integration", upstream=name,
                             sensitive_configuration="none found", sha256=sha(source),
                             normalized_sha256=normalized_sha(source)))

    base = (ROOT / "rw007-download/example/rw007_stm32_port.c").read_bytes().decode("utf-8")
    edited = (package / "rw007-latest/example/rw007_stm32_port.c").read_bytes().decode("utf-8")
    diff = "".join(difflib.unified_diff(base.splitlines(keepends=True), edited.splitlines(keepends=True),
                                         fromfile="a/example/rw007_stm32_port.c",
                                         tofile="b/example/rw007_stm32_port.c"))
    rw_patch.write_text(diff, encoding="utf-8", newline="")

    with inventory.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(tracked)} tracked changes, {len(untracked)} untracked files, "
          f"{len(ignored_required)} ignored file, and 3 package source changes")


if __name__ == "__main__":
    main()
