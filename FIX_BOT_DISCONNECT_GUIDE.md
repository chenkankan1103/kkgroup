# GCP BOT SSH 連接斷線 - 完整修復指南

## 🔴 問題根因

每次 SSH 連接時 BOT 斷線，原因：
1. **記憶體耗盡** (70%+) + SSH 連接消耗 → OOM Killer
2. **Systemd 配置缺陷** (ExecStartPost 語法錯誤)
3. **系統資源基線過低** (e2-micro 1GB)

---

## ✅ 修復步驟（按順序執行）

### **第一步：使用 Remote SSH 連接 GCP**

1. 按 `Ctrl+Shift+P` 開啟命令面板
2. 搜尋 "Remote-SSH: Connect to Host"
3. 選擇 `gcp-kkgroup`

---

### **第二步：添加 Swap 空間（最重要）**

在 Remote SSH 終端執行：

```bash
bash ~/fix_ssh_stability.sh
```

*如果文件不存在，執行：*
```bash
wget https://example.com/add_swap.sh  # 或手動上傳
bash ~/add_swap.sh
```

**預期結果：**
```
✓ 已添加 2G Swap
✓ 系統記憶體從 1GB 擴展至 ~3GB
```

---

### **第三步：修復 Systemd 配置**

在 Remote SSH 終端執行：

```bash
bash ~/fix_systemd_config.sh
```

**預期結果：**
```
✓ shopbot.service 已修復
✓ uibot.service 已修復
✓ 服務已自動重啟
```

---

### **第四步：驗證修復**

執行診斷腳本：

```bash
bash ~/diagnose_bot_disconnect.sh
```

檢查輸出：
- [ ] 沒有 OOM killer 事件
- [ ] 服務狀態：active
- [ ] 可用記憶體 > 500MB

---

### **第五步：測試 SSH 穩定性**

1. 保持 Remote SSH 連接打開
2. 在新終端執行：`ssh gcp-kkgroup "uptime"`
3. 上一步 Remote SSH 連接應該保持穩定
4. 重複執行 2-3 次，確認 BOT 沒有斷線

---

## 📊 預期改善

| 指標 | 修復前 | 修復後 |
|------|------|------|
| 可用記憶體 | 280MB | 1500MB+ |
| SSH 連接穩定性 | 50% | 95%+ |
| BOT 可靠性 | 斷線頻繁 | 穩定運行 |
| Swap 使用 | 0 | 10-20% (正常) |

---

## 🚨 如果問題持續

如果修復後仍有問題，執行追蹤診斷：

```bash
# 查看最近的 BOT 日誌
sudo journalctl -u bot.service -n 100 --no-pager

# 實時監控系統事件
sudo journalctl -f --since now
```

然後提供以下信息：
- `free -h` 的輸出
- `swapon -s` 的輸出
- `journalctl` 中的錯誤訊息

---

## 💡 長期建議

1. **升級 GCP 實例**
   - e2-micro → e2-small (2GB RAM, 費用 +$6/月)

2. **優化 BOT 記憶體**
   - 檢查是否有記憶體洩漏
   - 考慮分离 Flask API 到獨立實例

3. **實施監控告警**
   - 在記憶體 > 80% 時警告
   - 自動觸發清理訊務

---

## 📝 快速參考

**三個關鍵文件：**
```
/home/e193752468/kkgroup/add_swap.sh
/home/e193752468/kkgroup/fix_systemd_config.sh
/home/e193752468/kkgroup/diagnose_bot_disconnect.sh
/home/e193752468/kkgroup/fix_ssh_stability.sh
```

**三個關鍵命令：**
```bash
# 查看記憶體
free -h

# 查看 Swap
swapon -s

# 查看 BOT 狀態
systemctl status bot.service shopbot.service uibot.service
```

---

## ✍️ 執行記錄

在此記錄修復過程：

**時間：** _______________
**執行者：** _______________

- [ ] 添加 Swap 完成
- [ ] 修復 Systemd 完成
- [ ] 運行診斷完成
- [ ] 測試 SSH 完成
- [ ] 驗證 BOT 正常

**備註：** _______________________________

---

**最後一次修改：** 2026-02-08 
**作者：** GitHub Copilot
**版本：** 1.0
