import os
import re
from hazm import Normalizer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

INVISIBLE_CHARS_PATTERN = re.compile(r'[\u200E\u200F\u202A-\u202E\u200B\uFEFF]')
KESHIDE_PATTERN = re.compile(r'ـ+')
PUNCTUATION_SPACE_PATTERN = re.compile(r'\s+([،؛:\.\!\؟])')
MULTIPLE_NEWLINES_PATTERN = re.compile(r'\n{3,}')


HAZM_NORMALIZER = Normalizer(
    correct_spacing=True,
    remove_diacritics=True,
    remove_specials_chars=False,
    decrease_repeated_chars=True,
    persian_style=True,
    persian_numbers=True,
    unicodes_replacement=True,
    seperate_mi=True
)


def enterprise_persian_normalizer(text):

    if not text:
        return text
        
    text = INVISIBLE_CHARS_PATTERN.sub('', text)
    text = KESHIDE_PATTERN.sub('', text)
    text = PUNCTUATION_SPACE_PATTERN.sub(r'\1', text)
    text = MULTIPLE_NEWLINES_PATTERN.sub('\n\n', text)
    text = HAZM_NORMALIZER.normalize(text)
    
    return text.strip()


if __name__ == "__main__":
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    input_file_path = os.path.join(DATA_DIR, 'Rules_text.txt')
    output_file_path = os.path.join(DATA_DIR, 'Rules_normalized.txt')

    try:
        with open(input_file_path, 'r', encoding='utf-8') as f:
            raw_text = f.read()
            
        cleaned_text = enterprise_persian_normalizer(raw_text)
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(cleaned_text)
            
        print("✅ قدم اول (نرمال‌سازی معماری‌شده و بهینه) با موفقیت انجام شد.")
        
    except FileNotFoundError:
        print(f"❌ خطا: فایل {input_file_path} پیدا نشد. لطفاً فایل را در مسیر مشخص شده قرار دهید.")
    except Exception as e:
        print(f"❌ خطای غیرمنتظره در اجرای قدم اول: {e}")
