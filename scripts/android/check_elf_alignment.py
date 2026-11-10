#!/usr/bin/env python3
"""Fail when an APK contains an ELF LOAD segment aligned below 16 KiB."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path


MIN_ALIGNMENT = 16 * 1024


def load_alignments(readelf_output: str) -> list[int]:
    alignments: list[int] = []
    for line in readelf_output.splitlines():
        if not re.match(r"^\s*LOAD\s", line):
            continue
        token = line.split()[-1]
        alignments.append(int(token, 0))
    return alignments


def verify_apk(apk_path: Path, readelf: str = "readelf") -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="driver-control-elf-") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(apk_path) as archive:
            members = [name for name in archive.namelist() if name.endswith(".so")]
            if not members:
                return ["APK does not contain native libraries"]
            for member in members:
                target = root / Path(member).name
                target.write_bytes(archive.read(member))
                result = subprocess.run(
                    [readelf, "-lW", str(target)],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                alignments = load_alignments(result.stdout)
                if not alignments:
                    failures.append(f"{member}: no ELF LOAD segments found")
                elif min(alignments) < MIN_ALIGNMENT:
                    rendered = ", ".join(hex(value) for value in alignments)
                    failures.append(f"{member}: LOAD alignment {rendered}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    parser.add_argument("--readelf", default="readelf")
    args = parser.parse_args()
    if not args.apk.is_file():
        parser.error(f"APK not found: {args.apk}")
    failures = verify_apk(args.apk, args.readelf)
    if failures:
        print("16 KiB ELF alignment check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"16 KiB ELF alignment verified: {args.apk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
