# 🚀 Git 遠端維護工具 - 部署和測試流程

## 📋 檢查清單

### 第一步：本地驗證 ✅

```bash
# 1️⃣ 驗證工具是否正確註冊
cd /path/to/kkgroup
python check_registry.py

# 預期輸出：
# Found 3 Git-related tools: ['read_project_file', 'write_project_file', 'get_git_status']
```

### 第二步：部署到 GCP

```bash
# 2️⃣ 推送本地代碼到 GitHub（包含新工具）
cd /path/to/kkgroup
git add agent_tools.py
git commit -m "feat: 添加 Git 遠端維護工具（讀取、修改、狀態查詢）"
git push origin main

# 3️⃣ 在 GCP VM 上更新代碼
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "cd /home/e193752468/kkgroup && git pull origin main"

# 4️⃣ 確認檔案已更新
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "grep -c 'read_project_file' /home/e193752468/kkgroup/agent_tools.py"

# 預期輸出：應該有至少 1 個匹配
```

### 第三步：重啟 BOT 服務

```bash
# 5️⃣ 重啟 BOT 以加載新工具
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "sudo systemctl restart bot.service && echo '✅ Bot 已重啟'"

# 6️⃣ 檢查 BOT 狀態
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "sudo systemctl status bot.service --no-pager | head -20"
```

### 第四步：Discord 測試

#### 🧪 測試套組 A：基本讀取功能

1️⃣ **讀取 bot.py**
```
@KK園區中控室 讀取一下 bot.py 前 100 行代碼，告訴我它的功能
```

✅ 預期：返回 bot.py 的內容摘要

2️⃣ **讀取 commands/AI.py**
```
@KK園區中控室 help 一下 commands 目錄下的 AI.py 檔案
```

✅ 預期：返回 AI.py 的內容摘要

#### 🧪 測試套組 B：安全檢查

3️⃣ **嘗試讀取非 .py 檔案（應被拒絕）**
```
@KK園區中控室 讀一下 README.md 的內容
```

✅ 預期結果：
```
❌ 僅支持 .py 檔案，不支持 .md
```

4️⃣ **嘗試路徑遍歷（應被拒絕）**
```
@KK園區中控室 讀取 ../../../etc/passwd 的內容
```

✅ 預期結果：
```
❌ 安全檢查失敗：路徑超出專案目錄。
```

5️⃣ **非管理員使用（應被拒絕）**
```
使用非管理員帳號執行：
@KK園區中控室 讀一下 bot.py
```

✅ 預期結果：
```
存取拒絕：read_project_file 僅限園區管理員。
```

#### 🧪 測試套組 C：Git 狀態查詢

6️⃣ **查詢當前 Git 狀態**
```
@KK園區中控室 現在的 Git 狀態怎樣？有未提交的改動嗎？
```

✅ 預期結果：
```
🌿 當前分支：main
📝 最後提交：[最新 commit 信息]
[已提交/未提交情報]
```

#### 🧪 測試套組 D：文件修改和 Git Push（高級）

⚠️ **此測試應謹慎進行，確保在測試用檔案上操作**

7️⃣ **提交無效 Python 代碼（應被拒絕）**
```
@KK園區中控室 我想修改 test_invalid.py，新內容是：

def broken():  # 缺少冒號和內容
    print(

提交訊息：test: 無效語法測試
```

✅ 預期結果：
```
❌ 代碼語法檢查失敗（拒絕寫入）
📍 錯誤位置：第 2 行
❗ unexpected EOF while parsing
```

8️⃣ **提交有效代碼（應成功）**
```
@KK園區中控室 修改 test_valid_example.py，新內容是：

#!/usr/bin/env python3
# 測試有效代碼
def example():
    return "Success!"

if __name__ == "__main__":
    print(example())

提交訊息：test: 新增有效測試檔案
```

✅ 預期結果：
```
✅ 檔案修改完成並已推送到 GitHub
📝 修改檔案：test_valid_example.py
📊 新內容：8 行
💬 提交訊息：test: 新增有效測試檔案

🔧 Git 操作結果：
✅ git add 成功
✅ git commit 成功
✅ git push 成功
```

