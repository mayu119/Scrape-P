import os
import re
import logging
import requests
from bs4 import BeautifulSoup, NavigableString
from datetime import datetime
import pyperclip
import spacy
import ginza

def setup_logging():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, f'animanch_scraping_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return log_file

def detect_animanch_urls(text):
    """クリップボードテキストからあにまんchのURLを検出する"""
    try:
        # あにまんchのURLパターン
        pattern = r'https?://bbs\.animanch\.com/board/\d+/?'
        urls = re.findall(pattern, text)
        # 重複を削除
        unique_urls = list(dict.fromkeys(urls))
        return unique_urls
    except Exception as e:
        logging.error(f"URL検出中にエラー発生: {e}")
        return []

# 長いテキストを自然な区切りで分割する関数
def split_long_text(text, max_length=80, min_length=30):
    """意味を壊さず自然な分割を行い、短すぎる行を吸収するハイブリッド手法"""
    try:
        # Phase 1: 意味スコア分割
        blocks = semantic_aware_split(text, max_length, min_length)
    except Exception as e:
        logging.warning(f"semantic_aware_split失敗: {e}")
        try:
            # Phase 2: 文節ベース分割
            blocks = bunsetsu_based_split(text, max_length)
        except Exception as e:
            logging.warning(f"bunsetsu_based_split失敗: {e}")
            # Phase 3: 改良ルールベース
            blocks = improved_rule_based_split(text, max_length)
    # ここで短すぎる行を吸収
    return absorb_short_lines(blocks, min_length)

def semantic_aware_split(text, max_length=80, min_length=30):
    nlp = spacy.load("ja_ginza")
    doc = nlp(text)
    scores = calculate_break_scores(doc)
    result = []
    start_pos = 0
    while start_pos < len(text):
        ideal_end = min(start_pos + max_length, len(text))
        # min_length以上max_length以下で最適な区切りを探す
        best_break = find_best_break_position(scores, start_pos, ideal_end, min_length)
        if best_break > start_pos:
            result.append(text[start_pos:best_break].strip())
            start_pos = best_break
        else:
            # 強制分割
            result.append(text[start_pos:ideal_end].strip())
            start_pos = ideal_end
    return result

def calculate_break_scores(doc):
    scores = [0] * len(doc.text)
    for token in doc:
        pos = token.idx + len(token.text) - 1
        if token.text in ['。', '！', '？']:
            scores[pos] = 100
        elif token.text in ['、', '，']:
            scores[pos] = 80
        elif token.pos_ == 'ADP':
            scores[pos] = 60
        elif token.dep_ in ['case', 'aux']:
            scores[pos] = 40
        elif token.dep_ == 'acl':
            scores[pos] = 35
        elif token.dep_ == 'cc':
            scores[pos] = 10
    return scores

def find_best_break_position(scores, start, end, min_length=30):
    # 後方から最適な区切り位置を探す
    for i in range(end-1, start+min_length-1, -1):
        if scores[i] >= 60:
            return i+1
    for i in range(end-1, start+min_length-1, -1):
        if scores[i] > 0:
            return i+1
    return start

def bunsetsu_based_split(text, max_length=80):
    nlp = spacy.load("ja_ginza")
    doc = nlp(text)
    result = []
    current_block = ""
    for sent in doc.sents:
        bunsetsu_groups = build_bunsetsu_groups(sent)
        for group in bunsetsu_groups:
            if len(current_block + group) <= max_length:
                current_block += group
            else:
                if current_block.strip():
                    result.append(current_block.strip())
                if len(group) > max_length:
                    sub_parts = improved_rule_based_split(group, max_length)
                    result.extend(sub_parts[:-1])
                    current_block = sub_parts[-1]
                else:
                    current_block = group
    if current_block.strip():
        result.append(current_block.strip())
    return result

