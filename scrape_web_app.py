import os
import re
import logging
import requests
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
# spaCy + ginzaを削除してルールベース処理のみ使用
from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncio
import json
from typing import Dict, List
import uvicorn

# 既存のコードから必要な関数をインポート
# ログ設定
def setup_logging():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, f'web_app_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return log_file

# あにまんchのURL検出
def detect_animanch_urls(text):
    """クリップボードテキストからあにまんchのURLを検出する"""
    try:
        pattern = r'https?://bbs\.animanch\.com/board/\d+/?'
        urls = re.findall(pattern, text)
        unique_urls = list(dict.fromkeys(urls))
        return unique_urls
    except Exception as e:
        logging.error(f"URL検出中にエラー発生: {e}")
        return []

# 軽量テキスト分割（ルールベースのみ）
def split_long_text(text, max_length=80, min_length=30):
    """軽量なルールベース分割（spaCy不要）"""
    try:
        blocks = improved_rule_based_split(text, max_length)
        return absorb_short_lines(blocks, min_length)
    except Exception as e:
        logging.error(f"テキスト分割でエラー: {e}")
        # 最も基本的な分割にフォールバック
        return simple_split(text, max_length)

def improved_rule_based_split(text, max_length=80):
    break_chars = [
        ('。', 100), ('！', 100), ('？', 100),
        ('、', 80), ('，', 80),
        ('ので', 70), ('から', 70), ('けれど', 70),
        ('という', 60), ('ところ', 60),
        ('について', 50), ('に対して', 50),
        ('は', 40), ('が', 40), ('を', 40), ('に', 40),
        ('と', 30), ('で', 30), ('の', 30)
    ]
    result = []
    current_text = ""
    i = 0
    while i < len(text):
        current_text += text[i]
        if len(current_text) >= max_length:
            best_pos = -1
            best_score = 0
            for bc, score in break_chars:
                pos = current_text.rfind(bc)
                if pos > len(current_text)//2 and score > best_score:
                    best_pos = pos + len(bc)
                    best_score = score
            if best_pos > 0:
                result.append(current_text[:best_pos])
                current_text = current_text[best_pos:]
            else:
                result.append(current_text)
                current_text = ""
        i += 1
    if current_text:
        result.append(current_text)
    return result

def absorb_short_lines(blocks, min_length=30):
    """短すぎる行を前後に吸収して自然な分割にする"""
    if not blocks:
        return []
    new_blocks = []
    buffer = ""
    for block in blocks:
        if len(block) < min_length:
            buffer += block
        else:
            if buffer:
                new_blocks.append(buffer)
                buffer = ""
            new_blocks.append(block)
    if buffer:
        if new_blocks:
            new_blocks[-1] += buffer
        else:
            new_blocks.append(buffer)
    merged = []
    for block in new_blocks:
        if merged and len(block) < min_length:
            merged[-1] += block
        else:
            merged.append(block)
    return merged

