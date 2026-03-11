# scripts/generate_post.py
"""
Article generator for the ebook-focused blog.
- Collects topics from RSS or fallback list
- Generates 1–3 posts/day via OpenAI
- Skips duplicate titles/slugs and similar H2 structures
- Skips fallback topics used in the last 7 days
- Inserts pillar links, related articles, and Rakuten affiliate items
"""

import os
import re
import difflib
import datetime
import pathlib
import random
import argparse
import json
import unicodedata
import math
from collections import Counter
from urllib.parse import urlparse
from typing import List, Dict, Tuple, Set

import requests
from textwrap import dedent
from dotenv import load_dotenv
from slugify import slugify as slugify_lib
from openai import OpenAI

# ---------- paths / config ----------
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
HUGO_CONFIG_PATH = REPO_ROOT / "hugo.toml"
CONTENT_POSTS_DIR = REPO_ROOT / "content" / "posts"


def load_base_url() -> str:
    """Resolve baseURL for canonicalURL generation (prefer env, fallback to hugo.toml)."""
    for key in ("SITE_BASE_URL", "BASE_URL"):
        v = (os.getenv(key) or "").strip()
        if v:
            return v
    try:
        import tomllib

        if HUGO_CONFIG_PATH.exists():
            data = tomllib.loads(HUGO_CONFIG_PATH.read_text(encoding="utf-8"))
            v = (data.get("baseURL") or "").strip()
            if v:
                return v
    except Exception:
        pass
    return ""


BASE_URL = ""


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

# ---------- env ----------
load_dotenv()
BASE_URL = load_base_url()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-5.4").strip() or "gpt-5.4"
OPENAI_FALLBACK_MODELS = ["gpt-5.2", "gpt-5.1", "gpt-5"]
OPENAI_MODEL_CANDIDATES = [OPENAI_MODEL] + [m for m in OPENAI_FALLBACK_MODELS if m != OPENAI_MODEL]
OPENAI_CLIENT = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID")
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
GOOGLE_CSE_API_KEY = (os.getenv("GOOGLE_CSE_API_KEY") or "").strip()
GOOGLE_CSE_CX = (os.getenv("GOOGLE_CSE_CX") or "").strip()
BRAVE_SEARCH_API_KEY = (os.getenv("BRAVE_SEARCH_API_KEY") or "").strip()
GSC_SERVICE_ACCOUNT_FILE = (os.getenv("GSC_SERVICE_ACCOUNT_FILE") or "").strip()
GSC_SITE_URL = (os.getenv("GSC_SITE_URL") or BASE_URL or "").strip()
EXTERNAL_SERP_PROVIDER = (os.getenv("EXTERNAL_SERP_PROVIDER") or "auto").strip().lower()

CSE_DAILY_FREE_LIMIT = _int_env("CSE_DAILY_FREE_LIMIT", 100)
DEFAULT_CSE_BUDGET = _int_env("CSE_BUDGET", 80)
UPDATE_COOLDOWN_DAYS = _int_env("UPDATE_COOLDOWN_DAYS", 14)
GSC_MAX_ROWS = _int_env("GSC_MAX_ROWS", 2000)
BASE_URL_PATH = (urlparse(BASE_URL).path or "").rstrip("/")
SUPPLY_AUDIT_PATH = REPO_ROOT / "data" / "supply_gap_report.json"

# ---------- sources ----------
RSS_SOURCES = [
    "https://b.hatena.ne.jp/hotentry/it.rss",
    "https://rss.itmedia.co.jp/rss/2.0/topstory.xml",
    "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf",
    "https://gigazine.net/news/rss_2.0/",
    "https://rss.itmedia.co.jp/rss/2.0/mobile.xml",
    "https://www.watch.impress.co.jp/data/rss/1.0/avw/feed.rdf",
    "https://www.engadget.com/rss.xml",
    "https://forest.watch.impress.co.jp/data/rss/1.0/wf/feed.rdf",
    "https://japanese.engadget.com/rss.xml",
    "https://www.gizmodo.jp/index.xml",
    "https://www.lifehacker.jp/feed/index.xml",
    "https://wired.jp/rssfeeder/",
    "https://techcrunch.com/feed/",
]
GOOGLE_SUGGEST_QUERIES = [
    "電子書籍",
    "Kindle 読書",
    "Kobo 使い方",
    "Kindle Unlimited",
    "読書術",
]

CORE_KEYWORDS = [
    "kindle",
    "kobo",
    "paperwhite",
    "scribe",
    "oasis",
    "voyage",
    "clara",
    "libra",
    "sage",
    "forma",
    "ebook",
    "e-book",
    "e ink",
    "e-ink",
    "eink",
    "epub",
    "pdf",
    "azw",
    "mobi",
    "prime reading",
    "kindle unlimited",
    "kobo plus",
    "rakuten kobo",
    "電子書籍",
    "電子リーダー",
    "電子ペーパー",
    "リフロー",
    "固定レイアウト",
    "マンガ",
    "読書",
    "読書術",
    "学習",
    "勉強法",
    "ノート術",
    "情報整理",
    "ライフハック",
    "タブレット",
    "ipad",
    "androidタブレット",
    "pdfリーダー",
    "電子ノート",
    "手書き",
    "ペン入力",
    "ocr",
    "音声読み上げ",
    "オーディオブック",
    "audible",
    "audiobook",
]
WHITELIST = list(CORE_KEYWORDS)

# NOTE:
# Static fallback topics tend to get exhausted as the site grows. Keep a small set of
# evergreen seeds and generate long-tail variations at runtime (filtered by existing
# titles/slugs) so daily generation doesn't become a no-op.
FALLBACK_TOPIC_SEEDS = [
    "Kindle端末のストレージ整理：容量不足を防ぐ3ステップ（削除/アーカイブ/再DL）",
    "KoboでEPUBをきれいに表示するための変換設定（Calibreの基本）",
    "Send to KindleでPDFを送ると崩れる時のチェックリスト（余白/向き/サイズ）",
    "Kindleのハイライトを後で探しやすくするコツ：タグ化・メモ・週1レビュー",
    "電子ペーパー端末で目が疲れにくい設定：明るさ・色温度・リフレッシュの最適解",
    "電子書籍のバックアップと移行：端末買い替えで詰まらない手順",
    "電子書籍リーダーのロック設定：紛失時に困らないための最低限チェック",
    "KDPのカテゴリとキーワードの決め方：小さく勝つための考え方（初心者向け）",
]

FALLBACK_SCENARIOS = [
    "通勤",
    "寝る前",
    "旅行・出張",
    "スキマ時間",
    "学習",
]
FALLBACK_READABILITY_KNOBS = [
    "フォント・太字",
    "余白・行間",
    "明るさ・色温度",
    "ページ更新（残像）",
    "辞書・翻訳",
]
FALLBACK_FORMATS = [
    "EPUB",
    "PDF",
    "固定レイアウト",
    "マンガ",
]
FALLBACK_NOTE_TOOLS = [
    "Notion",
    "Obsidian",
    "Googleドキュメント",
]
FALLBACK_KDP_AREAS = [
    "カテゴリとキーワード",
    "本文レイアウト",
    "目次",
    "表紙",
    "販売ページの説明文",
]

FALLBACK_TOPIC_TEMPLATES = [
    "Kindleの読みやすさ設定：{knob}を{scenario}向けに最適化する手順",
    "Koboの読みやすさ設定：{knob}を{scenario}向けに最適化する手順",
    "電子書籍リーダーの読みやすさ設定：{knob}を{scenario}向けに最適化する手順",
    "Kindleで{format}を快適に読むためのチェックリスト（{scenario}編）",
    "Koboで{format}を快適に読むためのチェックリスト（{scenario}編）",
    "Send to Kindleで{format}を送ると崩れる時の対処法（余白/向き/サイズの調整）",
    "Calibreで{format}を整える：Kindle/Koboで読める形にする最低限の設定",
    "Kindleのハイライト/メモを{tool}に整理する運用（週1レビューで定着）",
    "電子ペーパー端末のバッテリー節約：{scenario}でも電池を持たせる設定チェック",
    "KDPで電子書籍を出版する前に確認したい「{area}」チェックリスト",
    "NotebookLMで電子書籍の読書メモを育てる：ハイライト→要約→次の行動まで",
]

QUALITY_MIN_WORDS = 200
MIN_CHAR_COUNT = 1500
RELAXED_MIN_WORDS = 150
RELAXED_MIN_CHAR_COUNT = 1000
RELAXED_MIN_WORD_COUNT_LOWER = 120
RELAXED_MIN_CHAR_COUNT_LOWER = 800
TREND_QUALITY_MIN_WORDS = 450
TREND_MIN_CHAR_COUNT = 2200
TREND_RELAXED_MIN_WORDS = 320
TREND_RELAXED_MIN_CHAR_COUNT = 1600
TREND_RELAXED_MIN_WORD_COUNT_LOWER = 220
TREND_RELAXED_MIN_CHAR_COUNT_LOWER = 1100
FINAL_MIN_WORDS = 100
FINAL_MIN_CHAR_COUNT = 600
FAILSAFE_MIN_WORDS = 80
FAILSAFE_MIN_CHAR_COUNT = 500
MAX_PRIMARY_EXPAND_ATTEMPTS = 1
MAX_PRIMARY_EXPAND_ATTEMPTS_TREND = 3
MAX_RELAXED_EXPAND_ATTEMPTS_TREND = 2
MAX_RELAXED_EXPAND_ATTEMPTS = 1
MAX_CONSECUTIVE_FAILS = 3
META_DESCRIPTION_MAX_CHARS = 120
SUPPLY_GAP_MIN_SCORE = 55
OPPORTUNITY_MIN_SCORE = 70
OLD_CONTENT_YEAR_THRESHOLD = 2
QUERY_PAGE_RELEVANCE_THRESHOLD = 0.55
TOP_QUERIES_FOR_SUPPLY_CHECK = 40

FORUM_DOMAIN_HINTS = [
    "chiebukuro.yahoo.co.jp",
    "okwave.jp",
    "oshiete.goo.ne.jp",
    "teratail.com",
    "reddit.com",
    "5ch.net",
]
PRIMARY_SOURCE_DOMAIN_HINTS = [
    "amazon.co.jp",
    "amazon.com",
    "rakuten.co.jp",
    "kobo.com",
    "help",
    "support",
]
HOWTO_HINTS = [
    "手順",
    "やり方",
    "方法",
    "設定",
    "対処",
    "解決",
    "できない",
    "直し方",
]
PAIN_SIGNAL_QUERIES = [
    ("chiebukuro", "site:chiebukuro.yahoo.co.jp {query}"),
    ("error", "{query} エラー"),
    ("inquiry", "{query} 問い合わせ"),
]

RELEVANCE_KEYWORDS = [kw.lower() for kw in CORE_KEYWORDS] + [
    "reader",
    "e-reader",
    "ereader",
    "reading device",
]

PILLAR_LINKS = [
    ("KindleとKoboの違い", "/posts/kindle-vs-kobo/"),
    ("Kindle Paperwhiteレビュー", "/posts/kindle-paperwhite-review/"),
    ("Kobo Claraレビュー", "/posts/kobo-clara-review/"),
]

