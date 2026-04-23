#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
更新 .env 中的 Twitter API 憑證
"""
import os
from pathlib import Path

# 新的 Bearer Token（@chnyxun629447 帳號）
NEW_BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAAMvJ9AEAAAAAiT%2F%2BDF%2FtRnRiHpK0gwhTtaKJilM%3DGRPXsQbvf3jC1xLrt5XoO5jqI18GFF8vfON7J1GDCXRoFgPNJA"
NEW_CONSUMER_KEY = "4YISOYjwht3gB4sA2fE2i4Ij3"
NEW_CONSUMER_SECRET = "MrlgOk8gicB0cF9UWYTHoMpWgsNeVyRfuJYWvwemwSQI5byfWU"

# .env 位置
ENV_FILE = Path(__file__).parent / ".env"

print(f"📝 正在更新 {ENV_FILE}")

if not ENV_FILE.exists():
    print(f"❌ 找不到 .env 檔案: {ENV_FILE}")
    exit(1)

# 讀取現有 .env
with open(ENV_FILE, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 更新 Token
updated = False
new_lines = []
for line in lines:
    if line.startswith("TWITTER_BEARER_TOKEN="):
        new_lines.append(f"TWITTER_BEARER_TOKEN={NEW_BEARER_TOKEN}\n")
        updated = True
        print(f"✅ 已更新 TWITTER_BEARER_TOKEN")
    elif line.startswith("TWITTER_CONSUMER_KEY="):
        new_lines.append(f"TWITTER_CONSUMER_KEY={NEW_CONSUMER_KEY}\n")
        print(f"✅ 已更新 TWITTER_CONSUMER_KEY")
    elif line.startswith("TWITTER_CONSUMER_SECRET="):
        new_lines.append(f"TWITTER_CONSUMER_SECRET={NEW_CONSUMER_SECRET}\n")
        print(f"✅ 已更新 TWITTER_CONSUMER_SECRET")
    else:
        new_lines.append(line)

# 如果沒找到 TWITTER_BEARER_TOKEN，就在 Reddit API 配置前添加
if not updated:
    final_lines = []
    for i, line in enumerate(new_lines):
        final_lines.append(line)
        if line.startswith("# Reddit API"):
            # 在 Reddit API 之前插入
            final_lines.insert(-1, f"TWITTER_BEARER_TOKEN={NEW_BEARER_TOKEN}\n")
            final_lines.insert(-1, f"TWITTER_CONSUMER_KEY={NEW_CONSUMER_KEY}\n")
            final_lines.insert(-1, f"TWITTER_CONSUMER_SECRET={NEW_CONSUMER_SECRET}\n")
            updated = True
            print("✅ 已新增 TWITTER_BEARER_TOKEN, CONSUMER_KEY, CONSUMER_SECRET")
            break
    new_lines = final_lines

# 寫回 .env
with open(ENV_FILE, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"\n✅ .env 已更新完成！")
print(f"\n🔍 驗證:")
with open(ENV_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith("TWITTER_"):
            print(f"  {line.rstrip()}")
