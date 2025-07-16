FROM python:3.11-slim

WORKDIR /app

# Python依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY api/ ./api/

# ポートを公開
EXPOSE 8000

# アプリケーションを起動
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8000"]