def should_canonicalize_to_kindle_vs_kobo(topic_text: str, title_text: str = "") -> bool:
    text = f"{topic_text}\n{title_text}".lower()
    must = ("kindle" in text) and ("kobo" in text)
    if not must:
        return False

    # Don't treat subscription/service comparisons as device comparisons.
    if any(k in text for k in ["kindle unlimited", "kobo plus", "prime reading", "読み放題", "サブスク"]):
        return False

    has_compare_intent = any(k in text for k in ["徹底比較", "比較", "違い", "どっち", "vs", "選ぶ", "選び方"])
    has_device_context = any(
        k in text
        for k in [
            "電子書籍リーダー",
            "端末",
            "デバイス",
            "e-ink",
            "e ink",
            "電子ペーパー",
            "paperwhite",
            "scribe",
            "clara",
            "libra",
            "sage",
            "elipsa",
        ]
    )
    has_year_or_latest = bool(re.search(r"\b20\d{2}\b", text)) or any(k in text for k in ["最新", "最新版"])
    return has_compare_intent and (has_device_context or has_year_or_latest)


def should_canonicalize_to_kindle_paperwhite_review(topic_text: str, title_text: str = "") -> bool:
    text = f"{topic_text}\n{title_text}".lower()
    if "paperwhite" not in text:
        return False

    # Don't canonicalize cross-brand comparisons.
    has_compare_intent = any(k in text for k in ["徹底比較", "比較", "違い", "どっち", "vs", "選ぶ", "選び方"])
    if ("kobo" in text or "clara" in text) and has_compare_intent:
        return False

    # Focus on "review / should you buy" type intent.
    review_intent = any(k in text for k in ["レビュー", "評判", "口コミ", "実機", "使ってみた", "良いところ", "惜しいところ", "総評"])
    return review_intent or ("第11世代" in text) or ("11世代" in text)


def should_canonicalize_to_kobo_clara_review(topic_text: str, title_text: str = "") -> bool:
    text = f"{topic_text}\n{title_text}".lower()
    if "clara" not in text:
        return False

    has_compare_intent = any(k in text for k in ["徹底比較", "比較", "違い", "どっち", "vs", "選ぶ", "選び方"])
    if ("kindle" in text or "paperwhite" in text) and has_compare_intent:
        return False

    review_intent = any(k in text for k in ["レビュー", "評判", "口コミ", "実機", "使ってみた", "良いところ", "惜しいところ", "総評"])
    return review_intent or ("2e" in text) or ("2 e" in text)

# ---------- prompts ----------
SYSTEM = "あなたは電子書籍・電子リーダー専門メディアの熟練編集者として、日本語でSEOを意識しつつオリジナル記事を作成してください。あなたは世界一のブロガーです。"
USER_TMPL = """\
以下のトピックで、重複しない切り口の高品質な記事を書いてください。

# テーマ
{topic}

# 要件
- 読者が初心者でも理解できるように5つ以上の具体例や対策を盛り込む
- 最新の利用シーンや活用アイデアを含める
- 見出しはH2(##)から開始し、H1(#)は使わない（ページタイトルは別途表示されます）
- 同じH2を連続させず、自然な流れでH2/H3を組み立てる
- Kindle/Koboなどの固有名詞は文脈に応じて出し分ける
- トーンは丁寧だが押し付けがましくしない
- 記事の途中に「## 結論（一次情報からの洞察）」というH2を作り、一般論ではない独自の視点を入れる
- 記事の後半に「## スペック比較表」というH2を作り、Markdownの表形式で競合や旧モデルとの違いを示す
- 内部リンク: 最後に [読書ガイド](/posts/) を1回だけURL付きで入れる
- まとめは簡潔に2〜3文

# 禁止
- 同じ文章や表現をリピートしない
- 競合サイトからの引用をしない
- 不自然なキーワード羅列は避ける
- 同じH2/H3構成を既存記事と近似させない
"""

TREND_USER_TMPL = """\
以下のトピックで、トレンドを踏まえた長文の記事を作成してください。専門的だが読みやすい構成にしてください。

# テーマ
{topic}

# 要件
- 文字数: 約2,000〜2,800字（増やせるなら3,000字歓迎）
- 見出しはH2(##)から開始し、H1(#)は使わない（ページタイトルは別途表示されます）
- 推奨H2構成:
  1. 現在の状況を3〜5行で背景説明
  2. 最新トレンドの概要
  3. 結論（一次情報からの洞察） ※ここだけは「私が感じたこと」として書く
  4. 利用メリット・デメリット
  5. 比較表（Markdown形式）
  6. ユースケースや成功事例
  7. 選び方 or 失敗しないポイント
  8. まとめと次のアクション
  9. Q&Aを2〜3個
- Q&A/FAQはH2内に3問以上、短く明快に回答
- トーン: 実用的かつ親しみやすい

# 禁止
- 同じ内容を繰り返さない
- 不確かな情報を断定しない
- 日本以外の読者を想定しない
"""

REVIEWER_SYSTEM = (
    "あなたは厳しい文章校正者です。事実誤認や重複表現、H2/H3の構成を点検し、"
    "指摘ではなく“修正後の完成稿”のみをMarkdownで返してください。"
    "前置き・見出し外の解説・箇条書きの改善案は書かないでください。"
)
REWRITER_SYSTEM = "あなたはSEOライターです。指定された記事を長文化し、重複を避け、自然な日本語に整えます。"
UPDATE_SYSTEM = (
    "あなたは電子書籍ブログの編集者です。既存記事に追記する補足セクションだけを"
    "Markdownで返してください。前置き・解説・コードフェンスは不要です。"
)
CHECKLIST = """\
以下の観点で修正してください
1) 内容は最新かつ具体的か
2) 重複表現や冗長な文はないか
3) 見出し: H2/H3が自然な流れか、近い見出しが続かないか
4) 読者が次に取れる行動が明確か
5) 内部リンクは末尾に1回だけ[読書ガイド]を入れる
6) トーンは丁寧で押し付けないか
7) 本文にH1（#）は使わない（見出しはH2/##から）
"""
TAG_SYSTEM = "あなたはSEOに詳しい編集者です。記事内容に沿うタグをJSON配列で返してください。"

