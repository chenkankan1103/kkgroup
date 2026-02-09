# KKGroup BOT 系統快速檢查
# 版本: 1.0

Write-Host "🔍 快速系統檢查" -ForegroundColor Cyan
Write-Host "==================" -ForegroundColor Cyan

try {
    # 檢查實例狀態
    $status = gcloud compute instances describe instance-20250501-142333 --zone=us-central1-c --format="value(status)"
    Write-Host "實例狀態: $status" -ForegroundColor $(if ($status -eq "RUNNING") { "Green" } else { "Red" })

    if ($status -eq "RUNNING") {
        # 檢查服務狀態
        $services = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 instance-20250501-142333.us-central1-c.kkgroup "systemctl is-active bot.service shopbot.service uibot.service"
        $serviceArray = $services -split "`n"
        $names = @("bot", "shopbot", "uibot")

        for ($i = 0; $i -lt $serviceArray.Length; $i++) {
            $color = if ($serviceArray[$i] -eq "active") { "Green" } else { "Red" }
            Write-Host "$($names[$i]): $($serviceArray[$i])" -ForegroundColor $color
        }

        # 檢查記憶體
        $mem = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 instance-20250501-142333.us-central1-c.kkgroup "free -h | grep '^Mem:' | awk '{print \$3 \"/\" \$2}'"
        Write-Host "記憶體: $mem" -ForegroundColor White
    }

} catch {
    Write-Host "檢查失敗: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "按 Enter 繼續"