FROM python:3.11-slim

WORKDIR /app

# Python依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションファイルをコピー
COPY api/ ./api/
COPY start.sh ./start.sh

# スタートアップスクリプトを実行可能にする
RUN chmod +x /app/start.sh

# Railway用ポート環境変数を使用
ENV PORT=8000
EXPOSE $PORT

# スタートアップスクリプトを実行
CMD ["./start.sh"]