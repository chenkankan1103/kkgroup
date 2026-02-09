# 收集可投放的頻道
eligible_channels = []
for guild in self.bot.guilds:
    member_role = guild.get_role(MEMBER_ROLE_ID)  # 確保環境中角色 ID 已正確配置
    if not member_role:
        print(f"❌ 無法在伺服器 {guild.name} 中找到角色: MEMBER_ROLE_ID={MEMBER_ROLE_ID}")
        continue

    for channel in guild.text_channels:
        try:
            # 確認頻道是否允許正式會員發送消息
            perms = channel.permissions_for(member_role)
            if perms.read_messages and perms.send_messages and not channel.is_forum():
                print(f"✅ 頻道 {channel.name} 是正式會員可用的頻道")
                eligible_channels.append(channel)
            else:
                print(f"🔒 頻道 {channel.name} 沒有足夠權限，跳過")
        except Exception as e:
            print(f"❌ 無法處理頻道 {channel.name}，錯誤: {e}")