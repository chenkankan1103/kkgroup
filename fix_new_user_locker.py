# -*- coding: utf-8 -*-
"""
紧急修复：为新用户生成置物柜面板

用途：当新用户加入但没有看到置物柜或纸娃娃时使用
"""

import sqlite3
import sys
sys.path.insert(0, '/home/e193752468/kkgroup')

from cogs.ui.utils.paperdoll_manager import build_api_url
from db_adapter import get_user

def fix_new_user_locker(user_id):
    """为新用户生成纸娃娃 URL 并验证"""
    print(f"\n🔧 开始修复用户 {user_id} 的置物柜...\n")
    
    # 获取用户数据
    user_data = get_user(user_id)
    
    if not user_data:
        print(f"❌ 找不到用户 {user_id}")
        return False
    
    print("📋 用户数据:")
    paperdoll_fields = ['face', 'hair', 'skin', 'top', 'bottom', 'shoes', 'gender', 'is_stunned']
    for field in paperdoll_fields:
        value = user_data.get(field)
        status = "⚠️ 缺失" if value is None else "✅"
        print(f"  {status} {field}: {value}")
    
    print("\n🌐 生成纸娃娃 URL...")
    
    # 测试默认姿态（stand1）
    url_stand = build_api_url(user_data, pose='stand1')
    print(f"  stand1: {url_stand[:80] if url_stand else '❌ 失败'}...")
    
    # 测试暈倒姿态（prone）- 系统会自动转换
    url_prone = build_api_url(user_data, pose='prone')
    print(f"  prone:  {url_prone[:80] if url_prone else '❌ 失败'}...")
    
    # 检查is_stunned逻辑
    print(f"\n📊 暈倒状态分析:")
    is_stunned = user_data.get('is_stunned', 0)
    print(f"  is_stunned 值: {is_stunned} (类型: {type(is_stunned).__name__})")
    print(f"  是否暈倒: {'是 (1)' if is_stunned == 1 else '否 (0)'}")
    
    if is_stunned == 1:
        print(f"  ✅ 暈倒状态已激活，紙娃娃会显示为 prone 姿态")
    
    print(f"\n✅ 用户 {user_id} 数据验证完成！")
    print(f"   - 纸娃娃 URL 生成: {'✅ 成功' if url_stand else '❌ 失败'}")
    print(f"   - 暈倒状态: {'✅ 激活' if is_stunned == 1 else '⚠️ 未激活'}")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    else:
        user_id = "1430046213012590592"
    
    fix_new_user_locker(user_id)
