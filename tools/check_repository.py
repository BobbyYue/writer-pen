#!/usr/bin/env python3
"""Check public packaging without loading private writing records."""
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", "node_modules", ".venv"}
EXAMPLE = ROOT / "examples/zhou-yi-jian"


def main():
    errors = []
    required = ["SKILL.md", "README.md", "LICENSE", "VERSION", "CHANGELOG.md",
                "agents/openai.yaml", "config/package.json", ".github/workflows/tests.yml",
                "examples/zhou-yi-jian/prompt.txt", "examples/zhou-yi-jian/rewrite-prompt.txt",
                "examples/zhou-yi-jian/story.txt", "examples/zhou-yi-jian/story.html",
                "examples/zhou-yi-jian/README.md", "docs/known-limitations.md"]
    for name in required:
        if not (ROOT / name).is_file():
            errors.append("Missing public file: " + name)
    paths = [path for path in ROOT.rglob("*")
             if path.is_file() and not SKIP.intersection(path.relative_to(ROOT).parts)]
    private_path = re.compile(r"/(?:Users|home)/[^/\s]+/|/(?:private)/var/|(?:bytedance\.)?(?:sg\.)?larkoffice\.com|ida\.tiktok-row\.net", re.I)
    credential = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{24,})")
    for path in paths:
        name = str(path.relative_to(ROOT))
        if path.is_symlink():
            errors.append("Symlink in public package: " + name)
        if path.suffix in {".sqlite3", ".pyc"} or {"private", "writing-records", "_runtime"}.intersection(path.relative_to(ROOT).parts):
            errors.append("Private/generated file in public package: " + name)
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append("Unexpected binary file in text-only package: " + name)
            continue
        if private_path.search(text) or credential.search(text):
            errors.append("Review private path, internal URL or credential: " + name)
        if path.suffix == ".md":
            for raw in re.findall(r"\]\(([^)]+)\)", text):
                target = raw.strip().strip("<>").split("#", 1)[0]
                if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                    continue
                resolved = (path.parent / target).resolve()
                if ROOT not in resolved.parents or not resolved.exists():
                    errors.append("Broken local link: " + name + " -> " + target)
    if all((ROOT / name).is_file() for name in required):
        version = (ROOT / "VERSION").read_text().strip()
        package = json.loads((ROOT / "config/package.json").read_text())
        if version != package["version"]:
            errors.append("VERSION differs from config/package.json")
        readme = (ROOT / "README.md").read_text()
        prompt = (EXAMPLE / "prompt.txt").read_text().strip()
        story = (EXAMPLE / "story.txt").read_text().strip()
        title, body = story.split("\n\n", 1)
        expected = {"prompt": "```text\n" + prompt + "\n```", "story": "### " + title + "\n\n" + body}
        for kind, value in expected.items():
            start, end = "<!-- example:" + kind + ":start -->", "<!-- example:" + kind + ":end -->"
            if readme.count(start) != 1 or readme.count(end) != 1 or readme.split(start)[-1].split(end)[0].strip() != value:
                errors.append("README differs from the example file: " + kind)
        if sum(not char.isspace() for char in story) > 1000:
            errors.append("Example exceeds the requested character limit")
        if "整理" not in (EXAMPLE / "rewrite-prompt.txt").read_text():
            errors.append("Reusable prompt must disclose reconstruction from multiple turns")
        if "尚未完成终稿验收" not in (EXAMPLE / "story.html").read_text():
            errors.append("Example HTML lost its actual incomplete-acceptance notice")
    print(json.dumps({"status": "fail" if errors else "pass", "files": len(paths), "errors": errors}, ensure_ascii=False))
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
