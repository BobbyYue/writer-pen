"""Pin exact local code and method resources without migrating old acceptance."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
INCLUDED = {"scripts", "config", "references", "assets", "agents"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def files(root):
    result = {}
    for path in sorted(Path(root).rglob("*")):
        name = path.relative_to(root)
        if "__pycache__" in name.parts or path.suffix == ".pyc":
            continue
        if name.parts[0] not in INCLUDED and str(name) != "SKILL.md":
            continue
        if path.is_symlink():
            raise ValueError("Runtime source cannot contain symbolic links: " + str(name))
        if path.is_file():
            result[str(name)] = {"sha256": digest(path), "bytes": path.stat().st_size}
    return result


def pin(task_dir, skill_root=None):
    source = Path(skill_root or ROOT).resolve()
    before = files(source)
    if "scripts/writer.py" not in before or "config/package.json" not in before:
        raise ValueError("The source is not a complete versioned writer-pen package")
    target = Path(task_dir) / "_runtime"
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    root = target / "writer-pen"
    root.mkdir(mode=0o700)
    for name in before:
        path = root / name
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.copy2(source / name, path)
    if before != files(source) or before != files(root):
        raise ValueError("Runtime source changed while pinning; do not use this partial task")
    package = json.loads((root / "config/package.json").read_text(encoding="utf-8"))
    manifest = {"format_version": 1, "package": package,
                "created_at": datetime.now(timezone.utc).isoformat(), "files": before}
    path = target / "manifest.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    path.chmod(0o600)
    return {"root": str(root.resolve()), "manifest": str(path.resolve()),
            "manifest_sha256": digest(path), "package_version": package["version"]}


def verify(value):
    root = Path(value["root"])
    manifest = Path(value.get("manifest", root.parent / "manifest.json"))
    if root.is_symlink() or not root.is_dir() or manifest.is_symlink():
        raise ValueError("Pinned runtime is missing or unsafe")
    if manifest.resolve() != (root.parent / "manifest.json").resolve():
        raise ValueError("Runtime manifest does not belong to this snapshot")
    if digest(manifest) != value["manifest_sha256"]:
        raise ValueError("Pinned runtime manifest changed")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("format_version") != 1 or data.get("files") != files(root):
        raise ValueError("Pinned runtime files changed; do not reuse acceptance")
    return root.resolve()


def compatibility(run):
    """Inspect legacy bindings without importing code or relabeling old reviews."""
    path = Path(run) / "lifecycle.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    implementation = state.get("implementation", {})
    config = implementation.get("config", {})
    engine_matches = implementation.get("engine") == digest(ROOT / "scripts/writing_lifecycle.py")
    config_path = Path(config.get("path", "/missing-writer-config"))
    config_matches = (config_path.is_file() and config.get("sha256") == digest(config_path)
                      and config_path.resolve() == (ROOT / "config/writing-quality.json").resolve())
    return {"status": "compatible-local-bindings" if engine_matches and config_matches else "original-runtime-required",
            "engine_matches": engine_matches, "config_matches": config_matches,
            "recorded_rounds": len(state.get("rounds", [])), "mutated": False,
            "next": "Use the original runtime and registry for legacy tasks; never reset rounds or rehash old judgments to migrate.",
            "boundary": "Compatibility preflight only, not checked delivery or a full provenance validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-legacy", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compatibility(args.check_legacy)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
