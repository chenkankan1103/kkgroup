param(
    [string]$VaultPath = "C:\Users\88697\Desktop\kkgroup\knowledge"
)

$obsidianPath = Join-Path $env:LOCALAPPDATA "Programs\Obsidian\Obsidian.exe"

if (-not (Test-Path $obsidianPath)) {
    Write-Error "找不到 Obsidian: $obsidianPath"
    exit 1
}

if (-not (Test-Path $VaultPath)) {
    Write-Error "找不到 knowledge vault: $VaultPath"
    exit 1
}

Start-Process -FilePath $obsidianPath -ArgumentList "`"$VaultPath`""
Write-Host "已開啟 Obsidian vault: $VaultPath"
