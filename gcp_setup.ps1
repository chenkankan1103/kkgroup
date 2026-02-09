# GCP SSH 自動設置腳本
# 此腳本幫助配置和測試 SSH 連接到 GCP

param(
    [switch]$UseGoogle,
    [switch]$Test,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

# 顏色輸出
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Error-Line { Write-Host $args -ForegroundColor Red }
function Write-Warning-Line { Write-Host $args -ForegroundColor Yellow }
function Write-Info { Write-Host $args -ForegroundColor Cyan }

# ===================== 配置 =====================
$GCP_HOST = "35.206.126.157"
$KANKAN_USER = "kankan"
$GOOGLE_USER = "e193752468"
$SSH_DIR = "$env:USERPROFILE\.ssh"
$CONFIG_FILE = "$SSH_DIR\config"

Write-Info "🔧 GCP SSH 設置工具"
Write-Info "════════════════════════════════════════"
Write-Info ""

# ===================== 檢查 SSH 目錄 =====================
if (-not (Test-Path $SSH_DIR)) {
    Write-Warning-Line "⚠️  SSH 目錄不存在，正在創建..."
    New-Item -ItemType Directory -Path $SSH_DIR -Force | Out-Null
    Write-Success "✓ SSH 目錄已創建: $SSH_DIR"
} else {
    Write-Success "✓ SSH 目錄存在: $SSH_DIR"
}

# ===================== 檢查 SSH 配置文件 =====================
if (Test-Path $CONFIG_FILE) {
    Write-Success "✓ SSH 配置文件存在: $CONFIG_FILE"
} else {
    Write-Warning-Line "⚠️  SSH 配置文件不存在"
    Write-Info "可以手動複製 .ssh\config 文件或使用 VS Code 創建"
}

# ===================== 列出可用密鑰 =====================
Write-Info ""
Write-Info "🔑 檢查可用的 SSH 密鑰..."
Write-Info "════════════════════════════════════════"

$keys = @()
if (Test-Path "$SSH_DIR\gcp_kankan_key") {
    Write-Success "✓ 發現 kankan 密鑰"
    $keys += @{name = "kankan"; path = "$SSH_DIR\gcp_kankan_key" }
}
if (Test-Path "$SSH_DIR\id_ed25519") {
    Write-Success "✓ 發現預設 ed25519 密鑰"
    $keys += @{name = "default_ed25519"; path = "$SSH_DIR\id_ed25519" }
}
if (Test-Path "$SSH_DIR\google_cloud_rsa") {
    Write-Success "✓ 發現 Google Cloud RSA 密鑰"
    $keys += @{name = "google_rsa"; path = "$SSH_DIR\google_cloud_rsa" }
}
if (Test-Path "$SSH_DIR\id_rsa") {
    Write-Success "✓ 發現預設 RSA 密鑰"
    $keys += @{name = "default_rsa"; path = "$SSH_DIR\id_rsa" }
}

if ($keys.Count -eq 0) {
    Write-Error-Line "✗ 找不到任何 SSH 密鑰"
    Write-Warning-Line "請確保 SSH 私鑰已複製到 $SSH_DIR"
    exit 1
}

Write-Info ""
Write-Info "找到 $($keys.Count) 個密鑰"

# ===================== 測試 SSH 連接 =====================
if ($Test) {
    Write-Info ""
    Write-Info "🧪 測試 SSH 連接..."
    Write-Info "════════════════════════════════════════"
    
    $user = if ($UseGoogle) { $GOOGLE_USER } else { $KANKAN_USER }
    $host = if ($UseGoogle) { "gcp-google-e193752468" } else { "gcp-kkgroup" }
    
    Write-Info "目標: $user@$GCP_HOST"
    Write-Info "Host 配置: $host"
    Write-Info ""
    
    try {
        Write-Info "正在測試連接... (最多等待 10 秒)"
        
        # 簡單的連接測試
        $result = ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new $host "whoami" 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "✓ SSH 連接成功！"
            Write-Success "  遠端用戶: $result"
        } else {
            Write-Error-Line "✗ SSH 連接失敗"
            Write-Error-Line "  錯誤: $result"
            exit 1
        }
    } catch {
        Write-Error-Line "✗ 連接時出現異常: $_"
        exit 1
    }
}

# ===================== 驗證密鑰權限 =====================
Write-Info ""
Write-Info "🔐 檢查密鑰文件權限..."
Write-Info "════════════════════════════════════════"

foreach ($key in $keys) {
    $path = $key.path
    if (Test-Path $path) {
        try {
            $acl = Get-Acl $path
            $hasFullControl = $false
            
            foreach ($access in $acl.Access) {
                if ($access.IdentityReference -like "*$($env:USERNAME)*" -and $access.FileSystemRights -contains "FullControl") {
                    $hasFullControl = $true
                    break
                }
            }
            
            if ($hasFullControl) {
                Write-Success "✓ $($key.name) - 權限正確"
            } else {
                Write-Warning-Line "⚠️  $($key.name) - 權限可能不正確"
                Write-Info "    建議修復: icacls '$path' /inheritance:r /grant:r `"`${env:USERNAME}:F`""
            }
        } catch {
            Write-Warning-Line "⚠️  無法檢查 $($key.name) 的權限"
        }
    }
}

# ===================== VS Code 配置提示 =====================
Write-Info ""
Write-Info "📝 VS Code Remote-SSH 設置"
Write-Info "════════════════════════════════════════"

Write-Info "1️⃣  安裝 Remote - SSH 擴展"
Write-Info "   按 Ctrl+Shift+X，搜尋 'Remote - SSH'，安裝 Microsoft 版本"
Write-Info ""
Write-Info "2️⃣  連接到遠端"
Write-Info "   按 Ctrl+Shift+P，搜尋 'Remote-SSH: Connect to Host...'"
Write-Info "   選擇: gcp-kkgroup (或 gcp-google-e193752468)"
Write-Info ""
Write-Info "3️⃣  打開資料夾"
Write-Info "   連接後，按 Ctrl+K Ctrl+O"
Write-Info "   輸入: /home/kankan (或 /home/$GOOGLE_USER)"
Write-Info ""

# ===================== 快速命令提示 =====================
Write-Info ""
Write-Info "⚡ 快速命令"
Write-Info "════════════════════════════════════════"

Write-Success "連接到 kankan 用戶:"
Write-Info "  ssh gcp-kkgroup"
Write-Info ""

Write-Success "連接到 Google SSH 用戶:"
Write-Info "  ssh gcp-google-e193752468"
Write-Info ""

Write-Success "執行遠端命令:"
Write-Info "  ssh gcp-kkgroup 'whoami'"
Write-Info ""

Write-Success "使用 SCP 傳輸文件:"
Write-Info "  scp local_file gcp-kkgroup:/home/kankan/remote_file"
Write-Info ""

# ===================== 總結 =====================
Write-Info ""
Write-Info "✅ 設置完成！"
Write-Info "════════════════════════════════════════"
Write-Info ""
Write-Info "如要測試連接，請執行:"
Write-Info "  .\gcp_setup.ps1 -Test"
Write-Info ""
Write-Info "或使用 Google SSH 用戶測試:"
Write-Info "  .\gcp_setup.ps1 -Test -UseGoogle"