# Tag pages can easily become thin/duplicated if we let the model invent new tags every day.
# Keep tags within a controlled set to reduce taxonomy bloat and improve topical clustering.
ALLOWED_TAGS: List[str] = [
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

TAG_SYNONYMS: Dict[str, str] = {
    "kindle本セール": "Kindleセール",
    "kindleセール": "Kindleセール",
    "amazonセール": "セール",
    "楽天セール": "セール",
    "電子書籍セール": "セール",
    "楽天ポイント": "楽天",
    "amazonポイント": "Amazon",
    "amazonポイント還元": "Amazon",
    "rakutenポイント": "楽天",
    "adobe脆弱性": "セキュリティ",
    "acrobat更新": "セキュリティ",
    "pdfセキュリティ": "セキュリティ",
    "セキュリティ情報": "セキュリティ",
    "任意コード実行": "セキュリティ",
}

RAKUTEN_API_ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
PEXELS_API_ENDPOINT = "https://api.pexels.com/v1/search"

RAKUTEN_FALLBACK_ITEMS: List[Dict[str, str]] = [
    {
        "title": "Kindle Paperwhite 用カバー",
        "url": "https://search.rakuten.co.jp/search/mall/Kindle+Paperwhite+%E3%82%AB%E3%83%90%E3%83%BC/",
        "price_text": "",
    },
    {
        "title": "Kobo Clara 用カバー",
        "url": "https://search.rakuten.co.jp/search/mall/Kobo+Clara+%E3%82%AB%E3%83%90%E3%83%BC/",
        "price_text": "",
    },
    {
        "title": "電子書籍リーダー 保護フィルム",
        "url": "https://search.rakuten.co.jp/search/mall/%E9%9B%BB%E5%AD%90%E6%9B%B8%E7%B1%8D%E3%83%AA%E3%83%BC%E3%83%80%E3%83%BC+%E4%BF%9D%E8%AD%B7%E3%83%95%E3%82%A3%E3%83%AB%E3%83%A0/",
        "price_text": "",
    },
]


def _is_model_availability_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    if "model" not in msg:
        return False
    return any(
        key in msg
        for key in [
            "not found",
            "does not exist",
            "not available",
            "do not have access",
            "insufficient permissions",
            "unsupported",
        ]
    )


def _extract_response_text(resp) -> str:
    text = (getattr(resp, "output_text", None) or "").strip()
    if text:
        return text

    chunks: list[str] = []
    for item in (getattr(resp, "output", None) or []):
        if getattr(item, "type", "") != "message":
            continue
        for content in (getattr(item, "content", None) or []):
            if getattr(content, "type", "") not in ("output_text", "text"):
                continue
            piece = (getattr(content, "text", None) or "").strip()
            if piece:
                chunks.append(piece)
    return "\n".join(chunks).strip()


def generate_openai_text(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    if OPENAI_CLIENT is None:
        raise RuntimeError("OPENAI_API_KEY not set")
    last_error: Exception | None = None
    for model in OPENAI_MODEL_CANDIDATES:
        try:
            resp = OPENAI_CLIENT.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            text = _extract_response_text(resp)
            if text:
                return text
            raise RuntimeError(f"Empty response text from model '{model}'.")
        except Exception as exc:
            last_error = exc
            if _is_model_availability_error(exc):
                print(f"[warn] OpenAI model '{model}' unavailable. Trying fallback model.")
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("OpenAI request failed with no explicit error.")


def _strip_markdown_code_fence(text: str) -> str:
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    return s.strip()


def parse_frontmatter(md_text: str):
    m = re.search(r"^---\s*(.*?)\s*---", md_text, re.S | re.M)
    data = {}
    if not m:
        return data
    fm = m.group(1)

    def pick(key):
        mm = re.search(rf"^{key}:\s*(.+)$", fm, re.M)
        if not mm:
            return None
        val = mm.group(1).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        return val

    data["title"] = pick("title")
    data["slug"] = pick("slug")
    data["date"] = pick("date")
    data["lastmod"] = pick("lastmod")
    data["url"] = pick("url")

    alias_list: list[str] = []
    alias_block = re.search(r"(?ms)^aliases:\s*(.*?)(?=^[A-Za-z0-9_-]+:\s|\Z)", fm)
    if alias_block:
        for line in alias_block.group(1).splitlines():
            mm = re.match(r"^\s*-\s*(.+?)\s*$", line)
            if not mm:
                continue
            alias = mm.group(1).strip().strip('"').strip("'")
            if alias:
                alias_list.append(alias)
    if alias_list:
        data["aliases"] = alias_list
    return data


def permalink_from(date_str: str, slug: str):
    y, m, _ = date_str.split("-")
    return f"/posts/{y}/{m}/{slug}/"


def list_existing_posts(out_dir: pathlib.Path):
    posts = []
    for p in sorted(out_dir.glob("*.md")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        fm = parse_frontmatter(txt)
        date = fm.get("date")
        lastmod = fm.get("lastmod")
        slug = fm.get("slug")
        title = fm.get("title")
        if (not date or not slug) and re.match(r"\d{4}-\d{2}-\d{2}", p.name):
            date_guess = p.name[:10]
            slug_guess = re.sub(r"^\d{4}-\d{2}-\d{2}-\d+-", "", p.name)
            slug_guess = slug_guess[:-3] if slug_guess.endswith(".md") else slug_guess
            date = date or date_guess
            slug = slug or slug_guess
        if not date or not slug:
            continue
        url = fm.get("url") or permalink_from(date, slug)
        aliases = fm.get("aliases") or []
        posts.append(
            {
                "url": url,
                "aliases": aliases,
                "title": title or slug,
                "date": date,
                "lastmod": lastmod or date,
                "slug": slug,
                "file_path": str(p),
            }
        )
    return posts


def recent_titles_within(posts: list[dict], days: int = 7) -> set[str]:
    recent = set()
    today = datetime.date.today()
    for p in posts:
        try:
            d = datetime.date.fromisoformat(p.get("date", ""))
        except Exception:
            continue
        if (today - d).days <= days:
            t = (p.get("title") or "").strip().lower()
            if t:
                recent.add(t)
    return recent


def extract_h2_headings(markdown: str) -> set[str]:
    headings = re.findall(r"(?m)^##\s+(.+)", markdown)
    return {re.sub(r"\s+", " ", h).strip() for h in headings if h.strip()}


def load_existing_headings(out_dir: pathlib.Path):
    data = []
    for p in sorted(out_dir.glob("*.md")):
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        data.append((p.name, extract_h2_headings(txt)))
    return data


def is_duplicate_headings(candidate: set[str], pool: list[tuple[str, set[str]]], threshold: float = 0.6) -> bool:
    if not candidate:
        return False
    for _, headings in pool:
        if not headings:
            continue
        overlap = len(candidate & headings)
        if overlap and overlap / max(len(candidate), 1) >= threshold:
            return True
    return False


def _tokenize(text: str) -> set[str]:
    cleaned = re.sub(r"[^0-9A-Za-z\u3040-\u30ff\u4e00-\u9fff]+", " ", text.lower())
    tokens = {t for t in cleaned.split() if len(t) >= 2}
    return tokens


def _normalize_for_similarity(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"\s+", "", t)
    # Treat common separators as noise to improve Japanese title matching.
    t = t.replace("・", "").replace("|", "")
    t = re.sub(r"[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+", "", t)
    return t


def _char_ngrams(text: str, n: int = 2) -> set[str]:
    if not text:
        return set()
    if len(text) < n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def is_similar_title(title: str, existing: list[str], threshold: float = 0.65) -> bool:
    """Check Jaccard similarity to avoid near-duplicate titles."""
    cand_tokens = _tokenize(title)
    cand_norm = _normalize_for_similarity(title)
    cand_grams = _char_ngrams(cand_norm, n=2) if cand_norm else set()
    for t in existing:
        base_tokens = _tokenize(t)
        if cand_tokens and base_tokens:
            overlap = len(cand_tokens & base_tokens)
            union = len(cand_tokens | base_tokens)
            if union and overlap / union >= threshold:
                return True

        # Japanese titles often have few separators, so token Jaccard can miss near-duplicates.
        base_norm = _normalize_for_similarity(t)
        if cand_norm and base_norm:
            if difflib.SequenceMatcher(None, cand_norm, base_norm).ratio() >= 0.55:
                return True
            if cand_grams and _jaccard(cand_grams, _char_ngrams(base_norm, n=2)) >= 0.25:
                return True
    return False


def is_similar_topic(topic: str, existing: list[str], threshold: float = 0.6) -> bool:
    """Avoid generating multiple posts on near-identical topics."""
    return is_similar_title(topic, existing, threshold=threshold)


def parse_bool_arg(value):
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("Expected true/false.")


def normalize_site_path(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    path = parsed.path if (parsed.scheme or parsed.netloc) else str(value)
    if not path:
        return ""
    path = "/" + path.lstrip("/")
    if BASE_URL_PATH and (path == BASE_URL_PATH or path.startswith(BASE_URL_PATH + "/")):
        path = path[len(BASE_URL_PATH) :] or "/"
        if not path.startswith("/"):
            path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def normalize_domain(url: str) -> str:
    try:
        domain = (urlparse(url).netloc or "").lower().strip()
    except Exception:
        domain = ""
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def has_domain_hint(domain: str, hints: list[str]) -> bool:
    d = (domain or "").lower()
    if not d:
        return False
    for hint in hints:
        h = hint.lower()
        if d == h or d.endswith("." + h) or h in d:
            return True
    return False


def _safe_total_results(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


class CSEBudget:
    def __init__(self, daily_limit: int, budget: int):
        self.max_calls = max(0, min(daily_limit, budget))
        self.used_calls = 0
        self.disabled_reason = ""

    def consume(self) -> bool:
        if self.disabled_reason:
            return False
        if self.used_calls >= self.max_calls:
            self.disabled_reason = "budget_exhausted"
            return False
        self.used_calls += 1
        return True

    def disable(self, reason: str):
        self.disabled_reason = reason


def fetch_gsc_query_page_rows(days: int, max_rows: int = GSC_MAX_ROWS) -> list[dict]:
    if not GSC_SERVICE_ACCOUNT_FILE:
        print("[warn] GSC_SERVICE_ACCOUNT_FILE is not set. Skipping GSC demand fetch.")
        return []
    if not GSC_SITE_URL:
        print("[warn] GSC_SITE_URL is not set. Skipping GSC demand fetch.")
        return []
    key_path = pathlib.Path(GSC_SERVICE_ACCOUNT_FILE)
    if not key_path.exists():
        raw_cred = (GSC_SERVICE_ACCOUNT_FILE or "").strip()
        inline_like = raw_cred.startswith("{") or len(raw_cred) > 200
        if inline_like:
            print("[warn] GSC_SERVICE_ACCOUNT_FILE must be a JSON file path, but inline text was provided.")
        else:
            print(f"[warn] GSC credential file not found: {key_path}")
        return []
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception:
        print("[warn] Google API dependencies are missing. Skipping GSC demand fetch.")
        return []

    today = datetime.date.today()
    start = today - datetime.timedelta(days=max(1, days))
    all_rows: list[dict] = []
    try:
        creds = service_account.Credentials.from_service_account_file(
            str(key_path),
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        start_row = 0
        while len(all_rows) < max_rows:
            row_limit = min(25000, max_rows - len(all_rows))
            body = {
                "startDate": start.isoformat(),
                "endDate": today.isoformat(),
                "dimensions": ["query", "page"],
                "rowLimit": row_limit,
                "startRow": start_row,
            }
            resp = service.searchanalytics().query(siteUrl=GSC_SITE_URL, body=body).execute()
            rows = resp.get("rows") or []
            if not rows:
                break
            for row in rows:
                keys = row.get("keys") or []
                if len(keys) < 2:
                    continue
                query = re.sub(r"\s+", " ", str(keys[0]).strip())
                page = str(keys[1]).strip()
                if not query or not page:
                    continue
                all_rows.append(
                    {
                        "query": query,
                        "page": page,
                        "clicks": float(row.get("clicks") or 0.0),
                        "impressions": float(row.get("impressions") or 0.0),
                        "ctr": float(row.get("ctr") or 0.0),
                        "position": float(row.get("position") or 0.0),
                    }
                )
            if len(rows) < row_limit:
                break
            start_row += len(rows)
    except Exception as exc:
        print(f"[warn] Failed to fetch GSC data: {exc}")
        return []
    return all_rows


def aggregate_gsc_queries(rows: list[dict], min_impressions: int, min_position: int, limit: int = TOP_QUERIES_FOR_SUPPLY_CHECK):
    by_query: dict[str, dict] = {}
    for row in rows:
        query = re.sub(r"\s+", " ", (row.get("query") or "").strip())
        if not query or not has_core_keyword(query):
            continue
        impressions = float(row.get("impressions") or 0.0)
        if impressions <= 0:
            continue
        entry = by_query.setdefault(
            query,
            {
                "query": query,
                "impressions": 0.0,
                "clicks": 0.0,
                "position_sum": 0.0,
                "page": "",
                "page_impressions": 0.0,
            },
        )
        entry["impressions"] += impressions
        entry["clicks"] += float(row.get("clicks") or 0.0)
        entry["position_sum"] += float(row.get("position") or 0.0) * impressions
        if impressions > entry["page_impressions"]:
            entry["page"] = row.get("page") or ""
            entry["page_impressions"] = impressions

    out: list[dict] = []
    for query, entry in by_query.items():
        impressions = entry["impressions"]
        if impressions < min_impressions:
            continue
        position = entry["position_sum"] / impressions if impressions else 0.0
        if position < min_position:
            continue
        ctr = (entry["clicks"] / impressions) if impressions else 0.0
        out.append(
            {
                "query": query,
                "page": entry["page"],
                "impressions": impressions,
                "position": position,
                "ctr": ctr,
            }
        )
    out.sort(key=lambda x: x["impressions"], reverse=True)
    return out[:limit]


def _extract_http_error_message(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
        message = ((payload.get("error") or {}).get("message") or "").strip()
        if message:
            return message
    except Exception:
        pass
    return (response.text or "").strip()[:300]


def resolve_serp_provider(provider: str = "auto") -> tuple[str, str]:
    target = (provider or EXTERNAL_SERP_PROVIDER or "auto").strip().lower()
    if target not in {"auto", "brave", "cse"}:
        target = "auto"

    has_brave = bool(BRAVE_SEARCH_API_KEY)
    has_cse = bool(GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX)

    if target == "brave":
        return ("brave", "") if has_brave else ("", "missing_brave_search_credentials")
    if target == "cse":
        return ("cse", "") if has_cse else ("", "missing_google_cse_credentials")

    if has_brave:
        return "brave", ""
    if has_cse:
        return "cse", ""
    return "", "missing_serp_credentials"


def fetch_google_cse(query: str, budget: CSEBudget, num: int = 10) -> tuple[dict | None, str | None]:
    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_CX:
        return None, "missing_credentials"
    if not budget.consume():
        return None, budget.disabled_reason or "budget_exhausted"
    endpoint = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_CSE_API_KEY,
        "cx": GOOGLE_CSE_CX,
        "q": query,
        "num": max(1, min(10, num)),
        "hl": "ja",
        "safe": "off",
    }
    try:
        resp = requests.get(endpoint, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        items = []
        for item in data.get("items") or []:
            link = item.get("link") or ""
            title = item.get("title") or ""
            snippet = item.get("snippet") or ""
            if not link:
                continue
            items.append({"link": link, "title": title, "snippet": snippet})
        total_results = _safe_total_results((data.get("searchInformation") or {}).get("totalResults"))
        return {"items": items, "total_results": total_results}, None
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        message = _extract_http_error_message(exc.response).lower()
        if status == 429:
            budget.disable("quota_or_rate_limit")
        elif status in (400, 403) and (
            "api key not valid" in message
            or "does not have the access to custom search json api" in message
            or "access not configured" in message
            or "forbidden" in message
        ):
            budget.disable("serp_access_denied")
        elif status == 403:
            budget.disable("quota_or_rate_limit")
        return None, f"http_{status}"
    except Exception as exc:
        return None, f"request_error:{exc}"


def fetch_brave_search(query: str, budget: CSEBudget, num: int = 10) -> tuple[dict | None, str | None]:
    if not BRAVE_SEARCH_API_KEY:
        return None, "missing_credentials"
    if not budget.consume():
        return None, budget.disabled_reason or "budget_exhausted"
    endpoint = "https://api.search.brave.com/res/v1/web/search"
    params = {
        "q": query,
        "count": max(1, min(20, num)),
        "search_lang": "jp",
        "safesearch": "off",
    }
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    }
    try:
        resp = requests.get(endpoint, headers=headers, params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        web = data.get("web") or {}
        items = []
        for item in web.get("results") or []:
            link = item.get("url") or ""
            title = item.get("title") or ""
            snippet = item.get("description") or item.get("snippet") or ""
            if not link:
                continue
            items.append({"link": link, "title": title, "snippet": snippet})
        total_results = _safe_total_results(web.get("total"))
        if total_results <= 0:
            total_results = len(items)
        return {"items": items, "total_results": total_results}, None
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else 0
        if status == 429:
            budget.disable("quota_or_rate_limit")
        elif status in (401, 403):
            budget.disable("serp_access_denied")
        return None, f"http_{status}"
    except Exception as exc:
        return None, f"request_error:{exc}"


def fetch_external_serp(provider: str, query: str, budget: CSEBudget, num: int = 10) -> tuple[dict | None, str | None]:
    if provider == "brave":
        return fetch_brave_search(query, budget, num=num)
    if provider == "cse":
        return fetch_google_cse(query, budget, num=num)
    return None, "unsupported_serp_provider"


def compute_supply_gap_metrics(items: list[dict]) -> dict:
    if not items:
        return {
            "old_content_ratio": 0.5,
            "domain_concentration": 1.0,
            "howto_lack_ratio": 1.0,
            "primary_source_lack_ratio": 1.0,
            "forum_pressure": 0.0,
            "supply_gap_score": 60.0,
        }

    domain_counts: Counter[str] = Counter()
    howto_hits = 0
    primary_hits = 0
    forum_hits = 0
    old_hits = 0
    dated_hits = 0
    current_year = datetime.date.today().year

    for item in items:
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        link = item.get("link") or ""
        text = f"{title} {snippet}"
        lower_text = text.lower()
        domain = normalize_domain(link)
        if domain:
            domain_counts[domain] += 1

        if any(k in text for k in HOWTO_HINTS):
            howto_hits += 1
        if "公式" in text or has_domain_hint(domain, PRIMARY_SOURCE_DOMAIN_HINTS):
            primary_hits += 1
        if has_domain_hint(domain, FORUM_DOMAIN_HINTS):
            forum_hits += 1

        years = [int(y) for y in re.findall(r"\b(20\d{2})\b", lower_text)]
        if years:
            dated_hits += 1
            if max(years) <= current_year - OLD_CONTENT_YEAR_THRESHOLD:
                old_hits += 1

    total = max(len(items), 1)
    old_content_ratio = (old_hits / dated_hits) if dated_hits else 0.5
    domain_concentration = (max(domain_counts.values()) / total) if domain_counts else 1.0
    howto_lack_ratio = 1.0 - (howto_hits / total)
    primary_source_lack_ratio = 1.0 - (primary_hits / total)
    forum_pressure = forum_hits / total

    score = (
        old_content_ratio * 20
        + domain_concentration * 20
        + howto_lack_ratio * 25
        + primary_source_lack_ratio * 20
        + forum_pressure * 15
    )
    supply_gap_score = max(0.0, min(100.0, score))
    return {
        "old_content_ratio": round(old_content_ratio, 4),
        "domain_concentration": round(domain_concentration, 4),
        "howto_lack_ratio": round(howto_lack_ratio, 4),
        "primary_source_lack_ratio": round(primary_source_lack_ratio, 4),
        "forum_pressure": round(forum_pressure, 4),
        "supply_gap_score": round(supply_gap_score, 2),
    }


def compute_pain_signal_score(signal_totals: dict[str, int]) -> float:
    def _norm(total: int) -> float:
        return min(1.0, math.log10(total + 1) / 6.0)

    score = (
        _norm(signal_totals.get("chiebukuro", 0)) * 10
        + _norm(signal_totals.get("error", 0)) * 10
        + _norm(signal_totals.get("inquiry", 0)) * 10
    )
    return round(score, 2)


def compute_demand_score(impressions: float, position: float) -> float:
    return round(math.log10(max(impressions, 0.0) + 1.0) * 20.0 + min(max(position, 0.0), 30.0), 2)


def query_post_relevance(query: str, post_title: str, post_slug: str) -> float:
    query_tokens = _tokenize(query)
    post_text = f"{post_title} {post_slug.replace('-', ' ')}".strip()
    post_tokens = _tokenize(post_text)
    token_jaccard = 0.0
    if query_tokens and post_tokens:
        token_jaccard = len(query_tokens & post_tokens) / max(len(query_tokens | post_tokens), 1)
    seq = difflib.SequenceMatcher(None, _normalize_for_similarity(query), _normalize_for_similarity(post_text)).ratio()
    return round((token_jaccard * 0.6) + (seq * 0.4), 4)


def build_post_url_index(posts: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for post in posts:
        permalink_guess = ""
        if post.get("date") and post.get("slug"):
            try:
                permalink_guess = permalink_from(post.get("date", ""), post.get("slug", ""))
            except Exception:
                permalink_guess = ""
        candidates = [
            post.get("url") or "",
            permalink_guess,
            f"/posts/{post.get('slug')}/" if post.get("slug") else "",
        ]
        aliases = post.get("aliases") or []
        for alias in aliases:
            candidates.append(alias)
        for raw in candidates:
            normalized = normalize_site_path(raw)
            if normalized:
                index.setdefault(normalized, post)
    return index


def find_best_post_match(query: str, posts: list[dict]) -> tuple[dict | None, float]:
    best_post = None
    best_score = 0.0
    for post in posts:
        score = query_post_relevance(query, post.get("title", ""), post.get("slug", ""))
        if score > best_score:
            best_score = score
            best_post = post
    return best_post, best_score


def write_supply_audit_report(report_rows: list[dict], metadata: dict):
    payload = {
        "generated_at": datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "metadata": metadata,
        "rows": report_rows,
    }
    try:
        SUPPLY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUPPLY_AUDIT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[info] Supply audit report written: {SUPPLY_AUDIT_PATH}")
    except Exception as exc:
        print(f"[warn] Failed to write supply audit report: {exc}")


def collect_external_supply_candidates(
    existing_posts: list[dict],
    gsc_days: int,
    gsc_min_impressions: int,
    gsc_min_position: int,
    cse_budget: int,
    serp_provider: str = "auto",
) -> dict:
    result = {
        "new_topics": [],
        "update_candidates": [],
        "audit_rows": [],
        "meta": {
            "cse_budget": cse_budget,
            "cse_used_calls": 0,
            "serp_budget": cse_budget,
            "serp_used_calls": 0,
            "serp_provider": "",
            "source": "gsc+serp",
            "fallback_reason": "",
            "evaluated_queries": 0,
        },
    }

    provider, provider_err = resolve_serp_provider(serp_provider)
    if not provider:
        result["meta"]["fallback_reason"] = provider_err or "missing_serp_credentials"
        return result
    result["meta"]["serp_provider"] = provider
    result["meta"]["source"] = f"gsc+{provider}"

    gsc_rows = fetch_gsc_query_page_rows(days=gsc_days, max_rows=GSC_MAX_ROWS)
    if not gsc_rows:
        result["meta"]["fallback_reason"] = "gsc_data_unavailable"
        return result

    aggregated = aggregate_gsc_queries(gsc_rows, min_impressions=gsc_min_impressions, min_position=gsc_min_position)
    if not aggregated:
        result["meta"]["fallback_reason"] = "no_gsc_queries_after_filter"
        return result

    budget = CSEBudget(CSE_DAILY_FREE_LIMIT, cse_budget)
    post_index = build_post_url_index(existing_posts)
    accepted_new: list[str] = []
    accepted_updates: list[dict] = []

    for entry in aggregated:
        query = entry["query"]
        serp, serp_err = fetch_external_serp(provider, query, budget, num=10)
        if serp is None:
            result["audit_rows"].append(
                {
                    "query": query,
                    "status": "skipped",
                    "reason": serp_err or f"{provider}_fetch_failed",
                    "impressions": round(entry["impressions"], 2),
                    "position": round(entry["position"], 2),
                }
            )
            if budget.disabled_reason in {"budget_exhausted", "quota_or_rate_limit", "serp_access_denied"}:
                break
            continue

        supply_metrics = compute_supply_gap_metrics(serp.get("items") or [])
        pain_totals: dict[str, int] = {}
        pain_errors: dict[str, str] = {}
        for label, query_tpl in PAIN_SIGNAL_QUERIES:
            sub_query = query_tpl.format(query=query)
            sub_resp, sub_err = fetch_external_serp(provider, sub_query, budget, num=10)
            if sub_resp is None:
                pain_totals[label] = 0
                if sub_err:
                    pain_errors[label] = sub_err
            else:
                pain_totals[label] = sub_resp.get("total_results") or 0
        pain_score = compute_pain_signal_score(pain_totals)
        demand_score = compute_demand_score(entry["impressions"], entry["position"])
        opportunity_score = round(demand_score + supply_metrics["supply_gap_score"] + pain_score, 2)

        match_method = "none"
        match_relevance = 0.0
        matched_post = None

        page_path = normalize_site_path(entry.get("page") or "")
        if page_path and page_path in post_index:
            matched_post = post_index[page_path]
            match_method = "gsc_page"
            match_relevance = query_post_relevance(query, matched_post.get("title", ""), matched_post.get("slug", ""))
        else:
            best_post, best_score = find_best_post_match(query, existing_posts)
            if best_post and best_score >= QUERY_PAGE_RELEVANCE_THRESHOLD:
                matched_post = best_post
                match_method = "similarity"
                match_relevance = best_score

        action = "new"
        if matched_post and match_relevance >= QUERY_PAGE_RELEVANCE_THRESHOLD and entry["position"] >= gsc_min_position:
            action = "update"

        accepted = (
            supply_metrics["supply_gap_score"] >= SUPPLY_GAP_MIN_SCORE
            and opportunity_score >= OPPORTUNITY_MIN_SCORE
        )
        if accepted:
            if action == "update" and matched_post and matched_post.get("file_path"):
                accepted_updates.append(
                    {
                        "query": query,
                        "opportunity_score": opportunity_score,
                        "demand_score": demand_score,
                        "supply_gap_score": supply_metrics["supply_gap_score"],
                        "pain_signal_score": pain_score,
                        "supply_metrics": supply_metrics,
                        "match_method": match_method,
                        "match_relevance": round(match_relevance, 4),
                        "post_title": matched_post.get("title"),
                        "post_slug": matched_post.get("slug"),
                        "post_file_path": matched_post.get("file_path"),
                        "page": entry.get("page"),
                    }
                )
            else:
                accepted_new.append(query)

        result["audit_rows"].append(
            {
                "query": query,
                "status": "accepted" if accepted else "rejected",
                "action": action,
                "reason": "",
                "impressions": round(entry["impressions"], 2),
                "position": round(entry["position"], 2),
                "ctr": round(entry["ctr"], 4),
                "gsc_page": entry.get("page"),
                "scores": {
                    "demand_score": demand_score,
                    "supply_gap_score": supply_metrics["supply_gap_score"],
                    "pain_signal_score": pain_score,
                    "opportunity_score": opportunity_score,
                },
                "supply_metrics": {
                    "old_content_ratio": supply_metrics["old_content_ratio"],
                    "domain_concentration": supply_metrics["domain_concentration"],
                    "howto_lack_ratio": supply_metrics["howto_lack_ratio"],
                    "primary_source_lack_ratio": supply_metrics["primary_source_lack_ratio"],
                    "forum_pressure": supply_metrics["forum_pressure"],
                },
                "pain_signal_totals": pain_totals,
                "pain_signal_errors": pain_errors,
                "match": {
                    "method": match_method,
                    "relevance": round(match_relevance, 4),
                    "post_slug": matched_post.get("slug") if matched_post else "",
                },
            }
        )
        if budget.disabled_reason in {"budget_exhausted", "quota_or_rate_limit", "serp_access_denied"}:
            break

    unique_updates: list[dict] = []
    seen_update_files: set[str] = set()
    for item in sorted(accepted_updates, key=lambda x: x["opportunity_score"], reverse=True):
        file_path = item.get("post_file_path") or ""
        if not file_path or file_path in seen_update_files:
            continue
        seen_update_files.add(file_path)
        unique_updates.append(item)

    result["new_topics"] = _unique_preserve_order(accepted_new)
    result["update_candidates"] = unique_updates
    result["meta"]["cse_used_calls"] = budget.used_calls
    result["meta"]["serp_used_calls"] = budget.used_calls
    result["meta"]["evaluated_queries"] = len(result["audit_rows"])
    if budget.disabled_reason and not result["meta"]["fallback_reason"]:
        result["meta"]["fallback_reason"] = budget.disabled_reason
    return result


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if not x:
            continue
        key = x.strip()
        if not key:
            continue
        low = key.lower()
        if low in seen:
            continue
        out.append(key)
        seen.add(low)
    return out


def generate_fallback_topic_candidates(seed: int) -> list[str]:
    rng = random.Random(seed)
    candidates: list[str] = list(FALLBACK_TOPIC_SEEDS)

    for tpl in FALLBACK_TOPIC_TEMPLATES:
        if "{knob}" in tpl:
            for scenario in FALLBACK_SCENARIOS:
                for knob in FALLBACK_READABILITY_KNOBS:
                    candidates.append(tpl.format(scenario=scenario, knob=knob))
        elif "{format}" in tpl:
            for scenario in FALLBACK_SCENARIOS:
                for fmt in FALLBACK_FORMATS:
                    candidates.append(tpl.format(scenario=scenario, format=fmt))
        elif "{tool}" in tpl:
            for tool in FALLBACK_NOTE_TOOLS:
                candidates.append(tpl.format(tool=tool))
        elif "{area}" in tpl:
            for area in FALLBACK_KDP_AREAS:
                candidates.append(tpl.format(area=area))
        else:
            candidates.append(tpl)

    candidates = _unique_preserve_order(candidates)
    rng.shuffle(candidates)
    return candidates


def build_fallback_topic_pool(
    existing_titles: list[str],
    used_titles: set[str],
    used_slugs: set[str],
    recent_titles: set[str],
    limit: int = 250,
) -> list[str]:
    seed = datetime.date.today().toordinal()
    candidates = generate_fallback_topic_candidates(seed)

    def accept(topic: str, check_similarity: bool) -> bool:
        topic_clean = re.sub(r"\s+", " ", (topic or "").strip())
        if not topic_clean:
            return False
        low = topic_clean.lower()
        if low in used_titles or low in recent_titles:
            return False
        if not has_core_keyword(topic_clean):
            return False
        if should_canonicalize_to_kindle_vs_kobo(topic_clean) and (CONTENT_POSTS_DIR / "kindle-vs-kobo.md").exists():
            return False
        if should_canonicalize_to_kindle_paperwhite_review(topic_clean) and (CONTENT_POSTS_DIR / "kindle-paperwhite-review.md").exists():
            return False
        if should_canonicalize_to_kobo_clara_review(topic_clean) and (CONTENT_POSTS_DIR / "kobo-clara-review.md").exists():
            return False

        slug_base = slugify_lib(topic_clean, lowercase=True, max_length=60, separator="-")
        if not slug_base or slug_base in used_slugs:
            return False

        if check_similarity and is_similar_topic(topic_clean, existing_titles, threshold=0.6):
            return False
        return True

    pool: list[str] = []
    for t in candidates:
        if accept(t, check_similarity=True):
            pool.append(t)
        if len(pool) >= limit:
            return pool

    # If we got too few, relax similarity a bit (slug/title uniqueness is still enforced).
    for t in candidates:
        if t in pool:
            continue
        if accept(t, check_similarity=False):
            pool.append(t)
        if len(pool) >= limit:
            break
    return pool


def collect_candidates(max_needed: int, fallback_topics: list[str] | None = None):
    """RSSから候補を集め、足りなければfallbackで補う"""
    items = []
    try:
        import importlib.util
        if importlib.util.find_spec("feedparser") is None:
            raise ImportError
        import feedparser
        for url in RSS_SOURCES:
            try:
                feed = feedparser.parse(url)
                for e in feed.entries[:30]:
                    title = (getattr(e, "title", "") or "").strip()
                    summary = (getattr(e, "summary", "") or "").strip()
                    combined = f"{title} {summary}"
                    if has_core_keyword(combined):
                        items.append(title)
            except Exception:
                pass
    except ImportError:
        items = []

    seen = set()
    uniq = []
    for t in items:
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"【.*?】|\\[.*?\\]|\\(.*?\\)|［.*?］", "", t).strip()
        t = re.sub(r"…+$", "", t)
        if t and t not in seen:
            uniq.append(t)
            seen.add(t)

    seed = datetime.date.today().toordinal()
    random.Random(seed).shuffle(uniq)

    fallback_list = fallback_topics or FALLBACK_TOPIC_SEEDS
    for fb in fallback_list:
        if len(uniq) >= max_needed:
            break
        if fb not in seen:
            uniq.append(fb)
            seen.add(fb)

    return uniq[:max_needed]


def ensure_pillar_links(text: str) -> str:
    heading = "## 関連ガイド"
    lower_text = text.lower()
    missing = [(title, url) for title, url in PILLAR_LINKS if url.lower() not in lower_text]
    if not missing or heading in text:
        return text
    lines = ["", heading, ""]
    for title, url in missing:
        lines.append(f"- [{title}]({url})")
    return text.rstrip() + "\n" + "\n".join(lines) + "\n"


def yaml_escape(value: str) -> str:
    """Escape a value for use inside a double-quoted YAML string."""
    v = (value or "").replace("\\", "\\\\").replace('"', '\\"')
    v = re.sub(r"\s+", " ", v).strip()
    return v


def generate_meta_description(topic: str, draft: str, max_chars: int = META_DESCRIPTION_MAX_CHARS) -> str:
    """Create a concise, unique meta description from generated content."""
    text = draft or ""
    text = re.sub(r"(?s)```.*?```", " ", text)
    text = re.sub(r"(?m)^#+\s+.*$", " ", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"(?i)\bphoto by\b.*?\bon pexels\b", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        fallback = f"{topic}のポイントと、選び方・手順をわかりやすくまとめました。"
        return fallback[:max_chars]

    desc = text[:max_chars].rstrip()
    if desc and desc[-1] not in "。.!?！？":
        desc += "。"
    return desc


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text))


def count_chars(text: str) -> int:
    return len(text.replace("\n", ""))


def has_core_keyword(text: str) -> bool:
    normalized = (text or "").lower()
    return any(keyword in normalized for keyword in RELEVANCE_KEYWORDS)


def contains_relevant_keyword(text: str) -> bool:
    return has_core_keyword(text)


def expand_to_min_words(topic: str, draft: str, min_words: int, min_chars: int, max_attempts: int) -> str:
    attempts = 0
    while (count_words(draft) < min_words or count_chars(draft) < min_chars) and attempts < max_attempts:
        attempts += 1
        expand_prompt = dedent(
            f"""\
            現在{count_words(draft)}語、{count_chars(draft)}文字です。内容を具体的に広げて、{topic}に関する独自の視点と手順を追加してください。
            - 目標: {min_words}語以上、{min_chars}文字以上
            - 事例や数字、手順をできるだけ入れる
            - 重複表現は避ける
            - 読者がすぐ行動できるようにする

            修正対象:

            --- draft ---
            {draft}
            --- draft ---
            """
        )
        draft = generate_openai_text(REWRITER_SYSTEM, expand_prompt, temperature=0.5).strip()
    return draft


def _normalize_allowed_tag(tag: str) -> str | None:
    t = re.sub(r"\s+", " ", (tag or "").strip())
    if not t:
        return None
    key = t.lower()
    t = TAG_SYNONYMS.get(key, t)
    if t not in set(ALLOWED_TAGS):
        return None
    return t


def _infer_core_tags(topic: str, draft: str) -> List[str]:
    text = f"{topic}\n{draft}".lower()
    inferred: List[str] = ["電子書籍"]

    if "kindle" in text:
        inferred.append("Kindle")
    if "kobo" in text:
        inferred.append("Kobo")

    if any(k in text for k in ["e-ink", "e ink", "電子ペーパー", "電子書籍リーダー", "端末", "デバイス"]):
        inferred.append("電子書籍リーダー")

    if any(k in text for k in ["比較", "違い", "どっち", "vs", "徹底比較"]):
        inferred.append("比較レビュー")
    if any(k in text for k in ["レビュー", "評判", "口コミ", "使ってみた", "実機", "感想", "評価"]):
        inferred.append("レビュー")

    if any(k in text for k in ["選び方", "おすすめ", "買う", "購入", "どれを選ぶ"]):
        inferred.append("端末選び")

    if any(k in text for k in ["読書術", "読書習慣", "集中", "目が疲れ", "快眠", "寝る前"]):
        inferred.append("読書術")

    if any(k in text for k in ["使い方", "手順", "方法", "コツ"]):
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

    if any(k in text for k in ["ai", "chatgpt", "gemini", "notebooklm"]):
        inferred.append("AI")

    if any(k in text for k in ["ニュース", "発表", "終了", "アップデート", "リリース"]):
        inferred.append("ニュース")

    if any(k in text for k in ["脆弱性", "セキュリティ", "不正", "攻撃"]):
        inferred.append("セキュリティ")
    if any(k in text for k in ["プライバシー", "個人情報"]):
        inferred.append("プライバシー")

    # Keep only allowed tags and preserve order.
    out: List[str] = []
    seen = set()
    allowed = set(ALLOWED_TAGS)
    for t in inferred:
        if t in allowed and t not in seen:
            out.append(t)
            seen.add(t)
    return out


def generate_tags(topic: str, draft: str, max_tags: int = 5):
    fallback = ["電子書籍", "Kindle", "Kobo", "読書術"]
    preview = re.sub(r"\s+", " ", draft.strip())[:1200]
    allowed_text = " / ".join(ALLOWED_TAGS)
    prompt = f"""テーマ: {topic}

前文抜粋: {preview}

次のタグ候補の中から、記事内容に合うタグを{max_tags}個まで選び、JSON配列で返してください。
タグ候補: {allowed_text}

ルール:
- 候補にないタグは作らない
- できれば「電子書籍」「Kindle」「Kobo」など主要語を優先"""
    try:
        raw_tags = generate_openai_text(TAG_SYSTEM, prompt, temperature=0.2)
        tags = json.loads(_strip_markdown_code_fence(raw_tags))
        if not isinstance(tags, list):
            raise ValueError("tag output is not a list")
        cleaned: List[str] = []
        for tag in tags:
            if not isinstance(tag, str):
                continue
            t = _normalize_allowed_tag(tag)
            if not t:
                continue
            if t not in cleaned:
                cleaned.append(t)
            if len(cleaned) >= max_tags:
                break

        combined: List[str] = []
        for t in _infer_core_tags(topic, draft) + cleaned:
            if t not in combined:
                combined.append(t)
            if len(combined) >= max_tags:
                break
        if combined:
            return combined
    except Exception:
        pass
    combined: List[str] = []
    for t in _infer_core_tags(topic, draft) + fallback:
        t = _normalize_allowed_tag(t) or t
        if t in set(ALLOWED_TAGS) and t not in combined:
            combined.append(t)
        if len(combined) >= max_tags:
            break
    return combined[:max_tags]


def generate_seo_title(topic: str, draft: str) -> str:
    preview = re.sub(r"\s+", " ", draft.strip())[:800]
    prompt = f"""テーマ: {topic}
本文: {preview}

検索で魅力的に見える日本語タイトルを1本だけ返してください。
条件:
- 32〜60文字程度
- Kindle/Kobo/電子書籍などの関連キーワードを自然に含める
- 具体的なメリットを示す
- 重複語を避ける
- 読む理由が明確になる
"""
    try:
        title = generate_openai_text(
            "あなたはSEO編集者です。検索意図に合うタイトルを1本だけ返してください。",
            prompt,
            temperature=0.4,
        )
        title = title.strip()
        title = re.sub(r'["“”]', "", title)
        if 10 <= len(title) <= 80:
            return title
    except Exception:
        pass
    return f"{topic} を徹底解説"


def build_search_keyword(topic: str, max_words: int = 6, max_chars: int = 60) -> str:
    """Build a compact, relevant Rakuten search keyword from a topic."""
    topic_lower = topic.lower()
    brand_keys = ["kindle", "paperwhite", "oasis", "scribe", "kobo", "clara", "libra", "sage", "elipsa"]
    category_keys = [
        "電子書籍リーダー",
        "電子書籍",
        "端末",
        "e ink",
        "e-ink",
        "epub",
        "pdf",
        "カバー",
        "保護フィルム",
    ]
    picked_brand = next((b for b in brand_keys if b in topic_lower), "")
    picked_category = next((c for c in category_keys if c in topic_lower), "")
    if picked_brand and picked_category:
        base = f"{picked_brand} {picked_category}"
    elif picked_brand:
        base = f"{picked_brand} 電子書籍リーダー"
    elif picked_category:
        base = f"{picked_category} 電子書籍リーダー"
    else:
        base = "電子書籍リーダー"
    cleaned = re.sub(r"[!?！？\[\]\(\)（）【】「」『』:：,，、。]", " ", base)
    words = [w for w in re.split(r"\s+", cleaned) if w]
    keyword = " ".join(words[:max_words]) or base
    return keyword[:max_chars]

def fetch_rakuten_items(topic: str, hits: int = 3) -> List[Dict[str, str]]:
    if not (RAKUTEN_APP_ID and RAKUTEN_AFFILIATE_ID):
        print("[Rakuten] Missing app or affiliate ID. Using fallback items.")
        return RAKUTEN_FALLBACK_ITEMS[:hits]

    keyword = build_search_keyword(topic)
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "affiliateId": RAKUTEN_AFFILIATE_ID,
        "keyword": keyword,
        "hits": hits,
        "imageFlag": 1,
        "sort": "-reviewAverage",
    }
    print(f"[Rakuten] Searching items for topic: {keyword}")
    try:
        resp = requests.get(RAKUTEN_API_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[Rakuten] Request failed: {exc}")
        return RAKUTEN_FALLBACK_ITEMS[:hits]

    items: List[Dict[str, str]] = []
    for entry in data.get("Items", []):
        item = entry.get("Item", {})
        title = item.get("itemName")
        url = item.get("affiliateUrl") or item.get("itemUrl")
        price = item.get("itemPrice")
        if not title or not url:
            continue
        price_text = ""
        try:
            price_text = f"¥{int(price):,}"
        except Exception:
            price_text = ""
        items.append({"title": title, "url": url, "price_text": price_text})
        if len(items) >= hits:
            break
    if not items:
        print(f"[Rakuten] No affiliate items found for {keyword}.")
        return RAKUTEN_FALLBACK_ITEMS[:hits]
    else:
        print(f"[Rakuten] Selected {len(items)} items for {keyword}.")
    return items



def fetch_google_suggest_topics(max_needed: int) -> list[str]:
    """Fallback: collect trending-ish topics from Google suggest."""
    endpoint = "https://suggestqueries.google.com/complete/search"
    results: list[str] = []
    seen = set()
    for seed in GOOGLE_SUGGEST_QUERIES:
        try:
            resp = requests.get(
                endpoint,
                params={"client": "firefox", "hl": "ja", "q": seed},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            suggestions = data[1] if isinstance(data, list) and len(data) > 1 else []
            for s in suggestions:
                if not isinstance(s, str):
                    continue
                t = re.sub(r"\s+", " ", s).strip()
                if not t or t.lower() in seen:
                    continue
                if has_core_keyword(t):
                    results.append(t)
                    seen.add(t.lower())
                    if len(results) >= max_needed:
                        return results
        except Exception:
            continue
    return results


def fetch_pexels_image(topic: str) -> Dict[str, str] | None:
    if not PEXELS_API_KEY:
        print("[Pexels] API key missing. Skipping image fetch.")
        return None
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": re.sub(r"\s+", " ", topic).strip()[:80],
        "per_page": 1,
        "orientation": "landscape",
    }
    print(f"[Pexels] Searching image for topic: {topic}")
    try:
        resp = requests.get(PEXELS_API_ENDPOINT, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"[Pexels] Request failed: {exc}")
        return None

    photos = data.get("photos") or []
    if not photos:
        print(f"[Pexels] No photos found for {topic}.")
        return None
    photo = photos[0]
    src = photo.get("src") or {}
    image_url = src.get("large") or src.get("medium")
    if not image_url:
        print(f"[Pexels] Photo found but missing usable URL for {topic}.")
        return None
    print(f"[Pexels] Using photo id={photo.get('id')} url={image_url}")
    return {
        "image_url": image_url,
        "photographer": photo.get("photographer") or "Pexels",
        "photographer_url": photo.get("photographer_url") or photo.get("url"),
        "pexels_url": photo.get("url"),
    }


def ensure_unique_path(basedir: pathlib.Path, prefix: str, slug: str):
    p = basedir / f"{prefix}-{slug}.md"
    if not p.exists():
        return p
    n = 2
    while True:
        q = basedir / f"{prefix}-{slug}-{n}.md"
        if not q.exists():
            return q
        n += 1


def ensure_pillar_links_block(draft: str) -> str:
    return ensure_pillar_links(draft)


_UNWANTED_PREFACE_PATTERNS = [
    r"^以下に、.*(リライト案|修正案|改善案).*$",
    r"^元テキストの流れは活かしつつ.*$",
    r"^以下は、?.*(リライト|修正|校正).*$",
    r"^（?注）?この(文章|記事)は.*(リライト|修正|校正).*$",
]


def strip_unwanted_preface(markdown: str) -> str:
    lines = markdown.splitlines()

    def is_stop_line(line: str) -> bool:
        s = line.lstrip()
        return s.startswith(("#", "![", "---"))

    i = 0
    while i < len(lines):
        line = lines[i]
        if is_stop_line(line):
            break
        if not line.strip():
            i += 1
            continue
        if any(re.match(p, line.strip()) for p in _UNWANTED_PREFACE_PATTERNS):
            i += 1
            continue
        break

    cleaned = "\n".join(lines[i:]).lstrip("\n")
    return cleaned


def downgrade_markdown_h1(markdown: str) -> str:
    """Downgrade Markdown level-1 headings (# ) to level-2 (## ) to avoid duplicate <h1>."""
    lines = markdown.splitlines()
    out: List[str] = []
    in_fence = False
    for line in lines:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and re.match(r"^#\s+", line):
            out.append("## " + line[1:].lstrip())
            continue
        out.append(line)
    return "\n".join(out)


def make_post(topic: str, slug: str, template: str = USER_TMPL):
    is_trend_template = template == TREND_USER_TMPL
    user = template.format(topic=topic)
    draft = generate_openai_text(SYSTEM, user, temperature=0.7).strip()
    for _ in range(2):
        review_prompt = f"""以下の記事を校正し、重複や構成の乱れを直してください。
必ず「修正後の完成稿（本文）」のみをMarkdownで返してください（前置き/解説/改善案は不要）。

{CHECKLIST}

--- candidate ---
{draft}
--- candidate ---
"""
        reviewed = generate_openai_text(REVIEWER_SYSTEM, review_prompt, temperature=0.4).strip()
        draft = strip_unwanted_preface(reviewed)

    def ensure_min_length(current: str, min_words: int, min_chars: int, attempts: int) -> str:
        if attempts <= 0:
            return current
        if min_words <= 0 and min_chars <= 0:
            return current
        if count_words(current) >= min_words and count_chars(current) >= min_chars:
            return current
        return expand_to_min_words(topic, current, min_words, min_chars, attempts)

    primary_words = TREND_QUALITY_MIN_WORDS if is_trend_template else QUALITY_MIN_WORDS
    primary_chars = TREND_MIN_CHAR_COUNT if is_trend_template else MIN_CHAR_COUNT
    primary_attempts = MAX_PRIMARY_EXPAND_ATTEMPTS_TREND if is_trend_template else MAX_PRIMARY_EXPAND_ATTEMPTS
    draft = ensure_min_length(draft, primary_words, primary_chars, primary_attempts)

    relaxed_words = TREND_RELAXED_MIN_WORDS if is_trend_template else RELAXED_MIN_WORDS
    relaxed_chars = TREND_RELAXED_MIN_CHAR_COUNT if is_trend_template else RELAXED_MIN_CHAR_COUNT
    relaxed_attempts = MAX_RELAXED_EXPAND_ATTEMPTS_TREND if is_trend_template else MAX_RELAXED_EXPAND_ATTEMPTS
    if count_words(draft) < relaxed_words or count_chars(draft) < relaxed_chars:
        draft = ensure_min_length(draft, relaxed_words, relaxed_chars, relaxed_attempts)

    lower_words = TREND_RELAXED_MIN_WORD_COUNT_LOWER if is_trend_template else RELAXED_MIN_WORD_COUNT_LOWER
    lower_chars = TREND_RELAXED_MIN_CHAR_COUNT_LOWER if is_trend_template else RELAXED_MIN_CHAR_COUNT_LOWER
    lower_attempts = 1 if is_trend_template else 0
    if lower_attempts and (count_words(draft) < lower_words or count_chars(draft) < lower_chars):
        draft = ensure_min_length(draft, lower_words, lower_chars, lower_attempts)

    draft = strip_unwanted_preface(draft)
    draft = downgrade_markdown_h1(draft)

    hero_image_url = None
    hero = fetch_pexels_image(topic)
    if hero:
        hero_image_url = hero.get("image_url") or None
        credit_url = hero.get("photographer_url") or hero.get("pexels_url")
        image_block = (
            f"![{topic}のイメージ]({hero['image_url']})"
            f"\n<small>Photo by [{hero['photographer']}]({credit_url}) on [Pexels]({hero['pexels_url']})</small>"
        )
        parts = draft.split("\n\n", 1)
        if len(parts) == 2:
            draft = parts[0].strip() + "\n\n" + image_block + "\n\n" + parts[1].strip()
        else:
            draft = image_block + "\n\n" + draft

    today = datetime.date.today()

    # 不要なラベルを除去
    draft = re.sub(r"(?m)^##\s*H2:\s*", "## ", draft)
    draft = re.sub(r"(?m)^###\s*H3:\s*", "### ", draft)
    draft = re.sub(r"\n?\[読書ガイド\]\(/posts/?\)\s*", "\n", draft)

    rakuten_items = fetch_rakuten_items(topic)
    show_rakuten_widget = bool(rakuten_items)

    out_dir = CONTENT_POSTS_DIR
    related = pick_related_urls(out_dir, today.isoformat(), k=3)
    related_block_lines = ["", "## 関連記事", ""]
    for title, url in related:
        related_block_lines.append(f"- [{title}]({url})")
    related_block = "\n".join(related_block_lines) + "\n"

    draft = ensure_pillar_links_block(draft)
    draft = draft.rstrip() + "\n\n" + related_block

    seo_title = generate_seo_title(topic, draft)
    tags = generate_tags(topic, draft)
    word_count = count_words(draft)
    meta_description = generate_meta_description(topic, draft)

    canonical_url = None
    robots_no_index = False
    if should_canonicalize_to_kindle_vs_kobo(topic, seo_title):
        if BASE_URL:
            canonical_url = f"{BASE_URL.rstrip('/')}/posts/kindle-vs-kobo/"
        else:
            print("[warn] baseURL is not resolved; canonicalURL will not be set.")
        robots_no_index = True

    # Python 3.11 does not allow backslashes inside f-string expressions.
    # Keep newline escapes out of {...} so GitHub Actions (3.11) can parse this file.
    sitemap_yaml = "sitemap:\n  disable: true" if robots_no_index else ""

    fm = dedent(
        f"""\
    ---
    title: "{seo_title}"
    date: {today.isoformat()}
    lastmod: {today.isoformat()}
    draft: false
    {"robotsNoIndex: true" if robots_no_index else ""}
    {sitemap_yaml}
    {f'canonicalURL: "{canonical_url}"' if canonical_url else ""}
    {f'images: ["{yaml_escape(hero_image_url)}"]' if hero_image_url else ""}
    tags: {tags}
    categories: ["電子書籍"]
    description: "{yaml_escape(meta_description)}"
    slug: "{slug}"
    hasRelatedProducts: false
    showRakutenWidget: {"true" if show_rakuten_widget else "false"}
    ---
    """
    )
    return slug, seo_title, fm + "\n" + draft + "\n", word_count


def pick_related_urls(out_dir: pathlib.Path, today_iso: str, k: int = 3):
    all_posts = list_existing_posts(out_dir)
    candidates = [p for p in all_posts if p["date"] != today_iso]
    if not candidates:
        return [("読書ガイド", "/posts/")] * k
    seed = datetime.date.today().toordinal()
    random.Random(seed).shuffle(candidates)
    picked = candidates[:k]
    while len(picked) < k:
        picked.append({"title": "読書ガイド", "url": "/posts/", "date": "1900-01-01"})
    return [(p["title"], p["url"]) for p in picked[:k]]


def parse_iso_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    text = str(value).strip().strip('"').strip("'")
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return datetime.date.fromisoformat(text)
    except Exception:
        return None


def split_yaml_frontmatter(md_text: str) -> tuple[str, str, str]:
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", md_text, re.S)
    if not m:
        return "", "", md_text
    return "---", m.group(1), md_text[m.end() :]


def upsert_lastmod(frontmatter: str, today_iso: str) -> str:
    if re.search(r"(?m)^lastmod:\s*.*$", frontmatter):
        return re.sub(r"(?m)^lastmod:\s*.*$", f"lastmod: {today_iso}", frontmatter, count=1)
    if re.search(r"(?m)^date:\s*.*$", frontmatter):
        return re.sub(r"(?m)^date:\s*.*$", lambda m: m.group(0) + f"\nlastmod: {today_iso}", frontmatter, count=1)
    lines = frontmatter.rstrip("\n").splitlines()
    lines.append(f"lastmod: {today_iso}")
    return "\n".join(lines)


def ensure_update_section_shape(section: str, query: str, existing_h2: set[str]) -> str:
    cleaned = _strip_markdown_code_fence(strip_unwanted_preface(section or "").strip())
    cleaned = downgrade_markdown_h1(cleaned)
    heading_match = re.match(r"(?m)^##\s+(.+)$", cleaned)
    if not heading_match:
        cleaned = f"## 追記: {query}\n\n{cleaned}".strip()
        return cleaned
    first_heading = re.sub(r"\s+", " ", heading_match.group(1)).strip()
    if first_heading in existing_h2:
        cleaned = re.sub(r"(?m)^##\s+.+$", f"## 追記: {query}", cleaned, count=1)
    return cleaned.strip()


def insert_update_section(body: str, section: str) -> str:
    insert_patterns = [
        r"(?m)^##\s*まとめ.*$",
        r"(?m)^##\s*結論.*$",
        r"(?m)^##\s*関連ガイド.*$",
        r"(?m)^##\s*関連記事.*$",
    ]
    for pattern in insert_patterns:
        m = re.search(pattern, body)
        if not m:
            continue
        head = body[: m.start()].rstrip()
        tail = body[m.start() :].lstrip()
        return f"{head}\n\n{section.strip()}\n\n{tail}".strip() + "\n"
    return body.rstrip() + "\n\n" + section.strip() + "\n"


def build_update_section(
    query: str,
    current_title: str,
    current_body: str,
    score_payload: dict,
) -> str | None:
    snippet = re.sub(r"\s+", " ", current_body).strip()[:4200]
    supply_metrics = score_payload.get("supply_metrics") or {}
    prompt = dedent(
        f"""\
        既存記事に追記する補足セクションを作成してください。本文全体の書き直しは禁止です。

        # 対象記事タイトル
        {current_title}

        # 追加で拾う検索意図
        {query}

        # 供給不足ヒント（外部SERP分析）
        - old_content_ratio: {supply_metrics.get('old_content_ratio', '')}
        - domain_concentration: {supply_metrics.get('domain_concentration', '')}
        - howto_lack_ratio: {supply_metrics.get('howto_lack_ratio', '')}
        - primary_source_lack_ratio: {supply_metrics.get('primary_source_lack_ratio', '')}
        - forum_pressure: {supply_metrics.get('forum_pressure', '')}

        # 現在本文（抜粋）
        {snippet}

        # 出力要件
        - 追記セクションのみをMarkdownで返す
        - H1は使わず、H2(##)から始める
        - 手順や症状別の分岐を具体的に入れる
        - 断定を避け、未確認情報は「要確認」と書く
        - 誇大表現は禁止
        - 重複しやすい定型文は避ける
        """
    )
    try:
        section = generate_openai_text(UPDATE_SYSTEM, prompt, temperature=0.4)
    except Exception as exc:
        print(f"[warn] Failed to generate update section for '{query}': {exc}")
        return None
    return section.strip()


def apply_external_updates(
    update_candidates: list[dict],
    max_updates: int,
    cooldown_days: int = UPDATE_COOLDOWN_DAYS,
) -> int:
    if max_updates <= 0:
        return 0
    if OPENAI_CLIENT is None:
        print("[warn] OPENAI_API_KEY is not set. Skip update generation.")
        return 0

    today = datetime.date.today()
    updated_count = 0

    for candidate in sorted(update_candidates, key=lambda x: x.get("opportunity_score", 0), reverse=True):
        if updated_count >= max_updates:
            break
        file_path = pathlib.Path(candidate.get("post_file_path") or "")
        query = (candidate.get("query") or "").strip()
        if not query or not file_path.exists():
            continue

        try:
            md_text = file_path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"[warn] Failed to read update target '{file_path}': {exc}")
            continue

        fm_data = parse_frontmatter(md_text)
        last_seen = parse_iso_date(fm_data.get("lastmod") or fm_data.get("date"))
        if last_seen and (today - last_seen).days < cooldown_days:
            print(f"[skip] Update skipped for '{file_path.name}' because it was updated recently.")
            continue

        delim, frontmatter, body = split_yaml_frontmatter(md_text)
        if not delim:
            print(f"[skip] Update skipped for '{file_path.name}' because YAML front matter was not found.")
            continue

        section = build_update_section(
            query=query,
            current_title=fm_data.get("title") or candidate.get("post_title") or file_path.stem,
            current_body=body,
            score_payload=candidate,
        )
        if not section:
            continue

        existing_h2 = extract_h2_headings(body)
        section = ensure_update_section_shape(section, query, existing_h2)
        new_body = insert_update_section(body, section)
        new_frontmatter = upsert_lastmod(frontmatter, today.isoformat())
        new_md = f"---\n{new_frontmatter.strip()}\n---\n\n{new_body.lstrip()}"

        try:
            file_path.write_text(new_md, encoding="utf-8")
            updated_count += 1
            print(f"updated: {file_path}")
        except Exception as exc:
            print(f"[warn] Failed to write updated post '{file_path}': {exc}")
            continue
    return updated_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1, help="1〜3記事生成")
    parser.add_argument("--updates", type=int, default=0, help="既存記事の更新数（0〜3）")
    parser.add_argument(
        "--external-supply-check",
        type=parse_bool_arg,
        nargs="?",
        const=True,
        default=True,
        help="外部SERP供給不足チェックを使う (true/false)",
    )
    parser.add_argument("--supply-audit-only", action="store_true", help="供給不足判定レポートのみ出力して終了")
    parser.add_argument("--cse-budget", type=int, default=DEFAULT_CSE_BUDGET, help="外部SERP API呼び出し予算")
    parser.add_argument(
        "--serp-provider",
        type=str,
        default=EXTERNAL_SERP_PROVIDER if EXTERNAL_SERP_PROVIDER in {"auto", "brave", "cse"} else "auto",
        choices=["auto", "brave", "cse"],
        help="外部SERPプロバイダ (auto/brave/cse)",
    )
    parser.add_argument("--gsc-days", type=int, default=28, help="GSC取得期間（日数）")
    parser.add_argument("--gsc-min-impressions", type=int, default=50, help="GSCの最小表示回数")
    parser.add_argument("--gsc-min-position", type=int, default=10, help="GSCの最小掲載順位")
    args = parser.parse_args()

    # Safety guard: disable accidental generation unless explicitly enabled.
    if os.getenv("DISABLE_POST_GENERATION", "true").lower() != "false" and not args.supply_audit_only:
        print("[info] Post generation is disabled. Set DISABLE_POST_GENERATION=false to enable.")
        return

    requested_count = max(1, min(3, args.count))
    if requested_count != args.count:
        print(f"[info] Adjusted count from {args.count} to {requested_count} (allowed range: 1-3).")
    requested_updates = max(0, min(3, args.updates))
    if requested_updates != args.updates:
        print(f"[info] Adjusted updates from {args.updates} to {requested_updates} (allowed range: 0-3).")

    out_dir = CONTENT_POSTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    existing_today = sorted(out_dir.glob(f"{today}-*.md"))
    already = len(existing_today)

    need = max(0, requested_count - already)
    need = min(need, 3)

    existing_posts = list_existing_posts(out_dir)
    external_result = {
        "new_topics": [],
        "update_candidates": [],
        "audit_rows": [],
        "meta": {"source": "disabled", "fallback_reason": ""},
    }

    if args.external_supply_check:
        try:
            external_result = collect_external_supply_candidates(
                existing_posts=existing_posts,
                gsc_days=max(1, args.gsc_days),
                gsc_min_impressions=max(1, args.gsc_min_impressions),
                gsc_min_position=max(1, args.gsc_min_position),
                cse_budget=max(0, args.cse_budget),
                serp_provider=args.serp_provider,
            )
        except Exception as exc:
            print(f"[warn] External supply check failed; fallback to existing topic sources. ({exc})")
            external_result["meta"]["fallback_reason"] = "external_check_exception"

        write_supply_audit_report(external_result.get("audit_rows", []), external_result.get("meta", {}))
        if external_result.get("meta", {}).get("fallback_reason"):
            print(f"[warn] External supply check fallback reason: {external_result['meta']['fallback_reason']}")

    if args.supply_audit_only:
        print("[info] Supply audit only mode completed.")
        return

    if OPENAI_CLIENT is None:
        raise SystemExit("OPENAI_API_KEY not set")

    if need == 0 and requested_updates == 0:
        print(f"Already have {already} posts for {today}. Nothing to do.")
        return

    existing_title_pool = [(p.get("title") or "").strip() for p in existing_posts if p.get("title")]
    used_titles = {(p.get("title") or "").strip().lower() for p in existing_posts if p.get("title")}
    used_slugs = {p.get("slug") for p in existing_posts if p.get("slug")}
    existing_headings = load_existing_headings(out_dir)
    recent_titles = recent_titles_within(existing_posts, days=7)
    generated_headings: list[Tuple[str, Set[str]]] = []
    similar_title_pool: list[str] = list(existing_title_pool)
    topic_pool: list[str] = list(existing_title_pool)

    fallback_topics = build_fallback_topic_pool(
        existing_titles=existing_title_pool,
        used_titles=used_titles,
        used_slugs=used_slugs,
        recent_titles=recent_titles,
        limit=300,
    )
    external_topics = external_result.get("new_topics") or []
    if external_topics:
        print(f"[info] External supply-gap candidates: {external_topics}")

    raw_topics = list(external_topics)
    fallback_raw_topics = collect_candidates(max(need * 15, 30), fallback_topics=fallback_topics)
    for topic in fallback_raw_topics:
        if topic not in raw_topics:
            raw_topics.append(topic)
    scored = []
    for t in raw_topics:
        score = 0
        lowered = t.lower()
        for kw in ["kindle", "kobo", "電子書籍", "ebook", "reader", "epub", "読書", "端末", "活用"]:
            if kw in lowered:
                score += 2
        for kw in ["無料", "セール", "比較", "最新", "長持ち", "選び方"]:
            if kw in lowered:
                score += 1
        scored.append((score, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    filtered_topics = [t for s, t in scored if s > 0]
    topics = filtered_topics
    if need == 0:
        topics = []
    start_index = already + 1
    generated = 0
    index = start_index
    fallback_queue = [t for t in fallback_topics if t.lower() not in recent_titles]
    attempted_fallback: set[str] = set()
    consecutive_fails = 0

    def next_fallback_topic() -> str | None:
        nonlocal fallback_queue
        while True:
            while fallback_queue:
                candidate = fallback_queue.pop(0)
                cand_lower = candidate.lower()
                if cand_lower in attempted_fallback:
                    continue
                if cand_lower in used_titles or cand_lower in recent_titles:
                    attempted_fallback.add(cand_lower)
                    continue
                attempted_fallback.add(cand_lower)
                return candidate

            # Refill once with remaining candidates (shuffled) to avoid repeating the same head element forever.
            remaining = [
                t
                for t in fallback_topics
                if (t.lower() not in attempted_fallback)
                and (t.lower() not in used_titles)
                and (t.lower() not in recent_titles)
            ]
            if not remaining:
                return None
            random.Random(datetime.date.today().toordinal() + len(attempted_fallback)).shuffle(remaining)
            fallback_queue = remaining

    def generate_for_topic(raw_topic: str, allow_fallback=True, allow_final=False, use_failsafe=False) -> bool:
        nonlocal generated, index, similar_title_pool, topic_pool
        topic_clean = re.sub(r"\s+", " ", raw_topic).strip()
        if not topic_clean:
            return False
        lowered = topic_clean.lower()
        if lowered in used_titles:
            return False

        # Avoid creating duplicate/cannibal pages for the main pillar article.
        if should_canonicalize_to_kindle_vs_kobo(topic_clean) and (CONTENT_POSTS_DIR / "kindle-vs-kobo.md").exists():
            print(f"[skip] Topic '{topic_clean}' skipped because it targets the existing pillar /posts/kindle-vs-kobo/.")
            return False

        # Avoid generating obvious duplicates of other pillar review pages.
        if should_canonicalize_to_kindle_paperwhite_review(topic_clean) and (CONTENT_POSTS_DIR / "kindle-paperwhite-review.md").exists():
            print(
                f"[skip] Topic '{topic_clean}' skipped because it targets the existing pillar /posts/kindle-paperwhite-review/."
            )
            return False
        if should_canonicalize_to_kobo_clara_review(topic_clean) and (CONTENT_POSTS_DIR / "kobo-clara-review.md").exists():
            print(f"[skip] Topic '{topic_clean}' skipped because it targets the existing pillar /posts/kobo-clara-review/.")
            return False

        if is_similar_topic(topic_clean, topic_pool, threshold=0.6):
            print(f"[skip] Topic '{topic_clean}' skipped because it is too similar to an existing or generated topic.")
            return False
        if is_similar_title(topic_clean, similar_title_pool, threshold=0.7):
            print(f"[skip] Topic '{topic_clean}' skipped because it is too similar to an existing title.")
            return False

        slug_base = slugify_lib(topic_clean, lowercase=True, max_length=60, separator="-")
        if not slug_base:
            return False
        if slug_base in used_slugs:
            print(f"[skip] Topic '{topic_clean}' skipped because its slug '{slug_base}' already exists (likely same search intent).")
            return False
        slug_candidate = slug_base

        templates = [USER_TMPL]
        if not contains_relevant_keyword(topic_clean):
            templates = [TREND_USER_TMPL, USER_TMPL]

        for tmpl in templates:
            slug, seo_title, content, word_count = make_post(topic_clean, slug_candidate, template=tmpl)

            if should_canonicalize_to_kindle_vs_kobo(topic_clean, seo_title) and (CONTENT_POSTS_DIR / "kindle-vs-kobo.md").exists():
                print(f"[skip] Draft '{seo_title}' skipped because it targets the existing pillar /posts/kindle-vs-kobo/.")
                continue
            if should_canonicalize_to_kindle_paperwhite_review(topic_clean, seo_title) and (
                CONTENT_POSTS_DIR / "kindle-paperwhite-review.md"
            ).exists():
                print(
                    f"[skip] Draft '{seo_title}' skipped because it targets the existing pillar /posts/kindle-paperwhite-review/."
                )
                continue
            if should_canonicalize_to_kobo_clara_review(topic_clean, seo_title) and (
                CONTENT_POSTS_DIR / "kobo-clara-review.md"
            ).exists():
                print(f"[skip] Draft '{seo_title}' skipped because it targets the existing pillar /posts/kobo-clara-review/.")
                continue

            title_key = seo_title.strip().lower()
            if title_key in used_titles:
                print(f"[skip] Draft '{seo_title}' skipped because title already exists.")
                continue
            if is_similar_title(seo_title, similar_title_pool, threshold=0.6):
                print(f"[skip] Draft '{seo_title}' skipped because it is too close to an existing title.")
                continue
            char_count = count_chars(content)
            meets_relaxed = word_count >= RELAXED_MIN_WORDS and char_count >= RELAXED_MIN_CHAR_COUNT
            meets_lower = word_count >= RELAXED_MIN_WORD_COUNT_LOWER and char_count >= RELAXED_MIN_CHAR_COUNT_LOWER
            meets_final = False
            if allow_final:
                final_words = FAILSAFE_MIN_WORDS if use_failsafe else FINAL_MIN_WORDS
                final_chars = FAILSAFE_MIN_CHAR_COUNT if use_failsafe else FINAL_MIN_CHAR_COUNT
                meets_final = word_count >= final_words and char_count >= final_chars
            h2_set = extract_h2_headings(content)
            if h2_set and is_duplicate_headings(h2_set, existing_headings + generated_headings, threshold=0.5):
                print(f"[skip] Draft '{seo_title}' skipped because H2が既存記事と近い構成です。")
                continue
            if meets_relaxed or meets_lower or meets_final:
                prefix = f"{today}-{index}"
                path = ensure_unique_path(out_dir, prefix, slug)
                path.write_text(content, encoding="utf-8")
                print(f"generated: {path}")
                used_titles.add(seo_title.strip().lower())
                used_slugs.add(slug)
                similar_title_pool.append(seo_title)
                topic_pool.append(topic_clean)
                generated_headings.append((path.name, h2_set))
                generated += 1
                index += 1
                if meets_final and not (meets_relaxed or meets_lower):
                    print(f"[info] Draft '{seo_title}' accepted under final fallback threshold ({word_count} words / {char_count} chars).")
                elif meets_lower and not meets_relaxed:
                    print(f"[info] Draft '{seo_title}' accepted under relaxed lower threshold ({word_count} words / {char_count} chars).")
                return True
            else:
                label = "trend" if tmpl == TREND_USER_TMPL else "default"
                print(f"[skip] Draft '{seo_title}' too short with {label} template ({word_count} words / {char_count} chars).")
        if allow_fallback:
            fb_topic = next_fallback_topic()
            if fb_topic:
                print(f"[info] Trying fallback topic '{fb_topic}'.")
                return generate_for_topic(fb_topic, allow_fallback=False, allow_final=True, use_failsafe=use_failsafe)
        return False

    for topic in topics:
        if generate_for_topic(topic):
            consecutive_fails = 0
            if generated >= need:
                break
        else:
            consecutive_fails += 1
            if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                fb_topic = next_fallback_topic()
                if fb_topic and generate_for_topic(fb_topic):
                    consecutive_fails = 0
                    if generated >= need:
                        break
                else:
                    consecutive_fails = 0

    while generated < need:
        fb_topic = next_fallback_topic()
        if not fb_topic:
            break
        if generate_for_topic(fb_topic):
            continue

    if generated < need:
        suggest_topics = fetch_google_suggest_topics(max(need * 10, 20))
        if suggest_topics:
            print(f"[info] Using Googleサジェストで補充: {suggest_topics}")
        for t in suggest_topics:
            if generate_for_topic(t, allow_fallback=False, allow_final=True):
                if generated >= need:
                    break

    if generated == 0:
        print("[info] No articles generated from RSS; forcing ebook fallback.")
        for fb_topic in fallback_topics:
            if generate_for_topic(fb_topic, allow_fallback=False, allow_final=True):
                break

    if generated < need:
        print("[warn] Still insufficient articles. Applying failsafe ebook-only generation with relaxed thresholds.")
        for fb_topic in fallback_topics:
            if generate_for_topic(fb_topic, allow_fallback=False, allow_final=True, use_failsafe=True):
                if generated >= need:
                    break

    if generated < need:
        print("[warn] Trying remaining fallback pool with failsafe thresholds.")
        remaining_fb = [t for t in fallback_queue if t.lower() not in used_titles]
        for fb_topic in remaining_fb:
            if generate_for_topic(fb_topic, allow_fallback=False, allow_final=True, use_failsafe=True):
                if generated >= need:
                    break

    if generated < need:
        print("[warn] As a last resort, reusing fallback topics even if duplicates.")
        for fb_topic in fallback_topics:
            if generate_for_topic(fb_topic, allow_fallback=False, allow_final=True, use_failsafe=True):
                if generated >= need:
                    break

    if requested_updates > 0:
        update_candidates = external_result.get("update_candidates") or []
        if not update_candidates:
            print("[info] No external update candidates met thresholds.")
        else:
            updated = apply_external_updates(update_candidates, max_updates=requested_updates)
            if updated == 0:
                print("[info] No existing posts were updated.")
            else:
                print(f"[info] Updated existing posts: {updated}")

    if generated < need:
        msg = f"Unable to generate {need} unique posts (created {generated})."
        # Avoid failing the whole workflow when we intentionally skip duplicates/cannibal content.
        print(f"[warn] {msg}")
        print(f"::warning::{msg}")
        return


if __name__ == "__main__":
    main()