def build_bunsetsu_groups(sent):
    groups = []
    current_group = ""
    for token in sent:
        current_group += token.text
        if token.pos_ in ['ADP', 'AUX']:
            groups.append(current_group)
            current_group = ""
    if current_group:
        groups.append(current_group)
    return groups

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
        # 最後に残った短い部分も前のブロックに吸収
        if new_blocks:
            new_blocks[-1] += buffer
        else:
            new_blocks.append(buffer)
    # さらに、すべてのブロックがmin_length以上になるように再調整
    merged = []
    for block in new_blocks:
        if merged and len(block) < min_length:
            merged[-1] += block
        else:
            merged.append(block)
    return merged

def split_long_text_fallback(text, max_length=80):
    """従来のルールベースの分割方法（フォールバック用）"""
    if len(text) <= max_length:
        return [text]
    result = []
    current_text = ""
    # 文章の区切りとなる助詞と句読点
    break_chars = [
        'から', 'より', 'だし','れて','や','が','たな','も',
        'ね', 'わ', 'ぞ', 'ぜ','からな',
        '。', '！', '？', '」', '）', '】', ' ', '...', '、',
    ]
    for i, char in enumerate(text):
        current_text += char
        # 文字数が制限を超えた場合の処理
        if len(current_text) >= max_length:
            # 後ろから最も近い区切り文字を探す
            last_break = -1
            found_break_char = None
            for break_char in break_chars:
                pos = current_text.rfind(break_char)
                if pos > last_break:
                    last_break = pos
                    found_break_char = break_char
            # 適切な区切り文字が見つかった場合
            if last_break > max_length // 2 and found_break_char is not None:
                split_point = last_break + len(found_break_char)
                result.append(current_text[:split_point])
                current_text = current_text[split_point:]
            else:
                # 区切り文字が見つからない場合は単純に最大長で切る
                result.append(current_text)
                current_text = ""
    # 残りのテキストを追加
    if current_text:
        result.append(current_text)
    return result

def add_line_breaks(text, length=22, max_total_chars=20000, do_split=True, character_set=None):
    """改行の追加とキャラクター名の挿入、文字数制限付き"""
    try:
        result_lines = []
        # キャラクターセットの定義
        character_sets = {
            'classic': ['ゆっくり霊夢', 'ゆっくり魔理沙', 'ゆっくり妖夢'],
            'voicevox': ['四国めたん', '春日部つむぎ', 'ずんだもん', '青山龍星']
        }
        # デフォルトのキャラクターセットを'classic'に設定
        if character_set is None:
            character_set = 'classic'
        characters = character_sets[character_set]
        char_index = 0
        total_chars = 0
        
        for comment in text.split('\n'):
            if not comment.strip():
                continue
            # 引用符を削除（このスクリプトでは引用符付きのフォーマットを使用）
            comment = comment.strip().strip('"')
            # 新しいコメントの開始時にキャラクターを更新
            current_char = characters[char_index]
            char_index = (char_index + 1) % len(characters)
            
            # 分割オプションに基づいて処理
            if do_split and len(comment) > 80:
                split_comments = split_long_text(comment)
            else:
                split_comments = [comment]
            
            # 各分割部分を別々のブロックとして処理（同じキャラクターを使用）
            for split_comment in split_comments:
                # 各分割部分を行に分ける（length文字ごと）
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
                    # 各分割部分をそれぞれ独立したコメントとして出力（同じキャラクター）
                    comment_text = chr(10).join(comment_lines)
                    comment_length = len(split_comment)
                    
                    # 文字数制限チェック
                    if total_chars + comment_length > max_total_chars and total_chars > 0:
                        return '\n'.join(result_lines)
                    
                    formatted_comment = f'{current_char}\t"{comment_text}"\t{comment_length}'
                    result_lines.append(formatted_comment)
                    total_chars += comment_length
        
        return '\n'.join(result_lines)
    except Exception as e:
        logging.error(f"改行追加処理でエラー発生: {e}")
        raise

