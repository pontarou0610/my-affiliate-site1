# scripts/generate_post.py
"""
Article generator for the ebook-focused blog.
- Collects topics from RSS or fallback list
- Generates 1?3 posts/day via OpenAI
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
    "??kobo",
    "????",
    "????????",
    "??????",
    "?????",
    "??????",
    "?????",
    "????",
]
WHITELIST = list(CORE_KEYWORDS)

FALLBACK_TOPICS = [
    # ??????
    "Kindle?Kobo?????????2025???",
    "2025??????????????3?",
    "Kindle Unlimited?Kobo Plus??????????",
    "Kindle?Kobo??????????????????????????",

    # ????????
    "EPUB?PDF?????????????????????",
    "??????????????????????????",
    "??????????????????????",
    "??????????????1?30???15?????",
    "?????????Kindle???????????",

    # ??????
    "E-Ink???????????????????",
    "?????????????????????????",
    "?????????????????????????",
    "?????????????????????????",

    # ????????
    "??????????????????",
    "PC?????Kindle?????????????????",
    "??????????????????????",
    "??????????????????????",
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
    ("Kindle?Kobo?????", "/posts/kindle-vs-kobo/"),
    ("Kindle Paperwhite????", "/posts/kindle-paperwhite-review/"),
    ("Kobo Clara????", "/posts/kobo-clara-review/"),
]

SYSTEM = "?????????????????????????????????SEO????????????????????????????????"
USER_TMPL = """\
???????????????????????????????

# ???
{topic}

# ??
?????????????????????????????????5??????????????????????????????????????????????

# ?????
- ???: ??2500??????????3000??????
- ??: ???3?5?????????? H2????H2?H3?????????????
- ?H2????????????????????????????????????????????????????
- ?????????????????????????????????????????????????
- ??: ????????????????
- ?????: ???? [????](/posts/) ?1??????URL???
- ???: ????????????????2?3?

# ????
- ????????????????????????????
- ?????????????????????????
- ?????????????????????????????????????
- ???????????????????????????????????
"""

TREND_USER_TMPL = """\
?????????????????????????????????????????????????

# ???
{topic}

# ??
?????????????????????????????????????????????????????????

# ?????
- ???: ??2000?????2800?3000??????????????????????
- ???H2???:
  1. ??????3?5???????
  2. ??????????????
  3. ????????????????????
  4. ????????????????????/??????
  5. ?????????? or ?????????
  6. ??????????????
  7. ?????????????????2?3??
- Q&A/FAQ??????H2??????????3????Q&A???
- ?H2?????1?H3??????????????QA?FAQ??????????
- ??: ???????????????????????

# ????
- ??????????????????????????
- ??????????????????????
- ???????????????????????????????????
"""

REVIEWER_SYSTEM = "?????????????????????????????????????????????????????"
REWRITER_SYSTEM = "????SEO????????????????????????????????????????????????"
CHECKLIST = """\
??????????????
1) ??????????????????????
2) ?????????????????
3) ??: ???H2/H3??????????????????
4) ???????????????????????????
5) ???????????????????????[????]????
6) ???????????????????
"""
TAG_SYSTEM = "????SEO??????????????????????????????????JSON???????????"

RAKUTEN_API_ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
PEXELS_API_ENDPOINT = "https://api.pexels.com/v1/search"



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
        url = permalink_from(date, slug)
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


def collect_candidates(max_needed: int):
    """RSS???????????????????FALLBACK???"""
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

    seen = set(); uniq = []
    for t in items:
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"?.*??|\[.*?\]|\(.*?\)|?.*??", "", t).strip()
        t = re.sub(r"?+$", "", t)
        if t and t not in seen:
            uniq.append(t); seen.add(t)

    seed = datetime.date.today().toordinal()
    random.Random(seed).shuffle(uniq)

    for fb in FALLBACK_TOPICS:
        if len(uniq) >= max_needed: break
        if fb not in seen:
            uniq.append(fb); seen.add(fb)

    return uniq[:max_needed]


def ensure_pillar_links(text: str) -> str:
    heading = "## ??????????????"
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
        expand_prompt = dedent(f"""\
            ???????{count_words(draft)}??{count_chars(draft)}???????????????????{topic}??????
            - ?????{min_words}????{min_chars}??????????????
            - ??????????????????????????????????????
            - ?????????????????????
            - ??????????????????????????

            ????????????????????

            --- ?????? ---
            {draft}
            --- ?????? ---
            """)
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            messages=[
                {"role": "system", "content": REWRITER_SYSTEM},
                {"role": "user", "content": expand_prompt},
            ],
        )
        draft = resp.choices[0].message.content.strip()
    return draft


def generate_tags(topic: str, draft: str, max_tags: int = 5):
    fallback = ["????????", "Kindle", "Kobo", "???"]
    preview = re.sub(r"\s+", " ", draft.strip())[:1200]
    prompt = f"""?????: {topic}

