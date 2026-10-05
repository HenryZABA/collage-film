#!/usr/bin/env python3
"""Offline ViTMatte refinement of an already selected SAM mask.

This improves boundaries; it does not choose subjects or repair all interior
background mistakes. --doctor is read-only and always exits zero.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

MODEL_ID = "hustvl/vitmatte-small-composition-1k"
MODEL_REVISION = "6a58ad7646403c1df626fbd746900aec7361ea1d"
MODEL_LICENSE = "Apache-2.0"
MODEL_SOURCE = "https://huggingface.co/" + MODEL_ID
TRIMAP_SOURCE = "https://github.com/hustvl/Matte-Anything/blob/874951ac0b8d324ad9f885baf1c7de711b8dc1b0/matte_anything.py"
MODEL_FILES = {
    "model.safetensors": (103294572, "bda9289db1bb6762d978b42d1c62ae3f34daf7497171a347a1d09657efd788cb"),
    "config.json": (837, "ae1006f5a83227048b563b2e60709d4203e432b2276949ebef41a8cfeeeaf45f"),
    "preprocessor_config.json": (284, "0db558038b96a3f5c97e46d4ec8966fcc479e9aa58a391bca60b5094a5f7fee0"),
    "README.md": (1716, "5545af4bf41cc017cd1a75ff096d27ff4e6e6ea0bb41c9a272dd4072a0fefaaf"),
}

# The trimap procedure below is adapted from Matte-Anything. The model is
# loaded via transformers, not by copying Matte-Anything's application.
TRIMAP_MIT_NOTICE = """MIT License
Copyright (c) 2023 Hust Vision Lab

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def cache_root():
    return Path(os.environ.get("COLLAGE_FILM_CACHE", str(Path.home()/".cache/collage-film"))).expanduser().resolve()


def runtime_config_path():
    return cache_root()/"vitmatte/runtime.json"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b""):
            digest.update(block)
    return digest.hexdigest()


def offline_environment():
    env = os.environ.copy()
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
                "PYTORCH_ENABLE_MPS_FALLBACK": "1"})
    return env


def dependency_probe(python):
    program = """import json,sys
import torch,numpy,cv2,PIL,transformers,safetensors
from transformers import VitMatteImageProcessor,VitMatteForImageMatting
print(json.dumps({'python':sys.executable,'isolated':sys.prefix!=sys.base_prefix,
'versions':{'torch':torch.__version__,'numpy':numpy.__version__,'opencv':cv2.__version__,
'pillow':PIL.__version__,'transformers':transformers.__version__,'safetensors':safetensors.__version__},
'mps_available':torch.backends.mps.is_available()}))
"""
    result = subprocess.run([str(python), "-c", program], capture_output=True, text=True,
                            env=offline_environment(), timeout=90)
    if result.returncode:
        raise RuntimeError("ViTMatte imports unavailable in selected Python: " + result.stderr[-1600:])
    return json.loads(result.stdout)


def inspect_model(model_dir):
    errors = []
    for name, (size, checksum) in MODEL_FILES.items():
        path = Path(model_dir)/name
        if not path.is_file(): errors.append("missing " + name)
        elif path.stat().st_size != size or sha256(path) != checksum:
            errors.append("pinned checksum mismatch " + name)
    return errors


def runtime_ready():
    report = {"ready": False, "model": MODEL_ID, "revision": MODEL_REVISION,
              "license": MODEL_LICENSE, "source": MODEL_SOURCE,
              "runtime_config": str(runtime_config_path()),
              "setup_command": [sys.executable, str(Path(__file__).with_name("setup_vitmatte.py"))]}
    try:
        config = json.loads(runtime_config_path().read_text(encoding="utf-8"))
        if config.get("model_revision") != MODEL_REVISION:
            raise RuntimeError("Runtime has a different model revision; rerun setup")
        python = Path(config["python"])
        if not python.is_file(): raise RuntimeError("Configured Python is unavailable")
        errors = inspect_model(config["model_dir"])
        if errors: raise RuntimeError("; ".join(errors))
        probe = dependency_probe(python)
        if not probe["isolated"]: raise RuntimeError("Configured Python must be an isolated environment")
        report.update({"ready": True, "python": str(python), "model_dir": config["model_dir"],
                       "model_sha256": MODEL_FILES["model.safetensors"][1],
                       "runtime": probe, "offline_inference": True})
    except Exception as exc:
        report["reason"] = str(exc)
    return report


