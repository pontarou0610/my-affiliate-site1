from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
import os


@dataclass(frozen=True)
class AutopostConfig:
    content_globs: tuple[str, ...] = ("content/posts/**/*.md",)
    output_dir: Path = Path("public")
    state_path: Path = Path(".autopost/state.json")
    summary_target_min_chars: int = 120
    summary_target_max_chars: int = 160
    hashtags: tuple[str, ...] = ()
    hugo_binary: str = "hugo"
    hugo_args: tuple[str, ...] = ("--minify",)

    @staticmethod
    def from_env() -> "AutopostConfig":
        content_globs = _split_csv_env("AUTOPOST_CONTENT_GLOBS") or ["content/posts/**/*.md"]
        hashtags = _split_csv_env("AUTOPOST_HASHTAGS") or []
        output_dir = Path(os.getenv("AUTOPOST_OUTPUT_DIR", "public"))
        state_path = Path(os.getenv("AUTOPOST_STATE_PATH", ".autopost/state.json"))

        summary_min = _env_int("AUTOPOST_SUMMARY_MIN_CHARS", default=120)
        summary_max = _env_int("AUTOPOST_SUMMARY_MAX_CHARS", default=160)
        if summary_min > summary_max:
            summary_min, summary_max = summary_max, summary_min

        hugo_binary = os.getenv("HUGO_BIN", "hugo")
        hugo_args = tuple(_split_shellish_env("HUGO_ARGS") or ["--minify"])

        return AutopostConfig(
            content_globs=tuple(content_globs),
            output_dir=output_dir,
            state_path=state_path,
            summary_target_min_chars=summary_min,
            summary_target_max_chars=summary_max,
            hashtags=tuple(hashtags),
            hugo_binary=hugo_binary,
            hugo_args=tuple(hugo_args),
        )


@dataclass(frozen=True)
class HugoConfig:
    config_path: Path | None
    base_url: str
    permalinks: dict[str, str]


def load_hugo_config(repo_root: Path) -> HugoConfig:
    candidates = [
        "hugo.toml",
        "config.toml",
        "config.yaml",
        "config.yml",
        "config.json",
        "hugo.yaml",
        "hugo.yml",
        "hugo.json",
    ]

    for name in candidates:
        path = repo_root / name
        if path.exists() and path.is_file():
            data = _load_config_file(path)
            base_url = str(data.get("baseURL", "") or data.get("baseUrl", "") or "")
            permalinks_raw = data.get("permalinks", {}) or {}
            permalinks = {str(k): str(v) for k, v in permalinks_raw.items()} if isinstance(permalinks_raw, dict) else {}
            return HugoConfig(
                config_path=path,
                base_url=_normalize_base_url(base_url),
                permalinks=permalinks,
            )

    return HugoConfig(config_path=None, base_url="", permalinks={})


def _load_config_file(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".toml":
        import tomllib

        return tomllib.loads(text)
    if suffix in {".yaml", ".yml"}:
        from .parse_frontmatter import parse_simple_yaml

        data = parse_simple_yaml(text)
        return data if isinstance(data, dict) else {}
    if suffix == ".json":
        return json.loads(text)
    return {}


def _normalize_base_url(base_url: str) -> str:
    base_url = (base_url or "").strip()
    if not base_url:
        return ""
    if not base_url.endswith("/"):
        base_url += "/"
    return base_url


def _env_int(name: str, *, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _split_csv_env(name: str) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return []
    items: list[str] = []
    for part in raw.replace("\n", ",").split(","):
        value = part.strip()
        if value:
            items.append(value)
    return items


def _split_shellish_env(name: str) -> list[str]:
    raw = os.getenv(name)
    if raw is None:
        return []
    raw = raw.strip()
    if not raw:
        return []
    parts: list[str] = []
    current: list[str] = []
    in_quotes = False
    quote_char = ""
    for ch in raw:
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
        if ch.isspace():
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))
    return parts

