# KKGroup SSH TCP 衝突修復完成
# 版本: 1.0
# 日期: 2026-02-08

✅ **修復狀態: 成功**

## 🔍 問題分析
- **根本原因**: gcloud 使用 plink.exe 0.81 版本，參數解析與預期的 `-o` 選項不兼容
- **表現**: `plink: unknown option "-o"` 錯誤，導致 SSH 連線不穩定
- **影響**: 在記憶體緊張時，多次連線重試會觸發 OOM killer

## 🛠️ 修復方案
1. **使用原生 OpenSSH**: 避免 plink 的參數解析問題
2. **正確的 SSH 金鑰配置**: 使用 gcloud compute config-ssh
3. **環境變數設定**: `$env:GCE_SSH_CLIENT = "ssh"`

## 🚀 使用方法

### 方法 1: 直接使用原生 SSH (推薦)
```bash
ssh instance-20250501-142333.us-central1-c.kkgroup
# 或者
ssh e193752468@35.206.126.157
```

### 方法 2: 使用批次檔案
```cmd
.\ssh_to_gcp.bat
```

### 方法 3: 使用 PowerShell 腳本
```powershell
.\ssh_to_gcp.ps1
```

## 📊 測試結果
- ✅ SSH 連線: 成功
- ✅ 記憶體使用: 710Mi/969Mi + 2GB swap
- ✅ TCP 衝突: 已解決
- ✅ BOT 服務: 全部正常運行

## 📝 檔案說明
- `ssh_to_gcp.bat` - Windows 批次連線腳本
- `ssh_to_gcp.ps1` - PowerShell 連線腳本
- `GCP-SSH-Module.psm1` - PowerShell 模組
- `fix_ssh_tcp_conflict_v2.ps1` - 修復驗證腳本

## 💡 建議
1. **優先使用原生 SSH** 避免 plink 相容性問題
2. **定期檢查記憶體使用** 確保系統穩定
3. **備份 SSH 金鑰** 防止意外遺失

---
**修復完成時間**: 2026-02-08 19:52
**測試狀態**: ✅ 通過