def validate_paths(input_path, mask_path, output_path):
    source = Path(input_path).expanduser().resolve(strict=True)
    mask = Path(mask_path).expanduser().resolve(strict=True)
    output = Path(output_path).expanduser().resolve()
    if output in (source, mask): raise ValueError("Output must differ from the source and mask")
    if output.exists(): raise ValueError("Output already exists; choose a fresh filename")
    if output.suffix.lower() != ".png": raise ValueError("Output must be PNG to preserve alpha")
    return source, mask, output


def validate_parameters(kernel_size, iterations):
    if kernel_size not in (3, 5) or not 1 <= iterations <= 10:
        raise ValueError("kernel_size must be 3 or 5; iterations must be from 1 to 10")


def bounded_inference_size(width, height, max_pixels=2_000_000):
    """Preserve aspect ratio while bounding attention memory on large photos."""
    if width < 1 or height < 1 or max_pixels < 1:
        raise ValueError("Image dimensions and pixel budget must be positive")
    scale = min(1.0, math.sqrt(max_pixels / (width * height)))
    return max(1, int(width * scale)), max(1, int(height * scale))


def run_refine(input_path, mask_path, output_path, device="auto", kernel_size=5, iterations=5):
    source, mask, output = validate_paths(input_path, mask_path, output_path)
    validate_parameters(kernel_size, iterations)
    if device not in ("auto", "mps", "cpu"): raise ValueError("device must be auto, mps or cpu")
    ready = runtime_ready()
    if not ready["ready"]:
        raise RuntimeError(ready.get("reason", "ViTMatte unavailable") + ". Run setup explicitly: " + " ".join(ready["setup_command"]))
    command = [ready["python"], str(Path(__file__).resolve()), "--worker", "--input", str(source),
               "--mask", str(mask), "--output", str(output), "--device", device,
               "--kernel-size", str(kernel_size), "--iterations", str(iterations)]
    process = subprocess.run(command, capture_output=True, text=True, env=offline_environment(), timeout=300)
    if process.returncode:
        raise RuntimeError(process.stderr.strip()[-3000:] or "ViTMatte worker failed")
    return json.loads(process.stdout)


