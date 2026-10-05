#!/usr/bin/env python3
"""Explicit one-time installation of a pinned native SAM 2.1 backend."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ENGINE_COMMIT = "416186c501d060df7ca02989d49b38080f5f81f3"
GGML_COMMIT = "331b9cba52b23d895bc4ad218c007eb5e667540f"
ENGINE_ARCHIVE_SHA256 = "97a9ca1a97ab7a71519f2465c55ab7d0b2abcfa1bb27c1470ceb13d40ccc8380"
GGML_ARCHIVE_SHA256 = "ba76a5e9517e9863e50a08be3c0f9ced15772cd73229eff8774f495a2aa14cd9"
MODEL_REVISION = "a3892b63b918e872671322e116982a8910f0ffb7"
MODEL_NAME = "sam2.1_hiera_tiny_f16.ggml"
MODEL_SHA256 = "98ea059bb39bcf42a3109ee14ab3d25650adb737e896362716e2737d7833ae95"
MODEL_URL = f"https://huggingface.co/PABannier/sam3.cpp/resolve/{MODEL_REVISION}/{MODEL_NAME}"
ENGINE_LICENSE = "MIT"
MODEL_LICENSE = "Apache-2.0 (original SAM 2.1 weights; GGML conversion by PABannier)"
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "sam2_native"


def default_cache():
    shared = Path(os.environ.get("COLLAGE_FILM_CACHE", "~/.cache/collage-film")).expanduser()
    return Path(os.environ.get("COLLAGE_SAM2_CACHE", str(shared / "sam2"))).expanduser().resolve()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wrapper_hash():
    h = hashlib.sha256()
    for name in ("CMakeLists.txt", "main.cpp"):
        h.update(name.encode())
        h.update((TEMPLATE / name).read_bytes())
    return h.hexdigest()


def doctor(cache):
    cache = Path(cache).expanduser().resolve()
    reasons = []
    try:
        manifest = json.loads((cache / "manifest.json").read_text())
        if not isinstance(manifest, dict):
            raise ValueError("Manifest is not an object")
    except (OSError, ValueError):
        manifest = {}
        reasons.append("missing_or_invalid_manifest")
    binary = cache / "build" / "collage-sam2"
    model = cache / "models" / MODEL_NAME
    for key, expected in (("engine_commit", ENGINE_COMMIT), ("ggml_commit", GGML_COMMIT),
                          ("model_sha256", MODEL_SHA256), ("wrapper_sha256", wrapper_hash())):
        if manifest.get(key) != expected:
            reasons.append("mismatch_" + key)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        reasons.append("missing_executable")
    elif sha256(binary) != manifest.get("binary_sha256"):
        reasons.append("binary_hash_mismatch")
    else:
        try:
            probe = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=10)
            if probe.returncode != 0 or probe.stdout.strip() != "collage-sam2-protocol-1":
                reasons.append("executable_protocol_mismatch")
        except (OSError, subprocess.SubprocessError):
            reasons.append("executable_unusable_on_this_host")
    if not model.is_file():
        reasons.append("missing_model")
    elif sha256(model) != MODEL_SHA256:
        reasons.append("model_hash_mismatch")
    if importlib.util.find_spec("PIL") is None:
        reasons.append("pillow_missing_in_current_python")
    return {"ready": not reasons, "cache": str(cache), "reasons": reasons,
            "engine": "sam3.cpp / SAM 2.1 Tiny F16", "engine_commit": ENGINE_COMMIT,
            "ggml_commit": GGML_COMMIT, "model_sha256": MODEL_SHA256,
            "engine_license": ENGINE_LICENSE, "model_license": MODEL_LICENSE,
            "setup_command": f'python3 "{Path(__file__).resolve()}"',
            "binary": str(binary), "model": str(model)}


def run(args, cwd=None):
    subprocess.run([str(x) for x in args], cwd=cwd, check=True, stdout=sys.stderr)


def download(url, output, expected=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    print(f"Downloading {url}", file=sys.stderr)
    try:
        with urllib.request.urlopen(url, timeout=90) as response, partial.open("wb") as f:
            shutil.copyfileobj(response, f, length=4 * 1024 * 1024)
        if expected and sha256(partial) != expected:
            raise ValueError("Downloaded file SHA256 differs from pinned release")
        partial.replace(output)
    finally:
        partial.unlink(missing_ok=True)


def extract_archive(archive, output):
    # Source archives contain code only. Reject traversal, links, and special files.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            parts = Path(member.name).parts[1:]
            if not parts:
                continue
            if any(p in ("..", "") for p in parts) or Path(*parts).is_absolute():
                raise ValueError("Unsafe source archive path")
            target = output.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            else:
                raise ValueError("Source archive contains unsupported link or special file")


def prepare_source(cache, local_source=None):
    source = cache / "source"
    stamp = source / ".collage-source.json"
    expected = {"engine_commit": ENGINE_COMMIT, "ggml_commit": GGML_COMMIT}
    if stamp.is_file() and json.loads(stamp.read_text()) == expected:
        return source
    if source.exists():
        raise ValueError(f"Unrecognized source directory: {source}; use a fresh --cache directory")
    with tempfile.TemporaryDirectory(prefix="sam2-source-", dir=cache) as tmp:
        staged = Path(tmp) / "source"
        if local_source:
            local_source = Path(local_source).expanduser().resolve()
            for directory, revision in ((local_source, ENGINE_COMMIT), (local_source / "ggml", GGML_COMMIT)):
                actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
                dirty = subprocess.check_output(["git", "-C", str(directory), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
                if actual != revision or dirty:
                    raise ValueError(f"Local source must be clean and pinned to {revision}")
            shutil.copytree(local_source, staged, ignore=shutil.ignore_patterns(".git", "build", "__pycache__"))
        else:
            archive = Path(tmp) / "source.tar.gz"
            download(f"https://codeload.github.com/PABannier/sam3.cpp/tar.gz/{ENGINE_COMMIT}", archive, ENGINE_ARCHIVE_SHA256)
            extract_archive(archive, staged)
            download(f"https://codeload.github.com/PABannier/ggml/tar.gz/{GGML_COMMIT}", archive, GGML_ARCHIVE_SHA256)
            extract_archive(archive, staged / "ggml")
        (staged / ".collage-source.json").write_text(json.dumps(expected, indent=2) + "\n")
        staged.rename(source)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=default_cache())
    parser.add_argument("--doctor", action="store_true", help="Inspect readiness, no downloads; exit 0 even when not ready")
    parser.add_argument("--source-dir", type=Path, help="Reuse a clean, pinned Git checkout instead of downloading source")
    parser.add_argument("--model-file", type=Path, help="Reuse an existing exact-hash model instead of downloading it")
    args = parser.parse_args()
    cache = args.cache.expanduser().resolve()
    if args.doctor:
        print(json.dumps(doctor(cache), ensure_ascii=False))
        return
    cache.mkdir(parents=True, exist_ok=True)
    source = prepare_source(cache, args.source_dir)
    model = cache / "models" / MODEL_NAME
    if not model.is_file() or sha256(model) != MODEL_SHA256:
        model.parent.mkdir(parents=True, exist_ok=True)
        if args.model_file:
            if sha256(args.model_file) != MODEL_SHA256:
                raise ValueError("--model-file has the wrong SHA256")
            shutil.copy2(args.model_file, model)
        else:
            download(MODEL_URL, model, MODEL_SHA256)
    # Build tools live in this cache; no global Python or package configuration changes.
    venv = cache / "build-tools"
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    cmake = venv / ("Scripts/cmake.exe" if os.name == "nt" else "bin/cmake")
    ninja = venv / ("Scripts/ninja.exe" if os.name == "nt" else "bin/ninja")
    if not cmake.is_file() or not ninja.is_file():
        run([sys.executable, "-m", "venv", venv])
        run([python, "-m", "pip", "install", "cmake==4.4.4", "ninja==1.13.2"])
    build = cache / "build"
    run([cmake, "-S", TEMPLATE, "-B", build, "-G", "Ninja",
         f"-DCMAKE_MAKE_PROGRAM={ninja}", f"-DSAM3_SOURCE_DIR={source}",
         "-DCMAKE_BUILD_TYPE=Release"])
    run([cmake, "--build", build, "--target", "collage-sam2", "-j", "4"])
    binary = build / "collage-sam2"
    manifest = {"engine_commit": ENGINE_COMMIT, "ggml_commit": GGML_COMMIT,
                "model_revision": MODEL_REVISION, "model_url": MODEL_URL,
                "model_sha256": MODEL_SHA256, "wrapper_sha256": wrapper_hash(),
                "binary_sha256": sha256(binary), "engine_license": ENGINE_LICENSE,
                "model_license": MODEL_LICENSE, "platform": platform.platform(),
                "engine_license_url": f"https://github.com/PABannier/sam3.cpp/blob/{ENGINE_COMMIT}/LICENSE",
                "model_license_url": "https://github.com/facebookresearch/sam2/blob/main/LICENSE"}
    (cache / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(doctor(cache), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
