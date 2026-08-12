<#
Consensus review loop for Windows PowerShell 5.1+
Called by Stop hook. Exit 0 = approved, 1 = rejected (block stop)
#>

param()

$ErrorActionPreference = "Stop"

function Coalesce($val, $default) { if ($null -ne $val) { $val } else { $default } }

$SESSION_ID = Coalesce $env:CLAUDE_SESSION_ID ((Get-Date).ToString("yyyyMMddHHmmss"))
$MAX_ROUNDS = 3
$ROUND = 1
$PREV_FINDINGS = ""

Write-Host "🔍 Starting consensus review (session: $SESSION_ID)"

while ($ROUND -le $MAX_ROUNDS) {
    Write-Host "=== Round $ROUND / $MAX_ROUNDS ==="

    $CONTEXT = ""
    if (-not [string]::IsNullOrEmpty($PREV_FINDINGS)) {
        $CONTEXT = "Previous round findings to address: $PREV_FINDINGS"
    }

    # Build JSON argument
    $jsonArgs = @{
        sessionId = $SESSION_ID
        context   = $CONTEXT
        mode      = "deliberate-deep"
    } | ConvertTo-Json -Compress -Depth 5

    # Call review_precommit via MCP
    try {
        $RESULT = npx -y codex-claude-bridge@latest review_precommit -- $jsonArgs 2>&1
    } catch {
        Write-Warning "Review call failed (continuing): $_"
        exit 0  # Don't block on infrastructure failures
    }

    $parsed = $RESULT | ConvertFrom-Json
    $VERDICT = Coalesce $parsed.verdict "unknown"
    $FINDINGS = Coalesce $parsed.findings @()

    Write-Host "Verdict: $VERDICT"
    Write-Host "Findings count: $($FINDINGS.Count)"

    if ($VERDICT -eq "approved") {
        Write-Host "✅ Consensus reached — approved"
        exit 0
    }

    if ($VERDICT -in @("rejected", "changes_requested")) {
        Write-Host "❌ Changes requested:"
        foreach ($f in $FINDINGS) {
            $file = if ($f.file) { $f.file } else { "general" }
            $line = if ($f.line) { $f.line } else { 0 }
            $msg  = Coalesce $f.message ""
            Write-Host "  - $($file):$($line) $msg"
        }
        $PREV_FINDINGS = ($FINDINGS | ConvertTo-Json -Compress -Depth 5)
    }

    $ROUND++
}

Write-Warning "Max rounds ($MAX_ROUNDS) reached without consensus"
Write-Host "📋 Final findings:"
$PREV_FINDINGS | ConvertFrom-Json | ForEach-Object {
    $file = if ($_.file) { $_.file } else { "general" }
    $line = if ($_.line) { $_.line } else { 0 }
    $msg  = Coalesce $_.message ""
    Write-Host "  - $($file):$($line) $msg"
}
exit 1
