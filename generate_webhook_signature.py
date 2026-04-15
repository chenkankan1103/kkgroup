#!/usr/bin/env python3
"""
模擬 GitHub webhook 請求，用於測試簽名驗證
"""
import hmac
import hashlib
import json

WEBHOOK_SECRET = ""  # 如果未設置，簽名驗證將被跳過

payload_json = {
    "ref": "refs/heads/restructure-project-20260414",
    "commits": [
        {
            "id": "abc123def456",
            "message": "Test commit"
        }
    ],
    "action": "push"
}

payload_bytes = json.dumps(payload_json).encode()

# 計算簽名
if WEBHOOK_SECRET:
    signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    signature_header = f"sha256={signature}"
else:
    signature_header = ""

print(f"Content-Type: application/json")
print(f"X-GitHub-Event: push")
if signature_header:
    print(f"X-Hub-Signature-256: {signature_header}")
print(f"")
print(json.dumps(payload_json, indent=2))
