test_msg = "P圖一下這個logo"
content_lower = test_msg.lower()
print(f"原文: {test_msg}")
print(f"小寫: {content_lower}")

keywords = ["編", "P圖", "編輯圖", "改", "修改", "調整", "改圖"]
for kw in keywords:
    kw_lower = kw.lower()
    result = kw_lower in content_lower
    print(f"  '{kw}' -> '{kw_lower}' in '{content_lower}' = {result}")
