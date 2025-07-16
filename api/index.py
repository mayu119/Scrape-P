import os
import re
import logging
import requests
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse

# 軽量なログ設定
logging.basicConfig(level=logging.INFO)

# FastAPIアプリケーション
app = FastAPI()

# あにまんちスクレイピング機能
def detect_animanch_urls(text):
    pattern = r'https?://bbs\.animanch\.com/board/\d+/?'
    urls = re.findall(pattern, text)
    return list(dict.fromkeys(urls))

def simple_split(text, max_length=80):
    if len(text) <= max_length:
        return [text]
    
    result = []
    current_pos = 0
    
    while current_pos < len(text):
        end_pos = min(current_pos + max_length, len(text))
        
        if end_pos < len(text):
            for i in range(end_pos - 1, current_pos + max_length // 2, -1):
                if text[i] in ['。', '！', '？', '、', '，']:
                    end_pos = i + 1
                    break
        
        result.append(text[current_pos:end_pos])
        current_pos = end_pos
    
    return result

def clean_text(text):
    try:
        text = re.sub(r'>>\d+\s*', '', text)
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            if not line.strip():
                continue
            if any(skip_text in line for skip_text in [
                'RSS', 'All Rights Reserved', 'http://', 'https://', '.com'
            ]):
                continue
            filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)
    except Exception as e:
        logging.error(f"テキストクリーニングエラー: {e}")
        return text

def add_line_breaks(text, length=22, max_total_chars=4800, do_split=True):
    try:
        result_lines = []
        characters = ['ゆっくり霊夢', 'ゆっくり魔理沙', 'ゆっくり妖夢']
        char_index = 0
        total_chars = 0
        
        for comment in text.split('\n'):
            if not comment.strip():
                continue
            comment = comment.strip().strip('"')
            current_char = characters[char_index]
            char_index = (char_index + 1) % len(characters)
            
            if do_split and len(comment) > 80:
                split_comments = simple_split(comment)
            else:
                split_comments = [comment]
            
            for split_comment in split_comments:
                comment_lines = []
                current_line = ''
                for char in split_comment:
                    current_line += char
                    if len(current_line) >= length:
                        comment_lines.append(current_line)
                        current_line = ''
                if current_line:
                    comment_lines.append(current_line)
                
                if comment_lines:
                    comment_text = '\n'.join(comment_lines)
                    comment_length = len(split_comment)
                    
                    if total_chars + comment_length > max_total_chars and total_chars > 0:
                        return '\n'.join(result_lines)
                    
                    formatted_comment = f'{current_char}\t"{comment_text}"\t{comment_length}'
                    result_lines.append(formatted_comment)
                    total_chars += comment_length
        
        return '\n'.join(result_lines)
    except Exception as e:
        logging.error(f"改行追加エラー: {e}")
        raise

