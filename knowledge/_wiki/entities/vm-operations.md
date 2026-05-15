# VM Operations

## 連線

- `gcloud compute ssh e193752468@instance-20250501-142333 --zone us-central1-c --tunnel-through-iap`

## 驗證重點

- 服務是否正常啟動
- 日誌是否有關鍵錯誤
- Git 版本是否同步到預期提交
- 隧道與 Nginx 是否仍可轉發

## 原則

- 先在本地驗證，再同步到 VM
- 盡量不要直接在 VM 上做資料庫主修復
- 系統服務文件在 VM 管理，不上傳 Git

## 相關文檔

- [部署和維運指南](../concepts/deployment-and-operations.md)
- [Webhook and Tunnel](../concepts/webhook-and-tunnel.md)
- [VM 實際配置狀況](vm-actual-configuration.md)
- [Command Registry](command-registry.md)