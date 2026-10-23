"""Build source-bound literary guidance without task data, writes or network calls.

Call method_packet(role) when constructing each lifecycle packet, before its
outer hash is recorded. Author and professional use identical criteria; reader
receives only neutral readback questions. skill_root selects a local staged copy
for maintenance/tests; the default is this script's own skill, never an installed
fallback. Sources are read afresh on every call.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


VERSION = 1
_REVIEW = "references/literary-review.md"
_CHARACTER = "references/character-first.md"
_SHARED = "共用文学准则"
_READER = "独立读者回读"
_REACTION = "反应的程度是否有支撑"
_COVERAGE = "references/review-coverage.md"
_COVERAGE_SECTION = "专业审稿必答项"
_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _section(raw: bytes, title: str) -> str:
    """Select one ATX section, including subheadings, from maintained Markdown."""
    lines = raw.decode("utf-8").splitlines(keepends=True)
    headings = []
    fence = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence) and not stripped[len(run):].strip():
                fence = None
            continue
        if fence is None:
            match = _HEADING.fullmatch(line.rstrip("\r\n"))
            if match:
                headings.append((index, len(match[1]), match[2]))
    matches = [(index, level) for index, level, name in headings if name == title]
    if len(matches) != 1:
        raise ValueError("Literary method source requires one heading: " + title)
    start, level = matches[0]
    end = next((index for index, depth, _ in headings if index > start and depth <= level), len(lines))
    if not "".join(lines[start + 1:end]).strip():
        raise ValueError("Literary method section is empty: " + title)
    return "".join(lines[start:end])


def check_names(*, skill_root=None):
    """One maintained source drives dispatch, schema, templates and validation."""
    root = (Path(skill_root) if skill_root is not None else Path(__file__).resolve().parents[1]).resolve()
    path = (root / _COVERAGE).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Review coverage source escapes skill root')
    section = _section(path.read_bytes(), _COVERAGE_SECTION)
    names = re.findall(r'^### ([a-z][a-z_]+)[ \t]*$', section, re.MULTILINE)
    headings = re.findall(r'^### (.+)$', section, re.MULTILINE)
    if not names or len(names) != len(set(names)) or len(names) != len(headings):
        raise ValueError('Review coverage requires unique machine-readable check headings')
    for name in names:
        _section(section.encode('utf-8'), name)
    return tuple(names)


def method_packet(role: str = "professional", *, skill_root=None) -> dict:
    """Return JSON-ready version, role, sources, guidance and canonical sha256.

    Each source records its root-relative path, exact file-byte sha256, selected
    heading anchor and exact UTF-8 section sha256 (including trailing newlines).
    The packet sha256 covers canonical JSON of all other fields: UTF-8,
    ensure_ascii=False, sort_keys=True, separators=(',', ':'). VERSION describes
    the packet format; source changes are identified by hashes, not a manual bump.
    Missing/ambiguous sources raise rather than silently omitting criteria.
    """
    if not isinstance(role, str) or role not in {"author", "professional", "reader"}:
        raise ValueError("Unknown literary method role: " + repr(role))
    root = (Path(skill_root) if skill_root is not None else Path(__file__).resolve().parents[1]).resolve()
    routes = [(_REVIEW, _READER)] if role == "reader" else [(_REVIEW, _SHARED), (_CHARACTER, _REACTION), (_COVERAGE, _COVERAGE_SECTION)]
    if role != 'reader':
        check_names(skill_root=root)
    sources, excerpts = [], []
    for relative, heading in routes:
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Literary method source escapes skill root: " + relative)
        raw = path.read_bytes()
        section = _section(raw, heading)
        sources.append({"path": relative, "sha256": _sha(raw), "anchor": heading,
                        "section_sha256": _sha(section.encode("utf-8"))})
        excerpts.append(section.strip())
    packet = {"version": VERSION, "role": role, "sources": sources,
              "guidance": "\n\n".join(excerpts)}
    packet["sha256"] = _sha(json.dumps(packet, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8"))
    return packet