async def scrape_animanch(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        comments = {}
        comment_items = soup.select('li.list-group-item')
        
        for item in comment_items:
            try:
                res_id_match = re.search(r'res(\d+)', item.get('id', ''))
                if not res_id_match:
                    continue
                comment_id = res_id_match.group(1)
                
                resheader = item.select_one('.resheader')
                if not resheader:
                    continue
                resnumber = resheader.select_one('.resnumber')
                if not resnumber:
                    continue
                
                resbody = item.select_one('div[class^="resbody"]')
                if not resbody:
                    continue
                
                comment_text = ""
                for p in resbody.find_all('p'):
                    if not p.parent or p.parent.name != 'blockquote':
                        if not p.select('img') and not p.select('a.thumb'):
                            p_text = p.get_text().strip()
                            if p_text and p_text != "このレスは削除されています":
                                if comment_text:
                                    comment_text += " " + p_text
                                else:
                                    comment_text = p_text
                
                if resbody.select('a.thumb img'):
                    if comment_text:
                        comment_text += " [画像あり]"
                    else:
                        comment_text = "[画像あり]"
                
                if comment_text:
                    comments[comment_id] = {
                        'id': comment_id,
                        'text': comment_text
                    }
                
            except Exception as e:
                logging.error(f"コメント処理エラー: {e}")
        
        return {'comments': comments, 'url': url}
    except Exception as e:
        logging.error(f"スクレイピングエラー: {e}")
        raise

def format_comments_simple(comments):
    formatted_text = []
    for comment in comments.values():
        if comment['text']:
            text = comment['text'].replace('[画像あり]', '').strip()
            if text:
                formatted_text.append(f'"{text}"')
    return "\n".join(formatted_text)

# ルートエンドポイント
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>あにまんch スクレイピングツール</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h1 { color: #333; text-align: center; margin-bottom: 30px; }
        .section { margin-bottom: 30px; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input, textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 16px; margin-bottom: 10px; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        .result { margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px; border: 1px solid #dee2e6; display: none; white-space: pre-wrap; font-family: monospace; max-height: 400px; overflow-y: auto; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .copy-btn { background: #28a745; margin-left: 10px; font-size: 14px; padding: 5px 10px; }
        .copy-btn:hover { background: #218838; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 あにまんch スクレイピングツール</h1>
        
        <div class="section">
            <h3>URLスクレイピング</h3>
            <label for="url">あにまんch URL:</label>
            <input type="text" id="url" placeholder="https://bbs.animanch.com/board/123456/">
            <button onclick="scrapeUrl()">スクレイピング開始</button>
            <button class="copy-btn" onclick="copyResult('scrape-result')">コピー</button>
            <div id="scrape-result" class="result"></div>
        </div>
        
        <div class="section">
            <h3>テキスト処理</h3>
            <label for="text">処理するテキスト:</label>
            <textarea id="text" rows="5" placeholder="ここにテキストを貼り付けてください"></textarea>
            <label><input type="checkbox" id="split_text" checked> 長いテキストを自動分割する</label>
            <button onclick="processText()">テキスト処理開始</button>
            <button class="copy-btn" onclick="copyResult('process-result')">コピー</button>
            <div id="process-result" class="result"></div>
        </div>
    </div>
    
    <script>
        function showResult(elementId, text, isError = false) {
            const element = document.getElementById(elementId);
            element.textContent = text;
            element.className = isError ? 'result error' : 'result';
            element.style.display = 'block';
        }
        
        async function scrapeUrl() {
            const url = document.getElementById('url').value;
            if (!url) { showResult('scrape-result', 'URLを入力してください', true); return; }
            
            try {
                const response = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `url=${encodeURIComponent(url)}`
                });
                const result = await response.text();
                showResult('scrape-result', result, !response.ok);
            } catch (error) {
                showResult('scrape-result', `エラー: ${error.message}`, true);
            }
        }
        
        async function processText() {
            const text = document.getElementById('text').value;
            const splitText = document.getElementById('split_text').checked;
            if (!text) { showResult('process-result', 'テキストを入力してください', true); return; }
            
            try {
                const response = await fetch('/api/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: `text=${encodeURIComponent(text)}&split_text=${splitText}`
                });
                const result = await response.text();
                showResult('process-result', result, !response.ok);
            } catch (error) {
                showResult('process-result', `エラー: ${error.message}`, true);
            }
        }
        
        function copyResult(elementId) {
            const text = document.getElementById(elementId).textContent;
            navigator.clipboard.writeText(text).then(() => {
                alert('コピーしました！');
            }).catch(() => {
                alert('コピーに失敗しました');
            });
        }
    </script>
</body>
</html>""")

@app.post("/api/scrape")
async def scrape_url(url: str = Form(...)):
    try:
        if not url or not url.strip():
            return "URLが入力されていません。"
        
        url = url.strip()
        if not url.startswith('https://bbs.animanch.com/board/'):
            return "無効なURLです。あにまんchの掲示板URLを入力してください。"
        
        scraped_data = await scrape_animanch(url)
        if not scraped_data or not scraped_data['comments']:
            return "コメントが見つかりませんでした。"
        
        simple_text = format_comments_simple(scraped_data['comments'])
        formatted_text = add_line_breaks(simple_text)
        
        return formatted_text
        
    except Exception as e:
        logging.error(f"スクレイピング処理エラー: {e}")
        return f"エラーが発生しました: {str(e)}"

@app.post("/api/process")
async def process_text(text: str = Form(...), split_text: bool = Form(True)):
    try:
        if not text or not text.strip():
            return "テキストが入力されていません。"
        
        text = text.strip()
        if len(text) > 50000:
            return "テキストが長すぎます。50,000文字以下にしてください。"
        
        cleaned_text = clean_text(text)
        formatted_text = add_line_breaks(cleaned_text, do_split=split_text)
        
        return formatted_text
        
    except Exception as e:
        logging.error(f"テキスト処理エラー: {e}")
        return f"エラーが発生しました: {str(e)}"

@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "message": "あにまんch スクレイピングツール稼働中",
        "timestamp": datetime.now().isoformat()
    }

# Vercel用ハンドラー
handler = app