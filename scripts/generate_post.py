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
import datetime
import pathlib
import random
import argparse
import json
from typing import List, Dict, Tuple, Set

import requests
from textwrap import dedent
from dotenv import load_dotenv
from slugify import slugify as slugify_lib
import openai

# ---------- env ----------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY not set")
openai.api_key = OPENAI_API_KEY

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID")
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

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

FALLBACK_TOPICS = [
    # 比較
    "KindleとKoboの違いを2025年版で徹底解説",
    "2025年最新の電子書籍リーダー3選",
    "Kindle UnlimitedとKobo Plusの違いと選び方",
    "KindleとKoboを子供向け読書デバイスとして使い分けるコツ",

    # 使い方・ノウハウ
    "EPUBやPDFをKindleで快適に読むための完全ガイド",
    "電子書籍デバイスとスマホを併用するメリット",
    "見開き表示・縦書き・横書きで読みやすさがどう変わるか",
    "1日30分で読書習慣を作る15のアイデア",
    "無料本でKindle生活をはじめる方法",

    # デバイスケア
    "E-Ink端末のバッテリーを長持ちさせる設定と使い方",
    "防水モデルと普通モデルのどちらを選ぶべきか",
    "暗所で読むときに最適なフロントライトの設定",
    "ブルーライトを抑えて目を守る読書術",

    # 購入・セール
    "電子書籍のセールを効率よく追う方法",
    "PCなしでKindle本を管理・整理する手順",
    "買ってよかった電子書籍アクセサリーまとめ",
    "読み放題サービスを最大化する本の探し方",
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
    text = f"{topic_text}\n{title_text}"
    must = ("Kindle" in text) and ("Kobo" in text)
    if not must:
        return False
    has_year_or_latest = any(k in text for k in ["2025", "最新", "最新版"])
    has_compare_intent = any(k in text for k in ["徹底比較", "比較", "違い", "どっち"])
    return has_year_or_latest and has_compare_intent

# ---------- prompts ----------
SYSTEM = "あなたは電子書籍・電子リーダー専門メディアの熟練編集者として、日本語でSEOを意識しつつオリジナル記事を作成してください。あなたは世界一のブロガーです。"
USER_TMPL = """\
以下のトピックで、重複しない切り口の高品質な記事を書いてください。

# テーマ
{topic}

# 要件
- 読者が初心者でも理解できるように5つ以上の具体例や対策を盛り込む
- 最新の利用シーンや活用アイデアを含める
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
CHECKLIST = """\
以下の観点で修正してください
1) 内容は最新かつ具体的か
2) 重複表現や冗長な文はないか
3) 見出し: H2/H3が自然な流れか、近い見出しが続かないか
4) 読者が次に取れる行動が明確か
5) 内部リンクは末尾に1回だけ[読書ガイド]を入れる
6) トーンは丁寧で押し付けないか
"""
TAG_SYSTEM = "あなたはSEOに詳しい編集者です。記事内容に沿うタグをJSON配列で返してください。"

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
    data["url"] = pick("url")
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
        posts.append({"url": url, "title": title or slug, "date": date, "slug": slug})
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


def is_similar_title(title: str, existing: list[str], threshold: float = 0.65) -> bool:
    """Check Jaccard similarity to avoid near-duplicate titles."""
    cand_tokens = _tokenize(title)
    if not cand_tokens:
        return False
    for t in existing:
        base_tokens = _tokenize(t)
        if not base_tokens:
            continue
        overlap = len(cand_tokens & base_tokens)
        union = len(cand_tokens | base_tokens)
        if union and overlap / union >= threshold:
            return True
    return False


def is_similar_topic(topic: str, existing: list[str], threshold: float = 0.6) -> bool:
    """Avoid generating multiple posts on near-identical topics."""
    return is_similar_title(topic, existing, threshold=threshold)


def collect_candidates(max_needed: int):
    """RSSから候補を集め、足りなければFALLBACKで補う"""
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

    for fb in FALLBACK_TOPICS:
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
        resp = openai.chat.completions.create(
            model="gpt-5.1",
            temperature=0.5,
            messages=[
                {"role": "system", "content": REWRITER_SYSTEM},
                {"role": "user", "content": expand_prompt},
            ],
        )
        draft = resp.choices[0].message.content.strip()
    return draft


def generate_tags(topic: str, draft: str, max_tags: int = 5):
    fallback = ["電子書籍", "Kindle", "Kobo", "読書術"]
    preview = re.sub(r"\s+", " ", draft.strip())[:1200]
    prompt = f"""テーマ: {topic}

