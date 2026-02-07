# 🚀 KK幣排行榜 V2 升級 - 完整總結

## 📋 更新內容

### ✅ 已完成的改進

#### 1️⃣ **增強版排行榜** (`create_enhanced_leaderboard_image`)
- ✓ **前 15 名**（改為 15 名而非 20 名）
- ✓ **前 3 名特殊底色**（金/銀/銅半透明背景）
- ✓ **排名編號加邊框**（避免被長條覆蓋）
- ✓ **KK幣數加邊框**（右側突出顯示）
- ✓ **排名獎牌 Emoji**（🥇🥈🥉）

#### 2️⃣ **長條圖** (`create_bar_chart_image`)
- ✓ 金/銀/銅顏色分級（前3名）
- ✓ 紅色（4-10名）
- ✓ 藍色（11-15名）
- ✓ 數值框（bbox 邊框，防被遮蔽）
- ✓ 網格線和旋轉軸標籤

#### 3️⃣ **饼圖 + 周統計** (`create_pie_and_weekly_image`)
- ✓ 左上：饼圖（百分比分布）
- ✓ 右上：上週 vs 本週對比
- ✓ 增長率計算和顏色提示
- ✓ 下方：4個指標卡片
  - 💰 金庫總額
  - 📈 本週新增
  - 👥 參與成員
  - 📊 平均值

#### 4️⃣ **matplotlib 修復**
- ✓ 添加 `MATPLOTLIB_AVAILABLE` 檢查
- ✓ 前置檢查避免在生成時才發現錯誤
- ✓ 錯誤信息明確指出需要執行 `pip install matplotlib numpy`
- ✓ 每個文件頭部打印狀態 `✅ matplotlib 已正確載入`

### 🆕 新命令

```
/kkcoin_v2
```

**功能**：一次顯示 3 張圖
1. 排行榜（前15名，特殊設計）
2. 長條圖
3. 饼圖 + 周統計

---

## 📊 代碼文件

### 新建文件

**`commands/kkcoin_visualizer_v2.py`** (755 行)
- 改進的排行榜視覺化函數
- 3 個獨立的圖表生成函數
- matplotlib 可用性檢查

### 修改文件

**`commands/kcoin.py`** (+60 行)
- 新增 `kkcoin_v2` SlashCommand
- 處理 3 張圖的生成和上傳
- 完整的錯誤處理

---

## 🔍 問題診斷 & 解決方案

### ❌ 原始問題
```
生成排行榜時發生錯誤：matplotlib 未安裝，無法生成圖表。
```

### ✅ 根本原因
- matplotlib 導入缺少 `Agg` 後端設置
- 依賴在 `import matplotlib.pyplot` 前需設置後端
- 虛擬環境中 matplotlib 未正確安裝或配置

### 🔧 解決方案

**在 GCP 上執行**：
```bash
cd /home/e193752468/kkgroup
source venv/bin/activate
pip install --upgrade matplotlib numpy

# 驗證安裝
python3 -c "import matplotlib; print(matplotlib.__version__)"
```

**在本地 Windows 執行**（如需重新安裝）：
```powershell
cd C:\Users\88697\Desktop\kkgroup
.venv\Scripts\pip install --force-reinstall matplotlib numpy
```

---

## 📱 使用方式

### 在 Discord 中

```
/kkcoin_v2
```

### 預期結果

Bot 將發送 3 張組合圖片：
1. **leaderboard.png** - 排行榜（前15名）
2. **bar_chart.png** - 長條圖
3. **pie_weekly.png** - 饼圖 + 周統計

---

## 🎯 設計亮點 vs 原始圖片對比

| 特性 | 原圖 | V2 版本 |
|------|------|---------|
| 排名數量 | 20名 | **15名** ✨ |
| 前3名樣式 | 無特殊標記 | **金/銀/銅半透明底色** ✨ |
| 排名數字 | 普通 | **邊框框選** ✨ |
| KK幣數字 | 普通 | **邊框框選** ✨ |
| 圖表數量 | 1 或 2 張 | **3 張組合** ✨ |
| 周統計 | 單獨顯示 | **整合在饼圖下方** ✨ |
| 指標卡片 | 基礎 | **4個彩色卡片** ✨ |

---

## 🧪 測試步驟

### 本地測試

1. **確認 matplotlib 已安裝**
   ```powershell
   python -c "import matplotlib; print('✓ OK')"
   ```

2. **測試導入新模組**
   ```powershell
   ssh gcp-kkgroup "python3 -c 'from commands.kkcoin_visualizer_v2 import MATPLOTLIB_AVAILABLE; print(f\"matplotlib: {MATPLOTLIB_AVAILABLE}\")'\\h"
   ```

### Discord 測試

在任何頻道執行：
```
/kkcoin_v2
```

### GCP 日誌監控

```powershell
ssh gcp-kkgroup "tail -f /tmp/bot.log | grep -i 'kkcoin\|matplotlib'"
```

---

## 📝 下一步行動

### 立即可做的事

1. ✅ **手動同步文件** (如自動上傳失敗)
   ```powershell
   ssh gcp-kkgroup "mkdir -p /home/e193752468/kkgroup/commands"
   # 然後手動 SCP 上傳：
   # scp kkcoin_visualizer_v2.py ...
   ```

2. ✅ **重啟 Bot 應用 新代碼**
   ```bash
   ssh gcp-kkgroup "sudo systemctl restart bot"
   ```

3. ✅ **在 Discord 測試新命令**
   ```
   /kkcoin_v2
   ```

### 如果遇到 matplotlib 問題

```bash
# GCP 上執行
source /home/e193752468/kkgroup/venv/bin/activate
pip install --upgrade matplotlib numpy --force-reinstall

# 驗證
python3 << 'EOF'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
print("✅ Matplotlib 已正確配置")
print(f"Version: {matplotlib.__version__}")
EOF
```

---

## 🐛 已知問題 & 解決方案

| 問題 | 症狀 | 解決方案 |
|------|------|---------|
| matplotlib 未安裝 | `ModuleNotFoundError` | `pip install matplotlib numpy` |
| 後端未設置 | TypeError in `savefig()` | 確認代碼中有 `matplotlib.use('Agg')` |
| 虛擬環境問題 | 找不到模組 | 確認使用 `source venv/bin/activate` |
| 權限問題 | Permission denied | 確認 e193752468 擁有 kkgroup 目錄 |
| 字體缺失 | 方框亂碼 | 檢查 `fonts/NotoSansCJKtc-Regular.otf` 是否存在 |

---

## 📞 快速援助

**如果 /kkcoin_v2 無法使用**：

1. 檢查文件是否上傳
   ```bash
   ssh gcp-kkgroup "ls -la /home/e193752468/kkgroup/commands/kkcoin_visualizer_v2.py"
   ```

2. 檢查 matplotlib 狀態
   ```bash
   ssh gcp-kkgroup "python3 -c 'import matplotlib; print(\"✓\")'\\h"
   ```

3. 查看 Bot 錯誤日誌
   ```bash
   ssh gcp-kkgroup "tail -50 /tmp/bot.log"
   ```

4. 重新啟動 Bot
   ```bash
   ssh gcp-kkgroup "sudo systemctl restart bot"
   ```

---

**更新日期**: 2026/2/7
**版本**: KKCoin V2
**作者**: GitHub Copilot
**狀態**: ✅ 生產就緒（待測試）
