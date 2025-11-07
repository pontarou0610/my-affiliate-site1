# scripts/generate_post.py
import os, re, datetime, pathlib, random, argparse, json
from typing import List, Dict

import requests
from textwrap import dedent
from dotenv import load_dotenv
from slugify import slugify as slugify_lib

# ---------- env ----------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY not set")

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

WHITELIST = [
    # コアワード（電子書籍まわり）
    "kindle", "kobo", "電子書籍", "電子書籍リーダー",
    "ebook", "e-book", "e-ink", "e ink", "電子インク", "電子ペーパー",

    # Kindle / Kobo の具体的モデルや機能
    "paperwhite", "scribe", "oasis", "clara", "libra", "sage", "forma",
    "フロントライト", "バックライト", "防水", "解像度", "ppi", "ページ送り",
    "広告つき", "広告なし",

    # 読書機能・フォーマット
    "epub", "pdf", "azw", "mobi", "ドキュメント",
    "辞書", "ハイライト", "メモ", "しおり", "縦書き", "横書き", "フォント",

    # サービス名・使い方系
    "kindle unlimited", "kindle unlimited 読み放題",
    "楽天kobo", "kobo plus",
    "青空文庫",

    # 周辺用途
    "読書", "ブック", "本の管理", "ライブラリ", "クラウド",
    "drm", "drm解除",  # 触れるならフィルタ対象にしておく
]


FALLBACK_TOPICS = [
    # 比較・定番系
    "KindleとKoboの最新モデル比較（2025年版）",
    "2025年に買うべき電子書籍リーダー3選",
    "Kindle UnlimitedとKobo Plusの読み放題を徹底比較",

    # 使い方・ノウハウ
    "EPUBとPDFの使い分け：学習・技術書・漫画でどう違う？",
    "読書ハイライト活用術：メモ・引用を最短で整理する方法",
    "電子書籍のセール攻略：失敗しない買い方の順序",

    # 設定・快適さ
    "E-Inkリーダーの目の疲れを減らす設定おすすめ",
    "防水モデルは本当に必要か？通勤・お風呂・旅行で検証",
    "電子インク端末で日本語縦書きをきれいに表示するコツ",

    # トラブル・豆知識
    "電子書籍の返金・キャンセルの基礎知識",
    "PCやスマホ・Kindle間での読みかけ同期を確実にする方法",
]


def collect_candidates(max_needed: int):
    """RSSから候補収集→ユニーク化。足りなければFALLBACK補完。"""
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
                    text = f"{title} {summary}".lower()
                    if any(w in text for w in WHITELIST):
                        items.append(title)
            except Exception:
                pass
    except ImportError:
        items = []

    seen = set(); uniq = []
    for t in items:
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"【.*?】|\[.*?\]|（.*?）|\(.*?\)", "", t).strip()
        t = re.sub(r"。+$", "", t)
        if t and t not in seen:
            uniq.append(t); seen.add(t)

    seed = datetime.date.today().toordinal()
    random.Random(seed).shuffle(uniq)

    for fb in FALLBACK_TOPICS:
        if len(uniq) >= max_needed: break
        if fb not in seen:
            uniq.append(fb); seen.add(fb)

    return uniq[:max_needed]

# ---------- OpenAI ----------
import openai
openai.api_key = OPENAI_API_KEY

SYSTEM = "あなたは電子書籍リーダー専門ブログの編集長。事実に忠実で、誇張や過度な断定を避ける。SEO対策を完ぺきに施す。読者が具体的に動ける日本語記事を作る。"

USER_TMPL = """\
次のテーマで、読者が迷わず行動できる実用記事を書いてください。

# テーマ
{topic}

# 目的
初めての読者が「何を選び、どう設定し、どんな落とし穴を避けるか」を5分で掴める。

# 出力ルール
- 文字数: 2500〜3000字
- 構成: 冒頭に「要点まとめ」箇条書き3〜5行 → H2中心（必要に応じてH3）
- 方針: 手順・チェックリスト・判断基準を具体化。曖昧な主張・過度な煽りはNG
- 禁止: 外部リンク・価格断定・未検証の噂
- 内部リンク: 文末に [関連記事](/posts/) を1つだけ（※後で実URLに置換）
- 仕上げ: 最後に「今日できる小さな一歩」を短く

# スタイルと配慮（重要）
- 文章は「です・ます調」で、やさしくカジュアルに書く
- 中学生が読んでも理解できるように書く
- 専門用語は初出でかんたんな一言解説を入れる（例：「EPUB（電子書籍のファイル形式）」）
- 生成したら自己レビューして必要な改訂を行う（合計2回繰り返す想定）
"""

