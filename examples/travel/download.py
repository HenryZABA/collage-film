#!/usr/bin/env python3
"""Download the eight credited demo photos. Existing matching files are reused."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
ledger = json.loads(Path(__file__).with_name("sources.json").read_text())
for photo in ledger["photos"]:
    target = args.output / (photo["name"] + ".jpg")
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != photo["sha256"]:
            raise SystemExit("Existing photo differs; choose a fresh directory: " + str(target))
        print("reused " + photo["name"])
        continue
    request = urllib.request.Request(photo["image_url"], headers={"User-Agent": "collage-film-demo"})
    data = urllib.request.urlopen(request, timeout=90).read()
    if hashlib.sha256(data).hexdigest() != photo["sha256"]:
        raise SystemExit("Photo revision changed; verify source before using: " + photo["page"])
    with target.open("xb") as stream:
        stream.write(data)
    print("downloaded " + photo["name"])
