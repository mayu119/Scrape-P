import re
import os
import logging
from datetime import datetime
import pyperclip

def setup_logging():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    log_file = os.path.join(log_dir, f'text_processing_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return log_file

def clean_text(text):
    """基本的なテキストクリーニング"""
    try:
        # アンカーの削除
        text = re.sub(r'>>\d+\s*', '', text)
        
        # コメントNoの削除（000１などの形式）
        text = re.sub(r'^\d{4}(?:\s+|$)', '', text, flags=re.MULTILINE)
        
        # アンカー付き数字の削除（1とか2など）
        text = re.sub(r'^\d+(?:\s+|$)', '', text, flags=re.MULTILINE)
        
        # 名無しのあにまんchパターンの削除
        text = re.sub(r'\d+: 名無しのあにまんch \d{4}/\d{2}/\d{2}\(.\) \d{2}:\d{2}:\d{2}', '', text)
        
        # 行ごとに処理
        lines = text.split('\n')
        filtered_lines = []
        
        for line in lines:
            # 空行をスキップ
            if not line.strip():
                continue
                
            # 不要な情報を含む行をスキップ
            if any(skip_text in line for skip_text in [
                'RSS', 'All Rights Reserved', '問い合わせ',
                'ジャンプ', 'ワンピース', 'ナルト',
                '深夜アニメ界隈', 'まとめサイトです',
                'http://', 'https://', '.com'
            ]):
                continue
            
            filtered_lines.append(line)
        
        text = '\n'.join(filtered_lines)
        return text
    except Exception as e:
        logging.error(f"テキストクリーニングでエラー発生: {e}")
        raise

def split_long_text(text, max_length=70):
    """長いテキストを分割
    助詞や句読点などの自然な区切りで分割を試みる"""
    if len(text) <= max_length:
        return [text]
    
    result = []
    current_text = ""
    
    # 文章の区切りとなる助詞と句読点
    break_chars = [
        'から', 'より', 'だし','れて','や',
        'ね', 'わ', 'ぞ', 'ぜ','からな',
        '。', '！', '？', '」', '）', '】', ' ', '...', '、', 
    ]
    
    for i, char in enumerate(text):
        current_text += char
        
        # 文字数が制限を超えた場合の処理
        if len(current_text) >= max_length:
            # 後ろから最も近い区切り文字を探す
            last_break = -1
            for break_char in break_chars:
                pos = current_text.rfind(break_char)
                if pos > last_break:
                    last_break = pos
            
            # 適切な区切り位置が見つかった場合
            if last_break > max_length * 0.5:  # 最低でも半分以上は含める
                result.append(current_text[:last_break + 1])
                current_text = current_text[last_break + 1:]
            else:
                # 適切な区切りが見つからない場合は、現在の位置で分割
                result.append(current_text)
                current_text = ""
    
    # 残りのテキストを追加
    if current_text:
        result.append(current_text)
    
    return result

def add_line_breaks(text, length=22, max_total_chars=4800, do_split=True, character_set=None):
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
        current_comment_chars = 0
        
        for comment in text.split('\n'):
            if not comment.strip():
                continue
            
            # 新しいコメントの開始時にキャラクターを更新
            current_char = characters[char_index]
            char_index = (char_index + 1) % len(characters)
            
            # 分割オプションに基づいて処理
            if do_split:
                split_comments = split_long_text(comment.strip())
            else:
                split_comments = [comment.strip()]
            
            for split_comment in split_comments:
                comment_lines = []
                current_line = ''
                current_comment_chars = 0
                
                for char in split_comment:
                    current_line += char
                    current_comment_chars += 1
                    if len(current_line) >= length:
                        comment_lines.append(current_line)
                        current_line = ''
                
                if current_line:
                    comment_lines.append(current_line)
                
                if comment_lines:
                    # このコメントを追加した場合の合計文字数を計算
                    comment_text = chr(10).join(comment_lines)
                    comment_length = len(comment_text)
                    
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

def process_text(split_text=True, character_set=None):
    log_file = setup_logging()
    logging.info("処理を開始")
    
    try:
        # クリップボードからテキストを読み込む
        content = pyperclip.paste()
            
        if not content.strip():
            logging.error("クリップボードが空です")
            return
            
        # テキストのクリーニング
        content = clean_text(content)
        
        # 出力ファイル名を現在時刻で生成
        output_path = os.path.join(
            'output', 
            f'formatted_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        )
        
        # output ディレクトリがない場合は作成
        os.makedirs('output', exist_ok=True)
        
        # 改行を追加（分割オプション付き）
        formatted_content = add_line_breaks(content, length=22, max_total_chars=4800, do_split=split_text, character_set=character_set)
        
        # 結果を保存
        with open(output_path, 'w', encoding='utf-8') as file:
            file.write(formatted_content)
        
        logging.info(f"処理が完了しました。出力ファイル: {output_path}")
        
        # 処理したファイルとフォルダを開く
        try:
            if os.name == 'nt':
                os.startfile(output_path)
                os.startfile(os.path.dirname(output_path))
            else:
                import subprocess
                subprocess.run(['open', output_path])
                subprocess.run(['open', os.path.dirname(output_path)])
                
        except Exception as e:
            logging.error(f"ファイルまたはフォルダを開く際にエラーが発生: {e}")
        
    except Exception as e:
        logging.error(f"処理中にエラーが発生: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        # キャラクターセットの選択
        print("\nキャラクターセットを選択してください：")
        print("1: クラシック（ゆっくり霊夢、ゆっくり魔理沙、ゆっくり妖夢）")
        print("2: VOICEVOX（四国めたん、春日部つむぎ、ずんだもん、青山龍星）")
        
        while True:
            char_choice = input("キャラクターセットを選択 (1/2): ").strip()
            if char_choice in ['1', '2']:
                break
            print("1 または 2 を入力してください。")
        
        character_set = 'classic' if char_choice == '1' else 'voicevox'
        
        # クラシックモードの場合のみテキスト分割の選択を表示
        split_text = True  # VOICEVOXモードのデフォルト
        if char_choice == '1':
            while True:
                split_choice = input("\nテキストを分割しますか？ (y/n): ").lower()
                if split_choice in ['y', 'n']:
                    split_text = (split_choice == 'y')
                    break
                print("'y' または 'n' を入力してください。")
        
        # 選択に基づいて実行
        process_text(split_text=split_text, character_set=character_set)
    except Exception as e:
        logging.error(f"プログラムの実行中にエラーが発生: {e}") 