def scrape_animanch(url):
    """あにまんchの掲示板ページからコメントを抽出する"""
    try:
        logging.info(f"ページの取得を開始: {url}")
        # ユーザーエージェントを設定してリクエスト
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # エラーチェック
        logging.info(f"ページの取得に成功。ステータスコード: {response.status_code}")
        # HTMLの解析
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ページタイトルを取得
        title_element = soup.find('title')
        page_title = title_element.text.strip() if title_element else "タイトル不明"
        
        # あにまんち固有のスレッドタイトルを取得
        thread_title_element = soup.select_one('#threadTitle')
        if thread_title_element:
            # 最初のテキストノードのみを取得（子要素のテキストを除外）
            thread_title_text = ""
            for node in thread_title_element.contents:
                if isinstance(node, (str, NavigableString)):  # テキストノード
                    text_content = str(node).strip()
                    if text_content:
                        thread_title_text += text_content
                else:  # 最初の要素で停止
                    break
            
            # フォールバック: 上記で取得できない場合は全体から抽出して清浄化
            if not thread_title_text:
                thread_title_text = thread_title_element.get_text().strip()
                # 余計な部分（共有ボタンのテキスト等）を削除
                thread_title_text = re.sub(r'(共有|シェア|お気に入り|ブックマーク).*$', '', thread_title_text).strip()
                thread_title_text = re.sub(r'(favorite|share|bookmark).*$', '', thread_title_text, flags=re.IGNORECASE).strip()
            
            if thread_title_text:
                page_title = thread_title_text
                logging.info(f"スレッドタイトルを取得: {page_title}")
        
        # フォールバック: 一般的なタイトル要素も試す
        if page_title == "タイトル不明" or not page_title:
            content_title = soup.select_one('h1, .thread-title, .page-title')
            if content_title:
                content_title_text = content_title.get_text().strip()
                if content_title_text and content_title_text != page_title:
                    page_title = content_title_text
        
        logging.info(f"ページタイトル: {page_title}")
        
        # コメント情報を保持する辞書
        comments = {}
        # 各コメントブロック（リスト項目）を探索
        comment_items = soup.select('li.list-group-item')
        logging.info(f"コメントアイテム数: {len(comment_items)}")
        for item in comment_items:
            try:
                # コメント番号を取得
                res_id_match = re.search(r'res(\d+)', item.get('id', ''))
                if not res_id_match:
                    continue
                comment_id = res_id_match.group(1)
                # コメントヘッダー情報を取得
                resheader = item.select_one('.resheader')
                if not resheader:
                    continue
                resnumber = resheader.select_one('.resnumber')
                if not resnumber:
                    continue
                # コメント番号を取得（テキストとして）
                comment_number = resnumber.text.strip()
                # 投稿者名を取得
                author = resheader.select_one('.resname')
                author_text = author.text.strip() if author else "不明"
                # 投稿日時を取得
                date = resheader.select_one('.resposted')
                date_text = date.text.strip() if date else "日時不明"
                # コメント本文を取得
                resbody = item.select_one('div[class^="resbody"]')  # resbodyで始まるクラス名
                if not resbody:
                    continue
                # アンカーを取得 (まずアンカーを抽出する)
                anchors = []
                reslinks = resbody.select('a.reslink')
                for reslink in reslinks:
                    anchor_match = re.search(r'>>(\d+)', reslink.text)
                    if anchor_match:
                        anchor_id = anchor_match.group(1)
                        if anchor_id not in anchors:  # 重複を避ける
                            anchors.append(anchor_id)
                # コメント本文のテキストを抽出
                # 画像と引用部分を除いたpタグのみを対象にする
                paragraphs = []
                for p in resbody.find_all('p'):
                    # 親要素がblockquoteでない場合のみ処理
                    if not p.parent or p.parent.name != 'blockquote':
                        # 画像リンクがない場合のみ追加
                        if not p.select('img') and not p.select('a.thumb'):
                            paragraphs.append(p)
                # テキスト内容を抽出
                comment_text = ""
                for p in paragraphs:
                    # アンカー部分を除いたテキストを抽出
                    p_text = p.get_text()
                    # アンカー表記を削除
                    for anchor in anchors:
                        p_text = p_text.replace(f">>{anchor}", "")
                    # アンカーが含まれていたなど、削除後に空になった場合はスキップ
                    p_text = p_text.strip()
                    # 「このレスは削除されています」というテキストを除外
                    if p_text == "このレスは削除されています":
                        continue
                    if p_text:
                        if comment_text:
                            comment_text += " " + p_text
                        else:
                            comment_text = p_text
                # 画像がある場合は画像の存在を本文に追記
                if resbody.select('a.thumb img'):
                    if comment_text:
                        comment_text += " [画像あり]"
                    else:
                        comment_text = "[画像あり]"
                # コメント情報を辞書に追加
                comments[comment_id] = {
                    'id': comment_id,
                    'number': comment_number,
                    'author': author_text,
                    'date': date_text,
                    'text': comment_text,
                    'anchors': anchors
                }
                logging.info(f"コメント抽出完了: ID {comment_id}, コメント番号 {comment_number}, アンカー {anchors}")
            except Exception as e:
                logging.error(f"コメントブロックの処理中にエラー発生: {e}")
        logging.info(f"合計 {len(comments)} 件のコメントを抽出しました")
        
        # タイトルとコメントをまとめて返す
        return {
            'title': page_title,
            'comments': comments,
            'url': url
        }
    except Exception as e:
        logging.error(f"スクレイピング中にエラー発生: {e}", exc_info=True)
        raise

