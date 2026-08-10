#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修復 'name self is not defined' 錯誤的腳本
"""

import os
import subprocess
import re
from datetime import datetime


FORTRESS_FILE = "cogs/ui/fortress_defense.py"


def _validate_fortress_fix(content: str):
    signature_ok = (
        "def build_battle_embed(state: fs.FortressState, bot: discord.Client) -> discord.Embed:"
        in content
    )

    helper_match = re.search(
        r"def build_battle_embed\(.*?\n(?=def build_status_embed)",
        content,
        re.DOTALL,
    )
    helper_body = helper_match.group(0) if helper_match else ""
    has_invalid_self = "self." in helper_body

    return signature_ok and not has_invalid_self, {
        "signature_ok": signature_ok,
        "has_invalid_self": has_invalid_self,
    }


def fix_name_self_error():
    """修復 'name self is not defined' 錯誤"""
    print("🔧 開始修復 'name self is not defined' 錯誤")

    # 可能出現錯誤的文件列表
    error_files = [
        FORTRESS_FILE,
    ]

    fixed_count = 0

    for file_path in error_files:
        if os.path.exists(file_path):
            print(f"🔍 檢查文件: {file_path}")

            # 讀取文件內容
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 檢查並修復錯誤
            fixed_content = content

            if file_path == FORTRESS_FILE:
                fixed_content = fixed_content.replace(
                    "def build_battle_embed(state: fs.FortressState) -> discord.Embed:",
                    "def build_battle_embed(state: fs.FortressState, bot: discord.Client) -> discord.Embed:",
                )
                fixed_content = fixed_content.replace(
                    'value="\\n".join(_tower_summary_lines(state, self.bot)),',
                    'value="\\n".join(_tower_summary_lines(state, bot)),',
                )
                fixed_content = fixed_content.replace(
                    "embed = build_battle_embed(state)",
                    "embed = build_battle_embed(state, self.bot)",
                )
                fixed_content = fixed_content.replace(
                    "await msg.edit(embed=build_battle_embed(state_final), view=None)",
                    "await msg.edit(embed=build_battle_embed(state_final, self.bot), view=None)",
                )
                fixed_content = fixed_content.replace(
                    "await msg.edit(embed=build_battle_embed(state), view=view)",
                    "await msg.edit(embed=build_battle_embed(state, self.bot), view=view)",
                )

            if fixed_content != content:
                print(f"⚠️ 發現錯誤在: {file_path}")

                # 寫回修復後的內容
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(fixed_content)

                print(f"✅ 已修復: {file_path}")
                fixed_count += 1

                # 添加到 Git
                subprocess.run(["git", "add", file_path], check=True)
                print(f"📝 已添加到 Git: {file_path}")
            else:
                print(f"✅ 文件正常: {file_path}")
        else:
            print(f"⚠️ 文件不存在: {file_path}")

    print(f"🎯 修復完成，共修復 {fixed_count} 個文件")

    # 提交修復
    if fixed_count > 0:
        try:
            subprocess.run(["git", "config", "user.name", "Bug Fix Bot"], check=True)
            subprocess.run(
                ["git", "config", "user.email", "bug-fix@kkgroup.local"], check=True
            )

            commit_message = f"""fix: 修復 'name self is not defined' 錯誤

🔧 自動修復 GitHub Actions 中的 'name self is not defined' 錯誤
📊 修復文件數量: {fixed_count}
⏰ 修復時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

修復內容：
- 修正 fortress_defense 模組級 helper 中誤用 self 的問題
- 同步更新 build_battle_embed 呼叫點
- 自動提交修復到 Git
"""

            subprocess.run(["git", "commit", "-m", commit_message], check=True)
            subprocess.run(["git", "push", "origin", "main"], check=True)

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
        FORTRESS_FILE,
    ]

    results = []

    for file_path in test_files:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if file_path == FORTRESS_FILE:
                    is_valid, details = _validate_fortress_fix(content)
                    if is_valid:
                        print(f"✅ {file_path}: fortress self 錯誤檢查通過")
                        results.append(
                            {"file": file_path, "status": "success", "error": None}
                        )
                    else:
                        print(f"❌ {file_path}: fortress 驗證失敗 - {details}")
                        results.append(
                            {
                                "file": file_path,
                                "status": "error",
                                "error": str(details),
                            }
                        )
                else:
                    print(f"✅ {file_path}: 無額外測試")
                    results.append(
                        {"file": file_path, "status": "success", "error": None}
                    )

            except Exception as e:
                error_msg = str(e)
                if "name 'self' is not defined" in error_msg:
                    print(f"⚠️ {file_path}: 仍有 'name self' 錯誤")
                    results.append(
                        {
                            "file": file_path,
                            "status": "error",
                            "error": "name self error",
                        }
                    )
                else:
                    print(f"❌ {file_path}: 其他錯誤 - {error_msg}")
                    results.append(
                        {"file": file_path, "status": "error", "error": error_msg}
                    )
        else:
            print(f"⚠️ {file_path}: 文件不存在")
            results.append(
                {"file": file_path, "status": "missing", "error": "file not found"}
            )

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
        status_icon = (
            "✅"
            if result["status"] == "success"
            else "❌"
            if result["status"] == "error"
            else "⚠️"
        )
        print(f"{status_icon} {result['file']}: {result.get('error', 'N/A')}")

    return success_count == len(test_files) and error_count == 0


if __name__ == "__main__":
    print("🚀 開始修復 'name self is not defined' 錯誤")
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
