"""Recreate the RT-Spark source from pinned upstream commits and local patches.

This script only writes to a new --destination. Pass --source NAME=PATH to use
existing local Git clones instead of network access. It never touches the
known-working firmware checkout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {args}\n{result.stderr.strip()}")
    return result.stdout.strip()


def sources(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            raise ValueError("Use --source NAME=PATH")
        result[name] = str(Path(path).resolve())
    return result


def verify_inventory(destination: Path) -> None:
    mismatches = []
    newline_only = []
    with (HERE / "inventory.csv").open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            relative = row["source"].removeprefix("firmware/rt-thread/")
            reconstructed = destination / relative
            if not reconstructed.is_file():
                mismatches.append(relative)
                continue
            actual_bytes = reconstructed.read_bytes()
            if hashlib.sha256(actual_bytes).hexdigest() != row["sha256"]:
                normalized = hashlib.sha256(actual_bytes.replace(b"\r\n", b"\n")).hexdigest()
                if normalized == row["normalized_sha256"]:
                    newline_only.append(relative)
                else:
                    mismatches.append(relative)
    if mismatches:
        raise RuntimeError("Source comparison failed:\n" + "\n".join(mismatches))
    print("PASS: All inventoried working-source contents match")
    if newline_only:
        print("NOTE: line-ending-only differences (Git patch normalization): " + ", ".join(newline_only))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--source", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--verify-existing", action="store_true", help="Check an existing reconstruction without changes")
    args = parser.parse_args()
    destination = args.destination.resolve()
    if args.verify_existing:
        verify_inventory(destination)
        return
    if destination.exists():
        raise SystemExit(f"Destination already exists; refusing to overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_map = sources(args.source)
    manifest = json.loads((HERE / "dependency-manifest.json").read_text(encoding="utf-8"))

    for dependency in manifest["dependencies"]:
        name = dependency["name"]
        target = destination / dependency["destination"]
        target.parent.mkdir(parents=True, exist_ok=True)
        source = source_map.get(name, dependency["url"])
        if name in source_map:
            # Archive only the committed tree. Local uncommitted edits and .git
            # metadata cannot enter the reconstruction by this path.
            actual = run("git", "-C", source, "rev-parse", "HEAD")
            if actual != dependency["commit"]:
                raise RuntimeError(f"Wrong {name} source commit: {actual}")
            archive = subprocess.run(["git", "-C", source, "archive", "--format=tar", actual],
                                     check=True, capture_output=True).stdout
            target.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(target, filter="data")
        else:
            run("git", "clone", "--quiet", "--no-checkout", source, str(target))
            run("git", "checkout", "--quiet", "--detach", dependency["commit"], cwd=target)
            actual = run("git", "rev-parse", "HEAD", cwd=target)
        if actual != dependency["commit"]:
            raise RuntimeError(f"Wrong {name} commit: {actual}")
        for relative_patch in dependency["patches"]:
            patch = HERE / relative_patch
            run("git", "apply", "--check", str(patch), cwd=target)
            run("git", "apply", str(patch), cwd=target)
        print(f"Pinned and patched: {name} {actual}")

    overlay = HERE / manifest["overlay"]
    for source in overlay.rglob("*"):
        if source.is_file():
            target = destination / source.relative_to(overlay)
            if target.exists():
                raise RuntimeError(f"Overlay would overwrite an existing file: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    verify_inventory(destination)


if __name__ == "__main__":
    main()
