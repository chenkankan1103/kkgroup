# Coding Rules and Paths

## 高頻規則

- Python 檔案預設使用 UTF-8 編碼標頭
- Cog 必須提供 `async def setup(bot)`
- 永久視圖需要 `timeout=None`，並在 bot 啟動時 `add_view()`
- 不要在同步函式內直接做需要 `await` 的工作

## 路徑規則

- 字型位於 repo 根目錄的 `fonts/`
- 從 `cogs/common/` 出發，正確字型路徑是 `../../fonts/NotoSansCJKtc-Regular.otf`
- 如果相對路徑只退一層，通常會誤指到 `cogs/fonts/`

## Discord 指令規則

- 指令定義在 Cog 中
- 需要同步到集中式 CommandRegistry
- 視圖和按鈕優先沿用統一系統，不要零散定義

## 何時查原始指引

- 要寫 Discord bot 功能時，看 `.copilot-instructions.md`
- 要看部署、VM、字型、紙娃娃規則時，看 `.github/copilot-instructions.md`
- 要執行遠端操作時，看 `config/commands_registry.json` 與 `scripts/commands_manager.py`