#!/usr/bin/env python3
"""Download one pinned ViTMatte model into the user's cache. Never installs Python packages.

By default reuse the isolated Python configured by setup_birefnet.py. --python
can select another existing virtual environment with the required imports.
No images are uploaded. Inference is a separate, offline command.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import urllib.request

from vitmatte_backend import (MODEL_ID, MODEL_REVISION, MODEL_LICENSE, MODEL_SOURCE,
    MODEL_FILES, TRIMAP_SOURCE, TRIMAP_MIT_NOTICE, cache_root, runtime_config_path,
    sha256, dependency_probe, runtime_ready)


def verified_download(url, target, size, checksum):
    if target.is_file() and target.stat().st_size == size and sha256(target) == checksum:
        return {"file":target.name,"bytes":size,"sha256":checksum,"url":url,"reused":True}
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary = target.with_name(target.name+".part")
    request = urllib.request.Request(url,headers={"User-Agent":"collage-film-local-setup"})
    with urllib.request.urlopen(request,timeout=120) as response, temporary.open("wb") as sink:
        for chunk in iter(lambda:response.read(4*1024*1024),b""): sink.write(chunk)
    if temporary.stat().st_size != size or sha256(temporary) != checksum:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("Pinned download checksum failed: "+target.name)
    os.replace(temporary,target)
    return {"file":target.name,"bytes":size,"sha256":checksum,"url":url,"reused":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python",type=Path,help="Existing isolated Python; no packages are installed")
    parser.add_argument("--cache-root",type=Path,help="Override COLLAGE_FILM_CACHE; use the same override for inference")
    args = parser.parse_args()
    if args.cache_root: os.environ["COLLAGE_FILM_CACHE"] = str(args.cache_root.expanduser().resolve())
    setup_birefnet = [sys.executable,str(Path(__file__).with_name("setup_birefnet.py"))]
    if args.python:
        python = args.python.expanduser().absolute()
    else:
        try:
            config = json.loads((cache_root()/"birefnet/runtime.json").read_text(encoding="utf-8"))
            python = Path(config["python"]).expanduser().absolute()
        except (OSError,ValueError,KeyError):
            raise RuntimeError("No configured isolated Python. Run " + " ".join(setup_birefnet) + " first, or pass --python /path/to/venv/bin/python")
    if not python.is_file(): raise RuntimeError("Selected Python does not exist: "+str(python))
    try: probe = dependency_probe(python)
    except Exception as exc:
        raise RuntimeError(str(exc)+". Run "+" ".join(setup_birefnet)+" or use --python with a compatible isolated environment")
    if not probe["isolated"]: raise RuntimeError("--python must point to an isolated virtual environment; no global installs are performed")
    model_dir = cache_root()/"vitmatte/models"/MODEL_REVISION
    files = []
    for name,(size,checksum) in MODEL_FILES.items():
        url = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}/{name}"
        item = verified_download(url,model_dir/name,size,checksum);files.append(item)
        print(json.dumps({"verified":name,"bytes":size,"reused":item["reused"]}),file=sys.stderr,flush=True)
    config = {"schema_version":1,"created_at":datetime.now(timezone.utc).isoformat(),
              "python":str(python),"model_dir":str(model_dir),"model":MODEL_ID,"model_revision":MODEL_REVISION,
              "license":MODEL_LICENSE,"source":MODEL_SOURCE,"files":files,"runtime":probe,
              "trimap_source":TRIMAP_SOURCE,"trimap_license":"MIT",
              "photos_uploaded":False,"dependencies_modified":False,"inference_network_access":False}
    path = runtime_config_path();path.parent.mkdir(parents=True,exist_ok=True)
    path.with_name("Matte-Anything-LICENSE.txt").write_text(TRIMAP_MIT_NOTICE,encoding="utf-8")
    temporary = path.with_suffix(".json.part")
    temporary.write_text(json.dumps(config,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(temporary,path)
    status = runtime_ready()
    if not status["ready"]: raise RuntimeError("Post-setup verification failed: "+status.get("reason","unknown"))
    print(json.dumps(status,ensure_ascii=False,indent=2));return 0


if __name__ == "__main__":
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
