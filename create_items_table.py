#!/usr/bin/env python3
"""
此腳本用於GCP SSH執行，將 twms_fashion_db.json 整合到GCP資料庫的新 items 表
使用方法：在GCP上執行 python create_items_table.py --gcp-db-path <GCP資料庫路徑>
"""
import json
import sqlite3
from pathlib import Path
import argparse

def create_items_table(gcp_db_path: str, json_file: str = 'twms_fashion_db.json'):
    """將JSON數據整合到GCP資料庫的items表"""
    
    json_path = Path(json_file)
    if not json_path.exists():
        print(f"❌ 找不到JSON文件: {json_file}")
        return False
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 連接GCP資料庫
        conn = sqlite3.connect(gcp_db_path)
        cursor = conn.cursor()
        
        # 創建items表（如果不存在）
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
        
        # 插入數據（使用INSERT OR IGNORE避免重複）
        inserted_count = 0
        for item in data:
            cursor.execute('''
                INSERT OR IGNORE INTO items (id, name, category, region, version, image_url)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (item['id'], item['name'], item['category'], item['region'], item['version'], item['image_url']))
            inserted_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"✅ 整合完成！共插入 {inserted_count} 筆數據到 {gcp_db_path}")
        return True
        
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="將紙娃娃JSON數據整合到GCP資料庫")
    parser.add_argument('--gcp-db-path', required=True, help="GCP資料庫路徑（如 /path/to/database.db）")
    parser.add_argument('--json-file', default='twms_fashion_db.json', help="JSON文件路徑")
    
    args = parser.parse_args()
    create_items_table(args.gcp_db_path, args.json_file)
