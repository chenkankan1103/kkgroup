# excluded_modules 對比

## shopbot.py 的 excluded_modules
```python
excluded_modules = {
    'cannabis_farming', 'cannabis_merchant_view', 'cannabis_merchant_view_v2',
    'cannabis_config', 'database', 'config', 'views', 'views_base',
    'paperdoll_system', 'gambling', 'role_expiry_manager'
}
```

## uibot.py 的 excluded_modules  
```python
excluded_modules = {
    'cannabis_farming', 'cannabis_merchant_view', 'cannabis_merchant_view_v2',
    'cannabis_config', 'database', 'config', 'views', 'views_base',
    'paperdoll_system', 'gambling', 'role_expiry_manager', 'locker_panel',
    'locker_events', 'locker_tasks', 'locker_cache', 'locker_embed_generator',
    'image_utils', 'selection_views', 'crop_operations', 'personal_locker',
    'work_card'  # 這些都是 View 或 Modal 類，不是 Cog
}
```

## 問題
1. **shopbot.py** 缺少排除清單，但 shopbot 加載 cogs/shop，那裡有：
   - `cogs/shop/merchant/views.py` - 包含多個 View 類

2. **shopbot.py** 沒有明確排除 'views.py' 在 merchant 目錄中
   - find_and_load_extensions 會遞歸進入 merchant/ 目錄
   - 嘗試加載 views.py 作為 Cog
   - views.py 沒有 setup() 函數，會失敗

3. **bot.py 為什麼有效**？
   - 有 DB migration 和其他初始化
   - 可能有不同的錯誤處理機制
