# GCP 自動連接腳本

function gcpwork {
    ssh gcp-work "cd /home/e193752468/kkgroup && bash"
}

function gcpls {
    ssh gcp-work "cd /home/e193752468/kkgroup && ls -lh | head -20"
}

function gcpstatus {
    ssh gcp-work "cd /home/e193752468/kkgroup && pwd && echo '--- 文件統計 ---' && find . -type f | wc -l && echo '--- Python 文件 ---' && find . -name '*.py' | wc -l"
}

function gcpcmd {
    param([string]$Command)
    ssh gcp-work "cd /home/e193752468/kkgroup && $Command"
}

Set-Alias -Name 'gcp' -Value 'gcpwork' -Force
Write-Host "所有 GCP 命令已準備好！" -ForegroundColor Green
