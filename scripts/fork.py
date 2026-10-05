#!/usr/bin/env python3
"""Fork collage-film's reusable skill files without copying private runtime data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile


# Deliberately allow only skill-owned assets. A user project is not a source
# directory: photos, outputs and credentials must never silently enter forks.
TOP_LEVEL = {"SKILL.md", "agents", "scripts", "references", "assets", "templates", "LICENSE", "LICENSE.md", "THIRD_PARTY_NOTICES.md"}
EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".cache", ".DS_Store", "outputs", "output", "renders", "inputs", "user-assets", "raw", ".env", "credentials", "secrets"}


def ignore(directory: str, names: list[str]) -> list[str]:
    return [name for name in names if name in EXCLUDED or name.startswith(".env.") or name.endswith((".pyc", ".pyo", ".log", ".mp4", ".mov", ".webm"))]


def copy_tree(source: Path, target: Path) -> None:
    # A symlink may point outside the skill to private photos or auth state.
    for child in source.rglob("*"):
        if child.is_symlink():
            raise RuntimeError(f"Refusing a symbolic link in skill assets: {child}")
    shutil.copytree(source, target, ignore=ignore)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="New lowercase skill name, e.g. travel-collage")
    parser.add_argument("--destination", required=True, type=Path, help="New skill directory; must not already exist")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1], help="Existing skill root; defaults to this skill")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.name) or len(args.name) > 63:
        parser.error("Name must use lowercase letters/digits/hyphens and be at most 63 characters")
    source = args.source.expanduser().resolve()
    target_input = args.destination.expanduser()
    if target_input.exists() or target_input.is_symlink():
        parser.error(f"Destination already exists; refusing overwrite: {target_input}")
    target = target_input.resolve()
    if source == target or source in target.parents:
        parser.error("Destination must be outside the source skill")
    if target.name != args.name:
        parser.error("Destination folder name must match --name for skill discovery")
    skill_path = source / "SKILL.md"
    if not skill_path.is_file():
        parser.error(f"No SKILL.md at source: {source}")
    if skill_path.is_symlink():
        parser.error("SKILL.md must not be a symbolic link")
    original = skill_path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", original, flags=re.S)
    if not match or not re.search(r"(?m)^name:\s*.+$", match.group(1)):
        parser.error("Source SKILL.md must have YAML frontmatter with a name")
    frontmatter = re.sub(r"(?m)^name:\s*.+$", "name: " + args.name, match.group(1), count=1)
    new_skill = "---\n" + frontmatter + "\n---\n" + original[match.end():]
    target.parent.mkdir(parents=True, exist_ok=True)
    # Stage adjacent to destination so a failed copy leaves no partial fork.
    with tempfile.TemporaryDirectory(prefix=".collage-fork-", dir=target.parent) as tmp:
        staged = Path(tmp) / args.name
        staged.mkdir()
        for child in sorted(source.iterdir()):
            if child.name not in TOP_LEVEL:
                continue
            if child.is_symlink():
                raise RuntimeError(f"Refusing symbolic link: {child}")
            if child.is_dir():
                copy_tree(child, staged / child.name)
            else:
                shutil.copy2(child, staged / child.name)
        (staged / "SKILL.md").write_text(new_skill, encoding="utf-8")
        # Replace only literal invocation tokens. Preserve source attribution,
        # dependency skill names and the reference style text.
        yaml = staged / "agents" / "openai.yaml"
        source_name = re.search(r"(?m)^name:\s*['\"]?([^\n'\"]+)", match.group(1)).group(1).strip()
        if yaml.exists():
            content = yaml.read_text(encoding="utf-8")
            content = content.replace("$" + source_name, "$" + args.name)
            yaml.write_text(content, encoding="utf-8")
        for document in staged.rglob("*.md"):
            content = document.read_text(encoding="utf-8")
            content = content.replace("$" + source_name, "$" + args.name)
            content = content.replace("~/.codex/skills/" + source_name + "/", "~/.codex/skills/" + args.name + "/")
            document.write_text(content, encoding="utf-8")
        # Exclusive directory creation protects existing destinations even when
        # another process creates one while the staged fork is being prepared.
        target.mkdir(exist_ok=False)
        try:
            for child in staged.iterdir():
                shutil.move(str(child), str(target / child.name))
        except Exception:
            shutil.rmtree(target)
            raise
    print(json.dumps({"ok": True, "name": args.name, "path": str(target),
                      "copied": sorted(p.name for p in target.iterdir()),
                      "next": "Customize this fork's assets/preset.json and invoke $" + args.name}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
