#!/usr/bin/env python3
"""Initialize and manage the evidence directory for an argos-eye run.

The evidence directory contains the original image, the target description,
and every intermediate artifact the loop produces. It is the audit trail
for the returned coordinate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def cmd_init(args: argparse.Namespace) -> int:
    image = Path(args.image).expanduser().resolve()
    if not image.exists():
        print(f"error: image not found: {image}", file=sys.stderr)
        return 1

    base = Path(args.out).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_dir = base / timestamp
    run_dir.mkdir(parents=True, exist_ok=False)

    shutil.copy2(image, run_dir / f"input{image.suffix}")
    (run_dir / "target.txt").write_text(args.target, encoding="utf-8")
    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "created_at":   timestamp,
                "image_source": str(image),
                "target":       args.target,
                "max_iter":     args.max_iter,
                "zoom":         args.zoom,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(str(run_dir))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage argos-eye evidence directories.")
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="Create a new evidence run directory.")
    init_p.add_argument("--image",    required=True)
    init_p.add_argument("--target",   required=True)
    init_p.add_argument("--out",      default=".argos-eye")
    init_p.add_argument("--max-iter", type=int, default=3)
    init_p.add_argument("--zoom",     type=float, default=3.0)
    init_p.set_defaults(func=cmd_init)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
