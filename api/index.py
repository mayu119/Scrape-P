from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from datetime import datetime

# 最小限のFastAPIアプリケーション
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>あにまんch スクレイピングツール - 最小版</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background: #f0f0f0; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; margin-bottom: 30px; }
        .test-section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
        input, textarea { width: 100%; padding: 8px; margin: 5px 0; border: 1px solid #ccc; border-radius: 3px; }
        button { background: #007bff; color: white; padding: 8px 16px; border: none; border-radius: 3px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .result { margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 3px; border: 1px solid #dee2e6; font-family: monospace; white-space: pre-wrap; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 あにまんch ツール - 最小版</h1>
        <p><strong>Vercel動作テスト中...</strong></p>
        
        <div class="test-section">
            <h3>基本テスト</h3>
            <button onclick="testBasic()">基本動作テスト</button>
            <div id="basic-result" class="result" style="display:none;"></div>
        </div>
        
        <div class="test-section">
            <h3>テキスト処理テスト</h3>
            <textarea id="test-text" placeholder="テストテキストを入力"></textarea>
            <button onclick="testText()">テキスト処理テスト</button>
            <div id="text-result" class="result" style="display:none;"></div>
        </div>
    </div>
    
    <script>
        function showResult(elementId, text, isError = false) {
            const element = document.getElementById(elementId);
            element.textContent = text;
            element.className = isError ? 'result error' : 'result';
            element.style.display = 'block';
        }
        
        async function testBasic() {
            try {
                const response = await fetch('/api/test');
                const result = await response.text();
                showResult('basic-result', result, !response.ok);
            } catch (error) {
                showResult('basic-result', `エラー: ${error.message}`, true);
            }
        }
        
        async function testText() {
            const text = document.getElementById('test-text').value;
            if (!text) {
                showResult('text-result', 'テキストを入力してください', true);
                return;
            }
            
            try {
                const response = await fetch('/api/process-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `text=${encodeURIComponent(text)}`
                });
                const result = await response.text();
                showResult('text-result', result, !response.ok);
            } catch (error) {
                showResult('text-result', `エラー: ${error.message}`, true);
            }
        }
    </script>
</body>
</html>""")

@app.get("/api/test")
async def test_basic():
    """基本動作テスト"""
    return f"✅ Vercel FastAPI 基本動作 OK - {datetime.now().isoformat()}"

@app.post("/api/process-test")
async def test_process(text: str = Form(...)):
    """テキスト処理テスト（最小版）"""
    try:
        if not text or not text.strip():
            return "テキストが入力されていません。"
        
        text = text.strip()
        lines = text.split('\n')
        characters = ['ゆっくり霊夢', 'ゆっくり魔理沙', 'ゆっくり妖夢']
        
        result_lines = []
        for i, line in enumerate(lines[:3]):  # 最初の3行のみ
            if line.strip():
                char = characters[i % len(characters)]
                result_lines.append(f'{char}\t"{line.strip()}"\t{len(line.strip())}')
        
        if not result_lines:
            return "処理可能なテキストがありませんでした。"
        
        return '\n'.join(result_lines)
        
    except Exception as e:
        return f"エラーが発生しました: {str(e)}"

@app.get("/api/health")
async def health_check():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "message": "最小版 FastAPI 稼働中",
        "timestamp": datetime.now().isoformat(),
        "dependencies": ["fastapi", "python-multipart"]
    }

# Vercel用ハンドラー
handler = app