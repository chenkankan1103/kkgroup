# 設定環境變數強制使用 OpenSSH
$env:GCE_SSH_CLIENT = "ssh"

# KKGroup GCP SSH 連線函數
function Connect-GCP {
    param(
        [string]$InstanceName = "instance-20250501-142333",
        [string]$Zone = "us-central1-c",
        [string]$Username = "e193752468",
        [switch]$TestOnly
    )

    Write-Host "🔗 連線到 GCP 實例: $InstanceName" -ForegroundColor Cyan

    try {
        # 獲取實例 IP
        $ip = gcloud compute instances describe $InstanceName --zone=$Zone --format="value(networkInterfaces[0].accessConfigs[0].natIP)"
        Write-Host "📍 實例 IP: $ip" -ForegroundColor Green

        if ($TestOnly) {
            Write-Host "🧪 測試連線..." -ForegroundColor Yellow
            $result = & ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes $Username@$ip "echo 'SSH 測試成功 - \$(date)'" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ 連線測試成功!" -ForegroundColor Green
                return $true
            } else {
                Write-Host "❌ 連線測試失敗" -ForegroundColor Red
                Write-Host "錯誤詳情: $result" -ForegroundColor Red
                return $false
            }
        }

        Write-Host "🚀 啟動 SSH 連線..." -ForegroundColor Yellow
        Write-Host "💡 使用原生 OpenSSH (已設定 GCE_SSH_CLIENT=ssh)" -ForegroundColor Gray

        # 使用原生 SSH
        & ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 $Username@$ip

    } catch {
        Write-Host "❌ 錯誤: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# 匯出函數
Export-ModuleMember -Function Connect-GCP

Write-Host "✅ GCP SSH 模組已載入" -ForegroundColor Green
Write-Host "💡 使用方法:" -ForegroundColor Cyan
Write-Host "   Connect-GCP                    # 連線到預設實例" -ForegroundColor Gray
Write-Host "   Connect-GCP -TestOnly         # 僅測試連線" -ForegroundColor Gray
Write-Host "   Connect-GCP -InstanceName 'your-instance' # 指定實例" -ForegroundColor Gray