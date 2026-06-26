import json
import re
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

ARTICLE_PATTERN = re.compile(r'^ماده\s+([۰-۹]+)\.(.*)')
TABSAREH_PATTERN = re.compile(r'^تبصره\s+([۰-۹]+)\.(.*)')

def structural_chunker(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    lines = text.split('\n')
    
    chunks = []
    current_section = ""
    current_article_num = ""
    current_article_text = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('الف -') or line.startswith('ب -') or line.startswith('ج -'):
            continue

        if line.startswith('بخش') or line.startswith('پیوست'):
            current_section = line
            current_article_num = ""
            current_article_text = ""
            continue

        article_match = ARTICLE_PATTERN.match(line)
        if article_match:
            current_article_num = article_match.group(1)
            current_article_text = line
            
            chunk_text = f"[{current_section}] {line}"
            chunks.append({
                "chunk_id": f"article_{current_article_num}",
                "type": "ماده",
                "section": current_section,
                "article_number": current_article_num,
                "text": chunk_text
            })
            continue

        tabsareh_match = TABSAREH_PATTERN.match(line)
        if tabsareh_match and current_article_num:
            tab_num = tabsareh_match.group(1)
            
            chunk_text = f"[{current_section}] در ارتباط با ماده {current_article_num} ({current_article_text}) -> {line}"
            chunks.append({
                "chunk_id": f"article_{current_article_num}_tabsareh_{tab_num}",
                "type": "تبصره",
                "section": current_section,
                "article_number": current_article_num,
                "tabsareh_number": tab_num,
                "text": chunk_text
            })
            continue

        if 'پیوست' in current_section and ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                term = parts[0].strip()
                definition = parts[1].strip()
                chunk_text = f"[تعاریف آیین‌نامه آموزش] واژه «{term}» به این معناست: {definition}"
                chunks.append({
                    "chunk_id": f"definition_{term.replace(' ', '_')}",
                    "type": "تعریف",
                    "section": current_section,
                    "term": term,
                    "text": chunk_text
                })
                continue
                
        if chunks:
            chunks[-1]["text"] += f" {line}"

    return chunks


input_normalized_file = os.path.join(DATA_DIR, 'Rules_normalized.txt')
output_json_file = os.path.join(DATA_DIR, 'Rules_chunks.json')

try:
    documents = structural_chunker(input_normalized_file)
    
    with open(output_json_file, 'w', encoding='utf-8') as f:
        json.dump(documents, f, ensure_ascii=False, indent=4)
        
    print(f"✅ قدم دوم با موفقیت انجام شد. تعداد کل قطعات (Chunks) تولید شده: {len(documents)}")
except Exception as e:
    print(f"❌ خطا در اجرای قدم دوم: {e}")