import os, csv, json, datetime, pathlib, re, textwrap
from urllib import request
from pathlib import Path

# ===== local .env support (python-dotenv) =====
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    env_path = Path(".") / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass

MODEL = "gpt-4o-mini"
OUTPUT_DIR = pathlib.Path("content/posts")
TOPIC_CSV = pathlib.Path("data/topics.csv")
TZ = datetime.timezone(datetime.timedelta(hours=9))  # JST

def today_str():
    return datetime.datetime.now(TZ).strftime("%Y-%m-%d")

def read_topic_for_today():
    if not TOPIC_CSV.exists():
        print("No topics.csv found. Skip.")
        return None
    with TOPIC_CSV.open(newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            if (row.get("date") or "").strip() == today_str():
                return row
    print("No row for today in topics.csv. Skip.")
    return None

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[　\s/|]+", "-", s)
    s = re.sub(r"[^a-z0-9\-ぁ-んァ-ヶ一-龯]", "", s)
    return s or today_str()

def build_prompt(t):
    kw = t.get("keyword","").strip()
    intent = t.get("search_intent","").strip()
    angle = t.get("angle","").strip()
    cta = t.get("target_url","").strip()
    return f"""
あなたは日本語のSEOライター。Hugoブログ用のMarkdown記事を作成します。出力は本文のみ。

要件:
- タイトル（32文字前後でクリックされやすく）
- 導入（検索意図に沿った問題提起と「誰に何が分かるか」を一文で）
- 本文はH2/H3で論理展開（E-E-A-T）: 具体例・数字・箇条書き
- 注意点/落とし穴・よくある誤解も1セクション
- FAQを3つ以上
- 結論と行動（{cta} へ自然に誘導）
- 参考リンク3つ（一次情報URL。本文は自分の言葉で書く）
- 1200〜1800字目安

前提:
- 主キーワード: {kw}
- 検索意図: {intent}
- 切り口: {angle}

出力形式:
# {{タイトル}}
{{導入}}

## セクション見出し
本文…

### 小見出し
本文…

## よくある誤解・注意点
本文…

## よくある質問
Q: …
A: …
Q: …
A: …
Q: …
A: …

## 参考リンク
- https://…
- https://…
- https://…
""".strip()

def call_openai_chat(prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY が見つかりません。.env か Actions Secrets を設定してください。")
    req = request.Request(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"},
        data=json.dumps({
            "model": MODEL,
            "messages":[
                {"role":"system","content":"You are a helpful writing assistant."},
                {"role":"user","content": prompt}
            ],
            "temperature": 0.7
        }).encode("utf-8")
    )
    with request.urlopen(req) as res:
        j = json.loads(res.read().decode("utf-8"))
        return j["choices"][0]["message"]["content"]

def write_markdown(md_text: str, topic: dict):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_iso = datetime.datetime.now(TZ).strftime("%Y-%m-%dT09:00:00+09:00")
    title_line = md_text.splitlines()[0] if md_text else "# 無題"
    title = title_line.lstrip("# ").strip()[:80] or topic.get("keyword","自動生成記事")
    slug_base = slugify(topic.get("keyword","auto"))
    filename = f"{today_str()}-{slug_base}.md"
    fm = textwrap.dedent(f"""\
    ---
    title: "{title}"
    date: {date_iso}
    draft: false
    description: ""
    tags: ["自動投稿","{topic.get('search_intent','')}","{topic.get('angle','')}"]
    ---
    """)
    body = "\n".join(md_text.splitlines()[1:]).strip()
    (OUTPUT_DIR / filename).write_text(fm + "\n" + body + "\n", encoding="utf-8")
    print(f"Wrote: content/posts/{filename}")

def main():
    topic = read_topic_for_today()
    if not topic:
        return
    prompt = build_prompt(topic)
    md = call_openai_chat(prompt)
    write_markdown(md, topic)

if __name__ == "__main__":
    main()