前文抜粋: {preview}

記事内容に合う短いタグを{max_tags}個まで、日本語でJSON配列として返してください。10文字以内で汎用的でないものを優先。"""
    try:
        resp = openai.chat.completions.create(
            model="gpt-5.1",
            temperature=0.2,
            messages=[
                {"role": "system", "content": TAG_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        tags = json.loads(resp.choices[0].message.content.strip())
        cleaned = []
        seen = set()
        for tag in tags:
            if not isinstance(tag, str):
                continue
            t = tag.strip()
            if not t or len(t) > 12:
                continue
            key = t.lower()
            if key in seen:
                continue
            cleaned.append(t)
            seen.add(key)
            if len(cleaned) >= max_tags:
                break
        if cleaned:
            return cleaned
    except Exception:
        pass
    return fallback[:max_tags]


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
        resp = openai.chat.completions.create(
            model="gpt-5.1",
            temperature=0.4,
            messages=[
                {"role": "system", "content": "あなたはSEO編集者です。検索意図に合うタイトルを1本だけ返してください。"},
                {"role": "user", "content": prompt},
            ],
        )
        title = resp.choices[0].message.content.strip()
        title = re.sub(r'["“”]', "", title)
        if 10 <= len(title) <= 80:
            return title
    except Exception:
        pass
    return f"{topic} を徹底解説"


def build_search_keyword(topic: str, max_words: int = 6, max_chars: int = 60) -> str:
    """Rakuten???????????????????????????????"""
    topic_lower = topic.lower()
    brand_keys = ["kindle", "paperwhite", "oasis", "scribe", "kobo", "clara", "libra", "sage", "elipsa"]
    category_keys = ["????", "????????", "??????", "e ink", "?????", "???", "???", "?????"]
    picked_brand = next((b for b in brand_keys if b in topic_lower), "")
    picked_category = next((c for c in category_keys if c in topic_lower), "")
    if picked_brand and picked_category:
        base = f"{picked_brand} {picked_category}"
    elif picked_brand:
        base = f"{picked_brand} ????????"
    elif picked_category:
        base = f"{picked_category} ????????"
    else:
        base = "????????"
    cleaned = re.sub(r"[?!??\[\]\(\)??]", " ", base)
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
            price_text = f" ?{int(price):,}"
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


def make_post(topic: str, slug: str, template: str = USER_TMPL):
    is_trend_template = template == TREND_USER_TMPL
    user = template.format(topic=topic)
    resp = openai.chat.completions.create(
        model="gpt-5.1",
        temperature=0.7,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
    )
    draft = resp.choices[0].message.content.strip()
    for _ in range(2):
        review_prompt = f"""以下の記事を校正し、重複や構成の乱れを直してください。
必ず「修正後の完成稿（本文）」のみをMarkdownで返してください（前置き/解説/改善案は不要）。

{CHECKLIST}

--- candidate ---
{draft}
--- candidate ---
"""
        r = openai.chat.completions.create(
            model="gpt-5.1",
            temperature=0.4,
            messages=[{"role": "system", "content": REVIEWER_SYSTEM}, {"role": "user", "content": review_prompt}],
        )
        draft = strip_unwanted_preface(r.choices[0].message.content.strip())

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

    hero = fetch_pexels_image(topic)
    if hero:
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

    out_dir = pathlib.Path("content/posts")
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

    canonical_url = None
    robots_no_index = False
    if should_canonicalize_to_kindle_vs_kobo(topic, seo_title):
        canonical_url = f"{BASE_URL.rstrip('/')}/posts/kindle-vs-kobo/"
        robots_no_index = True

    fm = dedent(
        f"""\
    ---
    title: "{seo_title}"
    date: {today.isoformat()}
    draft: false
    {"robotsNoIndex: true" if robots_no_index else ""}
    {f'canonicalURL: \"{canonical_url}\"' if canonical_url else ""}
    tags: {tags}
    categories: ["電子書籍"]
    description: "{topic}に関する実用的なガイドと最新情報をまとめました。"
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