???????: {preview}

??????????????????????{max_tags}??JSON?????????????????10????????????????"""
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
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
    prompt = f"""?????: {topic}
????: {preview}

???????????????????????SEO?????1????????????
??:
- 32?60????
- ????????Kindle/Kobo/??????????????
- ??????????????????????????
- ???????????????????????
- ?????????"""
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[
                {"role": "system", "content": "????SEO????????????????"},
                {"role": "user", "content": prompt},
            ],
        )
        title = resp.choices[0].message.content.strip()
        title = re.sub(r'["??]', "", title)
        if 10 <= len(title) <= 80:
            return title
    except Exception:
        pass
    return f"{topic} ?????"


def build_search_keyword(topic: str, max_words: int = 6, max_chars: int = 60) -> str:
    cleaned = re.sub(r"[??????\[\]\(\)??]", " ", topic)
    words = [w for w in re.split(r"\s+", cleaned) if w]
    keyword = " ".join(words[:max_words]) or topic
    return keyword[:max_chars]


def fetch_rakuten_items(topic: str, hits: int = 3) -> List[Dict[str, str]]:
    if not (RAKUTEN_APP_ID and RAKUTEN_AFFILIATE_ID):
        print("[Rakuten] Missing app or affiliate ID. Skipping.")
        return []

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
        return []

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
    else:
        print(f"[Rakuten] Selected {len(items)} items for {keyword}.")
    return items


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


def make_post(topic: str, slug: str, template: str = USER_TMPL):
    is_trend_template = template == TREND_USER_TMPL
    user = template.format(topic=topic)
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
    )
    draft = resp.choices[0].message.content.strip()
    for _ in range(2):
        review_prompt = f"""????????????????????????????????????????????????

{CHECKLIST}

