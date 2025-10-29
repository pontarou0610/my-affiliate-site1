import os, re, datetime, pathlib, random
from textwrap import dedent
from dotenv import load_dotenv

# --- env ---
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise SystemExit("OPENAI_API_KEY not set")

# --- RSS sources (無料) ---
RSS_SOURCES = [
    "https://b.hatena.ne.jp/hotentry/it.rss",
    "https://rss.itmedia.co.jp/rss/2.0/topstory.xml",
    "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf",
]

# --- ホワイトリスト（テーマ固定） ---
WHITELIST = [
    "kindle","kobo","電子書籍","電子書籍リーダー","e-ink","e ink","epub","電子インク",
    "リーダー","pdf","青空文庫","読書","ブック","drm","ハイライト","辞書","縦書き",
    "フォント","フロントライト","防水","解像度","ppi","ページ送り","広告つき","広告なし",
]

# --- フォールバック ---
FALLBACK_TOPICS = [
    "KindleとKoboの最新モデル比較（2025年版）",
    "電子書籍の返金・キャンセルの基礎知識",
    "EPUBとPDFの使い分け：学習・技術書・漫画でどう違う？",
    "E-Inkリーダーの目の疲れ対策と設定おすすめ",
    "読書ハイライト活用術：メモ整理と検索を最短で",
    "防水モデルは本当に必要か？通勤・お風呂・旅行で検証",
    "電子書籍のセール攻略：失敗しない買い方の順序",
]

def pick_trending():
    import feedparser
    items = []
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
    uniq, seen = [], set()
    for t in items:
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in seen:
            uniq.append(t); seen.add(t)
    if uniq:
        seed = datetime.date.today().toordinal()
        random.Random(seed).shuffle(uniq)
        picked = uniq[0]
        topic = re.sub(r"【.*?】|\[.*?\]|（.*?）|\(.*?\)", "", picked).strip()
        topic = re.sub(r"。+$", "", topic)
        return topic, ["trend","hot"]
    else:
        seed = datetime.date.today().toordinal() % len(FALLBACK_TOPICS)
        return FALLBACK_TOPICS[seed], ["fallback"]

def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\-一-龠ぁ-んァ-ヴー]", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80]

topic, trend_tag = pick_trending()

# --- OpenAI 呼び出し ---
import openai
openai.api_key = OPENAI_API_KEY

SYSTEM = "あなたは電子書籍リーダー専門ブログの編集長。事実に忠実で、誇張や過度な断定を避ける。SEO対策を完ぺきに施す。読者が具体的に動ける日本語記事を作る。"

USER = f"""
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
- 内部リンク: 文末に [関連記事](/posts/) を1つだけ
- 仕上げ: 最後に「今日できる小さな一歩」を短く

# スタイルと配慮（重要）
- 文章は「です・ます調」で、やさしくカジュアルに書く
- 専門用語は初出でかんたんな一言解説を入れる（例：「EPUB（電子書籍のファイル形式）」）
- 生成したら自己レビューして必要な改訂を行う（合計3回繰り返す想定）
"""

# 初稿
resp = openai.chat.completions.create(
    model="gpt-4o-mini",
    temperature=0.7,
    messages=[{"role":"system","content":SYSTEM},{"role":"user","content":USER}]
)
draft = resp.choices[0].message.content.strip()

# 自己レビュー ×3
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

for _ in range(3):
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

body = draft

# 保存
today = datetime.date.today()
slug = slugify(topic)
filename = f"{today:%Y-%m-%d}-{slug}.md"
tags = ["電子書籍","Kindle","Kobo","読書術"] + trend_tag
tags = list(dict.fromkeys(tags))

fm = dedent(f"""\
---
title: "{topic}"
date: {today.isoformat()}
draft: false
tags: {tags}
categories: ["ガイド"]
description: "{topic}の要点と実用ヒントをやさしく解説。"
---
""")

out_dir = pathlib.Path("content/posts")
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / filename).write_text(fm + "\n" + body + "\n", encoding="utf-8")
print(f"generated: content/posts/{filename}")
