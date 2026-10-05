#!/usr/bin/env python3
"""Semantic SAM 2.1 masks from agent-selected boxes/points; entirely offline inference."""
import argparse
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from setup_sam2 import (default_cache, doctor, ENGINE_COMMIT, GGML_COMMIT,
                        MODEL_SHA256, ENGINE_LICENSE, MODEL_LICENSE)


def coordinate(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Coordinates must be finite numbers from 0 to 1, with origin at image top left")
    return float(value)


def validate_selection(selection):
    if not isinstance(selection, dict) or not isinstance(selection.get("subject"), str) or not selection["subject"].strip():
        raise ValueError("selection.subject must describe the desired visible subject")
    objects = selection.get("objects")
    if not isinstance(objects, list) or not 1 <= len(objects) <= 64:
        raise ValueError("selection.objects must contain 1 to 64 independent objects")
    prompts = []
    for obj in objects:
        if not isinstance(obj, dict):
            raise ValueError("Each object must be a dictionary")
        box = obj.get("box")
        if box is not None:
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError("object.box must be [x0,y0,x1,y1]")
            box = [coordinate(x) for x in box]
            if box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError("object.box must have positive width and height")
        points = obj.get("points", [])
        if not isinstance(points, list) or len(points) > 128:
            raise ValueError("object.points must be a list with at most 128 points")
        positive, negative = [], []
        for point in points:
            if not isinstance(point, list) or len(point) != 3 or type(point[2]) is not int or point[2] not in (0, 1):
                raise ValueError("Each point must be [x,y,1] for foreground or [x,y,0] for background")
            (positive if point[2] else negative).append([coordinate(point[0]), coordinate(point[1])])
        if box is None and not positive:
            raise ValueError("Each object needs a box or at least one positive point")
        prompts.append((box, positive, negative))
    return prompts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing output PNG")
    parser.add_argument("--cache", type=Path, default=default_cache())
    parser.add_argument("--device", choices=("metal", "cpu"), default="metal" if platform.system() == "Darwin" else "cpu")
    parser.add_argument("--doctor", action="store_true")
    args = parser.parse_args()
    status = doctor(args.cache)
    if args.doctor:
        print(json.dumps(status, ensure_ascii=False))
        return
    if not all((args.input, args.output, args.selection)):
        parser.error("--input, --output and --selection are required for inference")
    if not status["ready"]:
        raise ValueError("SAM 2 is not configured: " + ", ".join(status["reasons"]) + ". Run " + status["setup_command"])
    from PIL import Image, ImageChops
    if args.input.resolve() == args.output.resolve():
        raise ValueError("Input and output paths must differ")
    if args.output.exists() and not args.overwrite:
        raise ValueError("Output already exists; use --overwrite to replace it")
    if args.output.suffix.lower() != ".png":
        raise ValueError("Output must be a PNG to preserve alpha")
    selection = json.loads(args.selection.read_text())
    prompts = validate_selection(selection)
    with Image.open(args.input) as source:
        if source.getexif().get(274, 1) != 1:
            raise ValueError("Normalize EXIF orientation before inference; prompts must address the displayed canvas")
        if source.mode not in ("RGB", "RGBA"):
            raise ValueError("Input must be an orientation-normalized RGB or RGBA image")
        original = source.convert("RGBA")
        original_rgb = original.convert("RGB")
        profile = source.info.get("icc_profile")
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="collage-sam2-") as tmp:
        tmp = Path(tmp)
        original_rgb.save(tmp / "input.png")
        lines = [str(len(prompts))]
        for box, positive, negative in prompts:
            lines.append(" ".join(str(x) for x in ([int(box is not None)] + (box or [0, 0, 0, 0]) + [len(positive), len(negative)])))
            lines.extend(f"{x} {y}" for x, y in positive + negative)
        (tmp / "prompts.txt").write_text("\n".join(lines) + "\n")
        process = subprocess.run([status["binary"], status["model"], str(tmp / "input.png"),
                                  str(tmp / "prompts.txt"), str(tmp), args.device],
                                 capture_output=True, text=True, timeout=300)
        # Native diagnostics never pollute stdout's one JSON object.
        if process.returncode:
            print(process.stderr[-8000:], file=sys.stderr)
            raise ValueError(f"SAM 2 native runner failed with status {process.returncode}")
        result = json.loads(process.stdout)
        if (result["width"], result["height"]) != original.size or len(result["objects"]) != len(prompts):
            raise ValueError("Native output has an unexpected canvas or object count")
        union = Image.new("L", original.size, 0)
        warnings = ["binary_segmentation_not_fine_alpha_matting", "model_scores_do_not_replace_visual_review"]
        object_reports = []
        for i, item in enumerate(result["objects"]):
            # The native file naming protocol is local and fixed, not supplied by image content.
            with Image.open(tmp / f"mask-{i}.png") as decoded:
                mask = decoded.convert("L")
            if mask.size != original.size or mask.getbbox() is None:
                raise ValueError(f"Object {i} has an empty or incorrectly sized mask")
            positive, negative = prompts[i][1:]
            def hit(point):
                return mask.getpixel((min(mask.width - 1, int(point[0] * mask.width)),
                                      min(mask.height - 1, int(point[1] * mask.height)))) > 0
            missed = sum(not hit(p) for p in positive)
            included = sum(hit(p) for p in negative)
            if missed or included:
                warnings.append(f"object_{i}_prompt_disagreement:positive_missed={missed},negative_included={included}")
            coverage = sum(mask.histogram()[1:]) / (mask.width * mask.height)
            object_reports.append({"index": i, "iou_score": item["iou_score"],
                                   "object_score": item["object_score"], "coverage": coverage,
                                   "positive_points_missed": missed, "negative_points_included": included})
            union = ImageChops.lighter(union, mask)
        # Only alpha changes. Existing transparency is preserved, RGB is never redrawn or premultiplied.
        original.putalpha(ImageChops.multiply(union, original.getchannel("A")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        original.save(args.output, icc_profile=profile)
        if original.convert("RGB").tobytes() != original_rgb.tobytes():
            raise ValueError("RGB preservation invariant failed")
    actual_device = "cpu" if "using CPU backend" in process.stderr else args.device
    if actual_device != args.device:
        warnings.append(f"requested_{args.device}_unavailable_used_{actual_device}")
    print(json.dumps({"engine": "sam3.cpp / SAM 2.1 Tiny F16", "engine_commit": ENGINE_COMMIT,
                      "ggml_commit": GGML_COMMIT, "model_sha256": MODEL_SHA256,
                      "engine_license": ENGINE_LICENSE, "model_license": MODEL_LICENSE,
                      "device": actual_device, "subject": selection["subject"],
                      "objects": object_reports, "width": original.width, "height": original.height,
                      "full_canvas": True, "rgb_preserved": True, "alpha_kind": "binary_object_union",
                      "warnings": warnings, "elapsed_seconds": round(time.monotonic() - start, 3),
                      "output": str(args.output.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
