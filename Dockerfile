FROM python:3.11-slim

WORKDIR /app

# システムの依存関係をインストール
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# spaCyの日本語モデルをダウンロード
RUN python -m spacy download ja_core_news_sm

# アプリケーションファイルをコピー
COPY scrape_web_app.py .

# ポートを公開
EXPOSE 8000

# ログディレクトリを作成
RUN mkdir -p logs

# アプリケーションを起動
CMD ["uvicorn", "scrape_web_app:app", "--host", "0.0.0.0", "--port", "8000"]