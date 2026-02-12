import discord
import time


class UpdatePanelView(discord.ui.View):
    """更新面板視圖"""
    def __init__(self, cog, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        if not hasattr(UpdatePanelView, 'last_update'):
            UpdatePanelView.last_update = {}
    
    @discord.ui.button(label="更新面板", style=discord.ButtonStyle.primary, emoji="🔄", custom_id="update_panel_button")
    async def update_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_time = time.time()
        last_update_time = UpdatePanelView.last_update.get(interaction.user.id, 0)
        
        if current_time - last_update_time < 5:
            remaining_time = 5 - (current_time - last_update_time)
            await interaction.response.send_message(f"⏰ 請等待 {remaining_time:.1f} 秒後再更新面板！", ephemeral=True)
            return
        
        # 從訊息的 embed 中提取 user_id（從標題或描述中）
        panel_owner_id = self.user_id
        if panel_owner_id == 0 and interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            # 嘗試從 embed 的 field 中找到使用者 ID
            for field in embed.fields:
                if field.name == "🆔 使用者ID":
                    try:
                        panel_owner_id = int(field.value.strip('`'))
                        break
                    except:
                        pass
        
        # 檢查是否為面板擁有者
        if panel_owner_id != 0 and interaction.user.id != panel_owner_id:
            await interaction.response.send_message("❌ 你只能更新自己的面板！", ephemeral=True)
            return
            
        try:
            await interaction.response.defer(ephemeral=True)
            UpdatePanelView.last_update[interaction.user.id] = current_time
            
            user_data = self.cog.get_user_data(interaction.user.id)
            if not user_data:
                await interaction.followup.send("❌ 沒有找到你的資料！", ephemeral=True)
                return
            
            embed = await self.cog.create_user_embed(user_data, interaction.user)
            character_image_url = await self.cog.get_character_image_url(user_data)
            
            if character_image_url:
                embed.set_image(url=character_image_url)
            
            # 修改搜尋邏輯：直接更新當前訊息
            try:
                await interaction.message.edit(embed=embed, view=self)
                await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
                return
            except Exception as e:
                # 如果直接更新失敗，嘗試搜尋訊息
                async for message in interaction.channel.history(limit=100):
                    if (message.embeds and message.author == self.cog.bot.user and
                        message.embeds[0].title and 
                        "置物櫃" in message.embeds[0].title and
                        str(interaction.user.id) in str(message.embeds[0].description or "")):
                        try:
                            await message.edit(embed=embed, view=self)
                            await interaction.followup.send("✅ 面板已更新！", ephemeral=True)
                            return
                        except:
                            continue
            
            await interaction.followup.send("❌ 找不到面板訊息，請聯繫管理員！", ephemeral=True)
            
        except Exception as e:
            try:
                await interaction.followup.send("❌ 更新面板時發生錯誤！", ephemeral=True)
            except:
                pass
