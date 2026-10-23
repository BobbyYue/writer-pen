#!/usr/bin/env python3
"""Check literary HTML portability and exact manuscript correspondence.

Adapted from Reader's Seat's static validator; see references/html-origin.json.
This is not a browser inspection or a literary-quality verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from render_html import MARKER, manuscript


VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class ArtifactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.duplicate_ids: set[str] = set()
        self.hrefs: list[str] = []
        self.assets: list[tuple[str, str]] = []
        self.tables_total = 0
        self.tables_wrapped = 0
        self.html_lang: str | None = None
        self.visible_text: list[str] = []
        self._stack: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag not in VOID_TAGS:
            self._stack.append((tag, attributes))
        if tag == "html":
            self.html_lang = attributes.get("lang") or None
        if attributes.get("id"):
            if attributes["id"] in self.ids:
                self.duplicate_ids.add(attributes["id"])
            self.ids.add(attributes["id"])
        if attributes.get("href"):
            self.hrefs.append(attributes["href"])
        for attribute in ("src", "poster"):
            if attributes.get(attribute):
                self.assets.append((tag, attributes[attribute]))
        if tag == "link" and attributes.get("href"):
            self.assets.append((tag, attributes["href"]))
        if attributes.get('srcset'):
            for item in attributes['srcset'].split(','):
                if item.strip():
                    self.assets.append((tag, item.strip().split()[0]))
        if tag == "table":
            self.tables_total += 1
            if any(
                "table-wrap" in parent_attrs.get("class", "").split()
                for _, parent_attrs in self._stack[:-1]
            ):
                self.tables_wrapped += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        excluded = {"script", "style", "noscript", "svg", "code", "pre"}
        if any(tag in excluded for tag, _ in self._stack):
            return
        self.visible_text.append(data)


def is_remote(value: str) -> bool:
    return value.startswith('//') or urlparse(value).scheme in {"http", "https"}


class ManuscriptParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.works, self.stack, self.errors = [], [], []
        self.current = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if 'data-writer-work' in attributes:
            if self.current is not None:
                self.errors.append('Nested manuscript work')
            self.current = {'title': '', 'paragraphs': []}
            self.works.append(self.current)
        if tag not in VOID_TAGS:
            self.stack.append((tag, attributes))
        if self.current is not None and self.in_role('data-writer-body'):
            if tag == 'p':
                self.current['paragraphs'].append('')
            elif tag == 'br' and self.in_paragraph():
                self.current['paragraphs'][-1] += '\n'

    def in_role(self, name):
        return any(name in attrs for _, attrs in self.stack)

    def in_paragraph(self):
        return any(tag == 'p' for tag, _ in self.stack) and bool(self.current['paragraphs'])

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                if any('data-writer-work' in attrs for _, attrs in self.stack[i:]):
                    self.current = None
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.current is None:
            return
        if self.in_role('data-writer-title'):
            self.current['title'] += data
        elif self.in_role('data-writer-body'):
            if self.in_paragraph():
                self.current['paragraphs'][-1] += data
            elif data.strip():
                self.errors.append('Manuscript text outside a paragraph')


def check_manuscripts(html, paths, untitled=False):
    parser = ManuscriptParser()
    parser.feed(html)
    errors = list(parser.errors)
    expected = [manuscript(path, untitled) for path in paths]
    if len(parser.works) != len(expected):
        errors.append('HTML work count differs from manuscript count')
    for i, (actual, source) in enumerate(zip(parser.works, expected), 1):
        if actual['title'] != source['title']:
            errors.append(f'Work {i}: title differs from manuscript')
        if actual['paragraphs'] != source['paragraphs']:
            errors.append(f'Work {i}: prose or paragraph boundaries differ from manuscript')
    return errors


def check_review_binding(html_path, text_path, run, life):
    import writing_run as writing
    import writing_lifecycle as lifecycle
    with writing.session(run, write=False) as state:
        if writing.current(state)['text'] != Path(text_path).read_text(encoding='utf-8'):
            raise ValueError('HTML manuscript is not the current reviewed text')
        result = writing.check(state, lifecycle_run=life)
        if result['status'] != 'pass':
            raise ValueError('Literary review is not complete: ' + '; '.join(result['blockers']))
    with lifecycle.session(life) as state:
        if state['plan']['format'] != 'html':
            raise ValueError('Lifecycle did not declare HTML output')
        import presentation
        current = presentation.current(state, html_path)
        if current is None:
            layout = state['candidates'][-1]['layout']
            refs = {str(Path(p).resolve()) for p in layout.get('evidence_files', [])}
            if layout.get('status') != 'inspected' or str(Path(html_path).resolve()) not in refs:
                raise ValueError('The exact HTML was not bound as inspected layout evidence')
    return {'status': result['status'], 'text_sha256': result['sha256'], 'run': str(Path(run).resolve())}


def language_root(value: str) -> str:
    return value.strip().lower().split("-", 1)[0]


def dominant_language(text: str) -> tuple[str, int, int]:
    text = re.sub(r"https?://\S+", " ", text)
    cjk = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    total = cjk + latin
    if total < 80:
        return "unknown", cjk, latin
    cjk_share = cjk / total
    if cjk_share >= 0.25:
        return "zh", cjk, latin
    if cjk_share <= 0.10:
        return "en", cjk, latin
    return "mixed", cjk, latin


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("html_file", type=Path)
    parser.add_argument('--text', type=Path, action='append', help='Repeat in document order for multiple works')
    parser.add_argument('--run', type=Path, action='append', help='Completed native writing run, one per manuscript')
    parser.add_argument('--lifecycle-run', type=Path, action='append', help='Matching HTML literary lifecycle')
    parser.add_argument('--untitled', action='store_true', help='Compare body-only manuscripts without a visible title')
    parser.add_argument(
        "--scaffold",
        action="store_true",
        help="allow template placeholders while checking generated structure",
    )
    parser.add_argument(
        "--expected-language",
        help="expected dominant output language, for example en or zh-CN",
    )
    args = parser.parse_args()

    html_path = args.html_file.resolve()
    errors: list[str] = []
    if not html_path.is_file():
        print(f"ERROR: file not found: {html_path}")
        return 1

    text = html_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != MARKER:
        errors.append('Missing Writer Pen provenance comment on line 1')
    if "<html" not in text or not re.search(r"<html\b[^>]*\blang=", text, re.IGNORECASE):
        errors.append("html element must declare lang")
    if not args.scaffold:
        if not args.text:
            errors.append('Provide --text to verify title, prose and paragraph boundaries')
        else:
            try:
                errors.extend(check_manuscripts(text, args.text, args.untitled))
            except (OSError, ValueError) as error:
                errors.append(str(error))

    artifact = ArtifactParser()
    artifact.feed(text)
    for identifier in sorted(artifact.duplicate_ids):
        errors.append(f'duplicate id: {identifier}')
    if not artifact.html_lang or not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', artifact.html_lang):
        errors.append('Invalid html language tag')

    if args.expected_language:
        expected = language_root(args.expected_language)
        if not artifact.html_lang or language_root(artifact.html_lang) != expected:
            errors.append(
                f"html lang {artifact.html_lang!r} does not match expected language {expected}"
            )
        if not args.scaffold:
            detected, cjk, latin = dominant_language(" ".join(artifact.visible_text))
            if expected in {"en", "zh"} and detected not in {expected, 'unknown', 'mixed'}:
                print(
                    f"WARNING: visible text language signal is {detected}, expected {expected}; inspect in context "
                    f"(CJK={cjk}, Latin={latin})"
                )

    internal_targets = {href[1:] for href in artifact.hrefs if href.startswith("#")}
    for target in sorted(internal_targets - artifact.ids):
        errors.append(f"missing internal link target: #{target}")

    citation_refs = {
        int(match)
        for match in re.findall(r'href=["\']#cite-(\d+)["\']', text)
    }
    citation_targets = {
        int(match)
        for match in re.findall(r'id=["\']cite-(\d+)["\']', text)
    }
    for number in sorted(citation_refs - citation_targets):
        errors.append(f"citation has no source entry: cite-{number}")
    if not args.scaffold:
        for number in sorted(citation_targets - citation_refs):
            errors.append(f"source entry is not cited: cite-{number}")

    css_assets = re.findall(r"url\(\s*[\"']?([^\"')]+)", text)
    css_assets += re.findall(r'@import\s+["\']([^"\']+)', text)
    assets = artifact.assets + [("css", value.strip()) for value in css_assets]
    for tag, value in assets:
        if value.startswith('#'):
            if value[1:] not in artifact.ids:
                errors.append(f'missing asset fragment: {value}')
            continue
        if value.startswith("data:"):
            errors.append(f"base64/data asset is not portable: {tag} {value[:32]}")
            continue
        if is_remote(value):
            errors.append(f"remote runtime asset is forbidden: {tag} {value}")
            continue
        if value.startswith(("file://", "/")):
            errors.append(f"absolute local asset path is forbidden: {tag} {value}")
            continue
        if urlparse(value).scheme:
            errors.append(f'unsupported runtime asset scheme: {value}')
            continue
        clean = unquote(value.split("#", 1)[0].split("?", 1)[0])
        target = (html_path.parent / clean).resolve()
        if clean and not target.is_relative_to(html_path.parent):
            errors.append(f'asset escapes portable directory: {value}')
        elif clean and not target.is_file():
            errors.append(f"missing local asset: {value}")

    if artifact.tables_total != artifact.tables_wrapped:
        errors.append(
            f"{artifact.tables_total - artifact.tables_wrapped} table(s) are not inside .table-wrap"
        )

    reviews = []
    if args.run or args.lifecycle_run:
        if len(args.run or []) != len(args.text or []) or len(args.lifecycle_run or []) != len(args.text or []):
            errors.append('Provide one --run and --lifecycle-run per --text, in the same order')
        elif not errors:
            for source, run, life in zip(args.text, args.run, args.lifecycle_run):
                try:
                    reviews.append(check_review_binding(html_path, source, run, life))
                except (OSError, ValueError, KeyError, TypeError) as error:
                    errors.append(str(error))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"FAIL: {len(errors)} issue(s)")
        return 1

    print(json.dumps({'status': 'record-bound-html-checks-passed' if reviews else 'static-checks-passed', 'html': str(html_path),
                      'html_sha256': hashlib.sha256(html_path.read_bytes()).hexdigest(),
                      'manuscripts': [{'path': str(p.resolve()), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                                      for p in (args.text or [])],
                      'native_reviews': reviews,
                      'boundary': 'Static checks alone do not establish rendering or literary review. Bound mode also verifies existing native checks and recorded layout evidence; not human reception or publishing.'},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
