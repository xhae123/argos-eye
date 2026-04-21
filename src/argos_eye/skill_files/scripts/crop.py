#!/usr/bin/env python3
"""Crop a region of an image and (optionally) zoom it for re-inspection.

Reads a bbox from a JSON file produced by the loop, applies a padding margin
so the target is not flush against the crop edge, and writes the resulting
image. Prints the effective crop geometry (in original-image coordinates) to
stdout as JSON so the caller can remap later.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image


DEFAULT_PADDING_RATIO = 0.15


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def expand_with_padding(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    padding_ratio: float,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = bbox
    w, h = image_size
    bw = x2 - x1
    bh = y2 - y1
    pad_x = int(round(bw * padding_ratio))
    pad_y = int(round(bh * padding_ratio))
    return (
        clamp(x1 - pad_x, 0, w),
        clamp(y1 - pad_y, 0, h),
        clamp(x2 + pad_x, 0, w),
        clamp(y2 + pad_y, 0, h),
    )


def cmd_crop(args: argparse.Namespace) -> int:
    image_path = Path(args.image).expanduser().resolve()
    bbox_file  = Path(args.bbox_file).expanduser().resolve()
    out_path   = Path(args.out).expanduser().resolve()

    if not image_path.exists():
        print(f"error: image not found: {image_path}", file=sys.stderr)
        return 1
    if not bbox_file.exists():
        print(f"error: bbox file not found: {bbox_file}", file=sys.stderr)
        return 1

    bbox_payload = json.loads(bbox_file.read_text(encoding="utf-8"))
    bbox = bbox_payload.get("bbox")
    if bbox is None or len(bbox) != 4:
        print(f"error: bbox payload missing or malformed in {bbox_file}", file=sys.stderr)
        return 1

    with Image.open(image_path) as im:
        im.load()
        padded = expand_with_padding(tuple(bbox), im.size, args.padding)
        cropped = im.crop(padded)

        if args.zoom and args.zoom > 1.0:
            new_size = (
                max(1, int(round(cropped.width  * args.zoom))),
                max(1, int(round(cropped.height * args.zoom))),
            )
            cropped = cropped.resize(new_size, Image.LANCZOS)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        cropped.save(out_path)

    geometry = {
        "source_image":  str(image_path),
        "proposal_bbox": list(bbox),
        "padded_bbox":   list(padded),
        "zoom":          args.zoom,
        "crop_size":     [cropped.width, cropped.height],
        "out":           str(out_path),
    }
    print(json.dumps(geometry))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crop and zoom an image region.")
    parser.add_argument("--image",      required=True)
    parser.add_argument("--bbox-file",  required=True)
    parser.add_argument("--out",        required=True)
    parser.add_argument("--zoom",       type=float, default=3.0)
    parser.add_argument("--padding",    type=float, default=DEFAULT_PADDING_RATIO)
    parser.set_defaults(func=cmd_crop)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
