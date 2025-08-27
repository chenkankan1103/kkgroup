import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# === Google Sheet 授權 ===
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("kkgroup-0441c30231b7.json", scope)
client = gspread.authorize(creds)

# 開啟試算表 (用名稱 or 用網址)
sheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0").sheet1

# === 讀取 SQLite 資料庫 ===
conn = sqlite3.connect("kkgroup/user_data.db")
cursor = conn.cursor()

cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()

# 取得欄位名稱
col_names = [description[0] for description in cursor.description]

# === 清空 Google Sheet 再寫入 ===
sheet.clear()

# 寫入標題列
sheet.insert_row(col_names, 1)

# 寫入資料
for i, row in enumerate(rows, start=2):  # 從第2列開始
    sheet.insert_row(list(row), i)

conn.close()

print("✅ 已將 user_data.db 同步到 Google Sheet！")
