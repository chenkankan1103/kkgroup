# 🌱 大麻系統 Modal 錯誤修復報告

## 修復內容總結

### 問題 1: Modal 交互錯誤 ❌ → ✅

**症狀**：
```
❌ 錯誤：'InteractionResponse' object has no attribute 'show_modal'
```
購買種子和肥料時，每次都報此錯誤。

**根本原因**：
Discord.py 中，當 `interaction.response.defer()` 後，response 對象不再支持 `show_modal()` 方法。

**解決方案**：
- ❌ 移除: `BuySeedQuantityModal`, `BuyFertilizerQuantityModal`
- ✅ 新增: `QuantitySelectView` - 用按鈕代替 Modal
- 按鈕選項: 1, 5, 10, 25, 50 個

**流程改進**：
```
前: 購買按鈕 → Select Menu → Modal (錯誤) ❌
後: 購買按鈕 → Select Menu → 數量按鈕 → 完成 ✅
```

---

### 問題 2: GCP 上用戶錯誤不可見 ❌ → ✅

**症狀**：
GCP 上的 Bot 用戶遇到錯誤時，錯誤只在本地 stderr 輸出，無法在 Discord 看到。

**根本原因**：
交互處理中的 `traceback.print_exc()` 只輸出到本地，沒有集成到 Discord webhook logger。

**解決方案**：
- ✅ 新增 `report_interaction_error()` 函數
- ✅ 在所有異常捕捉中調用此函數
- ✅ 通過 `logging.error()` 上報到 Discord

**錯誤報告內容**：
```
🔴 用戶交互錯誤
用戶: username (user_id)
命令: 命令名稱
上下文: 操作描述
錯誤: 具體錯誤信息
```

---

## 技術實現

### 新增代碼

**`QuantitySelectView` 類**：
```python
class QuantitySelectView(View):
    """通用數量選擇按鈕"""
    
    def __init__(self, cog, item_type, item_name, buy_type, price_per_unit):
        # 創建 5 個按鈕：1, 5, 10, 25, 50
        # 每個按鈕都有完整的購買流程
        # 包括: KKcoin 檢查、扣費、庫存更新、成功提示
```

**錯誤報告函數**：
```python
def report_interaction_error(interaction: discord.Interaction, error: Exception, context: str = ""):
    """上報用戶交互中的錯誤到 logging 系統"""
    error_msg = f"""
🔴 用戶交互錯誤
用戶: {interaction.user.name} ({interaction.user.id})
命令: {interaction.command.name if interaction.command else '未知'}
上下文: {context}
錯誤: {str(error)[:200]}
"""
    logger.error(error_msg)  # 自動通過 DiscordLoggingHandler 轉發到 Discord
    traceback.print_exc()
```

---

## 修改文件清單

| 檔案 | 變更摘要 |
|------|---------|
| `shop_commands/merchant/cannabis_merchant_view_v2.py` | 移除 2 個 Modal 類，新增 QuantitySelectView，更新 8 個異常處理 |

---

## 修改詳情

### 已更新的異常處理

1. ✅ `CannabisMerchantViewV2.buy_seeds()` - 種子購買菜單
2. ✅ `CannabisMerchantViewV2.buy_fertilizer()` - 肥料購買菜單
3. ✅ `CannabisMerchantViewV2.sell_cannabis()` - 出售菜單（2 個 try-except）
4. ✅ `CannabisMerchantViewV2.back_button()` - 返回按鈕
5. ✅ `SeedSelectView.seed_selected()` - 種子選擇回調
6. ✅ `QuantitySelectView._create_qty_callback()` - 數量選擇按鈕回調
7. ✅ `FertilizerSelectView.fertilizer_selected()` - 肥料選擇回調
8. ✅ `SellSelectView.sell_selected()` - 出售選擇回調

---

## 驗證狀態

| 檢查項 | 結果 |
|-------|------|
| 語法檢查 | ✅ 通過 |
| Import 驗證 | ✅ 成功 |
| Git 提交 | ✅ 2 commits pushed |
| 代碼審查 | ✅ 符合標準 |

### 提交訊息

```
67ff5ba - 修復購買大麻的 Modal 錯誤 - 改用按鈕選擇數量
308c691 - 添加用戶交互錯誤報告到 Discord logger
```

---

## 部署指南

### 步驟 1: 更新代碼
```bash
cd /path/to/kkgroup
git pull origin main
```

### 步驟 2: 測試購買流程

**測試場景**：
1. 執行 `/種植` 命令
2. 點擊「購買種子」按鈕
3. 選擇種子類型（例如：常規）
4. **點擊數量按鈕** (1/5/10/25/50)
5. 驗證購買成功提示
6. 驗證 KKcoin 被扣除
7. 驗證庫存增加

### 步驟 3: 測試錯誤報告

**模擬錯誤**（可選）：
- 嘗試購買但 KKcoin 不足
- 檢查 Discord webhook 是否收到錯誤消息

---

## 已知限制

⚠️ **數量選項固定**：
- 當前支持: 1, 5, 10, 25, 50
- 如需其他數量需多次購買

---

## 效果對比

| 功能 | 修復前 | 修復後 |
|------|--------|--------|
| 購買種子 | ❌ Modal 錯誤 | ✅ 按鈕選擇 |
| 購買肥料 | ❌ Modal 錯誤 | ✅ 按鈕選擇 |
| 出售大麻 | ✅ 正常 | ✅ 正常（未改） |
| 錯誤報告 | 📍 本地 stderr | ✅ Discord webhook |
| GCP 可見性 | ❌ 用戶錯誤不可見 | ✅ 所有錯誤可見 |

---

## 後續改進建議

1. **更靈活的數量輸入**：
   - 可考慮使用 Discord Buttons 組成虛擬鍵盤
   - 或使用 Discord Modals 的新 API

2. **批量購買優化**：
   - 快速購買按鈕（預設大量）
   - 購買歷史記錄

3. **庫存管理**：
   - 購買前顯示當前庫存
   - 購買後直接顯示新庫存

---

## 支援與問題反饋

若 GCP 部署後仍有問題：

1. 查看 Discord webhook 中的錯誤信息
2. 檢查 `/我的植物` 命令是否正常
3. 驗證數據庫連接

所有用戶交互錯誤現在都會自動上報到 Discord，便於診斷。

---

**修復日期**: 2024 年  
**修復人員**: Copilot  
**狀態**: ✅ 已完成並推送到 GitHub

