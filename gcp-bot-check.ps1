# 設定
$VM = "instance-20250501-142333"
$ZONE = "us-central1-c"

Write-Host ">>> 正在透過 IAP 隧道發送代理人指令至 $VM..." -ForegroundColor Cyan

# 這行指令會直接讓遠端 VM 吐出日誌回傳到你的 VS Code 畫面
gcloud compute ssh $VM `
    --zone $ZONE `
    --tunnel-through-iap `
    --command "sudo journalctl -u bot.service -n 50 --no-pager"

Write-Host ">>> 日誌讀取完畢，請全選上方內容貼給 Copilot 進行分析。" -ForegroundColor Yellow