def simple_split(text, max_length=80):
    """最も基本的な分割（フォールバック用）"""
    if len(text) <= max_length:
        return [text]
    
    result = []
    current_pos = 0
    
    while current_pos < len(text):
        end_pos = min(current_pos + max_length, len(text))
        
        # 句読点で分割を試みる
        if end_pos < len(text):
            # 後ろから句読点を探す
            for i in range(end_pos - 1, current_pos + max_length // 2, -1):
                if text[i] in ['。', '！', '？', '、', '，']:
                    end_pos = i + 1
                    break
        
        result.append(text[current_pos:end_pos])
        current_pos = end_pos
    
    return result

# テキストクリーニング（Textprocessor.pyから）
def clean_text(text):
    """基本的なテキストクリーニング"""
    try:
        text = re.sub(r'>>\\d+\\s*', '', text)
        text = re.sub(r'^\\d{4}(?:\\s+|$)', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\\d+(?:\\s+|$)', '', text, flags=re.MULTILINE)
        text = re.sub(r'\\d+: 名無しのあにまんch \\d{4}/\\d{2}/\\d{2}\\(.\\) \\d{2}:\\d{2}:\\d{2}', '', text)
        
        lines = text.split('\\n')
        filtered_lines = []
        
        for line in lines:
            if not line.strip():
                continue
                
            if any(skip_text in line for skip_text in [
                'RSS', 'All Rights Reserved', '問い合わせ',
                'ジャンプ', 'ワンピース', 'ナルト',
                '深夜アニメ界隈', 'まとめサイトです',
                'http://', 'https://', '.com'
            ]):
                continue
            
            filtered_lines.append(line)
        
        text = '\\n'.join(filtered_lines)
        return text
    except Exception as e:
        logging.error(f"テキストクリーニングでエラー発生: {e}")
        raise

# 改行追加とキャラクター挿入
def add_line_breaks(text, length=22, max_total_chars=20000, do_split=True):
    """改行の追加とキャラクター名の挿入、文字数制限付き（ゆっくりボイス版のみ）"""
    try:
        result_lines = []
        characters = ['ゆっくり霊夢', 'ゆっくり魔理沙', 'ゆっくり妖夢']
        char_index = 0
        total_chars = 0
        
        for comment in text.split('\\n'):
            if not comment.strip():
                continue
            comment = comment.strip().strip('"')
            current_char = characters[char_index]
            char_index = (char_index + 1) % len(characters)
            
            if do_split and len(comment) > 80:
                split_comments = split_long_text(comment)
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
                    comment_text = chr(10).join(comment_lines)
                    comment_length = len(split_comment)
                    
                    if total_chars + comment_length > max_total_chars and total_chars > 0:
                        return '\\n'.join(result_lines)
                    
                    formatted_comment = f'{current_char}\\t"{comment_text}"\\t{comment_length}'
                    result_lines.append(formatted_comment)
                    total_chars += comment_length
        
        return '\\n'.join(result_lines)
    except Exception as e:
        logging.error(f"改行追加処理でエラー発生: {e}")
        raise

# スクレイピング機能
async def scrape_animanch(url, websocket: WebSocket = None):
    """あにまんchの掲示板ページからコメントを抽出する"""
    try:
        if websocket:
            await websocket.send_text(json.dumps({"type": "progress", "message": "ページの取得を開始しています..."}))
        
        logging.info(f"ページの取得を開始: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        if websocket:
            await websocket.send_text(json.dumps({"type": "progress", "message": "ページの解析中..."}))
        
        logging.info(f"ページの取得に成功。ステータスコード: {response.status_code}")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ページタイトルを取得
        title_element = soup.find('title')
        page_title = title_element.text.strip() if title_element else "タイトル不明"
        
        thread_title_element = soup.select_one('#threadTitle')
        if thread_title_element:
            thread_title_text = ""
            for node in thread_title_element.contents:
                if isinstance(node, (str, NavigableString)):
                    text_content = str(node).strip()
                    if text_content:
                        thread_title_text += text_content
                else:
                    break
            
            if not thread_title_text:
                thread_title_text = thread_title_element.get_text().strip()
                thread_title_text = re.sub(r'(共有|シェア|お気に入り|ブックマーク).*$', '', thread_title_text).strip()
                thread_title_text = re.sub(r'(favorite|share|bookmark).*$', '', thread_title_text, flags=re.IGNORECASE).strip()
            
            if thread_title_text:
                page_title = thread_title_text
                logging.info(f"スレッドタイトルを取得: {page_title}")
        
        if websocket:
            await websocket.send_text(json.dumps({"type": "progress", "message": "コメントの抽出中..."}))
        
        comments = {}
        comment_items = soup.select('li.list-group-item')
        logging.info(f"コメントアイテム数: {len(comment_items)}")
        
        for i, item in enumerate(comment_items):
            if websocket and i % 10 == 0:
                progress = int((i / len(comment_items)) * 100)
                await websocket.send_text(json.dumps({"type": "progress", "message": f"コメント処理中... {progress}%"}))
            
            try:
                res_id_match = re.search(r'res(\\d+)', item.get('id', ''))
                if not res_id_match:
                    continue
                comment_id = res_id_match.group(1)
                
                resheader = item.select_one('.resheader')
                if not resheader:
                    continue
                resnumber = resheader.select_one('.resnumber')
                if not resnumber:
                    continue
                
                comment_number = resnumber.text.strip()
                author = resheader.select_one('.resname')
                author_text = author.text.strip() if author else "不明"
                date = resheader.select_one('.resposted')
                date_text = date.text.strip() if date else "日時不明"
                
                resbody = item.select_one('div[class^="resbody"]')
                if not resbody:
                    continue
                
                anchors = []
                reslinks = resbody.select('a.reslink')
                for reslink in reslinks:
                    anchor_match = re.search(r'>>(\\d+)', reslink.text)
                    if anchor_match:
                        anchor_id = anchor_match.group(1)
                        if anchor_id not in anchors:
                            anchors.append(anchor_id)
                
                paragraphs = []
                for p in resbody.find_all('p'):
                    if not p.parent or p.parent.name != 'blockquote':
                        if not p.select('img') and not p.select('a.thumb'):
                            paragraphs.append(p)
                
                comment_text = ""
                for p in paragraphs:
                    p_text = p.get_text()
                    for anchor in anchors:
                        p_text = p_text.replace(f">>{anchor}", "")
                    p_text = p_text.strip()
                    if p_text == "このレスは削除されています":
                        continue
                    if p_text:
                        if comment_text:
                            comment_text += " " + p_text
                        else:
                            comment_text = p_text
                
                if resbody.select('a.thumb img'):
                    if comment_text:
                        comment_text += " [画像あり]"
                    else:
                        comment_text = "[画像あり]"
                
                comments[comment_id] = {
                    'id': comment_id,
                    'number': comment_number,
                    'author': author_text,
                    'date': date_text,
                    'text': comment_text,
                    'anchors': anchors
                }
                
            except Exception as e:
                logging.error(f"コメントブロックの処理中にエラー発生: {e}")
        
        if websocket:
            await websocket.send_text(json.dumps({"type": "progress", "message": "コメントの整理中..."}))
        
        logging.info(f"合計 {len(comments)} 件のコメントを抽出しました")
        
        return {
            'title': page_title,
            'comments': comments,
            'url': url
        }
    except Exception as e:
        if websocket:
            await websocket.send_text(json.dumps({"type": "error", "message": f"エラーが発生しました: {str(e)}"}))
        logging.error(f"スクレイピング中にエラー発生: {e}", exc_info=True)
        raise

def reorganize_comments(comments):
    """アンカー参照に基づいてコメントを再構成する"""
    try:
        organized_comments = []
        processed_ids = set()
        comment_ids = sorted([int(cid) for cid in comments.keys()])
        
        for current_id in comment_ids:
            current_id_str = str(current_id)
            if current_id_str in processed_ids:
                continue
            organized_comments.append(comments[current_id_str])
            processed_ids.add(current_id_str)
            process_anchors_dfs(current_id_str, comments, organized_comments, processed_ids)
        return organized_comments
    except Exception as e:
        logging.error(f"コメント再構成中にエラー発生: {e}", exc_info=True)
        raise

def process_anchors_dfs(comment_id, comments, organized_comments, processed_ids):
    """アンカー参照を深さ優先で処理する"""
    if comment_id not in comments:
        return
    anchors = comments[comment_id]['anchors']
    for anchor_id in anchors:
        if anchor_id in processed_ids or anchor_id not in comments:
            continue
        organized_comments.append(comments[anchor_id])
        processed_ids.add(anchor_id)
        process_anchors_dfs(anchor_id, comments, organized_comments, processed_ids)

def format_comments_simple(comments):
    """コメントを簡易形式で出力する（本文のみを引用符で囲む）"""
    try:
        formatted_text = []
        for comment in comments:
            if comment['text']:
                text = comment['text'].replace('[画像あり]', '').strip()
                if text:
                    formatted_text.append(f'"{text}"')
        return "\\n".join(formatted_text)
    except Exception as e:
        logging.error(f"コメント整形（簡易版）中にエラー発生: {e}", exc_info=True)
        raise

def format_with_speaker(comments, length=22, max_total_chars=20000, do_split=True):
    """コメントを話者付きで整形する"""
    try:
        simple_text = format_comments_simple(comments)
        formatted_text = add_line_breaks(
            simple_text,
            length=length,
            max_total_chars=max_total_chars,
            do_split=do_split
        )
        return formatted_text
    except Exception as e:
        logging.error(f"話者付き整形中にエラー発生: {e}", exc_info=True)
        raise

# FastAPI アプリケーション
app = FastAPI()

# WebSocket接続管理
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

manager = ConnectionManager()

# 静的ファイルとテンプレート（後で作成）
# app.mount("/static", StaticFiles(directory="static"), name="static")
# templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    html_content = """
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>あにまんch スクレイピング & テキスト処理ツール</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                color: #333;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
            }
            
            .header {
                text-align: center;
                margin-bottom: 40px;
                color: white;
            }
            
            .header h1 {
                font-size: 2.5rem;
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            
            .header p {
                font-size: 1.2rem;
                opacity: 0.9;
            }
            
            .tabs {
                display: flex;
                background: white;
                border-radius: 10px 10px 0 0;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            
            .tab {
                flex: 1;
                padding: 20px;
                background: #f8f9fa;
                border: none;
                cursor: pointer;
                font-size: 1.1rem;
                font-weight: bold;
                transition: all 0.3s ease;
            }
            
            .tab.active {
                background: white;
                color: #667eea;
            }
            
            .tab:hover {
                background: #e9ecef;
            }
            
            .tab-content {
                background: white;
                border-radius: 0 0 10px 10px;
                padding: 40px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            
            .form-group {
                margin-bottom: 25px;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: bold;
                color: #555;
            }
            
            .form-control {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 8px;
                font-size: 1rem;
                transition: border-color 0.3s ease;
            }
            
            .form-control:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            }
            
            textarea.form-control {
                resize: vertical;
                min-height: 200px;
            }
            
            .btn {
                padding: 12px 30px;
                border: none;
                border-radius: 8px;
                font-size: 1.1rem;
                font-weight: bold;
                cursor: pointer;
                transition: all 0.3s ease;
                margin-right: 10px;
            }
            
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            
            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
            }
            
            .btn-secondary {
                background: #6c757d;
                color: white;
            }
            
            .btn-secondary:hover {
                background: #5a6268;
            }
            
            .progress-container {
                margin: 20px 0;
                display: none;
            }
            
            .progress-bar {
                width: 100%;
                height: 20px;
                background: #f0f0f0;
                border-radius: 10px;
                overflow: hidden;
            }
            
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #667eea, #764ba2);
                width: 0%;
                transition: width 0.3s ease;
            }
            
            .progress-text {
                text-align: center;
                margin-top: 10px;
                font-weight: bold;
                color: #555;
            }
            
            .result-container {
                margin-top: 30px;
                display: none;
            }
            
            .result-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
            }
            
            .result-text {
                background: #f8f9fa;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 20px;
                min-height: 300px;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
                line-height: 1.6;
                white-space: pre-wrap;
                overflow-y: auto;
                max-height: 500px;
            }
            
            .copy-btn {
                background: #28a745;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                cursor: pointer;
                font-weight: bold;
                transition: background 0.3s ease;
            }
            
            .copy-btn:hover {
                background: #218838;
            }
            
            .copy-btn.copied {
                background: #17a2b8;
            }
            
            .hidden {
                display: none;
            }
            
            .loading {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid #f3f3f3;
                border-top: 3px solid #667eea;
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin-right: 10px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .error {
                background: #f8d7da;
                color: #721c24;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                border: 1px solid #f5c6cb;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 10px;
                }
                
                .header h1 {
                    font-size: 2rem;
                }
                
                .tab-content {
                    padding: 20px;
                }
                
                .tabs {
                    flex-direction: column;
                }
                
                .result-header {
                    flex-direction: column;
                    align-items: stretch;
                    gap: 10px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 あにまんch スクレイピングツール</h1>
                <p>URLからスクレイピング | テキスト処理 | ゆっくりボイス出力</p>
            </div>
            
            <div class="tabs">
                <button class="tab active" onclick="switchTab('scrape')">URLスクレイピング</button>
                <button class="tab" onclick="switchTab('process')">テキスト処理</button>
            </div>
            
            <div class="tab-content">
                <!-- スクレイピングタブ -->
                <div id="scrape-tab" class="tab-panel">
                    <form id="scrape-form">
                        <div class="form-group">
                            <label for="url">あにまんch URL:</label>
                            <input type="url" id="url" name="url" class="form-control" 
                                   placeholder="https://bbs.animanch.com/board/123456/" required>
                        </div>
                        <button type="submit" class="btn btn-primary">
                            <span id="scrape-loading" class="loading hidden"></span>
                            スクレイピング開始
                        </button>
                    </form>
                    
                    <div id="scrape-progress" class="progress-container">
                        <div class="progress-bar">
                            <div id="scrape-progress-fill" class="progress-fill"></div>
                        </div>
                        <div id="scrape-progress-text" class="progress-text">処理中...</div>
                    </div>
                    
                    <div id="scrape-result" class="result-container">
                        <div class="result-header">
                            <h3>スクレイピング結果（ゆっくりボイス形式）</h3>
                            <button class="copy-btn" onclick="copyToClipboard('scrape-result-text')">コピー</button>
                        </div>
                        <div id="scrape-result-text" class="result-text"></div>
                    </div>
                </div>
                
                <!-- テキスト処理タブ -->
                <div id="process-tab" class="tab-panel hidden">
                    <form id="process-form">
                        <div class="form-group">
                            <label for="text">処理するテキスト:</label>
                            <textarea id="text" name="text" class="form-control" 
                                      placeholder="ここにテキストを貼り付けてください..." required></textarea>
                        </div>
                        <div class="form-group">
                            <label>
                                <input type="checkbox" id="split_text" name="split_text" checked>
                                長いテキストを自動分割する
                            </label>
                        </div>
                        <button type="submit" class="btn btn-primary">
                            <span id="process-loading" class="loading hidden"></span>
                            テキスト処理開始
                        </button>
                    </form>
                    
                    <div id="process-result" class="result-container">
                        <div class="result-header">
                            <h3>処理結果（ゆっくりボイス形式）</h3>
                            <button class="copy-btn" onclick="copyToClipboard('process-result-text')">コピー</button>
                        </div>
                        <div id="process-result-text" class="result-text"></div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            let ws = null;
            
            function switchTab(tabName) {
                // タブの切り替え
                document.querySelectorAll('.tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                document.querySelectorAll('.tab-panel').forEach(panel => {
                    panel.classList.add('hidden');
                });
                
                document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
                document.getElementById(`${tabName}-tab`).classList.remove('hidden');
            }
            
            function showProgress(type) {
                document.getElementById(`${type}-progress`).style.display = 'block';
                document.getElementById(`${type}-result`).style.display = 'none';
                document.getElementById(`${type}-loading`).classList.remove('hidden');
            }
            
            function hideProgress(type) {
                document.getElementById(`${type}-progress`).style.display = 'none';
                document.getElementById(`${type}-loading`).classList.add('hidden');
            }
            
            function showResult(type, text) {
                hideProgress(type);
                document.getElementById(`${type}-result`).style.display = 'block';
                document.getElementById(`${type}-result-text`).textContent = text;
            }
            
            function showError(message) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'error';
                errorDiv.textContent = `エラー: ${message}`;
                document.querySelector('.tab-content').prepend(errorDiv);
                setTimeout(() => errorDiv.remove(), 5000);
            }
            
            // スクレイピングフォーム
            document.getElementById('scrape-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const url = document.getElementById('url').value;
                
                showProgress('scrape');
                
                try {
                    // WebSocket接続
                    ws = new WebSocket(`ws://localhost:8000/ws`);
                    
                    ws.onmessage = function(event) {
                        const data = JSON.parse(event.data);
                        if (data.type === 'progress') {
                            document.getElementById('scrape-progress-text').textContent = data.message;
                        } else if (data.type === 'error') {
                            hideProgress('scrape');
                            showError(data.message);
                        }
                    };
                    
                    const response = await fetch('/scrape', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: `url=${encodeURIComponent(url)}`
                    });
                    
                    const result = await response.text();
                    
                    if (response.ok) {
                        showResult('scrape', result);
                    } else {
                        hideProgress('scrape');
                        showError(result);
                    }
                    
                } catch (error) {
                    hideProgress('scrape');
                    showError(error.message);
                }
                
                if (ws) {
                    ws.close();
                }
            });
            
            // テキスト処理フォーム
            document.getElementById('process-form').addEventListener('submit', async (e) => {
                e.preventDefault();
                const text = document.getElementById('text').value;
                const splitText = document.getElementById('split_text').checked;
                
                showProgress('process');
                
                try {
                    const response = await fetch('/process', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: `text=${encodeURIComponent(text)}&split_text=${splitText}`
                    });
                    
                    const result = await response.text();
                    
                    if (response.ok) {
                        showResult('process', result);
                    } else {
                        hideProgress('process');
                        showError(result);
                    }
                    
                } catch (error) {
                    hideProgress('process');
                    showError(error.message);
                }
            });
            
            // コピー機能
            function copyToClipboard(elementId) {
                const text = document.getElementById(elementId).textContent;
                navigator.clipboard.writeText(text).then(() => {
                    const btn = event.target;
                    const originalText = btn.textContent;
                    btn.textContent = 'コピーしました！';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.textContent = originalText;
                        btn.classList.remove('copied');
                    }, 2000);
                }).catch(err => {
                    console.error('コピーに失敗:', err);
                    showError('コピーに失敗しました');
                });
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/scrape")
async def scrape_url(url: str = Form(...)):
    """URLからスクレイピングを実行"""
    try:
        # URLの検証
        if not url or not url.strip():
            return "URLが入力されていません。"
        
        url = url.strip()
        if not url.startswith('https://bbs.animanch.com/board/'):
            return "無効なURLです。あにまんchの掲示板URLを入力してください。\n例: https://bbs.animanch.com/board/123456/"
        
        # スクレイピング実行
        scraped_data = await scrape_animanch(url)
        if not scraped_data:
            return "ページの読み込みに失敗しました。URLを確認してください。"
        
        if not scraped_data.get('comments'):
            return "コメントが見つかりませんでした。このページにはコメントがない可能性があります。"
        
        # コメントの再構成と整形
        organized_comments = reorganize_comments(scraped_data['comments'])
        if not organized_comments:
            return "コメントの処理に失敗しました。"
        
        formatted_text = format_with_speaker(organized_comments)
        if not formatted_text or not formatted_text.strip():
            return "テキストの整形に失敗しました。"
        
        return formatted_text
        
    except requests.exceptions.RequestException as e:
        logging.error(f"ネットワークエラー: {e}")
        return f"ネットワークエラーが発生しました。しばらくしてから再試行してください。"
    except Exception as e:
        logging.error(f"スクレイピング処理でエラー: {e}", exc_info=True)
        return f"処理中にエラーが発生しました。管理者に連絡してください。\nエラー詳細: {str(e)[:100]}..."