--- ?? ---
{draft}
--- ???? ---
"""
        r = openai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[{"role": "system", "content": REVIEWER_SYSTEM}, {"role": "user", "content": review_prompt}],
        )
        draft = r.choices[0].message.content.strip()

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

    hero = fetch_pexels_image(topic)
    if hero:
        credit_url = hero.get("photographer_url") or hero.get("pexels_url")
        image_block = (
            f"![{topic}?????]({hero['image_url']})"\
            f"\n<small>Photo by [{hero['photographer']}]({credit_url}) on [Pexels]({hero['pexels_url']})</small>"
        )
        parts = draft.split("\n\n", 1)
        if len(parts) == 2:
            draft = parts[0].strip() + "\n\n" + image_block + "\n\n" + parts[1].strip()
        else:
            draft = image_block + "\n\n" + draft

    today = datetime.date.today()

    draft = re.sub(r"(?m)^##\s*H2:\s*", "## ", draft)
    draft = re.sub(r"(?m)^###\s*H3:\s*", "### ", draft)
    draft = re.sub(r"\n?\[????\]\(/posts/?\)\s*", "\n", draft)

    has_related_products = False
    rakuten_items = fetch_rakuten_items(topic)
    if rakuten_items:
        rakuten_lines = ["", "## ??????????", ""]
        for item in rakuten_items:
            rakuten_lines.append(f"- [{item['title']}]({item['url']}){item['price_text']}")
        rakuten_block = "\n".join(rakuten_lines) + "\n"
        has_related_products = True
        summary_match = re.search(r"(\n## ???[\s\S]*?)(?=\n## |\Z)", draft)
        if summary_match:
            insert_pos = summary_match.end()
            draft = draft[:insert_pos] + "\n\n" + rakuten_block + draft[insert_pos:]
        else:
            draft = draft.rstrip() + "\n\n" + rakuten_block

    out_dir = pathlib.Path("content/posts")
    related = pick_related_urls(out_dir, today.isoformat(), k=3)
    related_block_lines = ["", "## ????", ""]
    for title, url in related:
        related_block_lines.append(f"- [{title}]({url})")
    related_block = "\n".join(related_block_lines) + "\n"

    draft = ensure_pillar_links_block(draft)
    draft = draft.rstrip() + "\n\n" + related_block

    seo_title = generate_seo_title(topic, draft)
    tags = generate_tags(topic, draft)
    word_count = count_words(draft)

    fm = dedent(
        f"""\
    ---
    title: "{seo_title}"
    date: {today.isoformat()}
    draft: false
    tags: {tags}
    categories: ["???"]
    description: "{topic}????????????????????????????????????????????????"
    slug: "{slug}"
    hasRelatedProducts: {"true" if has_related_products else "false"}
    ---
    """
    )
    return slug, seo_title, fm + "\n" + draft + "\n", word_count


def pick_related_urls(out_dir: pathlib.Path, today_iso: str, k: int = 3):
    all_posts = list_existing_posts(out_dir)
    candidates = [p for p in all_posts if p["date"] != today_iso]
    if not candidates:
        return [("????", "/posts/")] * k
    seed = datetime.date.today().toordinal()
    random.Random(seed).shuffle(candidates)
    picked = candidates[:k]
    while len(picked) < k:
        picked.append({"title": "????", "url": "/posts/", "date": "1900-01-01"})
    return [(p["title"], p["url"]) for p in picked[:k]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1, help="????????1?3?")
    args = parser.parse_args()

    requested_count = max(1, min(3, args.count))
    if requested_count != args.count:
        print(f"[info] Adjusted count from {args.count} to {requested_count} (allowed range: 1-3).")

    out_dir = pathlib.Path("content/posts")
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    existing_today = sorted(out_dir.glob(f"{today}-*.md"))
    already = len(existing_today)

    need = max(1, requested_count - already)
    need = min(need, 3)
    if need == 0:
        print(f"Already have {already} posts for {today}. Nothing to do.")
        return

    existing_posts = list_existing_posts(out_dir)
    used_titles = {(p.get("title") or "").strip().lower() for p in existing_posts if p.get("title")}
    used_slugs = {p.get("slug") for p in existing_posts if p.get("slug")}
    existing_headings = load_existing_headings(out_dir)
    recent_titles = recent_titles_within(existing_posts, days=7)
    generated_headings: list[Tuple[str, Set[str]]] = []

    def prioritize_topics(candidates):
        scored = []
        for t in candidates:
            score = 0
            lowered = t.lower()
            for kw in ["kindle", "kobo", "????", "ebook", "reader", "epub", "???", "??", "???"]:
                if kw in lowered:
                    score += 2
            for kw in ["????", "??", "???", "???????", "???", "??", "?????"]:
                if kw in lowered:
                    score += 1
            scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored]

    raw_topics = collect_candidates(max(need * 3, need))
    scored = []
    for t in raw_topics:
        score = 0
        lowered = t.lower()
        for kw in ["kindle", "kobo", "????", "ebook", "reader", "epub", "???", "??", "???"]:
            if kw in lowered:
                score += 2
        for kw in ["????", "??", "???", "???????", "???", "??", "?????"]:
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
        nonlocal generated, index
        topic_clean = re.sub(r"\s+", " ", raw_topic).strip()
        if not topic_clean:
            return False
        lowered = topic_clean.lower()
        if lowered in used_titles:
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
            char_count = count_chars(content)
            meets_relaxed = word_count >= RELAXED_MIN_WORDS and char_count >= RELAXED_MIN_CHAR_COUNT
            meets_lower = word_count >= RELAXED_MIN_WORD_COUNT_LOWER and char_count >= RELAXED_MIN_CHAR_COUNT_LOWER
            meets_final = False
            if allow_final:
                final_words = FAILSAFE_MIN_WORDS if use_failsafe else FINAL_MIN_WORDS
                final_chars = FAILSAFE_MIN_CHAR_COUNT if use_failsafe else FINAL_MIN_CHAR_COUNT
                meets_final = word_count >= final_words and char_count >= final_chars
            h2_set = extract_h2_headings(content)
            if h2_set and is_duplicate_headings(h2_set, existing_headings + generated_headings, threshold=0.6):
                print(f"[skip] Draft '{seo_title}' skipped because H2??????????????????")
                continue
            if meets_relaxed or meets_lower or meets_final:
                prefix = f"{today}-{index}"
                path = ensure_unique_path(out_dir, prefix, slug)
                path.write_text(content, encoding="utf-8")
                print(f"generated: {path}")
                used_titles.add(seo_title.strip().lower())
                used_slugs.add(slug)
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