---

## 📊 預期測試結果

所有 8 個測試應該完成如下：

| 編號 | 測試名稱 | 預期結果 | 狀態 |
|------|--------|--------|------|
| 1️⃣ | 讀取 bot.py | ✅ 返回內容 | ⏳ |
| 2️⃣ | 讀取 AI.py | ✅ 返回內容 | ⏳ |
| 3️⃣ | 讀取非 .py 檔案 | ❌ 被拒絕 | ⏳ |
| 4️⃣ | 路徑遍歷攻擊 | ❌ 被拒絕 | ⏳ |
| 5️⃣ | 非管理員使用 | ❌ 被拒絕 | ⏳ |
| 6️⃣ | 查詢 Git 狀態 | ✅ 返回狀態 | ⏳ |
| 7️⃣ | 無效 Python 代碼 | ❌ 被拒絕 | ⏳ |
| 8️⃣ | 有效 Python 代碼 | ✅ 成功推送 | ⏳ |

---

## 🛠️ 故障排查

### 問題 1：工具未載入

**症狀**：AI 不認識新工具

**排查步驟**：
```bash
# 1. 檢查 GCP 上的檔案是否已更新
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "grep 'read_project_file' /home/e193752468/kkgroup/agent_tools.py"

# 2. 檢查 BOT 是否已重啟
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "ps aux | grep bot.py"

# 3. 查看 BOT 日誌
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "sudo journalctl -u bot.service -n 50 --no-pager | grep -i 'tool\|error\|warning'"
```

**解決方案**：
```bash
# 強制重啟 BOT
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "sudo systemctl restart bot.service"
```

---

### 問題 2：Git Push 失敗

**症狀**：修改成功但 git push 失敗

**排查步驟**：
```bash
# 1. 檢查 GCP 上的 Git 配置
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "cd /home/e193752468/kkgroup && git status"

# 2. 查看遠端配置
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "cd /home/e193752468/kkgroup && git remote -v"

# 3. 檢查 Git 認證
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "cd /home/e193752468/kkgroup && git push origin main --dry-run"
```

---

### 問題 3：權限被拒絕

**症狀**：非管理員使用工具無法被拒絕

**排查步驟**：
```python
# 檢查 LEADER_ID 是否正確設置
import os
from dotenv import load_dotenv
load_dotenv()
leader_id = int(os.getenv("LEADER_DISCORD_ID", "0"))
print(f"Current LEADER_ID: {leader_id}")
print(f"Expected ADMIN_ID: 432018481890983936")
```

---

## 📈 監控和日誌

### BOT 日誌查詢

```bash
# 查看最近 100 行日誌（包含工具呼叫）
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "sudo journalctl -u bot.service -n 100 --no-pager | tail -50"

# 搜索特定工具的日誌
gcloud compute ssh e193752468@instance-20250501-142333 \
  --zone us-central1-c \
  --tunnel-through-iap \
  --command "sudo journalctl -u bot.service | grep -i 'read_project_file\|write_project_file\|git_status'"
```

### Discord 日誌查詢

在 Discord 中提問：
```
@KK園區中控室 顯示最近的工具呼叫記錄
```

---

## ✅ 完成標準

所有測試完成後檢查清單：

- [ ] ✅ 本地驗證工具註冊成功
- [ ] ✅ 代碼已推送至 GitHub
- [ ] ✅ GCP 代碼已更新
- [ ] ✅ BOT 已重啟
- [ ] ✅ 讀取功能測試通過
- [ ] ✅ 安全檢查測試通過
- [ ] ✅ 修改功能測試通過
- [ ] ✅ Git 操作測試通過

---

## 📞 聯絡支援

如遇問題，請提供以下資訊：
1. 完整的 Discord 命令內容
2. BOT 的回應信息
3. GCP 日誌摘要（前 20 行）
4. 當前 Git 分支和最後一次提交訊息
