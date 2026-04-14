# kkgroup

## Remote GCP helper script

A convenient PowerShell helper lives at `scripts/gcp-ssh.ps1`.
It can SSH into the bot VM and either set an environment variable or run arbitrary commands.

**Examples**:

```powershell
# restart the bot service:
.\scripts\gcp-ssh.ps1 -RemoteCmd 'sudo systemctl restart bot.service'

# check disk usage on the remote host:
.\scripts\gcp-ssh.ps1 -RemoteCmd 'df -h'
```

Refer to the file headers for additional details and defaults.

 
