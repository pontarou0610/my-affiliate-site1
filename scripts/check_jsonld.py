#!/usr/bin/env python3
"""Check generated Hugo JSON-LD output."""

from __future__ import annotations

import argparse
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import frontmatter


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = REPO_ROOT / "content"


class JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_jsonld = False
        self._buffer: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        attr_map = {key.lower(): value for key, value in attrs}
        if (attr_map.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_jsonld:
            self.scripts.append("".join(self._buffer).strip())
            self._in_jsonld = False
            self._buffer = []


def normalize_type(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def walk_objects(value: Any) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    if isinstance(value, dict):
        objects.append(value)
        for child in value.values():
            objects.extend(walk_objects(child))
    elif isinstance(value, list):
        for child in value:
            objects.extend(walk_objects(child))
    return objects


def parse_jsonld(path: Path) -> tuple[list[Any], list[str]]:
    parser = JsonLdParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))

    parsed: list[Any] = []
    errors: list[str] = []
    for index, script in enumerate(parser.scripts, start=1):
        if not script:
            errors.append(f"{path}: empty JSON-LD script #{index}")
            continue
        try:
            parsed.append(json.loads(script))
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON-LD script #{index}: {exc}")
    return parsed, errors


def find_faq_pages(jsonld_items: list[Any]) -> list[dict[str, Any]]:
    faq_pages: list[dict[str, Any]] = []
    for item in jsonld_items:
        for obj in walk_objects(item):
            if "FAQPage" in normalize_type(obj.get("@type")):
                faq_pages.append(obj)
    return faq_pages


def content_url(metadata: dict[str, Any], path: Path) -> str:
    url = metadata.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()

    slug = metadata.get("slug")
    if isinstance(slug, str) and slug.strip():
        return f"/posts/{slug.strip('/')}/"

    rel = path.relative_to(CONTENT_DIR).with_suffix("")
    if rel.name == "_index":
        rel = rel.parent
    return "/" + "/".join(rel.parts).strip("/") + "/"


def html_path_for_url(root: Path, url: str) -> Path:
    clean = url.split("#", 1)[0].split("?", 1)[0].strip("/")
    if not clean:
        return root / "index.html"
    return root / clean / "index.html"


def expected_faq_pages() -> list[tuple[Path, str, list[dict[str, str]]]]:
    expected: list[tuple[Path, str, list[dict[str, str]]]] = []
    for path in sorted(CONTENT_DIR.rglob("*.md")):
        post = frontmatter.load(path)
        schema = post.metadata.get("schema")
        if not isinstance(schema, dict):
            continue
        faq = schema.get("faq")
        if not isinstance(faq, list) or not faq:
            continue

        questions: list[dict[str, str]] = []
        for item in faq:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or "").strip()
            answer = str(item.get("answer") or "").strip()
            if question and answer:
                questions.append({"question": question, "answer": answer})
        if questions:
            expected.append((path, content_url(post.metadata, path), questions))
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generated Hugo JSON-LD output.")
    parser.add_argument(
        "html_root",
        nargs="?",
        default="public",
        help="Generated Hugo output directory to scan, default: public",
    )
    args = parser.parse_args()

    root = Path(args.html_root)
    if not root.is_absolute():
        root = REPO_ROOT / root
    if not root.exists():
        print(f"Generated HTML directory does not exist: {root}")
        return 1

    issues: list[str] = []
    for html_path in sorted(root.rglob("*.html")):
        _, errors = parse_jsonld(html_path)
        issues.extend(errors)

    for source_path, url, expected_questions in expected_faq_pages():
        html_path = html_path_for_url(root, url)
        if not html_path.exists():
            issues.append(f"{source_path}: expected HTML not found for {url}: {html_path}")
            continue

        jsonld_items, errors = parse_jsonld(html_path)
        issues.extend(errors)
        faq_pages = find_faq_pages(jsonld_items)
        if len(faq_pages) != 1:
            issues.append(f"{source_path}: expected exactly 1 FAQPage in {html_path}, found {len(faq_pages)}")
            continue

        actual_entities = faq_pages[0].get("mainEntity")
        if not isinstance(actual_entities, list):
            issues.append(f"{source_path}: FAQPage mainEntity is not a list")
            continue
        if len(actual_entities) != len(expected_questions):
            issues.append(
                f"{source_path}: expected {len(expected_questions)} FAQ questions, found {len(actual_entities)}"
            )
            continue

        for index, (expected_item, actual_item) in enumerate(zip(expected_questions, actual_entities), start=1):
            if not isinstance(actual_item, dict):
                issues.append(f"{source_path}: FAQ question #{index} is not an object")
                continue
            actual_question = str(actual_item.get("name") or "").strip()
            answer = actual_item.get("acceptedAnswer")
            actual_answer = ""
            if isinstance(answer, dict):
                actual_answer = str(answer.get("text") or "").strip()
            if actual_question != expected_item["question"]:
                issues.append(
                    f"{source_path}: FAQ question #{index} mismatch: "
                    f"{actual_question!r} != {expected_item['question']!r}"
                )
            if actual_answer != expected_item["answer"]:
                issues.append(f"{source_path}: FAQ answer #{index} does not match front matter")

    if issues:
        print(f"JSON-LD check failed with {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    print(f"JSON-LD check passed for {root}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
