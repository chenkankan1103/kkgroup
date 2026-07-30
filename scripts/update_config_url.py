"""更新 config.json 使用新的永久網址"""
import json
import os

NEW_URL = "https://kkgroup2026.duckdns.org"
BASE = "/home/e193752468/kkgroup"

# 1. 更新 config/config.json
config_path = os.path.join(BASE, "config", "config.json")
with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

config["url"] = NEW_URL
config["API_BASE"] = NEW_URL

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print(f"✅ config/config.json → {NEW_URL}")

# 2. 更新 web/portal/config.json
portal_config_path = os.path.join(BASE, "web", "portal", "config.json")
with open(portal_config_path, "w", encoding="utf-8") as f:
    json.dump({"url": NEW_URL, "API_BASE": NEW_URL}, f, ensure_ascii=False, indent=2)

print(f"✅ web/portal/config.json → {NEW_URL}")

# 3. 驗證
print(f"\n📋 config/config.json url: {config.get('url')}")
print(f"📋 config/config.json API_BASE: {config.get('API_BASE')}")