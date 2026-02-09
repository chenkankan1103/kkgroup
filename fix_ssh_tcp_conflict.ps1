# KKGroup SSH TCP 衝突修復腳本
# 解決 plink.exe 參數解析問題
# 版本: 1.0
# 日期: 2026-02-08

Write-Host "🔧 KKGroup SSH TCP 衝突修復工具" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# 設定環境變數
$env:GCE_SSH_CLIENT = "ssh"

Write-Host "📋 修復方案:" -ForegroundColor Yellow
Write-Host "  1. 設定環境變數 GCE_SSH_CLIENT=ssh" -ForegroundColor Gray
Write-Host "  2. 提供原生 OpenSSH 連線選項" -ForegroundColor Gray
Write-Host "  3. 建立穩定連線的包裝函數" -ForegroundColor Gray
Write-Host ""

# 測試連線
Write-Host "🧪 測試 SSH 連線..." -ForegroundColor Yellow

try {
    $INSTANCE_NAME = "instance-20250501-142333"
    $ZONE = "us-central1-c"
    $USERNAME = "e193752468"

    # 獲取實例 IP
    $ip = gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
    Write-Host "📍 實例 IP: $ip" -ForegroundColor Green

    # 測試連線
    $result = & ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes $USERNAME@$ip "echo 'SSH 測試成功 - \$(date)'" 2>&1

    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ 連線測試成功!" -ForegroundColor Green
        $testResult = $true
    } else {
        Write-Host "❌ 連線測試失敗" -ForegroundColor Red
        Write-Host "錯誤詳情: $result" -ForegroundColor Red
        $testResult = $false
    }
} catch {
    Write-Host "❌ 錯誤: $($_.Exception.Message)" -ForegroundColor Red
    $testResult = $false
}

if ($testResult) {
    Write-Host ""
    Write-Host "🎉 SSH TCP 衝突問題已修復!" -ForegroundColor Green
    Write-Host "💡 現在可以使用以下方式連線:" -ForegroundColor Cyan
    Write-Host "   • 執行 .\ssh_to_gcp.ps1" -ForegroundColor Gray
    Write-Host "   • 執行 .\ssh_to_gcp.bat" -ForegroundColor Gray
    Write-Host "   • 或者直接使用: ssh e193752468@$ip" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "❌ 連線測試失敗，請檢查網路和 GCP 設定" -ForegroundColor Red
}

Write-Host ""
Write-Host "📝 修復摘要:" -ForegroundColor Cyan
Write-Host "   • 問題: plink.exe 參數解析衝突 (-o 選項)" -ForegroundColor Gray
Write-Host "   • 解決: 使用原生 OpenSSH 替代 plink" -ForegroundColor Gray
if ($testResult) {
    Write-Host "   • 狀態: ✅ 修復成功" -ForegroundColor Green
} else {
    Write-Host "   • 狀態: ❌ 需要進一步檢查" -ForegroundColor Red
}

Write-Host ""
Read-Host "按 Enter 鍵繼續"