REVIEWER_SYSTEM = "あなたは厳格な日本語編集者。論理・構成・可読性・初学者配慮を点検し、必要な修正を加えて完全原稿として返す。"
CHECKLIST = """\
【必ず満たすチェックリスト】
1) です・ます調で自然か？口調がぶれていないか？
2) 専門用語は初出で短い解説があるか？
3) 構成: 要点→H2/H3→結論と小さな一歩、が揃っているか？
4) 断定しすぎ・煽りがないか？根拠の薄い主張は言い切らない
5) 外部リンクを入れていないか？内部リンクは末尾の[関連記事]のみか？
6) 冗長な表現や重複を削って読みやすいか？
"""

TAG_SYSTEM = "あなたはSEOに強い日本語編集者です。記事内容から検索意図に合う短いタグを抽出し、JSON配列で返してください。"
RAKUTEN_API_ENDPOINT = "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601"
PEXELS_API_ENDPOINT = "https://api.pexels.com/v1/search"

# ---------- 既存記事のパース & パーマリンク構築 ----------
def parse_frontmatter(md_text: str):
    m = re.search(r'^---\s*(.*?)\s*---', md_text, re.S | re.M)
    data = {}
    if not m:
        return data
    fm = m.group(1)
    def pick(key):
        mm = re.search(rf'^{key}:\s*(.+)$', fm, re.M)
        if not mm: return None
        val = mm.group(1).strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        return val
    data["title"] = pick("title")
    data["slug"]  = pick("slug")
    data["date"]  = pick("date")
    return data

def permalink_from(date_str: str, slug: str):
    # hugo.toml: posts = "/posts/:year/:month/:slug/"
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
        # ファイル名から推定（保険）
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

def pick_related_urls(out_dir: pathlib.Path, today_iso: str, k: int = 3):
    all_posts = list_existing_posts(out_dir)
    # 今日生成分は除外
    candidates = [p for p in all_posts if p["date"] != today_iso]
    if not candidates:
        return ["/posts/"] * k
    # 安定シャッフル（当日でseed固定）
    seed = datetime.date.today().toordinal()
    random.Random(seed).shuffle(candidates)
    picked = candidates[:k]
    # URLだけ返すと寂しいので (title, url) で返す
    # 不足があれば /posts/ で埋める
    while len(picked) < k:
        picked.append({"title": "記事一覧", "url": "/posts/", "date": "1900-01-01"})
    return [(p["title"], p["url"]) for p in picked[:k]]

