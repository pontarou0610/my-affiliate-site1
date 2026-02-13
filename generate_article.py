import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# 環境変数の読み込み
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise SystemExit("OPENAI_API_KEY not set")
model = (os.getenv("OPENAI_MODEL") or "gpt-5.2").strip() or "gpt-5.2"

# OpenAIクライアント初期化
client = OpenAI(api_key=api_key)

# プロンプト
prompt = """
あなたはプロのアフィリエイトブロガーです。
「Amazonプライムのメリット」について、初心者向けに1000文字程度の記事を書いてください。
日本語で、見出しと本文を含むブログ記事の形式でお願いします。
"""

# Responses APIで問い合わせ
response = client.responses.create(
    model=model,
    input=[
        {"role": "system", "content": "あなたはプロの日本語SEOブロガーです。"},
        {"role": "user", "content": prompt},
    ],
    temperature=0.7,
)

article = (response.output_text or "").strip()
if not article:
    raise RuntimeError("OpenAI response did not include text output.")

# ファイル出力
today = datetime.now().strftime("%Y-%m-%d")
title = "amazon-prime-merit"
filename = f"content/posts/{title}.md"

with open(filename, "w", encoding="utf-8") as f:
    f.write(f"""---
title: "Amazonプライムのメリット"
date: {today}
draft: false
---

{article}
""")

print(f"{filename} に記事を出力しました。")
