# KKGroup BOT 系統監控腳本
# 監控 BOT 服務狀態和系統資源
# 版本: 1.0
# 日期: 2026-02-08

Write-Host "🔍 KKGroup BOT 系統監控" -ForegroundColor Cyan
Write-Host "============================" -ForegroundColor Cyan
Write-Host ""

$INSTANCE_NAME = "instance-20250501-142333"
$ZONE = "us-central1-c"

try {
    Write-Host "📊 檢查 GCP 實例狀態..." -ForegroundColor Yellow
    $instanceStatus = gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format="value(status)"
    Write-Host "實例狀態: $instanceStatus" -ForegroundColor $(if ($instanceStatus -eq "RUNNING") { "Green" } else { "Red" })
    Write-Host ""

    if ($instanceStatus -eq "RUNNING") {
        Write-Host "🤖 檢查 BOT 服務狀態..." -ForegroundColor Yellow

        # 使用原生 SSH 檢查服務狀態
        $serviceCheck = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 instance-20250501-142333.us-central1-c.kkgroup @"
systemctl is-active bot.service shopbot.service uibot.service 2>/dev/null || echo "systemd_unavailable"
"@

        if ($serviceCheck -match "systemd_unavailable") {
            Write-Host "❌ 無法檢查服務狀態 (systemd 不可用)" -ForegroundColor Red
        } else {
            $services = $serviceCheck -split "`n"
            $serviceNames = @("bot.service", "shopbot.service", "uibot.service")

            for ($i = 0; $i -lt $services.Length; $i++) {
                $status = $services[$i]
                $name = $serviceNames[$i]
                $color = if ($status -eq "active") { "Green" } else { "Red" }
                Write-Host "  $name : $status" -ForegroundColor $color
            }
        }

        Write-Host ""
        Write-Host "💾 檢查系統資源..." -ForegroundColor Yellow

        $systemInfo = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 instance-20250501-142333.us-central1-c.kkgroup @"
echo "Memory: \$(free -h | grep '^Mem:' | awk '{print \$3 \"/\" \$2}')"
echo "Swap: \$(free -h | grep '^Swap:' | awk '{print \$3 \"/\" \$2}')"
echo "Load: \$(uptime | awk -F'load average:' '{print \$2}' | sed 's/^ *//')"
"@

        Write-Host "系統資訊:" -ForegroundColor Gray
        Write-Host $systemInfo -ForegroundColor White

        Write-Host ""
        Write-Host "🔗 測試 SSH 連線穩定性..." -ForegroundColor Yellow

        $startTime = Get-Date
        $testResult = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 instance-20250501-142333.us-central1-c.kkgroup "echo 'SSH 連線測試成功 - \$(date +%H:%M:%S)'"
        $endTime = Get-Date
        $duration = [math]::Round(($endTime - $startTime).TotalMilliseconds)

        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ SSH 連線正常 (響應時間: ${duration}ms)" -ForegroundColor Green
            Write-Host "回應: $testResult" -ForegroundColor Gray
        } else {
            Write-Host "❌ SSH 連線失敗" -ForegroundColor Red
        }
    }

} catch {
    Write-Host "❌ 監控過程中發生錯誤: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "📋 監控摘要:" -ForegroundColor Cyan
Write-Host "  • 實例狀態: $(if ($instanceStatus -eq 'RUNNING') { '✅ 運行中' } else { '❌ 停止' })" -ForegroundColor $(if ($instanceStatus -eq "RUNNING") { "Green" } else { "Red" })
Write-Host "  • SSH 連線: $(if ($LASTEXITCODE -eq 0) { '✅ 正常' } else { '❌ 異常' })" -ForegroundColor $(if ($LASTEXITCODE -eq 0) { "Green" } else { "Red" })
Write-Host "  • 檢查時間: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray

Write-Host ""
Read-Host "按 Enter 鍵繼續"