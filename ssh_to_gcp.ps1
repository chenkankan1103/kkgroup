# KKGroup GCP SSH 連線腳本 - PowerShell 版本
# 使用原生 OpenSSH 避免 plink TCP 衝突
# 版本: 1.0
# 日期: 2026-02-08

param(
    [switch]$TestConnection,
    [switch]$UpdateKeys
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "KKGroup GCP SSH 連線工具 (PowerShell)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 設定變數
$INSTANCE_NAME = "instance-20250501-142333"
$ZONE = "us-central1-c"
$USERNAME = "e193752468"

try {
    Write-Host "[1/3] 獲取實例外部 IP..." -ForegroundColor Yellow
    $GCP_IP = gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format="value(networkInterfaces[0].accessConfigs[0].natIP)"

    if (-not $GCP_IP) {
        throw "無法獲取 GCP 實例 IP"
    }

    Write-Host "實例 IP: $GCP_IP" -ForegroundColor Green
    Write-Host ""

    if ($UpdateKeys) {
        Write-Host "[2/3] 更新 SSH 金鑰..." -ForegroundColor Yellow
        gcloud compute config-ssh --ssh-key-file="$env:USERPROFILE\.ssh\google_compute_engine"
        Write-Host "SSH 金鑰已更新" -ForegroundColor Green
        Write-Host ""
    }

    if ($TestConnection) {
        Write-Host "[3/3] 測試連線..." -ForegroundColor Yellow
        $result = ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes $USERNAME@$GCP_IP "echo 'SSH 連線測試成功 - $(date)'" 2>&1

        if ($LASTEXITCODE -eq 0) {
            Write-Host "連線測試成功!" -ForegroundColor Green
            Write-Host "回應: $result" -ForegroundColor Gray
        } else {
            Write-Host "連線測試失敗" -ForegroundColor Red
            Write-Host "錯誤: $result" -ForegroundColor Red
        }
        return
    }

    Write-Host "[3/3] 連線到 GCP 實例..." -ForegroundColor Yellow
    Write-Host "使用原生 OpenSSH 連線 (避免 plink TCP 衝突)" -ForegroundColor Gray
    Write-Host "命令: ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 $USERNAME@$GCP_IP" -ForegroundColor Gray
    Write-Host ""

    # 使用原生 SSH 連線，避免 plink 參數解析問題
    ssh -o StrictHostKeyChecking=no -o ConnectTimeout=30 $USERNAME@$GCP_IP

} catch {
    Write-Host "錯誤: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "SSH 連線已結束。" -ForegroundColor Cyan