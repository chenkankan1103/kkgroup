# PowerShell script to connect to GCP VM and add an environment variable
# Usage: run this script from any PowerShell prompt

param(
    [string]$Instance   = "e193752468@instance-20250501-142333",
    [string]$Zone       = "us-central1-c",
    [string]$Name       = "TEMP_VC_CATEGORY_ID",
    [string]$Value      = "1371429517750566962",
    # optional command to run remotely
    [string]$RemoteCmd  = ''
)

if ([string]::IsNullOrWhiteSpace($RemoteCmd)) {
    # default behaviour: add env var to bashrc if not already present
    $cmd = @"
grep -q '^export $Name=' ~/.bashrc || \
  echo 'export $Name=$Value' >> ~/.bashrc
"@
} else {
    # use provided command, quote to preserve spaces
    $cmd = $RemoteCmd
}

# execute on remote host
Write-Host "Running on $Instance (zone $Zone): $cmd"
gcloud compute ssh $Instance --zone=$Zone --command=$cmd