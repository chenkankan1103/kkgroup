param(
    [string]$Instance = "e193752468@instance-20250501-142333",
    [string]$Zone = "us-central1-a",
    [string]$LocalPath = "C:\Users\88697\Desktop\kkgroup\knowledge",
    [string]$RemotePath = "/home/e193752468/kkgroup/"
)

if (-not (Test-Path $LocalPath)) {
    Write-Error "找不到本機 knowledge 目錄: $LocalPath"
    exit 1
}

Write-Host "同步 knowledge 到 $Instance ..."
gcloud compute scp --recurse --zone $Zone --tunnel-through-iap $LocalPath "${Instance}:$RemotePath"

if ($LASTEXITCODE -ne 0) {
    Write-Error "同步失敗"
    exit $LASTEXITCODE
}

Write-Host "同步完成: $LocalPath -> ${Instance}:$RemotePath"
