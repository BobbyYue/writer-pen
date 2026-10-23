"""Version HTML independently while retaining immutable inspection evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlparse
import uuid


def ref(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("Presentation evidence is missing: " + str(path))
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def manuscript_matches(html, value):
    from validate_html_output import ManuscriptParser
    parser = ManuscriptParser()
    parser.feed(html)
    expected = value.replace("\r\n", "\n").rstrip("\n")
    matches = []
    for index, work in enumerate(parser.works):
        body = "\n\n".join(work["paragraphs"])
        actual = work["title"] + "\n\n" + body if work["title"] else body
        if actual == expected:
            matches.append(index)
    if parser.errors or len(matches) != 1:
        raise ValueError("Presentation must contain the exact reviewed title, prose and paragraph boundaries once")
    return matches[0]


def assets(html_path):
    from validate_html_output import ArtifactParser
    path = Path(html_path).resolve()
    html = path.read_text(encoding="utf-8")
    parser = ArtifactParser()
    parser.feed(html)
    values = [value for _, value in parser.assets]
    values += re.findall(r"url\(\s*[\"']?([^\"')]+)", html)
    values += re.findall(r'@import\s+["\']([^"\']+)', html)
    result = {}
    for value in values:
        if value.startswith("#"):
            continue
        if value.startswith(("/", "//")) or urlparse(value).scheme:
            raise ValueError("Presentation resources must use portable local paths")
        clean = unquote(value.split("#", 1)[0].split("?", 1)[0])
        if not clean:
            continue
        asset = (path.parent / clean).resolve()
        if not asset.is_relative_to(path.parent):
            raise ValueError("Presentation asset escapes its directory")
        result[str(asset)] = ref(asset)
    return list(result.values())


def capture(run, layout, value, artifact_sha256, *, initial=False):
    if layout.get("status") != "inspected":
        raise ValueError("Presentation has not been inspected")
    for key in ("reason", "target", "viewport", "findings"):
        if not isinstance(layout.get(key), str) or not layout[key].strip():
            raise ValueError("Presentation requires " + key)
    supplied = layout.get("evidence_files", [])
    if not isinstance(supplied, list) or not supplied:
        raise ValueError("Presentation needs actual inspection evidence")
    paths = [Path(p).resolve() for p in supplied]
    html_path = Path(layout["html"]).resolve() if layout.get("html") else None
    if html_path is None:
        htmls = [p for p in paths if p.suffix.lower() in {".html", ".htm"}]
        if len(htmls) != 1:
            raise ValueError("Identify the exact HTML in layout.html")
        html_path = htmls[0]
    if html_path not in paths or not any(p != html_path for p in paths):
        raise ValueError("Supply the HTML and separate browser inspection evidence")
    original = ref(html_path)
    work = manuscript_matches(html_path.read_text(encoding="utf-8"), value)
    reading = layout.get('reading_observation')
    if not isinstance(reading, dict) or any(not isinstance(reading.get(k), str) or not reading[k].strip()
                                          for k in ('quote', 'observation', 'status')):
        raise ValueError('Presentation needs reading_observation with current quote, actual reading observation and status')
    if reading['quote'] not in value:
        raise ValueError('Presentation reading_observation quote is not in the current manuscript')
    if reading['status'] != 'fit':
        raise ValueError('Presentation reading_observation is unresolved; repair layout before checked delivery')
    resource_refs = assets(html_path)
    effect = "unchanged" if initial else layout.get("reading_effect")
    if effect not in {"unchanged", "changed", "uncertain"}:
        raise ValueError("Declare reading_effect: unchanged, changed or uncertain")
    reason = layout.get("reading_reason", layout["reason"] if initial else "")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Explain the presentation's reading effect")
    all_refs = {str(path): ref(path) for path in paths}
    all_refs.update({item["path"]: item for item in resource_refs})
    directory = Path(run) / "presentations" / uuid.uuid4().hex
    directory.mkdir(mode=0o700, parents=True)
    snapshots = []
    for index, item in enumerate(all_refs.values()):
        source = Path(item["path"])
        target = directory / (str(index) + source.suffix)
        shutil.copy2(source, target)
        snapshot = ref(target)
        if snapshot["sha256"] != item["sha256"] or ref(source) != item:
            raise ValueError("Presentation evidence changed during capture")
        snapshots.append({"original": item, "snapshot": snapshot})
    result = {"artifact_sha256": artifact_sha256,
              "text_sha256": hashlib.sha256(value.encode()).hexdigest(),
              "html": original, "work_index": work, "assets": resource_refs,
              "status": "inspected", "reading_effect": effect, "reading_reason": reason,
              "target": layout["target"], "viewport": layout["viewport"],
              "findings": layout["findings"], "snapshots": snapshots}
    result['reading_observation'] = reading
    path = directory / "record.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    path.chmod(0o600)
    result["record"] = ref(path)
    return result


def current(state, html_path=None):
    if not state.get("candidates"):
        return None
    candidate = state["candidates"][-1]
    records = [item for item in state.get("presentations", [])
               if item["artifact_sha256"] == candidate["artifact"]["sha256"]
               and item["text_sha256"] == candidate["text_sha256"]]
    if not records:
        return None
    item = records[-1]
    if html_path is not None and Path(html_path).resolve() != Path(item["html"]["path"]):
        raise ValueError("The delivered HTML is not the current inspected presentation")
    if item["reading_effect"] != "unchanged":
        raise ValueError("Presentation changes or may change reading; a new literary candidate and review are required")
    if ref(item["html"]["path"]) != item["html"]:
        raise ValueError("Current HTML changed after inspection")
    for asset in item["assets"]:
        if ref(asset["path"]) != asset:
            raise ValueError("Current HTML resource changed after inspection")
    manuscript_matches(Path(item["html"]["path"]).read_text(encoding="utf-8"), candidate["text"])
    for snap in item["snapshots"]:
        if ref(snap["snapshot"]["path"]) != snap["snapshot"]:
            raise ValueError("Presentation history changed")
    if ref(item["record"]["path"]) != item["record"]:
        raise ValueError("Presentation record changed")
    return item
