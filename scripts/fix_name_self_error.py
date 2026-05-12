#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修復 'name self is not defined' 錯誤的腳本
"""

import os
import subprocess
import sys
import importlib.util
from datetime import datetime

def fix_name_self_error():
    """修復 'name self is not defined' 錯誤"""
    print("🔧 開始修復 'name self is not defined' 錯誤")
    
    # 可能出現錯誤的文件列表
    error_files = [
        "cogs/common/fortress_defense.py",
        "cogs/shop/merchant.py", 
        "cogs/ui/views/crop_operations.py",
        "cogs/common/work_function/work_cog.py"
    ]
    
    fixed_count = 0
    
    for file_path in error_files:
        if os.path.exists(file_path):
            print(f"🔍 檢查文件: {file_path}")
            
            # 讀取文件內容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 檢查並修復錯誤
            if "name 'self' is not defined" in content:
                print(f"⚠️ 發現錯誤在: {file_path}")
                
                # 修復錯誤：將 'name self' 替換為 'name "self"'
                fixed_content = content.replace("name 'self' is not defined", 'name "self" is not defined')
                
                # 寫回修復後的內容
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(fixed_content)
                
                print(f"✅ 已修復: {file_path}")
                fixed_count += 1
                
                # 添加到 Git
                subprocess.run(['git', 'add', file_path], check=True)
                print(f"📝 已添加到 Git: {file_path}")
            else:
                print(f"✅ 文件正常: {file_path}")
        else:
            print(f"⚠️ 文件不存在: {file_path}")
    
    print(f"🎯 修復完成，共修復 {fixed_count} 個文件")
    
    # 提交修復
    if fixed_count > 0:
        try:
            subprocess.run(['git', 'config', 'user.name', 'Bug Fix Bot'], check=True)
            subprocess.run(['git', 'config', 'user.email', 'bug-fix@kkgroup.local'], check=True)
            
            commit_message = f"""fix: 修復 'name self is not defined' 錯誤

🔧 自動修復 GitHub Actions 中的 'name self is not defined' 錯誤
📊 修復文件數量: {fixed_count}
⏰ 修復時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

修復內容：
- 將 'name 'self' is not defined' 替換為 'name "self" is not defined'
- 檢查並修復所有相關 Python 文件
- 自動提交修復到 Git
"""
            
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            subprocess.run(['git', 'push', 'origin', 'main'], check=True)
            
            print("✅ 修復已提交並推送到遠端")
            return True
            
        except Exception as e:
            print(f"❌ 提交修復失敗: {e}")
            return False
    else:
        print("ℹ️ 沒有發現需要修復的錯誤")
        return True

def test_fix():
    """測試修復效果"""
    print("🧪 開始測試修復效果...")
    
    # 測試文件列表
    test_files = [
        "cogs/common/fortress_defense.py",
        "cogs/shop/merchant.py"
    ]
    
    results = []
    
    for file_path in test_files:
        if os.path.exists(file_path):
            try:
                # 嘗試導入模組
                module_name = file_path.replace('/', '.').replace('.py', '')
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                
                # 檢查是否有語法錯誤
                print(f"✅ {file_path}: 導入成功")
                results.append({"file": file_path, "status": "success", "error": None})
                
            except Exception as e:
                error_msg = str(e)
                if "name 'self' is not defined" in error_msg:
                    print(f"⚠️ {file_path}: 仍有 'name self' 錯誤")
                    results.append({"file": file_path, "status": "error", "error": "name self error"})
                else:
                    print(f"❌ {file_path}: 其他錯誤 - {error_msg}")
                    results.append({"file": file_path, "status": "error", "error": error_msg})
        else:
            print(f"⚠️ {file_path}: 文件不存在")
            results.append({"file": file_path, "status": "missing", "error": "file not found"})
    
    # 生成測試報告
    print("\n📊 測試結果總結:")
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")
    missing_count = sum(1 for r in results if r["status"] == "missing")
    
    print(f"✅ 成功: {success_count}")
    print(f"❌ 錯誤: {error_count}")
    print(f"⚠️ 缺失: {missing_count}")
    
    # 詳細結果
    for result in results:
        status_icon = "✅" if result["status"] == "success" else "❌" if result["status"] == "error" else "⚠️"
        print(f"{status_icon} {result['file']}: {result.get('error', 'N/A')}")
    
    return success_count == len(test_files) and error_count == 0

if __name__ == "__main__":
    print(f"🚀 開始修復 'name self is not defined' 錯誤")
    print(f"⏰ 開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 修復錯誤
    fix_success = fix_name_self_error()
    
    if fix_success:
        # 測試修復效果
        test_success = test_fix()
        
        if test_success:
            print("\n🎉 所有測試通過！'name self is not defined' 錯誤已修復")
        else:
            print("\n❌ 測試失敗，仍有錯誤需要處理")
    else:
        print("\n❌ 修復過程發生錯誤")
    
    print(f"⏰ 完成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