def reorganize_comments(comments):
    """アンカー参照に基づいてコメントを再構成する"""
    try:
        # 結果を格納するリスト
        organized_comments = []
        # 処理済みコメントを追跡するセット
        processed_ids = set()
        # コメント番号のソート
        comment_ids = sorted([int(cid) for cid in comments.keys()])
        # 各コメントを順番に処理
        for current_id in comment_ids:
            current_id_str = str(current_id)
            # すでに処理済みの場合はスキップ
            if current_id_str in processed_ids:
                continue
            # 現在のコメントを追加
            organized_comments.append(comments[current_id_str])
            processed_ids.add(current_id_str)
            # このコメントが参照するアンカーを処理 (深さ優先探索)
            # 参照されたコメントとその参照コメントを再帰的に追加
            process_anchors_dfs(current_id_str, comments, organized_comments, processed_ids)
        return organized_comments
    except Exception as e:
        logging.error(f"コメント再構成中にエラー発生: {e}", exc_info=True)
        raise

def process_anchors_dfs(comment_id, comments, organized_comments, processed_ids):
    """アンカー参照を深さ優先で処理する"""
    if comment_id not in comments:
        return
    # このコメントのアンカーを取得
    anchors = comments[comment_id]['anchors']
    # 各アンカーを処理
    for anchor_id in anchors:
        # アンカー先がすでに処理済みか、存在しない場合はスキップ
        if anchor_id in processed_ids or anchor_id not in comments:
            continue
        # アンカー先のコメントを追加
        organized_comments.append(comments[anchor_id])
        processed_ids.add(anchor_id)
        # そのアンカー先のアンカーも再帰的に処理
        process_anchors_dfs(anchor_id, comments, organized_comments, processed_ids)

def format_comments(comments):
    """コメントを整形して出力する（詳細版）"""
    try:
        formatted_text = []
        for comment in comments:
            comment_line = f"[{comment['number']}] {comment['author']} {comment['date']}"
            formatted_text.append(comment_line)
            # アンカー情報があれば追加
            if comment['anchors']:
                anchors_text = f"参照: >>{', >>'.join(comment['anchors'])}"
                formatted_text.append(anchors_text)
            # 本文を追加（22文字ごとに改行）
            if comment['text']:
                text_lines = []
                current_line = ""
                for char in comment['text']:
                    current_line += char
                    if len(current_line) >= 22:
                        text_lines.append(current_line)
                        current_line = ""
                if current_line:
                    text_lines.append(current_line)
                formatted_text.append("\n".join(text_lines))
            else:
                formatted_text.append("[本文なし]")
            formatted_text.append("-" * 40)
        return "\n".join(formatted_text)
    except Exception as e:
        logging.error(f"コメント整形中にエラー発生: {e}", exc_info=True)
        raise

