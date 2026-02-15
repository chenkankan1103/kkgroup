#!/usr/bin/env python3
"""
本地測試用 - 將JSON數據整合到本地測試資料庫
使用方法: python init_local_test_db.py
"""
import json
import sqlite3
from pathlib import Path

def init_local_test_db(test_db_path='./test_paperdoll.db', json_file='twms_fashion_db.json'):
    """初始化本地測試資料庫"""
    
    json_path = Path(json_file)
    if not json_path.exists():
        print(f"❌ 找不到JSON文件: {json_file}")
        print("請確保 twms_fashion_db.json 存在於當前目錄")
        return False
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✅ 載入JSON文件成功，共 {len(data)} 筆記錄")
        
        # 連接或創建本地測試資料庫
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()
        
        # 創建items表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY,
                name TEXT,
                category TEXT,
                region TEXT,
                version TEXT,
                image_url TEXT
            )
        ''')
        
        # 清空舊數據（確保測試的乾淨）
        cursor.execute("DELETE FROM items")
        
        # 插入新數據
        for item in data:
            cursor.execute('''
                INSERT INTO items (id, name, category, region, version, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item['id'], item['name'], item['category'], item['region'], item['version'], item['image_url']))
        
        conn.commit()
        
        # 驗證
        cursor.execute("SELECT COUNT(*) FROM items")
        count = cursor.fetchone()[0]
        conn.close()
        
        print(f"✅ 本地測試資料庫初始化完成")
        print(f"   路徑: {test_db_path}")
        print(f"   記錄數: {count}")
        
        # 檢查分類
        conn = sqlite3.connect(test_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM items")
        categories = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        print(f"   分類數: {len(categories)}")
        print(f"   分類: {', '.join(categories[:5])}{'...' if len(categories) > 5 else ''}")
        
        return True
        
    except Exception as e:
        print(f"❌ 初始化失敗: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔄 開始初始化本地測試資料庫...")
    success = init_local_test_db()
    if success:
        print("\n✅ 初始化完成！可以開始測試紙娃娃系統了。")
        print("   運行機器人: python bot.py")
        print("   在Discord執行: /shopping")
        print("   點擊: 探索 → 進入衣帽間")
    else:
        print("\n❌ 初始化失敗，請檢查錯誤信息。")
