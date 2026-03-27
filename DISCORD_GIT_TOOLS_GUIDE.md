# 🧪 Discord 遠端維護工具測試指南

## 📋 概述

本文檔說明如何在 Discord 中使用新增的三個 Git 遠端維護工具：
1. **read_project_file** - 讀取專案檔案
2. **write_project_file** - 修改檔案並 git push
3. **get_git_status** - 查詢 Git 狀態

---

## 🛠️ 工具詳情

### 1️⃣ read_project_file - 讀取專案檔案

**功能**：讀取專案目錄內的任何 Python 檔案

**參數**：
- `file_path` (必需)：相對路徑，如 `"bot.py"` 或 `"commands/AI.py"`

**安全特性**：
- ✅ 只允許讀取 `.py` 檔案
- ✅ 防路徑遍歷攻擊
- ✅ 管理員驗證
- ✅ 返回檔案行數和字符數

---

### 2️⃣ write_project_file - 修改檔案並 git push

**功能**：修改檔案、檢查語法、Git 提交

**參數**：
- `file_path` (必需)：相對路徑
- `new_content` (必需)：新的完整檔案內容
- `commit_message` (必需)：Git 提交訊息

**動作流程**：
```
1️⃣ 權限檢查        → 只允許管理員
2️⃣ 路徑安全檢查     → 防止目錄遍歷
3️⃣ Python 語法檢查  → compile() 驗證
4️⃣ 寫入檔案         → 如果語法通過
5️⃣ Git 操作         → add + commit + push
```

**安全特性**：
- ✅ 拒絕語法錯誤的代碼
- ✅ 詳細的編譯錯誤信息
- ✅ 完整的 Git 工作流
- ✅ 管理員驗證

**錯誤拒絕示例**：
```
❌ 代碼語法檢查失敗（拒絕寫入）
📍 錯誤位置：第 5 行
❗ invalid syntax
📜 print("missing closing paren"
```

---

### 3️⃣ get_git_status - 查詢 Git 狀態

**功能**：獲取當前 Git 狀態摘要

**參數**：無

**返回信息**：
- 🌿 當前分支
- 📝 最後提交訊息
- 未提交的改動（如果有）
- 🔗 遠端狀態（領先/落後）

---

## 📱 Discord 測試命令

### 測試 1️⃣：讀取 bot.py

```
@KK園區中控室 讀取一下 bot.py 的內容，特別是最開始的部分
```

**預期回應**：
```
✅ 成功讀取 bot.py
📊 XXX 行，XXXX 字符

───────────────────────
import os
import sys
...
```

---

### 測試 2️⃣：讀取 commands/AI.py

```
@KK園區中控室 請告訴我 commands/AI.py 有多少行代碼
```

**預期回應**：
```
✅ 成功讀取 commands/AI.py
📊 500 行，25000 字符
...
```

---

### 測試 3️⃣：查詢 Git 狀態

```
@KK園區中控室 目前 Git 的狀態如何？有什麼未提交的改動嗎？
```

**預期回應**：
```
🌿 當前分支：main
📝 最後提交：fix: 修復某某功能
✅ 沒有未提交的改動
🔗 遠端狀態摘要：
Your branch is up to date with 'origin/main'.
```

---

### 測試 4️⃣：修改檔案（完整工作流程）

#### ❌ 第一步：測試無效語法被拒絕

```
@KK園區中控室 我想新增一個測試檔案，內容是：

def broken_function(:  # 👈 語法錯誤
    print("missing colon")
```

**預期回應**：
```
❌ 代碼語法檢查失敗（拒絕寫入）
📍 錯誤位置：第 1 行
❗ invalid syntax
📜 def broken_function(:
```

---

#### ✅ 第二步：提交有效的修改

```
@KK園區中控室 請修改 test_example.py 檔案，內容是：

# 測試示例
def hello_world():
    """簡單的問候函數"""
    return "Hello, World!"

if __name__ == "__main__":
    print(hello_world())

修改訊息是：feat: 新增測試示例檔案
```

**預期回應**：
```
✅ 檔案修改完成並已推送到 GitHub
📝 修改檔案：test_example.py
📊 新內容：9 行
💬 提交訊息：feat: 新增測試示例檔案

🔧 Git 操作結果：
✅ git add 成功
✅ git commit 成功
✅ git push 成功
```

---

## 🔒 權限系統

所有工具都需要管理員權限（Discord ID: `432018481890983936`）

