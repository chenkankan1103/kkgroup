# Paperdoll Workflow

## 核心原則

- 新用戶造型使用 `paperdoll_manager.get_random()` 生成
- 不要在 welcome 流程硬編碼造型值
- 所有 API URL 由 `paperdoll_manager.build_api_url()` 建構

## 修復流程

1. 診斷
2. 修復
3. 驗證
4. 部署
5. 刷新 `/admin_refresh_all_lockers`

## 常見風險

- fashion DB 中不存在的物品 ID
- 性別不一致
- VM 未同步最新資料或最新代碼

## 相關文檔

- [KK 園區系統地圖](kk-park-system-map.md)
- [專案架構總覽](project-architecture.md)
- [Coding Rules and Paths](coding-rules-and-paths.md)
- [部署和維運指南](deployment-and-operations.md)
