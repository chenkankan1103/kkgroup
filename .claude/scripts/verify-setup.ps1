<#
Setup verification for codex-claude-bridge
Run once after installation to verify everything works
#>

param()

$ErrorActionPreference = "Stop"

Write-Host " Verifying codex-claude-bridge setup..."

# 1. Check Codex CLI
Write-Host "`n1. Checking Codex CLI..."
try {
    $codexVersion = codex --version 2>&1
    Write-Host "    Codex CLI: $codexVersion"
} catch {
    Write-Error "    Codex CLI not installed. Run: npm i -g @openai/codex"
    exit 1
}

# 2. Check Codex auth (skip if using proxy)
Write-Host "`n2. Checking Codex auth..."
$authPath = "$env:USERPROFILE\.codex\auth.json"
if (Test-Path $authPath) {
    Write-Host "    Auth file exists: $authPath"
} else {
    Write-Host "    No auth file (using proxy or API key)"
}

# 3. Check Node/npx
Write-Host "`n3. Checking Node.js..."
$nodeVersion = node --version
Write-Host "    Node: $nodeVersion"

# 4. Test bridge call (dry run)
Write-Host "`n4. Testing bridge connection..."
try {
    $testResult = npx -y codex-claude-bridge@latest review_precommit -- '{"sessionId":"test-setup","context":"setup verification"}' 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    Bridge responded successfully"
    } else {
        Write-Warning "    Bridge returned non-zero (may be expected if no git changes): $testResult"
    }
} catch {
    Write-Error "    Bridge call failed: $_"
    exit 1
}

# 5. Check settings.json hook
Write-Host "`n5. Checking Stop hook..."
$settingsPath = ".claude/settings.json"
if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
    if ($settings.hooks.Stop) {
        Write-Host "    Stop hook configured"
    } else {
        Write-Warning "    No Stop hook found in settings.json"
    }
} else {
    Write-Warning "    settings.json not found"
}

Write-Host "`n Setup verification complete!"
Write-Host "`nNext steps:"
Write-Host "  1. Make some code changes"
Write-Host "  2. git add <files>"
Write-Host "  3. Try to stop/complete task - hook will trigger review"