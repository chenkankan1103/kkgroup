#!/usr/bin/env python3
"""Backfill locker_message_id for users by scanning forum thread messages.

Usage: run on the server where `user_data.db` and BOT token (.env) are available.
What it does:
- Ensure `locker_message_id` column exists in `users` table (ALTER TABLE if missing)
- For each user with `thread_id` and missing `locker_message_id`, call Discord API
  to fetch messages from that thread and look for the bot's embed that looks
  like a locker (title contains '置物櫃' or '個人置物櫃' or starts with '📦').
- If found, update the users table with the message id.

Note: must be run where BOT_TOKEN env var is set (UI_DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN).
"""

import os
import sqlite3
import requests
import time
from typing import Optional

DB_PATH = os.getenv('USER_DB_PATH', 'user_data.db')
BOT_TOKEN = os.getenv('UI_DISCORD_BOT_TOKEN') or os.getenv('DISCORD_BOT_TOKEN') or os.getenv('SHOP_DISCORD_BOT_TOKEN')
DISCORD_API = 'https://discord.com/api/v10'

if not BOT_TOKEN:
    print('❌ Bot token not found in environment (UI_DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN)')
    raise SystemExit(1)

HEADERS = {'Authorization': f'Bot {BOT_TOKEN}'}


def ensure_column(conn: sqlite3.Connection, column: str, col_type: str = 'INTEGER') -> None:
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info(users);")
    cols = [r[1] for r in cursor.fetchall()]
    if column in cols:
        return
    print(f"➕ Adding column '{column}' to users table")
    cursor.execute(f'ALTER TABLE users ADD COLUMN "{column}" {col_type}')
    conn.commit()


def get_bot_id() -> Optional[str]:
    r = requests.get(f"{DISCORD_API}/users/@me", headers=HEADERS, timeout=10)
    if r.status_code == 200:
        return r.json().get('id')
    print('❌ Failed to get bot id:', r.status_code, r.text[:200])
    return None


def fetch_thread_messages(thread_id: str, limit: int = 200):
    url = f"{DISCORD_API}/channels/{thread_id}/messages?limit={limit}"
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 200:
        return r.json()
    # rate limit or other error
    print(f"⚠️ Failed to fetch messages for thread {thread_id}: {r.status_code}")
    return []


def looks_like_locker_embed(embed: dict) -> bool:
    title = (embed.get('title') or '').strip()
    if not title:
        return False
    return ('置物櫃' in title) or ('個人置物櫃' in title) or title.startswith('📦')


def backfill(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_column(conn, 'locker_message_id', 'INTEGER')

    bot_id = get_bot_id()
    if not bot_id:
        print('Cannot determine bot id; aborting')
        return

    cursor = conn.cursor()
    cursor.execute("SELECT user_id, thread_id, locker_message_id FROM users WHERE thread_id IS NOT NULL AND thread_id != 0")
    rows = cursor.fetchall()

    print(f"🔎 Scanning {len(rows)} users with thread_id for locker message")

    updated = 0
    skipped = 0
    for r in rows:
        user_id = r['user_id']
        thread_id = r['thread_id']
        current = r['locker_message_id']
        if current and str(current).strip() != '':
            skipped += 1
            continue

        if not thread_id:
            continue

        msgs = fetch_thread_messages(thread_id)
        found_msg_id = None
        for m in msgs:
            # check author
            author = m.get('author', {})
            if str(author.get('id')) != str(bot_id):
                continue
            embeds = m.get('embeds') or []
            for e in embeds:
                if looks_like_locker_embed(e):
                    found_msg_id = m.get('id')
                    break
            if found_msg_id:
                break

        if found_msg_id:
            try:
                cursor.execute('UPDATE users SET locker_message_id = ? WHERE user_id = ?', (found_msg_id, user_id))
                conn.commit()
                updated += 1
                print(f"✅ user {user_id} backfilled with message {found_msg_id}")
            except Exception as ex:
                print(f"❌ Failed to update user {user_id}: {ex}")
        else:
            print(f"— user {user_id}: locker message not found in thread {thread_id}")

        # be gentle on rate limits
        time.sleep(0.15)

    print(f"Done. updated={updated}, skipped_with_existing={skipped}")
    conn.close()


if __name__ == '__main__':
    print('Starting locker_message_id backfill')
    backfill(DB_PATH)