def main():
    # Safety guard: disable accidental generation unless explicitly enabled.
    if os.getenv("DISABLE_POST_GENERATION", "true").lower() != "false":
        print("[info] Post generation is disabled. Set DISABLE_POST_GENERATION=false to enable.")
        return

    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1, help="1〜3記事生成")
    args = parser.parse_args()

    requested_count = max(1, min(3, args.count))
    if requested_count != args.count:
        print(f"[info] Adjusted count from {args.count} to {requested_count} (allowed range: 1-3).")

    out_dir = pathlib.Path("content/posts")
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    existing_today = sorted(out_dir.glob(f"{today}-*.md"))
    already = len(existing_today)

    need = max(0, requested_count - already)
    need = min(need, 3)
    if need == 0:
        print(f"Already have {already} posts for {today}. Nothing to do.")
        return

    existing_posts = list_existing_posts(out_dir)
    existing_title_pool = [(p.get("title") or "").strip() for p in existing_posts if p.get("title")]
    used_titles = {(p.get("title") or "").strip().lower() for p in existing_posts if p.get("title")}
    used_slugs = {p.get("slug") for p in existing_posts if p.get("slug")}
    existing_headings = load_existing_headings(out_dir)
    recent_titles = recent_titles_within(existing_posts, days=7)
    generated_headings: list[Tuple[str, Set[str]]] = []
    similar_title_pool: list[str] = list(existing_title_pool)
    topic_pool: list[str] = list(existing_title_pool)

    raw_topics = collect_candidates(max(need * 3, need))
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
    start_index = already + 1
    generated = 0
    index = start_index
    fallback_queue = [t for t in FALLBACK_TOPICS if t.lower() not in recent_titles]
    consecutive_fails = 0

    def next_fallback_topic() -> str | None:
        nonlocal fallback_queue
        while fallback_queue:
            candidate = fallback_queue.pop(0)
            cand_lower = candidate.lower()
            if cand_lower in used_titles or cand_lower in recent_titles:
                continue
            return candidate
        for candidate in FALLBACK_TOPICS:
            cand_lower = candidate.lower()
            if cand_lower in used_titles or cand_lower in recent_titles:
                continue
            return candidate
        return None

    def generate_for_topic(raw_topic: str, allow_fallback=True, allow_final=False, use_failsafe=False) -> bool:
        nonlocal generated, index, similar_title_pool, topic_pool
        topic_clean = re.sub(r"\s+", " ", raw_topic).strip()
        if not topic_clean:
            return False
        lowered = topic_clean.lower()
        if lowered in used_titles:
            return False

        # Avoid creating duplicate/cannibal pages for the main pillar article.
        if should_canonicalize_to_kindle_vs_kobo(topic_clean) and pathlib.Path("content/posts/kindle-vs-kobo.md").exists():
            print(f"[skip] Topic '{topic_clean}' skipped because it targets the existing pillar /posts/kindle-vs-kobo/.")
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
        slug_candidate = slug_base
        suffix = 2
        while slug_candidate in used_slugs:
            slug_candidate = f"{slug_base}-{suffix}"
            suffix += 1

        templates = [USER_TMPL]
        if not contains_relevant_keyword(topic_clean):
            templates = [TREND_USER_TMPL, USER_TMPL]

        for tmpl in templates:
            slug, seo_title, content, word_count = make_post(topic_clean, slug_candidate, template=tmpl)
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
        if not fb_topic or not generate_for_topic(fb_topic):
            break

    if generated < need:
        suggest_topics = fetch_google_suggest_topics(need - generated)
        if suggest_topics:
            print(f"[info] Using Googleサジェストで補充: {suggest_topics}")
        for t in suggest_topics:
            if generate_for_topic(t, allow_fallback=False, allow_final=True):
                if generated >= need:
                    break

    if generated == 0:
        print("[info] No articles generated from RSS; forcing ebook fallback.")
        for fb_topic in FALLBACK_TOPICS:
            if generate_for_topic(fb_topic, allow_fallback=False, allow_final=True):
                break

    if generated < need:
        print("[warn] Still insufficient articles. Applying failsafe ebook-only generation with relaxed thresholds.")
        for fb_topic in FALLBACK_TOPICS:
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
        for fb_topic in FALLBACK_TOPICS:
            if generate_for_topic(fb_topic, allow_fallback=False, allow_final=True, use_failsafe=True):
                if generated >= need:
                    break

    if generated < need:
        raise SystemExit(f"Unable to generate {need} unique posts (created {generated}).")


if __name__ == "__main__":
    main()
