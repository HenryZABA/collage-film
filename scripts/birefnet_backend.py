#!/usr/bin/env python3
"""Offline, pinned BiRefNet mask inference. Only the alpha channel is changed.

The public wrapper and --doctor require only the Python standard library.
Heavy inference runs in the isolated environment registered by setup_birefnet.py.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MODEL_ID = "ZhengPeng7/BiRefNet"
MODEL_REVISION = "e2bf8e4460fc8fa32bba5ea4d94b3233d367b0e4"
MODEL_LICENSE = "MIT"
MODEL_SOURCE = "https://huggingface.co/ZhengPeng7/BiRefNet"
LICENSE_SOURCE = "https://raw.githubusercontent.com/ZhengPeng7/BiRefNet/ebcc0bc8ec7fe919cec829f2dea656b3078acddc/LICENSE"
# Pin both executable architecture code and data. Remote code is read only
# from these verified local files during inference; no hub access is permitted.
MODEL_FILES = {
    "model.safetensors": (444473596, "9ab37426bf4de0567af6b5d21b16151357149139362e6e8992021b8ce356a154"),
    "birefnet.py": (91896, "208771ae626f653d64128fbf2d6ac9f8e645c5cc5e286258a73ec3322bbfe5ef"),
    "BiRefNet_config.py": (298, "e7b8c2a74f6cea6a59553d517f71d47f2c1d90e670a13416af17c25fe2f3dc52"),
    "config.json": (405, "c97ea21569daf66b205491a4635147dd3bc42c7c168b89d7d75b53f67ef548ae"),
    "README.md": (9965, "ceac4a1bb69b807eac5510bff80ff5599f606ef7458bee3b54b68d866e868532"),
    "LICENSE": (1066, "92a7089e0915fc32bc40067560b398f1e6a7a5958abd7d04eda393629a5acefb"),
}
DEPENDENCIES = {
    "torch": "2.8.0", "torchvision": "0.23.0", "numpy": "1.26.4",
    "pillow": "11.3.0", "transformers": "4.57.1", "timm": "1.0.20",
    "kornia": "0.8.1", "kornia_rs": "0.2.0", "einops": "0.8.1",
    "safetensors": "0.6.2", "accelerate": "1.10.1",
    "huggingface_hub": "0.36.2", "tokenizers": "0.22.2",
    "opencv-python": "4.11.0.86", "requests": "2.32.5", "psutil": "7.2.2",
}


def cache_root() -> Path:
    return Path(os.environ.get("COLLAGE_FILM_CACHE", str(Path.home()/".cache/collage-film"))).expanduser().resolve()


def runtime_config_path() -> Path:
    return cache_root()/"birefnet/runtime.json"


def sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(4*1024*1024),b""):
            digest.update(part)
    return digest.hexdigest()


def offline_environment() -> dict:
    env=os.environ.copy()
    env.update({"HF_HUB_OFFLINE":"1", "TRANSFORMERS_OFFLINE":"1",
                "HF_HUB_DISABLE_IMPLICIT_TOKEN":"1", "HF_HUB_DISABLE_TELEMETRY":"1",
                "HF_HOME":str(cache_root()/"hf-runtime"),
                "PYTORCH_ENABLE_MPS_FALLBACK":"1"})
    return env


def inspect_model(path: Path, full_hash: bool=True) -> list[str]:
    errors=[]
    for name,(size,checksum) in MODEL_FILES.items():
        file=path/name
        if not file.is_file(): errors.append("missing "+name)
        elif file.stat().st_size!=size: errors.append("wrong size "+name)
        elif (full_hash or name!="model.safetensors") and sha256(file)!=checksum:
            errors.append("hash mismatch "+name)
    return errors


def dependency_probe(python: Path) -> dict:
    program="""import json,sys
from importlib.metadata import version,PackageNotFoundError
keys=json.loads(sys.argv[1]); versions={}
for key in keys:
 try: versions[key]=version(key)
 except PackageNotFoundError: versions[key]=None
result={'python':sys.executable,'python_version':sys.version.split()[0],'isolated':sys.prefix!=sys.base_prefix,'versions':versions}
try:
 import torch
 result['mps_available']=torch.backends.mps.is_available()
 result['torch_importable']=True
