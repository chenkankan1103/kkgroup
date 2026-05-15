# Discord 靜音訊息寫法

## 最簡單的做法

- 發送訊息時：使用 `silent=True`
- 編輯訊息時：使用 `suppress=True`

## 為什麼這樣寫

- `silent=True` 是 discord.py v2.5+ 直接支援的簡潔參數。
- 它比 `flags=discord.MessageFlags(suppress_notifications=True)` 更短、更好讀。
- `flags=MessageFlags(...)` 仍然有效，但屬於較冗長的寫法。

## 範例

```python
await channel.send(embed=embed, silent=True)
```

```python
await message.edit(embed=embed, suppress=True)
```

## 注意事項

- `silent=True` 只適用於 `send()`。
- `edit()` 要使用 `suppress=True`，而不是 `silent=True`。
- 這兩種寫法會讓 Discord 發訊息時不發出推播通知，但訊息仍會出現在頻道裡。

## 專案內統一規則

- 盡量用 `silent=True` 發送所有不需要推播通知的 bot 訊息。
- 用 `suppress=True` 編輯現有訊息時保持靜音。
- 只有在特殊情況下需要精細控制 `MessageFlags` 時，才使用 `flags=discord.MessageFlags(...)`。

## 相關文檔

- [Discord 訊息 ID 持久化實踐](discord-message-id-persistence.md)
- [Discord Bot 系統詳解](discord-bot-system.md)