def generate_tags(topic: str, draft: str, max_tags: int = 5):
    fallback = ["電子書籍リーダー", "Kindle", "Kobo", "読書術"]
    preview = re.sub(r"\s+", " ", draft.strip())
    preview = preview[:1200]
    prompt = f"""記事テーマ: {topic}

本文冒頭プレビュー: {preview}

上記をもとに、検索意図に沿う日本語タグを最大{max_tags}個、JSON配列のみで出力してください。タグは10文字以内・名詞中心・重複なしで。"""
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.2,
            messages=[
                {"role": "system", "content": TAG_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()
        tags = json.loads(text)
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


def fetch_rakuten_items(topic: str, hits: int = 3) -> List[Dict[str, str]]:
    if not (RAKUTEN_APP_ID and RAKUTEN_AFFILIATE_ID):
        return []

    keyword = re.sub(r"\s+", " ", topic).strip()[:120]
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "affiliateId": RAKUTEN_AFFILIATE_ID,
        "keyword": keyword,
        "hits": hits,
        "imageFlag": 1,
        "sort": "-reviewAverage",
    }
    try:
        resp = requests.get(RAKUTEN_API_ENDPOINT, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    items: List[Dict[str, str]] = []
    for entry in data.get("Items", []):
        item = entry.get("Item", {})
        title = item.get("itemName")
        url = item.get("affiliateUrl") or item.get("itemUrl")
        price = item.get("itemPrice")
        if not title or not url:
            continue
        items.append(
            {
                "title": title,
                "url": url,
                "price": price,
            }
        )
        if len(items) >= hits:
            break
    return items


def fetch_pexels_image(topic: str) -> Dict[str, str] | None:
    if not PEXELS_API_KEY:
        return None
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": re.sub(r"\s+", " ", topic).strip()[:80],
        "per_page": 1,
        "orientation": "landscape",
    }
    try:
        resp = requests.get(PEXELS_API_ENDPOINT, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    photos = data.get("photos") or []
    if not photos:
        return None
    photo = photos[0]
    src = photo.get("src") or {}
    image_url = src.get("large") or src.get("medium")
    if not image_url:
        return None
    return {
        "image_url": image_url,
        "photographer": photo.get("photographer") or "Pexels",
        "photographer_url": photo.get("photographer_url") or photo.get("url"),
        "pexels_url": photo.get("url"),
    }

# ---------- 1本生成 ----------
def make_post(topic: str, slug: str):
    user = USER_TMPL.format(topic=topic)
    resp = openai.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[{"role":"system","content":SYSTEM},{"role":"user","content":user}]
    )
    draft = resp.choices[0].message.content.strip()
    for _ in range(2):
        review_prompt = f"""以下の原稿をチェックリストに沿って自己レビューし、必要な改訂を反映した最終版のみ返してください。

{CHECKLIST}

--- 原稿 ---
{draft}
--- ここまで ---
"""
        r = openai.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.4,
            messages=[{"role":"system","content":REVIEWER_SYSTEM},
                      {"role":"user","content":review_prompt}]
        )
        draft = r.choices[0].message.content.strip()

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

    draft = re.sub(r"\n?\[関連記事\]\(/posts/?\)\s*", "\n", draft)

    rakuten_items = fetch_rakuten_items(topic)
    if rakuten_items:
        rakuten_lines = ["\n## 関連アイテム（楽天）", ""]
        for item in rakuten_items:
            price_text = ""
            try:
                price_int = int(item.get("price"))
                price_text = f" — ¥{price_int:,}"
            except (TypeError, ValueError):
                pass
            rakuten_lines.append(f"- [{item['title']}]({item['url']}){price_text}")
        rakuten_block = "\n".join(rakuten_lines) + "\n"
        summary_match = re.search(r"(\n## まとめ[\s\S]*?)(?=\n## |\Z)", draft)
        if summary_match:
            insert_pos = summary_match.end()
            draft = draft[:insert_pos] + "\n\n" + rakuten_block + draft[insert_pos:]
        else:
            draft = draft.rstrip() + "\n\n" + rakuten_block

    out_dir = pathlib.Path("content/posts")
    related = pick_related_urls(out_dir, today.isoformat(), k=3)

    related_block_lines = ["\n## 関連記事", ""]
    for title, url in related:
        related_block_lines.append(f"- [{title}]({url})")
    related_block = "\n".join(related_block_lines) + "\n"

    draft = draft.rstrip() + "\n\n" + related_block

    tags = generate_tags(topic, draft)

    fm = dedent(f"""\
    ---
    title: "{topic}"
    date: {today.isoformat()}
    draft: false
    tags: {tags}
    categories: ["ガイド"]
    description: "{topic}の要点と実用ヒントをわかりやすく解説。"
    slug: "{slug}"
    ---
    """)
    return slug, fm + "\n" + draft + "\n"


def ensure_unique_path(basedir: pathlib.Path, prefix: str, slug: str):
    """{date}-{seq}-{slug}.md を基本に、衝突時は -2, -3… を付与"""
    p = basedir / f"{prefix}-{slug}.md"
    if not p.exists():
        return p
    n = 2
    while True:
        q = basedir / f"{prefix}-{slug}-{n}.md"
        if not q.exists():
            return q
        n += 1

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=3, help="本日の生成本数")
    args = parser.parse_args()

    out_dir = pathlib.Path("content/posts")
    out_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    existing_today = sorted(out_dir.glob(f"{today}-*.md"))
    already = len(existing_today)

    need = max(0, args.count - already)
    if need == 0:
        print(f"Already have {already} posts for {today}. Nothing to do.")
        return

    existing_posts = list_existing_posts(out_dir)
    used_titles = { (p.get("title") or "").strip().lower() for p in existing_posts if p.get("title") }
    used_slugs = { p.get("slug") for p in existing_posts if p.get("slug") }

    topics = collect_candidates(max(need * 3, need))
    start_index = already + 1
    generated = 0
    index = start_index

    for topic in topics:
        topic_clean = re.sub(r"\s+", " ", topic).strip()
        if not topic_clean:
            continue
        lowered = topic_clean.lower()
        if lowered in used_titles:
            continue

        slug_base = slugify_lib(topic_clean, lowercase=True, max_length=60, separator='-')
        if not slug_base:
            continue
        slug_candidate = slug_base
        suffix = 2
        while slug_candidate in used_slugs:
            slug_candidate = f"{slug_base}-{suffix}"
            suffix += 1

        slug, content = make_post(topic_clean, slug_candidate)
        prefix = f"{today}-{index}"  # 例: 2025-11-03-1, -2, -3
        path = ensure_unique_path(out_dir, prefix, slug)
        path.write_text(content, encoding="utf-8")
        print(f"generated: {path}")

        used_titles.add(lowered)
        used_slugs.add(slug)
        generated += 1
        index += 1

        if generated >= need:
            break

    if generated < need:
        raise SystemExit(f"Unable to generate {need} unique posts (created {generated}).")

if __name__ == "__main__":
    main()
