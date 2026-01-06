from __future__ import annotations

from html import unescape
import re


def extract_summary(markdown_body: str, *, target_min_chars: int = 120, target_max_chars: int = 160) -> str:
    plain = markdown_to_plain_text(markdown_body)
    paragraph = _pick_first_natural_paragraph(plain)
    if not paragraph:
        paragraph = plain.strip()
    if not paragraph:
        return ""

    summary = _format_summary(paragraph, target_min_chars=target_min_chars, target_max_chars=target_max_chars)
    return summary


_RE_FENCED_CODE = re.compile(r"(?ms)^```.*?^```\s*$")
_RE_INLINE_CODE = re.compile(r"`[^`]+`")
_RE_SHORTCODE = re.compile(r"{{[<%].*?[>%]}}", re.DOTALL)
_RE_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]+\)")
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_HTML_TAG = re.compile(r"<[^>]+>")
_RE_HEADING = re.compile(r"(?m)^#{1,6}\s+.*$")
_RE_BLOCKQUOTE = re.compile(r"(?m)^>\s?.*$")
_RE_LISTLINE = re.compile(r"(?m)^(?:\s*[-*+]\s+|\s*\d+\.\s+).*$")
_RE_URL = re.compile(r"https?://\S+")
_RE_PHOTO_CREDIT = re.compile(r"(?i)\bphoto by\b.*\b(pexels|unsplash|pixabay)\b")


def markdown_to_plain_text(markdown_body: str) -> str:
    text = markdown_body.replace("\r\n", "\n").replace("\r", "\n")
    text = _RE_FENCED_CODE.sub("", text)
    text = _RE_SHORTCODE.sub("", text)

    text = _RE_BLOCKQUOTE.sub("", text)
    text = _RE_LISTLINE.sub("", text)
    text = _RE_HEADING.sub("", text)

    # Images/credits tend to be noise for short summaries; drop the whole image syntax.
    text = _RE_MD_IMAGE.sub("", text)
    text = _RE_MD_LINK.sub(lambda m: m.group(1) or "", text)
    text = _RE_INLINE_CODE.sub("", text)

    # remove raw URLs (keep surrounding text)
    text = _RE_URL.sub("", text)

    # strip HTML tags (Hugo pages may include raw HTML)
    text = _RE_HTML_TAG.sub(" ", text)
    text = unescape(text)

    # remove emphasis markers and leftover markdown symbols
    text = text.replace("*", " ").replace("_", " ").replace("|", " ")

    # normalize whitespace
    text = re.sub(r"[ \\t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pick_first_natural_paragraph(plain: str) -> str:
    candidates: list[str] = []
    for paragraph in re.split(r"\n\s*\n", plain):
        p = paragraph.strip()
        if not p:
            continue
        p = re.sub(r"\s+", " ", p).strip()
        if len(p) < 30:
            continue
        if _looks_like_noise(p):
            continue
        candidates.append(p)
    if not candidates:
        return ""
    for p in candidates:
        if _has_japanese(p):
            return p
    return candidates[0]


def _looks_like_noise(text: str) -> bool:
    if _RE_PHOTO_CREDIT.search(text):
        return True
    if not re.search("[A-Za-z0-9\u3040-\u30FF\u4E00-\u9FFF]", text):
        return True
    if re.fullmatch(r"[\W_]+", text):
        return True
    return False


def _has_japanese(text: str) -> bool:
    return re.search("[\u3040-\u30FF\u4E00-\u9FFF]", text) is not None


def _format_summary(paragraph: str, *, target_min_chars: int, target_max_chars: int) -> str:
    paragraph = re.sub(r"\s+", " ", paragraph).strip()
    if not paragraph:
        return ""

    sentences = _split_sentences(paragraph)
    if sentences:
        summary = "".join(sentences[:2]).strip()
    else:
        summary = paragraph

    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > target_max_chars:
        summary = _truncate(summary, target_max_chars)

    # if too short, allow a bit more from the paragraph (still capped)
    if len(summary) < target_min_chars and len(paragraph) > len(summary):
        expanded = _truncate(paragraph, target_max_chars)
        if len(expanded) > len(summary):
            summary = expanded

    return summary


def _split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in {"。", "！", "？", "!", "?"}:
            s = "".join(buf).strip()
            if s:
                sentences.append(s)
            buf = []
            if len(sentences) >= 3:
                break
    rest = "".join(buf).strip()
    if rest:
        sentences.append(rest)
    return sentences


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # prefer cutting at sentence end if available
    last = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("!"), cut.rfind("?"))
    if last >= max(0, max_chars - 20):
        cut = cut[: last + 1]
    return cut.rstrip()
