#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discord 指令自動清理腳本
==========================================
自動定位並標記要刪除的指令

使用方式：
    python3 scripts/cleanup_discord_commands.py [--list-only] [--target "指令名"]

選項：
    --list-only     只列出要刪除的指令，不進行修改
    --target        只清理特定指令（例如 "kkcoin"）
"""

import os
import re
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Tuple

# 要刪除的指令映射（指令名 -> 所在文件）
COMMANDS_TO_DELETE = {
    # COMMON 模組
    "kkcoin": "cogs/common/kcoin.py",
    "kkcoin_rank": "cogs/common/kcoin.py",
    "reserve_status": "cogs/common/kcoin.py",
    "sync_status": "cogs/common/google_sheets_sync.py",
    "trends_jackpot": "cogs/common/trends_lottery.py",
    "sync_from_sheet": "cogs/common/google_sheets_sync.py",
    "export_to_sheet": "cogs/common/google_sheets_sync.py",
    "list_members": "cogs/common/google_sheets_sync.py",
    "ai_personality_set": "cogs/common/memory_manager.py",
    "ai_personality_list": "cogs/common/memory_manager.py",
    "ai_knowledge_add": "cogs/common/memory_manager.py",
    "ai_knowledge_search": "cogs/common/memory_manager.py",
    "ai_memory_cleanup": "cogs/common/memory_manager.py",
    "ai_memory_status": "cogs/common/memory_manager.py",
    "shellagent": "cogs/common/shell_agent.py",
    "update_and_restart": "cogs/common/admin_restartbot.py",
    "check_updates": "cogs/common/admin_restartbot.py",
    "restart_all": "cogs/common/admin_restartbot.py",
    "restart": "cogs/common/admin_restartbot.py",
    "status": "cogs/common/admin_restartbot.py",
    "trends_history": "cogs/common/trends_lottery.py",
    
    # SHOP 模組
    "paperdoll": "cogs/shop/shop.py",
    "feedback": "cogs/shop/feedback_cog.py",
    "grant_temporary_role": "cogs/shop/enhanced_role_manager.py",
    "check_my_roles": "cogs/shop/enhanced_role_manager.py",  # 兩個位置
    
    # UI 模組
    "anime_status": "cogs/ui/anime_tracker.py",
    "ad_violations": "cogs/ui/anti_advertising.py",
    "ad_settings": "cogs/ui/anti_advertising.py",
    "anime_start": "cogs/ui/anime_tracker.py",
    "unmute": "cogs/ui/anti_advertising.py",
    "clear_violations": "cogs/ui/anti_advertising.py",
    "cross_channel_status": "cogs/ui/anti_advertising.py",
    "emergency_cleanup": "cogs/ui/anti_advertising.py",
    "event_stats": "cogs/ui/ScamParkEvents.py",
    "event_reset": "cogs/ui/ScamParkEvents.py",
    "event_force": "cogs/ui/ScamParkEvents.py",
    "check_user_ids": "cogs/ui/id_diagnosis.py",
    "list_id_issues": "cogs/ui/id_diagnosis.py",
    "test_locker_equipment": "cogs/ui/cogs/locker_event_test.py",
    "test_locker_currency": "cogs/ui/cogs/locker_event_test.py",
    "test_locker_health": "cogs/ui/cogs/locker_event_test.py",
    "test_locker_full_refresh": "cogs/ui/cogs/locker_event_test.py",
    "set_character": "cogs/ui/commands/character_setup.py",
    "view_character": "cogs/ui/commands/character_setup.py",
    "random_character": "cogs/ui/commands/character_setup.py",
}


def find_command_in_file(filepath: str, command_name: str) -> Tuple[int, int, str]:
    """
    在文件中找到指令定義的位置
    
    返回: (開始行, 結束行, 代碼內容)
    """
    if not os.path.exists(filepath):
        return None, None, None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 搜尋 @app_commands.command(name="command_name"
    pattern = rf'@app_commands\.command\(name=["\']?{re.escape(command_name)}["\']?'
    
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            # 找到 decorator，現在找函數定義和結束
            start_line = i
            
            # 找到函數定義行
            func_start = None
            for j in range(i, min(i + 10, len(lines))):
                if lines[j].strip().startswith('async def ') or lines[j].strip().startswith('def '):
                    func_start = j
                    break
            
            if func_start is None:
                continue
            
            # 找到函數結束（下一個不是縮進的行，或下一個 decorator）
            func_end = None
            base_indent = len(lines[func_start]) - len(lines[func_start].lstrip())
            
            for j in range(func_start + 1, len(lines)):
                line = lines[j]
                
                # 如果是空行，繼續
                if not line.strip():
                    continue
                
                # 計算縮進
                indent = len(line) - len(line.lstrip())
                
                # 如果縮進 <= 基礎縮進，表示函數結束
                if line.strip() and indent <= base_indent:
                    func_end = j
                    break
            
            if func_end is None:
                func_end = len(lines)
            
            # 提取代碼
            code_content = ''.join(lines[start_line:func_end])
            return start_line + 1, func_end, code_content  # +1 因為行號從 1 開始
    
    return None, None, None


def list_commands(root_dir: str = "."):
    """列出所有要刪除的指令及其位置"""
    print("📋 要刪除的指令清單\n")
    
    files_involved = {}
    
    for cmd_name, file_path in COMMANDS_TO_DELETE.items():
        full_path = os.path.join(root_dir, file_path)
        
        start_line, end_line, content = find_command_in_file(full_path, cmd_name)
        
        if start_line is None:
            status = "❌ 找不到"
        else:
            status = f"✅ 行 {start_line}-{end_line}"
        
        print(f"  {cmd_name:25} | {file_path:40} | {status}")
        
        # 統計涉及的文件
        if file_path not in files_involved:
            files_involved[file_path] = 0
        files_involved[file_path] += 1
    
    print(f"\n涉及的文件數: {len(files_involved)}")
    print("按文件分類:")
    for file_path, count in sorted(files_involved.items(), key=lambda x: x[1], reverse=True):
        print(f"  {file_path:40} ({count} 個指令)")
    
    print(f"\n總計: {len(COMMANDS_TO_DELETE)} 個指令")


def cleanup_command(filepath: str, command_name: str, dry_run: bool = True) -> bool:
    """清理指定的指令"""
    
    full_path = os.path.join(".", filepath)
    
    if not os.path.exists(full_path):
        print(f"❌ 文件不存在: {filepath}")
        return False
    
    start_line, end_line, content = find_command_in_file(full_path, command_name)
    
    if start_line is None:
        print(f"❌ 找不到指令: {command_name}")
        return False
    
    print(f"🗑️  {command_name} ({filepath}:{start_line}-{end_line})")
    
    if dry_run:
        return True
    
    # 讀取文件
    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 刪除指令（行號是 1-based）
    del lines[start_line - 1:end_line]
    
    # 寫回文件
    with open(full_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ 已刪除: {command_name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Discord 指令自動清理"
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="只列出指令，不進行修改"
    )
    parser.add_argument(
        "--target",
        type=str,
        help="只清理特定指令"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="實際執行刪除（默認為 dry-run）"
    )
    
    args = parser.parse_args()
    
    if args.list_only or args.target is None:
        list_commands()
    
    if args.target:
        if args.target not in COMMANDS_TO_DELETE:
            print(f"❌ 未知指令: {args.target}")
            return
        
        filepath = COMMANDS_TO_DELETE[args.target]
        cleanup_command(filepath, args.target, dry_run=not args.execute)


if __name__ == "__main__":
    main()
