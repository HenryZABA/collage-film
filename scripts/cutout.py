#!/usr/bin/env python3
"""Local photograph segmentation and alpha QA for collage-film.

Requires Pillow and numpy. Uses installed BiRefNet for foreground alpha,
SAM 2 for agent-selected objects, or Apple Vision as a lightweight fallback.
No image is uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

try:
    import numpy as np
    from PIL import Image, ImageOps
except ImportError as exc:
    raise SystemExit("Missing Pillow/numpy. Use a project venv and install: python -m pip install Pillow numpy") from exc


SWIFT = r'''import Foundation
import Vision
import CoreImage
import ImageIO

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}

guard CommandLine.arguments.count == 4 else { fail("Expected input, output and instance selection") }
if #available(macOS 14.0, *) {
    do {
        let sourceURL = URL(fileURLWithPath: CommandLine.arguments[1])
        let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
        guard let source = CGImageSourceCreateWithURL(sourceURL as CFURL, nil),
              let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
        else { fail("Cannot decode normalized input") }
        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        let request = VNGenerateForegroundInstanceMaskRequest()
        try handler.perform([request])
        guard let observation = request.results?.first, !observation.allInstances.isEmpty
        else { fail("Vision found no foreground instances; use another photograph or a supplied alpha cutout") }
        let selection = CommandLine.arguments[3]
        var selected = observation.allInstances
        if selection != "all" {
            selected = IndexSet()
            for token in selection.split(separator: ",") {
                guard let number = Int(token), observation.allInstances.contains(number)
                else { fail("Requested instance is unavailable. Available: \(Array(observation.allInstances))") }
                selected.insert(number)
            }
        }
        let masked = try observation.generateMaskedImage(ofInstances: selected, from: handler, croppedToInstancesExtent: false)
        let result = CIImage(cvPixelBuffer: masked)
        let context = CIContext(options: [.cacheIntermediates: false])
        guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else { fail("Cannot create sRGB color space") }
        try context.writePNGRepresentation(of: result, to: outputURL, format: .RGBA8, colorSpace: colorSpace)
        let metadata: [String: Any] = ["available_instances": Array(observation.allInstances), "selected_instances": Array(selected)]
        let data = try JSONSerialization.data(withJSONObject: metadata, options: [.sortedKeys])
        print(String(data: data, encoding: .utf8)!)
    } catch { fail("Apple Vision segmentation failed: \(error.localizedDescription)") }
} else { fail("Apple Vision cutout requires macOS 14 or newer") }
'''

REMBG_SESSIONS = {}
ROOT = Path(__file__).resolve().parent


def backend_status(name: str) -> dict:
    helper = ROOT / f"{name}_backend.py"
    if not helper.is_file():
        return {"ready": False, "reason": f"{name} adapter is unavailable"}
    result = subprocess.run([sys.executable, str(helper), "--doctor"], capture_output=True, text=True, timeout=60)
    try:
        status = json.loads(result.stdout)
        if result.returncode or not isinstance(status, dict):
            raise ValueError("Invalid doctor result")
        return status
    except ValueError:
        return {"ready": False, "reason": result.stderr.strip()[-1000:] or f"{name} doctor did not return valid JSON"}


def load_selection(path: Path) -> dict:
    return validate_selection(json.loads(path.expanduser().read_text()))


def validate_selection(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - {"subject", "objects"}:
        raise ValueError("Selection must contain only subject and objects")
    if not isinstance(value.get("subject"), str) or not value["subject"].strip():
        raise ValueError("Selection needs a descriptive subject grounded in the actual image")
    objects = value.get("objects")
    if not isinstance(objects, list) or not 1 <= len(objects) <= 30:
        raise ValueError("Selection needs 1..30 independently prompted objects")
    def coord(x):
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and 0 <= x <= 1
    for obj in objects:
        if not isinstance(obj, dict) or set(obj) - {"box", "points"}:
            raise ValueError("Each object accepts box and points only")
        box = obj.get("box")
        if box is not None and (not isinstance(box, list) or len(box) != 4 or not all(coord(x) for x in box) or not (box[0] < box[2] and box[1] < box[3])):
            raise ValueError("box is normalized [left,top,right,bottom], with positive area")
        points = obj.get("points", [])
        if not isinstance(points, list) or any(not isinstance(p, list) or len(p) != 3 or not all(coord(x) for x in p[:2]) or type(p[2]) is not int or p[2] not in (0, 1) for p in points):
            raise ValueError("points are normalized [x,y,1=include or 0=exclude]")
        if box is None and not any(p[2] == 1 for p in points):
            raise ValueError("Each object needs a box or at least one positive point")
    return value


def model_cutout(image: Image.Image, backend: str, selection: dict | None) -> tuple[Image.Image, dict]:
    helper = ROOT / f"{backend}_backend.py"
    with tempfile.TemporaryDirectory(prefix=f"collage-{backend}-") as tmp:
        source, output = Path(tmp) / "input.png", Path(tmp) / "output.png"
        image.save(source)
        command = [sys.executable, str(helper), "--input", str(source), "--output", str(output)]
        if selection is not None:
            prompt = Path(tmp) / "selection.json"
            prompt.write_text(json.dumps(selection))
            command += ["--selection", str(prompt)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[-2500:] or result.stdout.strip()[-2500:] or f"{backend} failed")
        details = json.loads(result.stdout)
        with Image.open(output) as opened:
            return opened.convert("RGBA"), details


def refine_cutout(image: Image.Image, masked: Image.Image) -> tuple[Image.Image, dict]:
    with tempfile.TemporaryDirectory(prefix="collage-matting-") as tmp:
        source, mask, output = (Path(tmp) / name for name in ("input.png", "mask.png", "output.png"))
        image.save(source)
        masked.save(mask)
        command = [sys.executable, str(ROOT / "vitmatte_backend.py"), "--input", str(source), "--mask", str(mask), "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=600)
        if result.returncode:
            raise RuntimeError(result.stderr.strip()[-2500:] or "ViTMatte refinement failed")
        details = json.loads(result.stdout)
        with Image.open(output) as opened:
            return opened.convert("RGBA"), details


def rembg_cutout(image: Image.Image, args: argparse.Namespace) -> Image.Image:
    if importlib.util.find_spec("rembg") is None:
        raise RuntimeError("rembg is not installed in this Python environment. In an isolated project venv install 'rembg[cpu]', or provide a transparent PNG with --backend alpha. See references/cutout.md.")
    from rembg import new_session, remove
    from rembg.sessions import sessions_class
    session_type = next((item for item in sessions_class if item.name() == args.rembg_model), None)
    if session_type is None:
        raise RuntimeError(f"Installed rembg does not support {args.rembg_model}")
    filename = args.rembg_model + ".onnx"
    if hasattr(session_type, "resolve_existing"):
        cached = session_type.resolve_existing(filename)
    else:
        candidate = Path(session_type.u2net_home()) / filename
        cached = str(candidate) if candidate.is_file() else None
    if not cached and not args.allow_model_download:
        raise RuntimeError(f"rembg model {args.rembg_model} is not cached. First setup requires --backend rembg --allow-model-download; this downloads model weights without uploading your photo.")
    if args.rembg_model not in REMBG_SESSIONS:
        REMBG_SESSIONS[args.rembg_model] = new_session(args.rembg_model)
    return remove(image, session=REMBG_SESSIONS[args.rembg_model]).convert("RGBA")


def vision_binary() -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("Photo segmentation requires Apple Vision on macOS 14+. On other systems provide transparent PNGs (--backend alpha), or use an independently installed segmentation tool first.")
    compiler = shutil.which("swiftc")
    if not compiler:
        raise RuntimeError("Apple command line developer tools are required. Install them using xcode-select --install, then retry.")
    signature = hashlib.sha256((SWIFT + platform.machine() + platform.mac_ver()[0]).encode()).hexdigest()[:16]
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / "Library/Caches"))) / "collage-film" / signature
    binary = cache / "vision-cutout"
    if binary.is_file():
        return binary
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compile-", dir=cache) as tmp:
        source = Path(tmp) / "main.swift"
        candidate = Path(tmp) / "vision-cutout"
        source.write_text(SWIFT, encoding="utf-8")
        result = subprocess.run([compiler, "-O", str(source), "-o", str(candidate)], capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError("Could not compile Apple Vision helper: " + result.stderr[-3000:])
        os.replace(candidate, binary)
    return binary


def color(value: str) -> tuple[int, int, int]:
    token = value.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", token):
        raise argparse.ArgumentTypeError("Use a six-digit RGB color, e.g. '#00ff00'")
    return tuple(int(token[i:i + 2], 16) for i in (0, 2, 4))


def chroma(image: Image.Image, key: tuple[int, int, int], tolerance: float, feather: float) -> Image.Image:
    # This is deliberately an explicit studio/key-color operation, never the
    # automatic fallback for a photograph or a failed segmentation request.
    rgba = np.asarray(image, dtype=np.float32).copy()
    distance = np.sqrt(np.sum((rgba[:, :, :3] - np.array(key)) ** 2, axis=2))
    opacity = np.clip((distance - tolerance) / max(feather, 0.001), 0, 1)
    rgba[:, :, 3] *= opacity
    rgba[rgba[:, :, 3] < 1, :3] = 0
    return Image.fromarray(np.uint8(np.clip(rgba, 0, 255)), "RGBA")


def qa(image: Image.Image) -> dict:
    alpha = np.asarray(image.getchannel("A"))
    occupied = alpha > 16
    rows, columns = np.nonzero(occupied)
    if not len(rows):
        raise RuntimeError("Cutout is empty; no visible foreground pixels passed alpha QA")
    bbox = [int(columns.min()), int(rows.min()), int(columns.max()) + 1, int(rows.max()) + 1]
    edges = [name for name, values in (("top", occupied[0]), ("right", occupied[:, -1]), ("bottom", occupied[-1]), ("left", occupied[:, 0])) if np.any(values)]
    coverage = float(np.mean(occupied))
    warnings = []
    if np.min(alpha) == 255:
        raise RuntimeError("Output is fully opaque; background removal did not produce transparency")
    if coverage > 0.92:
        warnings.append("foreground_occupies_over_92_percent: check whether background remains")
    if coverage < 0.01:
        warnings.append("foreground_occupies_under_1_percent: inspect small or incomplete selection")
    if edges:
        warnings.append("subject_touches_source_edge: " + ", ".join(edges))
    return {"source_canvas_size": list(image.size), "foreground_bbox": bbox,
            "foreground_bbox_normalized": [round(value / size, 8) for value, size in zip(bbox, (image.width, image.height, image.width, image.height))],
            "foreground_coverage": round(coverage, 6),
            "partial_alpha_fraction": round(float(np.mean((alpha > 0) & (alpha < 255))), 6),
            "source_edge_contact": edges, "warnings": warnings,
            "visual_review_required": True}


def process(source: Path, args: argparse.Namespace, output_dir: Path) -> dict:
    source = source.expanduser().resolve(strict=True)
    if not source.is_file():
        raise RuntimeError(f"Input is not a file: {source}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    basename = re.sub(r"[^A-Za-z0-9_-]+", "-", source.stem).strip("-") or "image"
    output = output_dir / f"{basename}-{digest[:8]}.png"
    metadata_path = output.with_suffix(".cutout.json")
    if source == output:
        raise RuntimeError("Refusing to overwrite an input image")
    if (output.exists() or metadata_path.exists()) and not args.overwrite:
        raise RuntimeError(f"Output already exists: {output}. Choose another directory or use --overwrite for generated files.")
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    backend = args.backend
    has_alpha = image.getchannel("A").getextrema()[0] < 255
    fallback_reason = None
    if backend == "auto":
        if has_alpha:
            backend = "alpha"
        elif backend_status("birefnet").get("ready"):
            backend = "birefnet"
        else:
            backend = "vision" if platform.system() == "Darwin" else "rembg"
            fallback_reason = "BiRefNet is not configured; using the reported lightweight backend. Run scripts/setup_birefnet.py for the quality backend."
    extra = {}
    if backend == "alpha":
        if not has_alpha:
            raise RuntimeError("--backend alpha requires existing transparency; input is fully opaque")
        masked = image
    elif backend == "chroma":
        masked = chroma(image, args.key_color, args.tolerance, args.feather)
        extra = {"key_color": list(args.key_color), "tolerance": args.tolerance, "feather": args.feather}
    elif backend == "rembg":
        masked = rembg_cutout(image, args)
        extra = {"model": args.rembg_model, "model_download_allowed": args.allow_model_download}
    elif backend in ("birefnet", "sam2"):
        masked, extra = model_cutout(image, backend, args.selection)
    else:
        binary = vision_binary()
        with tempfile.TemporaryDirectory(prefix="collage-cutout-") as tmp:
            normalized = Path(tmp) / "normalized.png"
            generated = Path(tmp) / "masked.png"
            image.save(normalized)
            result = subprocess.run([str(binary), str(normalized), str(generated), args.instances], capture_output=True, text=True, timeout=180)
            if result.returncode:
                raise RuntimeError(result.stderr.strip()[-3000:] or "Vision helper failed")
            extra = json.loads(result.stdout)
            with Image.open(generated) as opened:
                masked = opened.convert("RGBA")
    if backend == "sam2" and args.refine != "none":
        refinement = backend_status("vitmatte")
        if refinement.get("ready") or args.refine == "vitmatte":
            masked, extra["refinement"] = refine_cutout(image, masked)
            extra["seed_alpha_kind"] = extra.get("alpha_kind")
            extra["alpha_kind"] = "vitmatte_soft_alpha"
            extra["warnings"] = [w for w in extra.get("warnings", []) if w != "binary_segmentation_not_fine_alpha_matting"]
            extra["warnings"].extend(extra["refinement"].get("warnings", []))
        else:
            extra["refinement"] = {"backend": "none", "reason": refinement.get("reason", "ViTMatte is not configured")}
            extra.setdefault("warnings", []).append("edge_refinement_unavailable: " + extra["refinement"]["reason"])
    if masked.size != image.size:
        raise RuntimeError("Segmentation output changed the source canvas dimensions")
    # Segmentation must only supply alpha. Keep the original oriented RGB,
    # including at semitransparent edges, for an exact full-photo handoff.
    original_rgb = image.convert("RGB").convert("RGBA")
    original_rgb.putalpha(masked.getchannel("A"))
    masked = original_rgb
    quality = qa(masked)
    quality["original_rgb_preserved"] = True
    quality["warnings"].extend(w for w in extra.get("warnings", []) if isinstance(w, str))
    if fallback_reason:
        quality["warnings"].append(fallback_reason)
    if args.selection:
        extra["selection"] = args.selection
        extra["selection_method"] = "agent_visual_geometry; subject label is documentation, not a text-to-mask model prompt"
    if args.no_crop:
        cropped = masked
        crop_box = [0, 0, *masked.size]
    else:
        crop_box = quality["foreground_bbox"]
        cropped = ImageOps.expand(masked.crop(tuple(crop_box)), border=args.padding, fill=(0, 0, 0, 0))
    record = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "source_file": str(source), "source_sha256": digest,
              "file": output.name, "metadata_file": metadata_path.name,
              "backend": backend, "backend_details": extra,
              "width": cropped.width, "height": cropped.height,
              "crop_box": crop_box, "padding": 0 if args.no_crop else args.padding,
              "qa": quality}
    cropped.save(output)
    metadata_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("inputs", nargs="+", type=Path, help="Local raster images; original files are never modified")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--backend", choices=("auto", "birefnet", "sam2", "vision", "rembg", "alpha", "chroma"), default="auto")
    parser.add_argument("--selection-file", type=Path, help="One-image SAM 2 subject plan: subject + independently prompted objects; normalized coordinates")
    parser.add_argument("--refine", choices=("auto", "none", "vitmatte"), default="auto", help="For SAM 2 only: auto refines edges with installed ViTMatte, none retains binary masks")
    parser.add_argument("--rembg-model", choices=("u2net", "u2netp", "isnet-general-use"), default="u2net")
    parser.add_argument("--allow-model-download", action="store_true", help="For explicit rembg setup only: allow fetching a missing model to the user's cache")
    parser.add_argument("--instances", default="all", help="Vision instance IDs, e.g. 1,2; default all detected foreground subjects")
    parser.add_argument("--key-color", type=color, help="Required for explicit chroma mode; never inferred from a photograph")
    parser.add_argument("--tolerance", type=float, default=24, help="Chroma RGB Euclidean distance cutoff")
    parser.add_argument("--feather", type=float, default=24, help="Chroma soft edge distance")
    parser.add_argument("--padding", type=int, default=24, help="Transparent pixels around tight foreground crop")
    parser.add_argument("--no-crop", action="store_true", help="Preserve source canvas dimensions")
    parser.add_argument("--overwrite", action="store_true", help="Replace this helper's generated PNG/metadata files")
    args = parser.parse_args()
    args.selection = None
    if args.backend == "sam2":
        if not args.selection_file or len(args.inputs) != 1:
            parser.error("SAM 2 requires exactly one input and --selection-file; use make.py --subjects for a batch")
        try:
            args.selection = load_selection(args.selection_file)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    elif args.selection_file:
        parser.error("--selection-file requires explicit --backend sam2; other models cannot consume object prompts")
    if args.refine == "vitmatte" and args.backend != "sam2":
        parser.error("--refine vitmatte requires SAM 2 object masks")
    if args.instances != "all" and args.backend != "vision":
        parser.error("--instances is specific to explicit --backend vision")
    if args.allow_model_download and args.backend != "rembg":
        parser.error("--allow-model-download requires explicit --backend rembg")
    if args.backend == "chroma" and args.key_color is None:
        parser.error("--backend chroma requires --key-color")
    if args.backend != "chroma" and args.key_color is not None:
        parser.error("--key-color requires explicit --backend chroma")
    if args.padding < 0 or args.padding > 4096 or args.tolerance < 0 or args.feather < 0:
        parser.error("padding must be 0–4096; tolerance and feather must be nonnegative")
    if not re.fullmatch(r"all|[1-9]\d*(,[1-9]\d*)*", args.instances):
        parser.error("--instances must be all or comma-separated positive IDs")
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "cutouts.json"
    existing = []
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))["assets"]
        except (ValueError, KeyError, TypeError) as exc:
            parser.error(f"Existing manifest is invalid: {manifest_path}: {exc}")
    records, errors = [], []
    for source in args.inputs:
        try:
            records.append(process(source, args, output_dir))
        except Exception as exc:
            errors.append({"source_file": str(source), "error": str(exc)})
    if records:
        merged = {r["file"]: r for r in existing}
        merged.update({r["file"]: r for r in records})
        manifest = {"schema_version": 1, "assets": list(merged.values())}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": not errors, "manifest": str(manifest_path) if manifest_path.exists() else None,
                      "assets": records, "errors": errors}, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
