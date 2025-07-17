FROM python:3.11-slim

# Layer 1: 確実にbashをインストール
RUN apt-get update && apt-get install -y \
    bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 2: 確実なファイルコピーと権限設定
COPY api/ ./api/
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh && \
    ls -la /app/start.sh && \
    echo "start.sh file verification:" && \
    file /app/start.sh

# Layer 3: フォールバック用のシンプル起動スクリプト作成
RUN echo '#!/bin/bash' > /app/fallback.sh && \
    echo 'PORT=${PORT:-8000}' >> /app/fallback.sh && \
    echo 'echo "Fallback: Starting uvicorn directly on port $PORT"' >> /app/fallback.sh && \
    echo 'exec uvicorn api.index:app --host 0.0.0.0 --port $PORT --log-level info' >> /app/fallback.sh && \
    chmod +x /app/fallback.sh

# Railway用ポート環境変数を使用
ENV PORT=8000
EXPOSE $PORT

# Layer 4: 確実な実行 - ENTRYPOINTとCMDの組み合わせ
ENTRYPOINT ["/bin/bash", "-c"]
CMD ["if [ -x /app/start.sh ]; then echo 'Executing start.sh'; exec /app/start.sh; else echo 'start.sh not found, using fallback'; exec /app/fallback.sh; fi"]