def format_comments_simple(comments):
    """コメントを簡易形式で出力する（本文のみを引用符で囲む）"""
    try:
        formatted_text = []
        for comment in comments:
            # 本文がある場合のみ処理
            if comment['text']:
                # [画像あり]の表記を削除
                text = comment['text'].replace('[画像あり]', '').strip()
                if text:
                    # 引用符で囲んで出力
                    formatted_text.append(f'"{text}"')
        return "\n".join(formatted_text)
    except Exception as e:
        logging.error(f"コメント整形（簡易版）中にエラー発生: {e}", exc_info=True)
        raise

def format_with_speaker(comments, character_set=None, length=22, max_total_chars=20000, do_split=True):
    """コメントを話者付きで整形する"""
    try:
        # まず簡易形式で出力
        simple_text = format_comments_simple(comments)
        # 次に話者と改行を追加
        formatted_text = add_line_breaks(
            simple_text,
            length=length,
            max_total_chars=max_total_chars,
            do_split=do_split,
            character_set=character_set
        )
        return formatted_text
    except Exception as e:
        logging.error(f"話者付き整形中にエラー発生: {e}", exc_info=True)
        raise

def format_existing_text(text):
    """既存のフォーマット済みテキストから本文のみを抽出する"""
    try:
        result = []
        current_text = []
        in_text_block = False
        for line in text.split('\n'):
            # ヘッダー行か区切り線の場合はスキップ
            if line.startswith('[') and ']' in line and '二次元好きの匿名さん' in line:
                if in_text_block and current_text:
                    # 前のテキストブロックを処理
                    full_text = ' '.join(current_text)
                    full_text = full_text.replace('[画像あり]', '').strip()
                    if full_text:
                        result.append(f'"{full_text}"')
                    current_text = []
                in_text_block = True
            elif line.startswith('参照:'):
                # 参照行はスキップ
                continue
            elif line.startswith('-' * 10):
                # 区切り線の場合
                if in_text_block and current_text:
                    full_text = ' '.join(current_text)
                    full_text = full_text.replace('[画像あり]', '').strip()
                    if full_text:
                        result.append(f'"{full_text}"')
                    current_text = []
                in_text_block = False
            elif in_text_block and line.strip() and line != '[本文なし]':
                # 本文行の場合は追加
                current_text.append(line.strip())
        # 最後のテキストブロックがあれば処理
        if in_text_block and current_text:
            full_text = ' '.join(current_text)
            full_text = full_text.replace('[画像あり]', '').strip()
            if full_text:
                result.append(f'"{full_text}"')
        return '\n'.join(result)
    except Exception as e:
        logging.error(f"既存テキスト整形中にエラー発生: {e}", exc_info=True)
        raise

