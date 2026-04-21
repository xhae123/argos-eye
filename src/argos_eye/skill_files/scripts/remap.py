#!/usr/bin/env python3
"""Coordinate remapping and run finalization.

Two subcommands:

  converge-check   compare consecutive proposals (after remap to the original
                   image coordinate system) and exit 0 if they converge.

  finalize         read all iteration artifacts in an evidence directory,
                   remap the final proposal to the original image, score
                   confidence, and write result.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def bbox_iou(a: list[int], b: list[int]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    intersection = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union  = area_a + area_b - intersection
    return 0.0 if union == 0 else intersection / union


def bbox_center(bbox: list[int]) -> list[int]:
    x1, y1, x2, y2 = bbox
    return [int(round((x1 + x2) / 2)), int(round((y1 + y2) / 2))]


def remap_crop_bbox_to_original(
    crop_bbox: list[int],
    padded_parent: list[int],
    zoom: float,
) -> list[int]:
    """Translate a bbox given in the zoomed crop's local coordinates back to
    the original image's coordinate system."""
    px1, py1, _px2, _py2 = padded_parent
    scale = 1.0 / zoom if zoom else 1.0
    cx1, cy1, cx2, cy2 = crop_bbox
    return [
        int(round(px1 + cx1 * scale)),
        int(round(py1 + cy1 * scale)),
        int(round(px1 + cx2 * scale)),
        int(round(py1 + cy2 * scale)),
    ]


def proposal_to_original(proposal: dict, parent_geometry: dict | None) -> list[int] | None:
    """Resolve a proposal's bbox in the original image space."""
    if proposal.get("bbox") is None:
        return None
    if proposal.get("source") == "full_image" or parent_geometry is None:
        return list(proposal["bbox"])
    return remap_crop_bbox_to_original(
        proposal["bbox"],
        parent_geometry["padded_bbox"],
        parent_geometry["zoom"],
    )


ITER_RE = re.compile(r"^iter-(\d+)-bbox\.json$")


def collect_iterations(evidence_dir: Path) -> list[tuple[int, dict]]:
    rows: list[tuple[int, dict]] = []
    for path in sorted(evidence_dir.iterdir()):
        m = ITER_RE.match(path.name)
        if m:
            rows.append((int(m.group(1)), load_json(path)))
    rows.sort(key=lambda r: r[0])
    return rows


def collect_crop_geometries(evidence_dir: Path) -> dict[int, dict]:
    geometries: dict[int, dict] = {}
    for path in sorted(evidence_dir.glob("iter-*-crop.geometry.json")):
        m = re.match(r"^iter-(\d+)-crop\.geometry\.json$", path.name)
        if m:
            geometries[int(m.group(1))] = load_json(path)
    return geometries


def cmd_converge_check(args: argparse.Namespace) -> int:
    prev = load_json(Path(args.prev))
    curr = load_json(Path(args.curr))

    if prev.get("bbox") is None or curr.get("bbox") is None:
        return 2

    parent_geometry = None
    if args.parent_geometry:
        parent_geometry = load_json(Path(args.parent_geometry))

    prev_in_orig = proposal_to_original(prev, parent_geometry if prev.get("source") == "crop" else None)
    curr_in_orig = proposal_to_original(curr, parent_geometry if curr.get("source") == "crop" else None)

    if prev_in_orig is None or curr_in_orig is None:
        return 2

    iou = bbox_iou(prev_in_orig, curr_in_orig)
    print(json.dumps({"iou": iou, "threshold": args.iou_threshold}))
    return 0 if iou >= args.iou_threshold else 1


def _score_confidence(iou_history: list[float]) -> float:
    if not iou_history:
        return 0.0
    last = iou_history[-1]
    trend_bonus = 0.0
    if len(iou_history) >= 2 and iou_history[-1] >= iou_history[-2]:
        trend_bonus = 0.05
    return round(min(1.0, last + trend_bonus), 3)


def cmd_finalize(args: argparse.Namespace) -> int:
    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    if not evidence_dir.exists():
        print(f"error: evidence dir not found: {evidence_dir}", file=sys.stderr)
        return 1

    iterations = collect_iterations(evidence_dir)
    geometries = collect_crop_geometries(evidence_dir)

    if not iterations:
        print(f"error: no iteration files in {evidence_dir}", file=sys.stderr)
        return 1

    not_found = any(it[1].get("not_found") for it in iterations)

    resolved: list[tuple[int, list[int] | None]] = []
    for idx, proposal in iterations:
        parent_geometry = geometries.get(idx - 1)
        resolved.append((idx, proposal_to_original(proposal, parent_geometry)))

    iou_history: list[float] = []
    for i in range(1, len(resolved)):
        prev = resolved[i - 1][1]
        curr = resolved[i][1]
        if prev is None or curr is None:
            continue
        iou_history.append(bbox_iou(prev, curr))

    final_idx, final_bbox = resolved[-1]
    converged = bool(iou_history) and iou_history[-1] >= 0.85
    confidence = 0.0 if not_found or final_bbox is None else _score_confidence(iou_history)

    result: dict
    if not_found or final_bbox is None or confidence < args.min_confidence:
        result = {
            "bbox":       None,
            "center":     None,
            "confidence": confidence,
            "iterations": len(iterations),
            "converged":  converged,
            "evidence":   str(evidence_dir),
            "reason":     "target not found or confidence below threshold",
        }
    else:
        result = {
            "bbox":       final_bbox,
            "center":     bbox_center(final_bbox),
            "confidence": confidence,
            "iterations": len(iterations),
            "converged":  converged,
            "evidence":   str(evidence_dir),
        }

    save_json(evidence_dir / "result.json", result)
    print(json.dumps(result, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coordinate remapping and finalization.")
    sub = parser.add_subparsers(dest="command", required=True)

    cc = sub.add_parser("converge-check", help="Check whether two consecutive proposals converge.")
    cc.add_argument("--prev",             required=True)
    cc.add_argument("--curr",             required=True)
    cc.add_argument("--parent-geometry",  help="Crop geometry JSON for the iteration that produced the current proposal.")
    cc.add_argument("--iou-threshold",    type=float, default=0.85)
    cc.set_defaults(func=cmd_converge_check)

    fz = sub.add_parser("finalize", help="Remap the final proposal and write result.json.")
    fz.add_argument("--evidence-dir",   required=True)
    fz.add_argument("--min-confidence", type=float, default=0.5)
    fz.set_defaults(func=cmd_finalize)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
