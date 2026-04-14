import sqlite3

DB = 'user_data.db.local_backup'

def main():
    try:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in cur.fetchall()]

        # 如果沒有 event_history 欄位，嘗試搜尋所有文字欄位中的關鍵字
        if 'event_history' in cols:
            cur.execute("SELECT user_id, event_history FROM users WHERE event_history IS NOT NULL AND event_history != '' LIMIT 1000")
            rows = cur.fetchall()
            matches = [(r['user_id'], r['event_history']) for r in rows if r['event_history'] and ('大麻' in str(r['event_history']) or 'cannabis' in str(r['event_history']) or '種植' in str(r['event_history']))]
            print(f'FOUND_via_event_history_column={len(matches)}')
            for uid, ev in matches[:20]:
                print('USER', uid, ev)

        # 掃描所有可能的文字欄位
        text_cols = [c for c in cols if c not in ('user_id',) and not c.startswith('_')]
        keyword_matches = []
        for col in text_cols:
            try:
                cur.execute(f"SELECT user_id, \"{col}\" FROM users WHERE \"{col}\" LIKE '%大麻%' OR \"{col}\" LIKE '%種植%' OR \"{col}\" LIKE '%cannabis%' LIMIT 20")
                for r in cur.fetchall():
                    keyword_matches.append((col, r['user_id'], r[1]))
            except Exception:
                continue

        print(f'FOUND_in_text_columns={len(keyword_matches)}')
        for col, uid, val in keyword_matches[:30]:
            print(col, uid, val)

        # 檢查是否有 last_event_message_id 欄位與內容
        if 'last_event_message_id' in cols:
            cur.execute("SELECT user_id, last_event_message_id FROM users WHERE last_event_message_id IS NOT NULL LIMIT 50")
            for r in cur.fetchall():
                print('LAST_MSG', r['user_id'], r['last_event_message_id'])

        conn.close()
    except Exception as e:
        print('ERROR', e)

if __name__ == '__main__':
    main()
