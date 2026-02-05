import sqlite3

conn = sqlite3.connect('user_data.db')
cursor = conn.cursor()

# 添加虛擬帳號以測試清理工具
cursor.execute("""
    INSERT INTO users (user_id, nickname, level, kkcoin, title)
    VALUES 
    (999999999999999991, 'Unknown_1234', 1, 1000, '新手'),
    (999999999999999992, 'Unknown_5678', 2, 2000, '勇者'),
    (999999999999999993, 'Unknown_9999', 3, 3000, '戰士')
""")
conn.commit()

cursor.execute("SELECT COUNT(*) FROM users WHERE nickname LIKE 'Unknown_%'")
print(f"已添加虛擬帳號: {cursor.fetchone()[0]} 個")

conn.close()
