param(
    [ValidateSet('tunnel', 'nginx', 'bot', 'all')]
    [string]$type = 'all'
)

$GCP_INSTANCE = "e193752468@instance-20250501-142333"
$GCP_ZONE = "us-central1-c"

function Get-TunnelLogs {
    Write-Host "`n=== GCP: Tunnel Logs (Last 30 lines) ===" -ForegroundColor Cyan
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo journalctl -u cloudflared.service -n 30 --no-pager 2>&1' | Select-Object -Last 20
    
    Write-Host "`n=== GCP: Current Tunnel URL ===" -ForegroundColor Green
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo journalctl -u cloudflared.service -S "10 minutes ago" --no-pager | grep -o "https://[a-zA-Z0-9-]*\.trycloudflare\.com" | sort -u | tail -1' 2>&1
}

function Get-NginxLogs {
    Write-Host "`n=== GCP: Nginx Access Log (Last 15 entries) ===" -ForegroundColor Cyan
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo tail -15 /var/log/nginx/access.log' 2>&1
    
    Write-Host "`n=== GCP: Nginx Error Log ===" -ForegroundColor Cyan
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo tail -10 /var/log/nginx/error.log' 2>&1
    
    Write-Host "`n=== GCP: Nginx Status ===" -ForegroundColor Green
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo systemctl is-active nginx' 2>&1
}

function Get-BotLogs {
    Write-Host "`n=== GCP: Bot Service Log (Last 50 - Errors/Warnings) ===" -ForegroundColor Cyan
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo journalctl -u bot.service -n 50 --no-pager 2>&1 | grep -iE "error|fail|warning|critical|tunnel|url"' 2>&1
    
    Write-Host "`n=== GCP: Bot Service Status ===" -ForegroundColor Green
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo systemctl is-active bot.service' 2>&1
}

function Get-ConnectivityTest {
    Write-Host "`n=== GCP: Connectivity Tests ===" -ForegroundColor Cyan
    
    Write-Host "`n  [1] Local Nginx Test (Internal IP):" -ForegroundColor Yellow
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'curl -I http://10.128.0.3/assets/leaderboard.png 2>&1 | head -3' 2>&1
    
    Write-Host "`n  [2] Tunnel Process Check:" -ForegroundColor Yellow
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'pgrep -a cloudflared' 2>&1
    
    Write-Host "`n  [3] Tunnel Connection Status:" -ForegroundColor Yellow
    gcloud -q compute ssh $GCP_INSTANCE --zone=$GCP_ZONE --tunnel-through-iap --command `
        'sudo journalctl -u cloudflared.service -n 5 --no-pager 2>&1 | grep -iE "registered|connection"' 2>&1
}

Write-Host "`n========================================" -ForegroundColor Magenta
Write-Host "KKGroup Debug Logs Monitor Tool" -ForegroundColor Magenta
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Gray
Write-Host "========================================`n" -ForegroundColor Magenta

switch ($type) {
    'tunnel' { Get-TunnelLogs; Get-ConnectivityTest }
    'nginx'  { Get-NginxLogs }
    'bot'    { Get-BotLogs }
    'all'    { Get-TunnelLogs; Get-NginxLogs; Get-BotLogs; Get-ConnectivityTest }
}

Write-Host "`n✓ Logs check completed!" -ForegroundColor Green