except Exception as exc:result['torch_importable']=False;result['import_error']=str(exc)
print(json.dumps(result))
"""
    result=subprocess.run([str(python),"-c",program,json.dumps(list(DEPENDENCIES))],capture_output=True,text=True,env=offline_environment(),timeout=45)
    if result.returncode: raise RuntimeError("Runtime probe failed: "+result.stderr[-2000:])
    return json.loads(result.stdout)


def version_matches(actual: str, expected: str) -> bool:
    # Official CPU wheels append a local build suffix, e.g. 2.8.0+cpu.
    return bool(actual) and actual.split("+",1)[0]==expected


def runtime_ready() -> dict:
    """Readiness object suitable for auto-backend selection; does not install."""
    report={"ready":False,"model":MODEL_ID,"revision":MODEL_REVISION,
            "license":MODEL_LICENSE,"source":MODEL_SOURCE,
            "runtime_config":str(runtime_config_path()),
            "setup_command":[sys.executable,str(Path(__file__).with_name("setup_birefnet.py"))]}
    try:
        config=json.loads(runtime_config_path().read_text(encoding="utf-8"))
        if config.get("model_revision")!=MODEL_REVISION:
            raise RuntimeError("Runtime is configured for a different pinned model revision")
        python=Path(config["python"]);model=Path(config["model_dir"])
        if not python.is_file():raise RuntimeError("Configured isolated Python is unavailable")
        problems=inspect_model(model)
        if problems:raise RuntimeError("; ".join(problems))
        probe=dependency_probe(python)
        if not probe.get("isolated"):raise RuntimeError("Configured Python is not an isolated virtual environment")
        if not probe.get("torch_importable"):raise RuntimeError(probe.get("import_error","PyTorch cannot be imported"))
        mismatch={key:{"expected":want,"actual":probe["versions"].get(key)} for key,want in DEPENDENCIES.items() if not version_matches(probe["versions"].get(key),want)}
        if mismatch:raise RuntimeError("Dependency versions differ: "+json.dumps(mismatch))
        report.update({"ready":True,"python":str(python),"model_dir":str(model),"model_bytes":MODEL_FILES["model.safetensors"][0],"model_sha256":MODEL_FILES["model.safetensors"][1],"runtime":probe,"offline_inference":True})
    except Exception as exc:
        report["reason"]=str(exc)
    return report


def run_cutout(input_path, output_path, device="auto", overwrite=False) -> dict:
    """Invoke the configured runtime; never downloads or changes the input."""
    ready=runtime_ready()
    if not ready["ready"]:
        raise RuntimeError(ready.get("reason","BiRefNet unavailable")+". Run setup explicitly: "+" ".join(ready["setup_command"]))
    command=[ready["python"],str(Path(__file__).resolve()),"--worker","--input",str(Path(input_path).expanduser().resolve()),"--output",str(Path(output_path).expanduser().resolve()),"--device",device]
    if overwrite:command.append("--overwrite")
    result=subprocess.run(command,capture_output=True,text=True,env=offline_environment(),timeout=300)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-3000:] or result.stdout.strip()[-3000:] or "BiRefNet worker failed")
    return json.loads(result.stdout)


def worker(input_path: Path, output_path: Path, device: str, overwrite: bool) -> dict:
    # Heavy imports happen only in the configured venv process.
    os.environ.update({key:value for key,value in offline_environment().items() if key.startswith(("HF_","TRANSFORMERS_","PYTORCH_"))})
    import numpy as np
    from PIL import Image,ImageOps
    import torch
    from torchvision import transforms
    from transformers import AutoModelForImageSegmentation
    source=input_path.expanduser().resolve(strict=True);output=output_path.expanduser().resolve()
    if source==output:raise RuntimeError("Refusing to overwrite the source image")
    if output.exists() and not overwrite:raise RuntimeError("Output already exists; use a fresh filename or --overwrite")
    config=json.loads(runtime_config_path().read_text(encoding="utf-8"));model_dir=Path(config["model_dir"])
    # The wrapper verifies the large weight; worker also verifies executable code
    # before trusting the offline architecture module.
    problems=inspect_model(model_dir,full_hash=False)
    if problems:raise RuntimeError("; ".join(problems))
    if device=="auto":device="mps" if torch.backends.mps.is_available() else "cpu"
    if device=="mps" and not torch.backends.mps.is_available():raise RuntimeError("MPS is unavailable; choose --device cpu")
    torch.set_num_threads(4)
    started=time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        model=AutoModelForImageSegmentation.from_pretrained(str(model_dir),trust_remote_code=True,local_files_only=True,dtype=torch.float32)
        model.eval().to(device)
    if device=="mps":torch.mps.synchronize()
    load_seconds=time.monotonic()-started
    with Image.open(source) as opened:image=ImageOps.exif_transpose(opened).convert("RGB")
    if image.width*image.height>48_000_000:raise RuntimeError("Input exceeds 48 megapixels; downsample explicitly first")
    transform=transforms.Compose([transforms.Resize((1024,1024)),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    infer_start=time.monotonic()
    batch=transform(image).unsqueeze(0).to(device)
    with torch.inference_mode():prediction=model(batch)[-1].sigmoid().cpu()[0].squeeze()
    if not torch.isfinite(prediction).all():raise RuntimeError("Model produced non-finite alpha values")
    alpha=transforms.ToPILImage()(prediction).resize(image.size,Image.Resampling.BILINEAR)
    inference_seconds=time.monotonic()-infer_start
    lo,hi=alpha.getextrema()
    if hi<=16 or lo==255:raise RuntimeError("Model produced an empty or entirely opaque mask; visual selection is required")
    result=image.copy();result.putalpha(alpha)
    exact=np.array_equal(np.asarray(result)[:,:,:3],np.asarray(image))
    if not exact:raise RuntimeError("RGB preservation invariant failed")
    output.parent.mkdir(parents=True,exist_ok=True);result.save(output,format="PNG")
    return {"ok":True,"backend":"birefnet","model":MODEL_ID,"revision":MODEL_REVISION,"source":MODEL_SOURCE,"license":MODEL_LICENSE,"device":device,"model_input_size":[1024,1024],"model_load_seconds":round(load_seconds,3),"inference_seconds":round(inference_seconds,3),"output":str(output),"source_size":list(image.size),"source_sha256":sha256(source),"output_sha256":sha256(output),"source_rgb_exactly_preserved":exact,"mask_only":True,"visual_review_required":True,"offline_inference":True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--doctor",action="store_true",help="Report readiness without installing; always exits zero")
    p.add_argument("--input",type=Path)
    p.add_argument("--output",type=Path)
    p.add_argument("--device",choices=("auto","cpu","mps"),default="auto")
    p.add_argument("--overwrite",action="store_true")
    p.add_argument("--worker",action="store_true",help=argparse.SUPPRESS)
    a=p.parse_args()
    if a.doctor:print(json.dumps(runtime_ready(),ensure_ascii=False,indent=2));return 0
    if not a.input or not a.output:p.error("--input and --output are required")
    result=worker(a.input,a.output,a.device,a.overwrite) if a.worker else run_cutout(a.input,a.output,a.device,a.overwrite)
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
