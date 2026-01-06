from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import json
import re


@dataclass(frozen=True)
class ParsedMarkdown:
    meta: dict[str, Any]
    body: str
    frontmatter_format: str | None


_YAML_DELIM = "---"
_TOML_DELIM = "+++"


def parse_markdown(markdown_text: str) -> ParsedMarkdown:
    lines = markdown_text.splitlines()
    if not lines:
        return ParsedMarkdown(meta={}, body="", frontmatter_format=None)

    first = lines[0].strip()
    if first == _YAML_DELIM:
        meta_text, body_text = _split_delimited_frontmatter(lines, delim=_YAML_DELIM)
        return ParsedMarkdown(meta=parse_simple_yaml(meta_text), body=body_text, frontmatter_format="yaml")
    if first == _TOML_DELIM:
        meta_text, body_text = _split_delimited_frontmatter(lines, delim=_TOML_DELIM)
        return ParsedMarkdown(meta=_parse_toml(meta_text), body=body_text, frontmatter_format="toml")

    # JSON front matter (Hugo): file begins with a JSON object, then a blank line, then body.
    if markdown_text.lstrip().startswith("{"):
        parsed = _try_parse_json_frontmatter(markdown_text)
        if parsed is not None:
            return parsed

    return ParsedMarkdown(meta={}, body=markdown_text, frontmatter_format=None)


def _split_delimited_frontmatter(lines: list[str], *, delim: str) -> tuple[str, str]:
    end_index = None
    for i in range(1, len(lines)):
        if lines[i].strip() == delim:
            end_index = i
            break
    if end_index is None:
        return "", "\n".join(lines)
    meta_text = "\n".join(lines[1:end_index]).strip("\n")
    body_text = "\n".join(lines[end_index + 1 :]).lstrip("\n")
    return meta_text, body_text


def _parse_toml(meta_text: str) -> dict[str, Any]:
    try:
        import tomllib

        data = tomllib.loads(meta_text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _try_parse_json_frontmatter(markdown_text: str) -> ParsedMarkdown | None:
    stripped = markdown_text.lstrip()
    start_offset = markdown_text.find(stripped)
    boundary = stripped.find("\n\n")
    if boundary <= 0:
        return None
    header = stripped[:boundary].strip()
    try:
        meta = json.loads(header)
        if not isinstance(meta, dict):
            return None
    except Exception:
        return None
    body = stripped[boundary + 2 :].lstrip("\n")
    if start_offset > 0:
        body = markdown_text[start_offset + boundary + 2 :].lstrip("\n")
    return ParsedMarkdown(meta=meta, body=body, frontmatter_format="json")


def parse_simple_yaml(yaml_text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    lines = yaml_text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        i += 1

        if not line.strip() or line.lstrip().startswith("#"):
            continue

        if line.startswith((" ", "\t")):
            continue

        if ":" not in line:
            continue

        key, rest = line.split(":", 1)
        key = key.strip()
        value = rest.strip()

        if not key:
            continue

        if value in {"|", ">"}:
            block_lines: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if nxt.startswith((" ", "\t")):
                    block_lines.append(nxt.lstrip())
                    i += 1
                else:
                    break
            result[key] = "\n".join(block_lines).strip("\n")
            continue

        if value == "":
            # list block
            items: list[Any] = []
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    i += 1
                    continue
                if not nxt.startswith((" ", "\t")):
                    break
                stripped = nxt.strip()
                if not stripped.startswith("- "):
                    break
                items.append(_parse_scalar(stripped[2:].strip()))
                i += 1
            if items:
                result[key] = items
            else:
                result[key] = ""
            continue

        result[key] = _parse_scalar(_strip_yaml_comment(value))

    return result


_RE_INLINE_LIST = re.compile(r"^\[(.*)\]$")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""

    if value.lower() in {"true", "false"}:
        return value.lower() == "true"

    if value.lower() in {"null", "nil", "~"}:
        return None

    if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
        return value[1:-1]

    m = _RE_INLINE_LIST.match(value)
    if m:
        inner = m.group(1).strip()
        if not inner:
            return []
        parts: list[str] = []
        current: list[str] = []
        in_quotes = False
        quote_char = ""
        for ch in inner:
            if in_quotes:
                if ch == quote_char:
                    in_quotes = False
                    quote_char = ""
                else:
                    current.append(ch)
                continue
            if ch in {"'", '"'}:
                in_quotes = True
                quote_char = ch
                continue
            if ch == ",":
                parts.append("".join(current).strip())
                current = []
                continue
            current.append(ch)
        parts.append("".join(current).strip())
        return [_parse_scalar(p) for p in parts if p != ""]

    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except Exception:
            return value

    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except Exception:
            return value

    return value


def _strip_yaml_comment(value: str) -> str:
    if "#" not in value:
        return value
    if value.startswith(("'", '"')):
        return value
    idx = value.find(" #")
    if idx == -1:
        idx = value.find("\t#")
    if idx == -1 and value.startswith("#"):
        return ""
    if idx == -1:
        return value
    return value[:idx].rstrip()
