# Discord.py 交互最佳實踐指南

## 🎯 四大核心原則

### 1️⃣ **永不超時 + 永久視圖**
```python
# ✅ 正確做法
view = discord.ui.View(timeout=None)  # 永久視圖，不會超時

# ❌ 錯誤做法
view = discord.ui.View()  # 默認 timeout=180秒，容易超時
```

### 2️⃣ **靜音回應 (Ephemeral)**
```python
# ✅ 正確做法 - 所有按鈕回應都靜音
async def button_callback(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    # ... 處理邏輯
    await interaction.edit_original_response(embed=new_embed, view=new_view)

# ❌ 錯誤做法
await interaction.response.defer()  # 會讓訊息被所有人看到
await interaction.followup.send("...")  # 會發送新訊息，而不是編輯原有的
```

### 3️⃣ **編輯原有 Embed（不發送新訊息）**
```python
# ✅ 正確做法 - 編輯原有訊息
await interaction.edit_original_response(embed=new_embed, view=new_view)

# ⚠️ 次佳做法 - 發送新訊息（會堆積）
await interaction.followup.send(embed=new_embed, view=new_view)

# ❌ 錯誤做法 - 刪除原訊息再發送
await interaction.delete_original_response()
await interaction.followup.send(embed=new_embed, view=new_view)
```

### 4️⃣ **初始訊息必須也靜音**
```python
# ✅ 在命令中發送初始 embed 時也要靜音
await interaction.response.send_message(
    embed=embed, 
    view=view, 
    ephemeral=True  # 重要！
)

# 然後在按鈕中編輯它
# await interaction.edit_original_response(embed=new_embed, view=new_view)
```

---

## 📋 完整實現範例

### 一鍵種植配置流程

```python
class CropPlantingView(discord.ui.View):
    def __init__(self, ...):
        super().__init__(timeout=None)  # 永久視圖
        self.plant_all_config = {}
        # ... 添加按鈕

    async def update_config_embed(self, interaction: discord.Interaction):
        """更新配置 embed"""
        try:
            # 1. 準備新 embed
            embed = discord.Embed(
                title="🌾 配置一鍵種植",
                description="選擇要種植的種子和數量",
                color=discord.Color.green()
            )
            
            for seed_name, qty in self.plant_all_config.items():
                max_qty = self.seeds_dict.get(seed_name, 0)
                if max_qty > 0:
                    config = CANNABIS_SHOP["種子"][seed_name]
                    embed.add_field(
                        name=f"{config['emoji']} {seed_name}",
                        value=f"已選擇: {qty} / 可用: {max_qty}",
                        inline=True
                    )
            
            # 2. 重建視圖（timeout=None）
            view = discord.ui.View(timeout=None)
            
            # 3. 添加所有按鈕...
            # (減少、顯示、增加)
            
            # 4. **最重要：編輯原訊息而不是發送新訊息**
            await interaction.edit_original_response(
                embed=embed, 
                view=view
            )
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ 錯誤：{str(e)[:100]}", 
                ephemeral=True
            )

    async def button_callback(self, interaction: discord.Interaction):
        """所有按鈕的回應"""
        try:
            # 1. 立即回應，使用靜音
            await interaction.response.defer(ephemeral=True)
            
            # 2. 處理邏輯
            self.plant_all_config[seed_name] += 1
            
            # 3. 編輯原訊息
            await self.update_config_embed(interaction)
            
        except Exception as e:
            # 4. 錯誤時發送新訊息（因為已 defer）
            await interaction.followup.send(
                f"❌ 錯誤：{str(e)[:100]}", 
                ephemeral=True
            )
```

---

## 🔑 Defer 技巧

### 什麼時候用 `defer` vs 直接 `send_message`？

```python
# ✅ 快速操作（< 1秒）
async def quick_button(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    self.count += 1
    await interaction.edit_original_response(content=f"計數: {self.count}")

# ✅ 慢速操作（需要查詢資料庫等）
async def slow_button(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # 先回應，不讓用戶等待
    
    # ... 做耗時操作（最多 15 分鐘）
    result = await fetch_from_database()
    
    await interaction.edit_original_response(content=f"結果: {result}")
```

### Defer 的兩種方式

```python
# 方式 1: 靜音 Defer（推薦用於私密操作）
await interaction.response.defer(ephemeral=True)

# 方式 2: 公開 Defer（推薦用於公開操作）
await interaction.response.defer(ephemeral=False)
```

---

## ⚡ 性能優化

### 避免重複建立視圖

```python
# ❌ 不好 - 每次按鈕點擊都重建視圖
async def button_callback(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # 這裡每次都重建整個視圖！
    view = discord.ui.View(timeout=None)
    # ... 添加 20 個按鈕
    
    await interaction.edit_original_response(view=view)

# ✅ 好 - 使用 View 實例
class MyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_buttons()  # 初始化時就添加
    
    def add_buttons(self):
        for i in range(20):
            btn = discord.ui.Button(label=f"按鈕 {i}")
            btn.callback = self.button_callback
            self.add_item(btn)
    
    async def button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # ... 編輯 embed，但視圖保持不變
        await interaction.edit_original_response(embed=new_embed)
```

---

## 🛠️ 常見陷阱 

### 陷阱 1: 重複 Defer
```python
# ❌ 錯誤
await interaction.response.defer(ephemeral=True)
await interaction.response.defer(ephemeral=True)  # 會拋錯！

# ✅ 正確
await interaction.response.defer(ephemeral=True)
await interaction.edit_original_response(embed=embed)
```

### 陷阱 2: Defer 後用 send_message
```python
# ❌ 錯誤 - 會變成新訊息
await interaction.response.defer(ephemeral=True)
await interaction.followup.send("訊息")  # 這是新訊息，不是編輯原訊息

# ✅ 正確 - 編輯原訊息
await interaction.response.defer(ephemeral=True)
await interaction.edit_original_response(content="訊息")
```

### 陷阱 3: 忘記 timeout=None
```python
# ❌ 180 秒後視圖會失效
view = discord.ui.View()

# ✅ 永久有效
view = discord.ui.View(timeout=None)
```

---

## 📊 交互流程圖

```
用戶點擊按鈕
    ↓
[回應] await interaction.response.defer(ephemeral=True)
    ↓
[處理] 更新狀態、計算結果
    ↓
[編輯] await interaction.edit_original_response(embed=embed, view=view)
    ↓
訊息被編輯（只有用戶看得到）
    ↓
用戶點擊新按鈕
    ↓
... 重複 ...
```

---

## 🎓 總結清單

- ✅ 永久視圖：`timeout=None`
- ✅ 靜音回應：`ephemeral=True`
- ✅ 編輯原訊息：`edit_original_response()`
- ✅ 所有回應都 defer：`response.defer(ephemeral=True)`
- ✅ 錯誤時用 followup：`followup.send(ephemeral=True)`
- ✅ 初始訊息也靜音：`send_message(ephemeral=True)`
- ✅ 避免重複建立視圖

---

## 🔗 進階技巧

### 長時間操作（超過 3 秒）
```python
async def long_operation(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    # 可以安全地做最多 15 分鐘的操作
    result = await some_long_task()
    
    await interaction.edit_original_response(
        embed=create_result_embed(result),
        view=create_result_view()
    )
```

### 主動更新（不需要用戶點擊）
```python
# 在視圖外部編輯訊息
async def update_message_elsewhere(self, message: discord.Message):
    # 通過保存訊息 ID
    new_embed = create_updated_embed()
    new_view = discord.ui.View(timeout=None)
    
    await message.edit(embed=new_embed, view=new_view)
```
