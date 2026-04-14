# kkgroup

## 🔄 專案重組通知（2026年4月14日）

**重要**：專案目錄結構已進行重大重組。所有核心模組已移至 `bots/`, `shared/`, `web/`, `cogs/` 等組織化目錄。

### 快速導覽
- **Bot 入口**：`bots/bot.py`, `bots/shopbot.py`, `bots/uibot.py`
- **共享模組**：`shared/db/`, `shared/utils/`
- **Web API**：`web/api/`, `web/blueprints/`
- **Discord 命令**：`cogs/common/`, `cogs/shop/`, `cogs/ui/`
- **配置檔**：`config/services/`, `config/nginx/`, `config/scripts/`
- **文檔**：`docs/` | **備份**：`archive/`

### 向後相容性
根目錄的 `db_adapter.py` 作為相容層，現存代碼無需改動即可運作。

### 部署指南
詳見 [RESTRUCTURE_DEPLOYMENT_GUIDE.md](RESTRUCTURE_DEPLOYMENT_GUIDE.md) 以了解如何在 GCP VM 上部署這些變更。

### 工作流程指南
每次修改代碼前，請閱讀 [docs/workflow-guidelines.md](docs/workflow-guidelines.md)

---

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

 