def save_to_file(text, prefix="animanch"):
    """テキストをファイルに保存する"""
    try:
        output_dir = 'processed_texts'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # テキストの最初のコメント行を取得（あれば）
        first_comment = ""
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line and (line.startswith('"') or '\t"' in line):
                # 引用符を除去してファイル名に使用できる部分だけを抽出
                comment_text = line.split('"')[1] if '"' in line else line
                # 先頭の20文字だけを使用
                first_comment = comment_text[:20]
                # ファイル名に使えない文字を除去
                first_comment = re.sub(r'[\\/*?:"<>|]', '', first_comment)
                break
        
        # ファイル名の作成（最初のコメント + 現在時刻）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if first_comment:
            output_path = os.path.join(output_dir, f'{first_comment}_{timestamp}.txt')
        else:
            output_path = os.path.join(output_dir, f'{prefix}_{timestamp}.txt')
        
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(text)
        logging.info(f"結果をファイルに保存しました: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"ファイル保存中にエラー発生: {e}", exc_info=True)
        raise

def main():
    try:
        # クリップボードのテキストを取得
        clipboard_text = pyperclip.paste()
        print("クリップボードのテキストを取得しました。")
        # あにまんchのURLを検出
        urls = detect_animanch_urls(clipboard_text)
        print(f"検出されたURL: {urls}")
        # 既存の整形済みテキストの検出
        has_formatted_text = '[二次元好きの匿名さん' in clipboard_text
        print(f"整形済みテキストの検出: {has_formatted_text}")
        # 処理モードを判断
        if has_formatted_text:
            # 既存の整形済みテキストの処理
            # 簡易版の整形
            simple_text = format_existing_text(clipboard_text)
            # ゆっくり話者を追加
            formatted_text = add_line_breaks(simple_text, character_set='classic')
            prefix = "yukkuri"
            # 結果をクリップボードにコピー
            pyperclip.copy(formatted_text)
            print("ゆっくりボイス形式でクリップボードにコピーしました。")
            # ファイルに保存
            output_path = save_to_file(formatted_text, prefix=prefix)
            print(f"ゆっくりボイス形式でファイルに保存しました: {output_path}")
            # 処理したファイルを開く
            open_file(output_path)
        elif urls:
            # URLからのスクレイピング
            selected_url = ""
            if len(urls) == 1:
                selected_url = urls[0]
            else:
                print("スクレイピングするURLを選択してください:")
                for i, url in enumerate(urls):
                    print(f"{i}: {url}")
                url_choice = input(f"選択 (0-{len(urls)-1}, デフォルト=0): ").strip()
                if not url_choice or not url_choice.isdigit() or int(url_choice) >= len(urls):
                    url_choice = "0"
                selected_url = urls[int(url_choice)]
            # URLからコメントを抽出
            scraped_data = scrape_animanch(selected_url)
            if not scraped_data or not scraped_data['comments']:
                print("コメントが抽出できませんでした。処理を中止します。")
                return
            # アンカー参照に基づいてコメントを再構成
            organized_comments = reorganize_comments(scraped_data['comments'])
            # ゆっくり話者付きで出力
            formatted_text = format_with_speaker(organized_comments, character_set='classic')
            prefix = "yukkuri"
            # ファイルに保存
            output_path = save_to_file(formatted_text, prefix=prefix)
            print(f"ゆっくりボイス形式でファイルに保存しました: {output_path}")
            # 結果をクリップボードにコピー
            pyperclip.copy(formatted_text)
            print("ゆっくりボイス形式でクリップボードにコピーしました。")
            # 処理したファイルを開く
            open_file(output_path)
        else:
            # URLも整形済みテキストもない場合はデフォルトURLを使用
            print("クリップボードからURLも整形済みテキストも検出できませんでした。")
            print("スクレイピングするURLを入力するか、以下のデフォルトを使用します。")
            default_url = "https://bbs.animanch.com/board/4635009/"
            user_url = input(f"URL (デフォルト: {default_url}): ").strip()
            if not user_url:
                user_url = default_url
            # URLからコメントを抽出
            scraped_data = scrape_animanch(user_url)
            if not scraped_data or not scraped_data['comments']:
                print("コメントが抽出できませんでした。処理を中止します。")
                return
            # アンカー参照に基づいてコメントを再構成
            organized_comments = reorganize_comments(scraped_data['comments'])
            # ゆっくり話者付きで出力
            formatted_text = format_with_speaker(organized_comments, character_set='classic')
            prefix = "yukkuri"
            # ファイルに保存
            output_path = save_to_file(formatted_text, prefix=prefix)
            print(f"ゆっくりボイス形式でファイルに保存しました: {output_path}")
            # 結果をクリップボードにコピー
            pyperclip.copy(formatted_text)
            print("ゆっくりボイス形式でクリップボードにコピーしました。")
            # 処理したファイルを開く
            open_file(output_path)
    except Exception as e:
        print(f"処理中にエラーが発生: {e}")

def open_file(file_path):
    """ファイルを開く"""
    try:
        if os.name == 'nt':
            os.startfile(file_path)
        else:
            import subprocess
            subprocess.run(['xdg-open' if os.name == 'posix' else 'open', file_path])
    except Exception as e:
        logging.error(f"ファイルを開く際にエラーが発生: {e}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"プログラムの実行中にエラーが発生: {e}")