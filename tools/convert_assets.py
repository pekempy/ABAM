#!/usr/bin/env python3
"""Batch convert Aurora .asset/.assets files into PNG images."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from aurora_engine.asset_parser import AuroraAssetFile
from aurora_engine.texture.decode import convert_asset_to_png_bytes


def convert_assets(source: Path, destination: Path | None) -> tuple[int, int]:
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=True)

    files = sorted(list(source.rglob("*.asset")) + list(source.rglob("*.assets")))
    total_files = 0
    total_images = 0

    for asset_path in files:
        total_files += 1
        try:
            asset = AuroraAssetFile(asset_path.read_bytes())
        except Exception as exc:
            print(f"Skip {asset_path}: {exc}")
            continue

        per_file = 0
        for idx, entry in enumerate(asset.entries):
            if not (entry.size > 0 and entry.texture_header and entry.video_data):
                continue

            png = convert_asset_to_png_bytes(entry.texture_header, entry.video_data)
            if not png:
                continue

            if destination is None:
                out_path = asset_path.with_name(f"{asset_path.name}_entry_{idx}.png")
            else:
                safe_rel = asset_path.relative_to(source).as_posix().replace("/", "__")
                out_path = destination / f"{safe_rel}_entry_{idx}.png"
            out_path.write_bytes(png)
            per_file += 1
            total_images += 1

        print(f"{asset_path}: {per_file} image(s)")

    return total_files, total_images


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Aurora .asset/.assets files to PNG images."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Source folder containing .asset/.assets files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=False,
        help="Destination folder for generated PNG files. Omit to write PNG files next to each source .asset file.",
    )

    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve() if args.output else None

    if not source.exists() or not source.is_dir():
        print(f"Input folder does not exist or is not a directory: {source}")
        return 1

    total_files, total_images = convert_assets(source, destination)
    print(f"Done. Files scanned: {total_files}, PNGs written: {total_images}")
    if destination is None:
        print("Output mode: wrote PNG files next to each source .asset/.assets file")
    else:
        print(f"Output folder: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
