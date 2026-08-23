# Upload anime_tracker.py to VM and restart uibot.service
$localFile = "C:\Users\88697\Desktop\kkgroup\cogs\ui\anime_tracker.py"
$remotePath = "/home/e193752468/kkgroup/cogs/ui/anime_tracker.py"

Write-Host "Uploading anime_tracker.py to VM..."
$scpResult = echo "" | gcloud -q compute scp $localFile e193752468@instance-20250501-142333:$remotePath --zone=us-central1-a --tunnel-through-iap
if ($LASTEXITCODE -ne 0) {
    Write-Host "SCP failed:" $scpResult
    exit 1
}
Write-Host "Upload successful!"

Write-Host "Restarting uibot.service..."
$sshResult = echo "" | gcloud -q compute ssh e193752468@instance-20250501-142333 --zone=us-central1-a --tunnel-through-iap --command "sudo systemctl restart uibot.service"
if ($LASTEXITCODE -ne 0) {
    Write-Host "SSH failed:" $sshResult
    exit 1
}
Write-Host "Restart command sent!"

# Wait a bit and check status
Start-Sleep -Seconds 5
$statusResult = echo "" | gcloud -q compute ssh e193752468@instance-20250501-142333 --zone=us-central1-a --tunnel-through-iap --command "sudo systemctl status uibot.service --no-pager"
Write-Host $statusResult