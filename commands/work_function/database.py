import sqlite3
import os
import traceback
import discord
from discord.ext import commands

DB_PATH = os.getenv("DB_PATH", "user_data.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            kkcoin INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            last_checkin TEXT DEFAULT NULL
        )
    """)
    conn.commit()
    
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = [col[1] for col in cursor.fetchall()]
    
    if "streak" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN streak INTEGER DEFAULT 0")
    if "level" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
    if "title" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN title TEXT DEFAULT '車手'")
    if "last_work_date" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_work_date TEXT DEFAULT NULL")
    if "last_action_date" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_action_date TEXT DEFAULT NULL")
    if "actions_used" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN actions_used TEXT DEFAULT '{}'")
    if "is_locked" not in existing_columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_locked INTEGER DEFAULT 0")
    
    conn.commit()
    conn.close()

def get_user(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
        user = c.fetchone()
        if not user:
            c.execute("INSERT INTO users (user_id) VALUES (?)", (str(user_id),))
            conn.commit()
            c.execute("SELECT * FROM users WHERE user_id = ?", (str(user_id),))
            user = c.fetchone()
        conn.close()
        return dict(user) if user else None
    except Exception as e:
        traceback.print_exc()
        return None

def update_user(user_id, **kwargs):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        for key, value in kwargs.items():
            c.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, str(user_id)))
        conn.commit()
        conn.close()
    except Exception as e:
        traceback.print_exc()

def delete_user(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE user_id = ?", (str(user_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        traceback.print_exc()

def reset_user(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''UPDATE users SET
                        level = 1,
                        xp = 0,
                        kkcoin = 0,
                        last_work_date = NULL,
                        streak = 0,
                        is_locked = 0,
                        actions_used = '{}'
                     WHERE user_id = ?''', (str(user_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        traceback.print_exc()

class DatabaseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

# 設置函數 - Discord.py 需要這個函數來載入 cog
async def setup(bot):
    await bot.add_cog(DatabaseCog(bot))