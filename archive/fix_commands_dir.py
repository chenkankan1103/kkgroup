#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速修復腳本：更新三個 bot 的 COMMANDS_DIR 配置以匹配新的 cogs 結構
使用方法: python fix_commands_dir.py
或在 GCP VM 上执行: cd /home/e193752468/kkgroup && python fix_commands_dir.py
"""

import os
import re

def fix_commands_dir_in_file(filepath, old_pattern, new_value):
    """
    修復文件中的 COMMANDS_DIR 配置
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 使用正則表達式查找並替換 COMMANDS_DIR
        modified_content = re.sub(
            r'COMMANDS_DIR\s*=\s*["\'].*?["\']',
            f'COMMANDS_DIR = "{new_value}"',
            content
        )
        
        if content == modified_content:
            print(f"⚠️  {filepath} - 沒有進行修改（可能已是正確值）")
            return False
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        
        print(f"✅ {filepath} - 已修改為: COMMANDS_DIR = \"{new_value}\"")
        return True
    except Exception as e:
        print(f"❌ {filepath} - 修改失敗: {e}")
        return False

def main():
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    fixes = [
        (os.path.join(base_path, 'bots', 'bot.py'), 'cogs/common'),
        (os.path.join(base_path, 'bots', 'shopbot.py'), 'cogs/shop'),
        (os.path.join(base_path, 'bots', 'uibot.py'), 'cogs/ui'),
    ]
    
    print("=" * 60)
    print("🔧 開始修復 COMMANDS_DIR 配置")
    print("=" * 60)
    
    fixed_count = 0
    for filepath, new_value in fixes:
        if os.path.exists(filepath):
            if fix_commands_dir_in_file(filepath, None, new_value):
                fixed_count += 1
        else:
            print(f"❌ {filepath} - 文件不存在")
    
    print("=" * 60)
    print(f"✅ 修復完成！共修改 {fixed_count}/3 個文件")
    print("=" * 60)

if __name__ == '__main__':
    main()