### ❌ 非管理員嘗試使用

```
普通用戶：@KK園區中控室 讀取一下 bot.py

回應：存取拒絕：read_project_file 僅限園區管理員。
```

---

## 🚀 進階用法

### 場景 1：批量文件檢查

```
@KK園區中控室 檢查一下 bot.py 和 commands/AI.py 的代碼行數
```

機器人會逐個讀取並回報。

---

### 場景 2：在 AI 幫助下修改代碼

```
@KK園區中控室 我想在 bot.py 裡加入一個新的日誌記錄函數，
請根據現有代碼風格設計這個函數。

然後讀取 bot.py，分析現有的日誌設計，提出建議。
最後如果改動不大，可以直接修改。
```

工作流：
1. AI 讀取檔案
2. AI 分析現有代碼
3. AI 提出建議
4. 確認後，AI 提交修改版本

---

### 場景 3：監控 Git 狀態

```
@KK園區中控室 現在的代碼有什麼未同步到 GitHub 的改動嗎？

回應：
🌿 當前分支：main
📝 最後提交：修復某功能
📝 未提交的改動：
M  bot.py
M  commands/AI.py
?? new_file.py

🔗 遠端狀態摘要：
Your branch is ahead of 'origin/main' by 2 commits.
```

---

## ⚠️ 常見陷阱

### ❌ 陷阱 1：路徑錯誤

```
錯誤：@KK園區中控室 讀取 bot.py 的內容
正確：@KK園區中控室 讀取 Bot.py 或完整相對路徑

（注意：路徑是區分大小寫的）
```

### ❌ 陷阱 2：嘗試讀取非 .py 文件

```
請求：@KK園區中控室 讀取 README.md

回應：❌ 僅支持 .py 檔案，不支持 .md
```

### ❌ 陷阱 3：路徑遍歷攻擊被阻止

```
請求：@KK園區中控室 讀取 ../../../etc/passwd

回應：❌ 安全檢查失敗：路徑超出專案目錄。只允許讀取專案內的文件。
```

### ❌ 陷阱 4：未完整提供新內容

```
錯誤：@KK園區中控室 修改 bot.py，添加一行日誌
正確：@KK園區中控室 修改 bot.py，新內容是：
[完整的檔案內容，包括所有現有代碼 + 新改動]
```

---

## 📊 工具能力矩陣

| 工具 | 讀取檔案 | 修改檔案 | 語法檢查 | Git Push | 管理員檢查 | 路徑防護 |
|------|--------|--------|---------|---------|----------|--------|
| read_project_file | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ |
| write_project_file | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| get_git_status | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## 🧪 本地測試

若要在本地測試這些工具（無需 Discord）：

```bash
# 1. 驗證工具是否註冊
python check_registry.py

# 2. 運行完整測試套組
python test_git_remote_tools.py
```

---

## 🔧 故障排查

### 問題：工具不出現在列表中

```bash
# 檢查工具註冊
python check_registry.py | grep -i "git"

# 預期看到：
# Found 3 Git-related tools: ['read_project_file', 'write_project_file', 'get_git_status']
```

### 問題：Git 操作超時

- 可能原因：網絡連接慢，倉庫很大
- 解決方案：檢查 GCP 網絡連接，確保 Git 有效

### 問題：語法檢查誤判

- 如果合法代碼被拒絕，檢查是否有特殊字符編碼問題
- 嘗試複製代碼到純文本編輯器後重新提交

---

## 📚 相關文檔

- [agent_tools.py](agent_tools.py) - 工具實現源代碼
- [prompt_function_calling.py](prompt_function_calling.py) - 工具呼叫系統
- [commands/AI.py](commands/AI.py) - Discord AI 命令處理

---

## ✅ 測試清單

完成以下測試以確認系統正常：

- [ ] 讀取 bot.py（測試基本讀取）
- [ ] 讀取 commands/AI.py（測試子目錄）
- [ ] 查詢 Git 狀態（測試狀態查詢）
- [ ] 嘗試讀取 README.md（應被拒絕）
- [ ] 嘗試讀取 ../../../etc/passwd（應被拒絕）
- [ ] 非管理員使用（應被拒絕）
- [ ] 提交無效語法（應被拒絕）
- [ ] 提交有效改動（應成功）

---

## 🎯 下一步

1. 部署到 GCP
2. 通過 Discord 進行測試
3. 監控工具執行結果
4. 根據反饋調整工具參數
