#!/usr/bin/env python3
"""
Normalize Hugo post tags to a controlled set.

Why:
- Avoid tag bloat (thin taxonomy pages)
- Consolidate synonyms (e.g., Kindle本セール -> Kindleセール)
- Keep tag navigation consistent for SEO/UX
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, Optional


POSTS_ROOT = Path("content/posts")
MAX_TAGS = 5

ALLOWED_TAGS: list[str] = [
    "電子書籍",
    "Kindle",
    "Kobo",
    "電子ペーパー",
    "電子書籍リーダー",
    "比較レビュー",
    "レビュー",
    "端末選び",
    "読書術",
    "使い方",
    "設定",
    "EPUB",
    "PDF",
    "読み放題",
    "サブスク",
    "セール",
    "Kindleセール",
    "Amazon",
    "楽天",
    "KDP",
    "出版",
    "AI",
    "NotebookLM",
    "ニュース",
    "セキュリティ",
    "プライバシー",
    "電子書籍入門",
]

TAG_SYNONYMS: dict[str, str] = {
    "kindle本セール": "Kindleセール",
    "kindleセール": "Kindleセール",
    "kindle本": "Kindle",
    "amazonセール": "セール",
    "楽天セール": "セール",
    "電子書籍セール": "セール",
    "まとめ買い": "セール",
    "楽天ポイント": "楽天",
    "rakutenポイント": "楽天",
    "amazonポイント": "Amazon",
    "amazonポイント還元": "Amazon",
    "adobe脆弱性": "セキュリティ",
    "acrobat更新": "セキュリティ",
    "pdfセキュリティ": "セキュリティ",
    "セキュリティ情報": "セキュリティ",
    "任意コード実行": "セキュリティ",
    "notebooklm": "NotebookLM",
}


def _uniq(seq: Iterable[str]) -> list[str]:
    out: list[str] = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


def normalize_tag(tag: str) -> Optional[str]:
    t = re.sub(r"\s+", " ", (tag or "").strip())
    if not t:
        return None
    key = t.lower()
    t = TAG_SYNONYMS.get(key, t)
    if t not in set(ALLOWED_TAGS):
        return None
    return t


def infer_tags(title: str, body: str) -> list[str]:
    text = f"{title}\n{body}".lower()
    inferred: list[str] = ["電子書籍"]

    if "kindle" in text:
        inferred.append("Kindle")
    if "kobo" in text:
        inferred.append("Kobo")
    if any(k in text for k in ["e-ink", "e ink", "電子ペーパー", "電子書籍リーダー", "端末", "デバイス"]):
        inferred.append("電子ペーパー")
        inferred.append("電子書籍リーダー")

    if any(k in text for k in ["比較", "違い", "どっち", "vs", "徹底比較"]):
        inferred.append("比較レビュー")
    if any(k in text for k in ["レビュー", "評判", "口コミ", "実機", "使ってみた", "感想", "評価"]):
        inferred.append("レビュー")
    if any(k in text for k in ["選び方", "おすすめ", "買う", "購入", "どれを選ぶ"]):
        inferred.append("端末選び")

    if any(k in text for k in ["読書術", "読書習慣", "集中", "目が疲れ", "快眠", "寝る前"]):
        inferred.append("読書術")
    if any(k in text for k in ["使い方", "手順", "方法", "コツ", "設定"]):
        inferred.append("使い方")
    if "設定" in text:
        inferred.append("設定")

    if "epub" in text:
        inferred.append("EPUB")
    if "pdf" in text:
        inferred.append("PDF")

    if any(k in text for k in ["読み放題", "unlimited", "kobo plus", "サブスク", "定額"]):
        inferred.append("読み放題")
        inferred.append("サブスク")

    if any(k in text for k in ["セール", "キャンペーン", "クーポン", "ブラックフライデー", "プライムデー", "還元"]):
        inferred.append("セール")
        if "kindle" in text:
            inferred.append("Kindleセール")

    if any(k in text for k in ["kdp", "自費出版", "出版", "著者"]):
        inferred.append("出版")
        if "kdp" in text:
            inferred.append("KDP")

    if any(k in text for k in ["notebooklm"]):
        inferred.append("NotebookLM")
        inferred.append("AI")
    elif any(k in text for k in ["ai", "chatgpt", "gemini"]):
        inferred.append("AI")

    if any(k in text for k in ["ニュース", "発表", "終了", "アップデート", "リリース"]):
        inferred.append("ニュース")

    if any(k in text for k in ["脆弱性", "セキュリティ", "不正", "攻撃"]):
        inferred.append("セキュリティ")
    if any(k in text for k in ["プライバシー", "個人情報"]):
        inferred.append("プライバシー")

    if any(k in text for k in ["入門", "初心者", "はじめて"]):
        inferred.append("電子書籍入門")

    # Keep only allowed tags, preserve order.
    allowed = set(ALLOWED_TAGS)
    out: list[str] = []
    for t in inferred:
        if t in allowed and t not in out:
            out.append(t)
    return out


def parse_front_matter(text: str) -> tuple[str, str, str] | None:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None
        return ("---", parts[1], parts[2])
    if text.startswith("+++"):
        parts = text.split("+++", 2)
        if len(parts) < 3:
            return None
        return ("+++", parts[1], parts[2])
    return None


def extract_title(fm: str, delimiter: str) -> str:
    if delimiter == "+++":  # TOML
        m = re.search(r'(?m)^title\s*=\s*"(.*?)"\s*$', fm)
        return (m.group(1).strip() if m else "")
    m = re.search(r'(?m)^title:\s*"(.*?)"\s*$', fm)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?m)^title:\s*(.*?)\s*$", fm)
    return (m.group(1).strip().strip('"') if m else "")


def extract_tags(fm: str, delimiter: str) -> list[str]:
    if delimiter == "+++":  # TOML
        m = re.search(r"(?m)^tags\s*=\s*(\[.*\])\s*$", fm)
        if not m:
            return []
        raw = m.group(1).strip()
    else:  # YAML
        m = re.search(r"(?m)^tags:\s*(\[.*\])\s*$", fm)
        if m:
            raw = m.group(1).strip()
        else:
            # Multiline YAML:
            # tags:
            #   - a
            #   - b
            m = re.search(r"(?m)^tags:\s*$", fm)
            if not m:
                return []
            # Extract lines after tags: that start with "- "
            lines = fm.splitlines()
            idx = next((i for i, line in enumerate(lines) if line.strip() == "tags:"), None)
            if idx is None:
                return []
            out: list[str] = []
            for line in lines[idx + 1 :]:
                if not re.match(r"^\s*-\s+", line):
                    break
                out.append(re.sub(r"^\s*-\s+", "", line).strip().strip('"').strip("'"))
            return out
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, (str, int, float))]
    except Exception:
        pass
    try:
        import ast

        parsed = ast.literal_eval(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if isinstance(x, (str, int, float))]
    except Exception:
        pass
    return []


def replace_tags_in_front_matter(fm: str, delimiter: str, new_tags: list[str]) -> str:
    yaml_tags_line = f"tags: {json.dumps(new_tags, ensure_ascii=False)}"

    if delimiter == "+++":  # TOML
        toml_tags_line = f"tags = {json.dumps(new_tags, ensure_ascii=False)}"
        had_trailing_newline = fm.endswith("\n")

        # Remove existing tags entries (avoid duplicates), then insert a single normalized one.
        lines = [line for line in fm.splitlines() if not re.match(r"^tags\s*=", line)]

        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if (not inserted) and re.match(r"^title\s*=", line):
                out.append(toml_tags_line)
                inserted = True

        if not inserted:
            insert_at = 0
            while insert_at < len(out) and out[insert_at].strip() == "":
                insert_at += 1
            out.insert(insert_at, toml_tags_line)

        return "\n".join(out) + ("\n" if had_trailing_newline else "")

    # YAML
    had_trailing_newline = fm.endswith("\n")
    lines = fm.splitlines()

    # Remove existing tags entries (single-line or multi-line).
    stripped: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^tags:\s*\[.*\]\s*$", line):
            i += 1
            continue
        if line.strip() == "tags:":
            i += 1
            while i < len(lines) and re.match(r"^\s*-\s+", lines[i]):
                i += 1
            continue
        stripped.append(line)
        i += 1

    # Insert after draft if present, else after title, else after leading blank lines.
    insert_at: int | None = None
    for idx, line in enumerate(stripped):
        if re.match(r"^draft\s*[:=]\s*", line):
            insert_at = idx + 1
            break
    if insert_at is None:
        for idx, line in enumerate(stripped):
            if re.match(r"^title\s*[:=]\s*", line):
                insert_at = idx + 1
                break
    if insert_at is None:
        insert_at = 0
        while insert_at < len(stripped) and stripped[insert_at].strip() == "":
            insert_at += 1

    stripped.insert(insert_at, yaml_tags_line)
    return "\n".join(stripped) + ("\n" if had_trailing_newline else "")


def normalize_tags_for_post(path: Path, max_tags: int = MAX_TAGS) -> tuple[bool, str]:
    raw = path.read_text(encoding="utf-8")
    parsed = parse_front_matter(raw)
    if not parsed:
        return (False, raw)
    delim, fm, body = parsed

    title = extract_title(fm, delim)
    existing = extract_tags(fm, delim)

    normalized_existing: list[str] = []
    for t in existing:
        nt = normalize_tag(t)
        if nt and nt not in normalized_existing:
            normalized_existing.append(nt)

    inferred = infer_tags(title, body)
    combined = _uniq(inferred + normalized_existing)
    combined = combined[:max_tags]
    if not combined:
        combined = ["電子書籍"]

    fm2 = replace_tags_in_front_matter(fm, delim, combined)
    if not fm2.startswith("\n"):
        fm2 = "\n" + fm2
    if not fm2.endswith("\n"):
        fm2 = fm2 + "\n"
    if body and not body.startswith("\n"):
        body = "\n" + body
    updated = f"{delim}{fm2}{delim}{body}"
    return (updated != raw, updated)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize tags in Hugo posts.")
    parser.add_argument("--posts-dir", type=Path, default=POSTS_ROOT)
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--max-tags", type=int, default=MAX_TAGS)
    args = parser.parse_args()

    posts = sorted(args.posts_dir.glob("*.md"))
    changed = 0
    for p in posts:
        if p.name == "_index.md":
            continue
        did_change, new_text = normalize_tags_for_post(p, max_tags=max(1, args.max_tags))
        if not did_change:
            continue
        changed += 1
        if args.apply:
            p.write_text(new_text, encoding="utf-8")
        else:
            print(f"[would change] {p}")

    print(f"changed: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