def worker(input_path, mask_path, output_path, device, kernel_size, iterations):
    source, mask_path, output = validate_paths(input_path, mask_path, output_path)
    validate_parameters(kernel_size, iterations)
    os.environ.update({k:v for k,v in offline_environment().items() if k.startswith(("HF_", "TRANSFORMERS_", "PYTORCH_"))})
    import cv2
    import numpy as np
    from PIL import Image
    import torch
    from transformers import VitMatteImageProcessor, VitMatteForImageMatting

    with Image.open(source) as opened:
        if opened.getexif().get(274, 1) != 1:
            raise ValueError("Normalize EXIF orientation before inference so the mask and image align")
        if opened.mode not in ("RGB", "RGBA"):
            raise ValueError("Input must be an orientation-normalized RGB or RGBA image")
        rgb = opened.convert("RGB")
        original_alpha = opened.getchannel("A") if opened.mode == "RGBA" else None
        profile = opened.info.get("icc_profile")
    with Image.open(mask_path) as opened:
        if opened.getexif().get(274, 1) != 1 or opened.size != rgb.size:
            raise ValueError("Mask must have the exact source canvas and normalized orientation")
        if opened.mode not in ("L", "1", "RGBA"):
            raise ValueError("Mask must be an L/1 image or RGBA image with an alpha channel")
        raw = np.asarray(opened.getchannel("A") if opened.mode == "RGBA" else opened.convert("L"))
        mask = np.where(raw >= 128, 255, 0).astype(np.uint8)
    if not np.any(mask) or np.all(mask): raise ValueError("Mask is empty or entirely opaque; select a subject first")
    ys, xs = np.where(mask > 0)
    padding = 64
    bbox = (max(0, int(xs.min())-padding), max(0, int(ys.min())-padding),
            min(rgb.width, int(xs.max())+padding+1), min(rgb.height, int(ys.max())+padding+1))
    x0,y0,x1,y1 = bbox
    inference_size = bounded_inference_size(x1-x0, y1-y0)
    resized = inference_size != (x1-x0, y1-y0)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    eroded = cv2.erode(mask, kernel, iterations=iterations)
    dilated = cv2.dilate(mask, kernel, iterations=iterations)
    trimap = np.zeros_like(mask)
    trimap[dilated == 255] = 128
    trimap[eroded == 255] = 255
    config = json.loads(runtime_config_path().read_text(encoding="utf-8"))
    errors = inspect_model(config["model_dir"])
    if errors: raise RuntimeError("; ".join(errors))
    if device == "auto": device = "mps" if torch.backends.mps.is_available() else "cpu"
    if device == "mps" and not torch.backends.mps.is_available(): raise ValueError("MPS unavailable; use --device cpu")
    torch.set_num_threads(4)
    started = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        processor = VitMatteImageProcessor.from_pretrained(config["model_dir"], local_files_only=True)
        model = VitMatteForImageMatting.from_pretrained(config["model_dir"], local_files_only=True).eval().to(device)
    if device == "mps": torch.mps.synchronize()
    load_seconds = time.monotonic()-started
    crop_rgb = rgb.crop(bbox)
    crop_trimap = Image.fromarray(trimap).crop(bbox)
    if resized:
        crop_rgb = crop_rgb.resize(inference_size, Image.Resampling.LANCZOS)
        crop_trimap = crop_trimap.resize(inference_size, Image.Resampling.NEAREST)
    inputs = processor(images=crop_rgb, trimaps=crop_trimap, return_tensors="pt").to(device)
    started = time.monotonic()
    with torch.inference_mode():
        pred = model(**inputs).alphas[0,0,:inference_size[1],:inference_size[0]].detach().float().cpu().numpy()
    if not np.isfinite(pred).all(): raise RuntimeError("Model produced non-finite alpha")
    elapsed = time.monotonic()-started
    alpha = np.zeros(mask.shape, dtype=np.uint8)
    if resized:
        pred = np.asarray(Image.fromarray(pred).resize((x1-x0,y1-y0),Image.Resampling.BILINEAR))
    alpha[y0:y1,x0:x1] = np.clip(np.rint(pred*255),0,255).astype(np.uint8)
    if original_alpha is not None:
        alpha = np.rint(alpha.astype(np.float32)*np.asarray(original_alpha)/255).astype(np.uint8)
    rgba = rgb.copy(); rgba.putalpha(Image.fromarray(alpha))
    if not np.array_equal(np.asarray(rgba)[:,:,:3], np.asarray(rgb)):
        raise RuntimeError("RGB preservation invariant failed")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also prevents races from replacing existing work.
    with output.open("xb") as sink: rgba.save(sink, format="PNG", icc_profile=profile)
    return {"ok": True, "backend": "vitmatte", "model": MODEL_ID, "revision": MODEL_REVISION,
            "license": MODEL_LICENSE, "model_sha256": MODEL_FILES["model.safetensors"][1],
            "device": device, "kernel_size": kernel_size, "iterations": iterations,
            "unknown_band_radius_pixels": (kernel_size-1)//2*iterations,
            "inference_crop_xyxy": list(bbox), "context_padding": padding, "input_resize": resized,
            "model_input_size": list(inference_size),
            "model_padded_input_size": [inputs["pixel_values"].shape[-1], inputs["pixel_values"].shape[-2]],
            "inference_scale_xy": [inference_size[0]/(x1-x0), inference_size[1]/(y1-y0)],
            "model_load_seconds": round(load_seconds,3), "inference_seconds": round(elapsed,3),
            "width": rgb.width, "height": rgb.height, "full_canvas": True,
            "source_rgb_exactly_preserved": True, "rgb_preserved": True,
            "source_sha256": sha256(source), "mask_sha256": sha256(mask_path),
            "output": str(output), "output_sha256": sha256(output),
            "alpha_kind": "soft_matting", "offline_inference": True, "photos_uploaded": False,
            "visual_review_required": True,
            "warnings": ["refinement_does_not_select_subjects", "interior_background_errors_may_remain"]
                        + (["downsampled_refinement"] if resized else [])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doctor", action="store_true")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--device", choices=("auto", "mps", "cpu"), default="auto")
    parser.add_argument("--kernel-size", type=int, choices=(3,5), default=5)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.doctor:
        print(json.dumps(runtime_ready(), ensure_ascii=False, indent=2)); return 0
    if not all((args.input,args.mask,args.output)): parser.error("--input, --mask and --output are required")
    fn = worker if args.worker else run_refine
    result = fn(args.input,args.mask,args.output,args.device,args.kernel_size,args.iterations)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__":
    try: sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
