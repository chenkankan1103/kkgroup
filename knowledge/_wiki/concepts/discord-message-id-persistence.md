# Discord 訊息 ID 持久化實踐

## 概述

在 KKGroup 專案中，為了解決 Bot 重啟後失去 Discord 訊息引用的問題，我們建立了統一的訊息 ID 持久化機制。

## 統一做法

### 1. 使用 `.env` 檔案持久化

所有需要跨重啟保存的訊息 ID 都應該儲存在 `.env` 檔案中：

```env
ANNOUNCEMENT_MESSAGE_ID=123456789012345678
LOGMONITOR_MESSAGE_ID=987654321098765432
```

### 2. 命名慣例

遵循 `{MODULE}_MESSAGE_ID` 格式：
- `ANNOUNCEMENT_MESSAGE_ID` - 公告系統
- `LOGMONITOR_MESSAGE_ID` - 日誌監控系統
- `STOCK_MESSAGE_ID` - 股票系統（範例）

### 3. 實作模式

#### 基本實作（推薦）

```python
import os
from dotenv import load_dotenv

load_dotenv()

def _save_message_state(message_id: int):
    """保存訊息 ID 到 .env 檔案"""
    try:
        env_file = os.path.join(parent_dir, ".env")

        # 讀取現有 .env 內容
        lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        # 移除舊的行
        lines = [line for line in lines if not line.strip().startswith('MODULE_MESSAGE_ID=')]

        # 添加新的 message ID
        lines.append(f"MODULE_MESSAGE_ID={message_id}\n")

        # 寫回檔案
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        logger.info(f"已保存訊息 ID 到 .env: {message_id}")
    except Exception as e:
        logger.error(f"保存訊息 ID 到 .env 失敗: {e}")

def _load_message_state() -> Optional[int]:
    """從 .env 載入訊息 ID"""
    try:
        message_id = os.getenv("MODULE_MESSAGE_ID")
        if message_id:
            return int(message_id)
        return None
    except Exception as e:
        logger.error(f"從 .env 載入訊息 ID 失敗: {e}")
        return None
```

#### 進階實作（announcement.py 模式）

```python
def _save_and_verify_message_id(self, message_id: int) -> bool:
    """加強版的保存和驗證方法"""
    max_retries = 3

    for attempt in range(max_retries):
        # 保存到 .env
        self._write_message_id_to_env(message_id)
        time.sleep(0.3 if attempt < 2 else 0.5)

        # 驗證
        verify_id = self._read_message_id_from_env()
        if verify_id == message_id:
            logger.info(f"驗證成功 - MESSAGE_ID 已確認保存: {message_id}")
            return True

    # 環境變數備用
    os.environ['MODULE_MESSAGE_ID'] = str(message_id)
    return False
```

### 4. 啟動時恢復機制

```python
async def _restore_message_reference(self):
    """嘗試恢復舊訊息的引用"""
    message_id = _load_message_state()
    if not message_id:
        return

    try:
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(CHANNEL_ID)

        if not channel:
            logger.warning(f"找不到通知頻道 {CHANNEL_ID}")
            return

        # 嘗試獲取舊訊息
        message = await channel.fetch_message(message_id)
        self._summary_message = message
        logger.info(f"✅ 成功恢復舊訊息引用: {message_id}")

    except discord.NotFound:
        logger.info(f"舊訊息 {message_id} 已被刪除，將創建新訊息")
        _clear_message_state()
    except discord.Forbidden:
        logger.warning(f"沒有權限存取訊息 {message_id}")
        _clear_message_state()
```

## 專案實際案例

### 1. announcement.py - 公告系統
- **檔案**: `cogs/common/announcement.py`
- **變數**: `ANNOUNCEMENT_MESSAGE_ID`
- **特色**: 多次驗證、環境變數備用、完整錯誤處理

### 2. log_monitor.py - 日誌監控系統
- **檔案**: `cogs/common/log_monitor.py`
- **變數**: `LOGMONITOR_MESSAGE_ID`
- **特色**: 基本實作、啟動恢復、錯誤處理

### 3. merchant/views.py - 拉霸機系統
- **檔案**: `cogs/shop/merchant/views.py`
- **方式**: 記憶體內 `original_message` 屬性
- **適用**: 短期會話，不需要跨重啟持久化

## 使用時機

### ✅ 需要持久化的情況
- 系統通知（日誌監控、公告）
- 長期運行的互動介面
- Bot 重啟後需要繼續編輯的訊息

### ❌ 不需要持久化的情況
- 短期互動（拉霸機、個人對話）
- 臨時訊息
- 用戶特定的 ephemeral 訊息

## 最佳實踐

1. **統一命名**: 使用 `{MODULE}_MESSAGE_ID` 格式
2. **錯誤處理**: 包含完整的異常處理
3. **驗證機制**: 保存後驗證是否成功
4. **備用方案**: 環境變數作為最後備用
5. **清理機制**: 提供清除功能
6. **日誌記錄**: 詳細的日誌用於除錯

## 注意事項

- `.env` 檔案已在 `.gitignore` 中，不會被提交
- 環境變數在 Bot 重啟後會丟失，只能作為臨時備用
- 訊息被刪除時要及時清除對應的 ID
- 頻道 ID 變更時需要清除舊的訊息 ID

## 相關文檔

- [SECURITY_GUIDE_TW.md](../sources/SECURITY_GUIDE_TW.md) - 安全最佳實踐
- [discord-silent-messages.md](discord-silent-messages.md) - Discord 訊息機制
- [Discord Bot 系統詳解](discord-bot-system.md) - Bot 與訊息模組分工
- [KK 園區系統地圖](kk-park-system-map.md) - 總覽入口
