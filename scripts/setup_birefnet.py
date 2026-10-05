#!/usr/bin/env python3
"""Explicit one-time BiRefNet setup into the user's cache, never global Python.

Downloads ~445 MB of pinned weights/code plus missing Python wheels. Photos are
never sent. Inference is a separate offline command after setup succeeds.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import urllib.request

from birefnet_backend import (MODEL_ID,MODEL_REVISION,MODEL_LICENSE,MODEL_SOURCE,
    LICENSE_SOURCE,MODEL_FILES,DEPENDENCIES,cache_root,runtime_config_path,sha256,
    dependency_probe,runtime_ready,version_matches)


def verified_download(url: str, target: Path, size: int, checksum: str):
    if target.is_file() and target.stat().st_size==size and sha256(target)==checksum:
        return {"file":target.name,"bytes":size,"sha256":checksum,"reused":True,"url":url}
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_name(target.name+".part")
    request=urllib.request.Request(url,headers={"User-Agent":"collage-film-local-setup"})
    with urllib.request.urlopen(request,timeout=120) as response,temporary.open("wb") as sink:
        while True:
            part=response.read(4*1024*1024)
            if not part:break
            sink.write(part)
    if temporary.stat().st_size!=size or sha256(temporary)!=checksum:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Pinned download checksum failed: "+target.name)
    os.replace(temporary,target)
    return {"file":target.name,"bytes":size,"sha256":checksum,"reused":False,"url":url}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--python",default=sys.executable,help="Python 3.9–3.12 used to create the isolated environment; Python 3.11/3.12 recommended on new machines")
    p.add_argument("--reuse-installed-torch",action="store_true",help="Create venv with read-only system-package access to reuse compatible torch; all package installs still go into venv")
    p.add_argument("--cache-root",type=Path,help="Override COLLAGE_FILM_CACHE; use the same environment override for inference")
    p.add_argument("--venv",type=Path,help="Existing or new dedicated venv under the cache root")
    p.add_argument("--model-dir",type=Path,help="Existing model directory under the cache root")
    a=p.parse_args()
    if a.cache_root:os.environ["COLLAGE_FILM_CACHE"]=str(a.cache_root.expanduser().resolve())
    root=cache_root();base=root/"birefnet";base.mkdir(parents=True,exist_ok=True)
    # Adopt this skill's earlier benchmark cache, if present, rather than
    # silently downloading another copy of the same model or PyTorch.
    legacy_env=root/"birefnet-venv";legacy_model=root/"models/BiRefNet"/MODEL_REVISION
    venv=(a.venv.expanduser() if a.venv else legacy_env if (legacy_env/"pyvenv.cfg").exists() else base/"venv").resolve()
    model_dir=(a.model_dir.expanduser() if a.model_dir else legacy_model if (legacy_model/"model.safetensors").is_file() else base/"models"/MODEL_REVISION).resolve()
    if root not in venv.parents or root not in model_dir.parents:
        p.error("venv and model-dir must be dedicated paths inside the cache root")
    if venv.exists() and not (venv/"pyvenv.cfg").is_file():
        p.error("Refusing a non-venv directory for package installation")
    if not venv.exists():
        version=json.loads(subprocess.run([a.python,"-c","import sys,json;print(json.dumps(list(sys.version_info[:2])))"],check=True,capture_output=True,text=True).stdout)
        if not ((3,9)<=tuple(version)<(3,13)):p.error("Pinned runtime requires Python 3.9–3.12; select --python python3.12")
        command=[a.python,"-m","venv"]
        if a.reuse_installed_torch:command.append("--system-site-packages")
        subprocess.run(command+[str(venv)],check=True)
    python=venv/("Scripts/python.exe" if os.name=="nt" else "bin/python")
    probe=dependency_probe(python)
    if not probe.get("isolated"):raise RuntimeError("Refusing to install into a global Python")
    needed=[f"{name}=={version}" for name,version in DEPENDENCIES.items() if not version_matches(probe["versions"].get(name),version)]
    torch_packages=[spec for spec in needed if spec.split("==")[0] in ("torch","torchvision")]
    # This backend supports CPU and Apple MPS. On Linux/Windows fetch official
    # CPU wheels instead of implicitly pulling multi-GB CUDA dependencies.
    if torch_packages and platform.system()!="Darwin":
        subprocess.run([str(python),"-m","pip","install","--disable-pip-version-check",*torch_packages,"--index-url","https://download.pytorch.org/whl/cpu"],check=True)
        needed=[spec for spec in needed if spec not in torch_packages]
    if needed:
        subprocess.run([str(python),"-m","pip","install","--disable-pip-version-check",*needed],check=True)
    files=[]
    for name,(size,checksum) in MODEL_FILES.items():
        url=LICENSE_SOURCE if name=="LICENSE" else f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{name}"
        item=verified_download(url,model_dir/name,size,checksum);files.append(item)
        print(json.dumps({"verified":name,"bytes":size,"reused":item["reused"]}),file=sys.stderr,flush=True)
    config={"schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),"python":str(python),"model_dir":str(model_dir),"model":MODEL_ID,"model_revision":MODEL_REVISION,"license":MODEL_LICENSE,"source":MODEL_SOURCE,"dependencies":DEPENDENCIES,"files":files,"photos_uploaded":False,"inference_network_access":False}
    runtime_config_path().write_text(json.dumps(config,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    status=runtime_ready()
    if not status["ready"]:raise RuntimeError("Post-setup verification failed: "+status.get("reason","unknown"))
    print(json.dumps(status,ensure_ascii=False,indent=2));return 0


if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
