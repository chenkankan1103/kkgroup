#!/usr/bin/env python3
"""
Backfill `embed_image_source` user field for existing users.
Priority:
 1) use users.cached_character_image.discord_url if present
 2) else use a MapleStory.io API URL (best-effort)

Run on the production VM as the app user:
  sudo -u e193752468 bash -lc "python3 /home/e193752468/kkgroup/tools/backfill_embed_image_source.py"
"""
import json
from db_adapter import get_all_users, get_user_field, set_user_field
from uicommands.utils.image_utils import build_maplestory_api_url

updated = 0
skipped = 0
failed = 0

for u in get_all_users():
    try:
        user_id = u.get('user_id')
        if not user_id:
            skipped += 1
            continue

        existing = get_user_field(user_id, 'embed_image_source', default=None)
        if existing:
            skipped += 1
            continue

        # 1) prefer cached_character_image (stored JSON with discord_url)
        cached = get_user_field(user_id, 'cached_character_image', default=None)
        if cached:
            try:
                obj = json.loads(cached)
                discord_url = obj.get('discord_url')
                if discord_url:
                    set_user_field(user_id, 'embed_image_source', discord_url)
                    updated += 1
                    continue
            except Exception:
                pass

        # 2) fallback: build a MapleStory API URL from user fields (best-effort)
        try:
            user_data = {
                'face': u.get('face', 20005),
                'hair': u.get('hair', 30120),
                'skin': u.get('skin', 12000),
                'top': u.get('top', 1040014),
                'bottom': u.get('bottom', 1060096),
                'shoes': u.get('shoes', 1072005),
                'is_stunned': u.get('is_stunned', 0)
            }
            api_url = build_maplestory_api_url(user_data, animated=True)
            set_user_field(user_id, 'embed_image_source', api_url)
            updated += 1
        except Exception as e:
            print('failed to build/store for', user_id, e)
            failed += 1

    except Exception as e:
        print('unexpected failure for user', u.get('user_id'), e)
        failed += 1

print(f"done — updated={updated} skipped={skipped} failed={failed}")