@app.post("/process")
async def process_text(text: str = Form(...), split_text: bool = Form(True)):
    """テキストを処理してゆっくりボイス形式で出力"""
    try:
        # 入力検証
        if not text or not text.strip():
            return "テキストが入力されていません。処理したいテキストを貼り付けてください。"
        
        text = text.strip()
        if len(text) > 50000:  # 50KB制限
            return "テキストが長すぎます。50,000文字以下にしてください。"
        
        # テキストのクリーニング
        try:
            cleaned_text = clean_text(text)
        except Exception as e:
            logging.warning(f"テキストクリーニングでエラー: {e}")
            # クリーニングに失敗した場合は元のテキストを使用
            cleaned_text = text
        
        if not cleaned_text or not cleaned_text.strip():
            return "クリーニング後のテキストが空になりました。別のテキストを試してください。"
        
        # ゆっくりボイス形式で整形
        try:
            formatted_text = add_line_breaks(
                cleaned_text,
                length=22,
                max_total_chars=4800,
                do_split=split_text
            )
        except Exception as e:
            logging.error(f"テキスト整形でエラー: {e}")
            # 基本的な整形にフォールバック
            lines = cleaned_text.split('\n')[:10]  # 最初の10行のみ
            formatted_text = '\n'.join([f'ゆっくり霊夢\t"{line}"\t{len(line)}' for line in lines if line.strip()])
        
        if not formatted_text or not formatted_text.strip():
            return "テキストの整形に失敗しました。入力テキストを確認してください。"
        
        return formatted_text
        
    except Exception as e:
        logging.error(f"テキスト処理でエラー: {e}", exc_info=True)
        return f"処理中にエラーが発生しました。\nエラー詳細: {str(e)[:100]}..."

@app.get("/health")
async def health_check():
    """ヘルスチェック用エンドポイント"""
    return {
        "status": "ok",
        "message": "あにまんch スクレイピングツール稼働中",
        "timestamp": datetime.now().isoformat()
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # WebSocketはプログレス通知用
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logging.error(f"WebSocketエラー: {e}")
        manager.disconnect(websocket)

if __name__ == "__main__":
    setup_logging()
    uvicorn.run(app, host="0.0.0.0", port=8000)