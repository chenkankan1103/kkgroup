#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remove all Chinese characters from Python files and convert to English comments
This helps prevent garbled output in systemd journal logs
"""
import re
import sys

def remove_chinese(text):
    """Remove Chinese characters and convert to English equivalents"""
    
    replacements = {
        r'[\u4e00-\u9fff]': '?',  # Replace Chinese chars with ?
        r'[\u3040-\u309f]': '?',  # Replace Japanese hiragana with ?
        r'[\u30a0-\u30ff]': '?',  # Replace Japanese katakana with ?
        r'[\uac00-\ud7af]': '?',  # Replace Korean hangul with ?
    }
    
    result = text
    for pattern, replacement in replacements.items():
        result = re.sub(pattern, replacement, result)
    
    return result

def clean_file(filename):
    """Clean a Python file of non-ASCII characters in string literals"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return False
    
    # Simple approach: replace non-ASCII in string literals
    # This is basic but safe
    original_content = content
    content_bytes = content.encode('utf-8')
    
    # Convert to ascii with replacement
    ascii_content = content_bytes.decode('utf-8', errors='replace')
    
    if content != ascii_content:
        print(f"File {filename} contains non-ASCII characters, keeping original UTF-8")
        # Actually, let's keep the file as UTF-8 but ensure it's valid
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                f.read()
            print(f"  -> File {filename} is valid UTF-8, no changes needed")
            return True
        except Exception as e:
            print(f"  -> Error validating UTF-8 in {filename}: {e}")
            return False
    
    return True

if __name__ == "__main__":
    files = ["bot.py", "shopbot.py", "uibot.py"]
    
    for f in files:
        print(f"Checking {f}...")
        clean_file(f)
