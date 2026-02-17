#!/usr/bin/env python3
"""Check user paperdoll fields in user_data.db and report missing/zero values."""
import sqlite3
import json

DB = 'user_data.db'

def run():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Count total users
    total = cur.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    # Count users with missing or zero paperdoll fields
    q = '''SELECT COUNT(*) FROM users WHERE
           face IS NULL OR hair IS NULL OR skin IS NULL OR top IS NULL OR bottom IS NULL OR shoes IS NULL
        '''
    missing = cur.execute(q).fetchone()[0]

    # Count users with default/zero paperdoll (all zeros or default values)
    q2 = '''SELECT COUNT(*) FROM users WHERE (face IS NULL OR face=0) AND (hair IS NULL OR hair=0)'''
    zero_minimal = cur.execute(q2).fetchone()[0]

    print(f"total_users={total}")
    print(f"missing_paperdoll_fields={missing}")
    print(f"zero_face_hair_count={zero_minimal}")

    # Show sample users with missing/zero fields (limit 10)
    rows = cur.execute("SELECT user_id, face, hair, skin, top, bottom, shoes, embed_image_source IS NOT NULL AS has_image_source, cached_character_image IS NOT NULL AS has_cached_image FROM users WHERE face IS NULL OR hair IS NULL OR top IS NULL OR bottom IS NULL OR shoes IS NULL LIMIT 10").fetchall()
    if rows:
        print('\nSample users with missing fields:')
        for r in rows:
            print(dict(r))

    # Show how many users have cached_character_image
    cached_count = cur.execute("SELECT COUNT(*) FROM users WHERE cached_character_image IS NOT NULL").fetchone()[0]
    print(f"cached_character_image_count={cached_count}")

    # Show how many have embed_image_source
    embed_src_count = cur.execute("SELECT COUNT(*) FROM users WHERE embed_image_source IS NOT NULL").fetchone()[0]
    print(f"embed_image_source_count={embed_src_count}")

    conn.close()

if __name__ == '__main__':
    run()