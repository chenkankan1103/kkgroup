"""
置物櫃 ID 對應修復工具
檢查並修復 cannabis.db 中的 user_id 映射問題
"""
import sqlite3
import asyncio
from pathlib import Path

DB_PATH = './shop_commands/merchant/cannabis.db'


def check_id_mapping():
    """檢查 cannabis.db 中的 ID 映射"""
    if not Path(DB_PATH).exists():
        print(f"❌ {DB_PATH} 不存在")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        print("=== 檢查 Cannabis Plants 表 ===")
        
        # 獲取所有 distinct user_id
        c.execute('SELECT DISTINCT user_id FROM cannabis_plants ORDER BY user_id')
        user_ids = c.fetchall()
        
        print(f"\n📊 總計 {len(user_ids)} 個不同的用戶")
        print("\nUser IDs 清單:")
        
        for user_id in user_ids:
            uid = user_id[0]
            # 檢查是否有效 (18位數字)
            uid_str = str(uid)
            is_valid = len(uid_str) == 18 and uid_str.isdigit() and 100000000000000000 <= uid <= 999999999999999999
            
            # 計算植物數
            c.execute('SELECT COUNT(*) FROM cannabis_plants WHERE user_id = ?', (uid,))
            plant_count = c.fetchone()[0]
            
            # 檢查庫存
            c.execute('SELECT COUNT(*) FROM cannabis_inventory WHERE user_id = ?', (uid,))
            inventory_count = c.fetchone()[0]
            
            status = "✅ 有效" if is_valid else "⚠️  可疑"
            print(f"  {status} {uid} - {plant_count} 株植物，{inventory_count} 項庫存")
        
        print("\n=== 檢查 Inventory 表 ===")
        c.execute('SELECT DISTINCT user_id FROM cannabis_inventory ORDER BY user_id')
        inv_user_ids = c.fetchall()
        print(f"庫存表中 {len(inv_user_ids)} 個不同用戶")
        
        conn.close()
        return True
    
    except Exception as e:
        print(f"❌ 檢查失敗: {e}")
        return False


def find_id_offset():
    """嘗試找出 ID 偏差"""
    if not Path(DB_PATH).exists():
        return None
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        print("\n=== 分析 ID 偏差 ===")
        
        c.execute('SELECT MIN(user_id), MAX(user_id) FROM cannabis_plants')
        min_id, max_id = c.fetchone()
        
        print(f"ID 範圍: {min_id} ~ {max_id}")
        print(f"ID 跨度: {max_id - min_id if min_id and max_id else 'N/A'}")
        
        # 檢查是否都是有效ID
        c.execute('SELECT COUNT(*) FROM cannabis_plants WHERE user_id < 100000000000000000 OR user_id > 999999999999999999')
        invalid_count = c.fetchone()[0]
        
        if invalid_count > 0:
            print(f"⚠️  找到 {invalid_count} 個無效 ID（不是18位數字）")
            
            # 列出無效ID
            c.execute('SELECT DISTINCT user_id FROM cannabis_plants WHERE user_id < 100000000000000000 ORDER BY user_id')
            for row in c.fetchall()[:10]:
                print(f"  - {row[0]}")
        else:
            print("✅ 所有 ID 都是有效的 18 位數字")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ 分析失敗: {e}")


def fix_id_offset(offset: int):
    """修復所有 ID 偏差"""
    if offset == 0:
        print("❌ 偏差為零，無需修復")
        return False
    
    if not Path(DB_PATH).exists():
        print(f"❌ {DB_PATH} 不存在")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        print(f"\n⚠️  開始修復 ID 偏差 (offset={offset})...")
        
        # 備份
        backup_path = f"{DB_PATH}.backup_before_id_fix"
        import shutil
        shutil.copy(DB_PATH, backup_path)
        print(f"✅ 備份已保存到: {backup_path}")
        
        # 更新 cannabis_plants
        c.execute('UPDATE cannabis_plants SET user_id = user_id + ? WHERE user_id < 100000000000000000', (offset,))
        plants_updated = c.rowcount
        
        # 更新 cannabis_inventory
        c.execute('UPDATE cannabis_inventory SET user_id = user_id + ? WHERE user_id < 100000000000000000', (offset,))
        inventory_updated = c.rowcount
        
        conn.commit()
        
        print(f"✅ 更新完成:")
        print(f"   - cannabis_plants: {plants_updated} 條記錄")
        print(f"   - cannabis_inventory: {inventory_updated} 條記錄")
        
        conn.close()
        return True
    
    except Exception as e:
        print(f"❌ 修復失敗: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("置物櫃 ID 映射診斷工具")
    print("=" * 60)
    
    check_id_mapping()
    find_id_offset()
    
    print("\n" + "=" * 60)
    print("用法:")
    print("  python check_locker_id_mapping.py          # 檢查 ID")
    print("  python check_locker_id_mapping.py fix 500  # 修復偏差 (+500)")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == 'fix':
        offset = int(sys.argv[2]) if len(sys.argv) > 2 else 500
        fix_id_offset(offset)
