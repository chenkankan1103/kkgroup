import sqlite3
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheet 授權
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("kkgroup-0441c30231b7.json", scope)
client = gspread.authorize(creds)

sheet = client.open_by_url(
    "https://docs.google.com/spreadsheets/d/1ixMX389tQZ4f4R93KO9rGj7MmU7DHEYSIAgykDVnIpM/edit#gid=0"
).sheet1

# 讀取 SQLite
conn = sqlite3.connect("user_data.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM users")
rows = cursor.fetchall()
col_names = [desc[0] for desc in cursor.description]
conn.close()

# 清空 Sheet
sheet.clear()

# 寫入標題列
sheet.update("A1", [col_names])

# 寫入所有資料（批次）
sheet.update(f"A2", rows)
print("✅ 已批次同步 DB → Google Sheet！")
