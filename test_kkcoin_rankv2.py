"""
测试 KKCoin RankV2 排行榜生成器
本地预览生成效果
"""
import asyncio
import os
import sys
from PIL import Image
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

# 导入必要模块
from commands.kcoin import make_leaderboard_image_v2

class MockMember:
    """模拟 Discord Member 对象"""
    def __init__(self, user_id, display_name, avatar_url=None):
        self.id = user_id
        self.display_name = display_name
        self._avatar_url = avatar_url
        
    @property
    def display_avatar(self):
        if self._avatar_url:
            return type('obj', (object,), {'url': self._avatar_url})()
        return None
    
    @property
    def avatar(self):
        return self.display_avatar
    
    @property
    def default_avatar(self):
        # Discord 默认头像 URL
        return type('obj', (object,), {
            'url': 'https://cdn.discordapp.com/embed/avatars/0.png'
        })()

async def test_rankv2():
    """测试 V2 排行榜生成"""
    print("🎨 开始生成 KKCoin RankV2 排行榜测试图...")
    
    # 创建模拟数据（20个用户）
    mock_data = [
        (MockMember(1, "神秘大佬", "https://cdn.discordapp.com/embed/avatars/0.png"), 15000),
        (MockMember(2, "KK币土豪", "https://cdn.discordapp.com/embed/avatars/1.png"), 12500),
        (MockMember(3, "聊天达人", "https://cdn.discordapp.com/embed/avatars/2.png"), 10200),
        (MockMember(4, "积极玩家", "https://cdn.discordapp.com/embed/avatars/3.png"), 8900),
        (MockMember(5, "每日签到王", "https://cdn.discordapp.com/embed/avatars/4.png"), 7800),
        (MockMember(6, "语音常驻", "https://cdn.discordapp.com/embed/avatars/0.png"), 6500),
        (MockMember(7, "活动狂人", "https://cdn.discordapp.com/embed/avatars/1.png"), 5900),
        (MockMember(8, "深夜水群侠", "https://cdn.discordapp.com/embed/avatars/2.png"), 5300),
        (MockMember(9, "表情包收藏家", "https://cdn.discordapp.com/embed/avatars/3.png"), 4800),
        (MockMember(10, "资深潜水员", "https://cdn.discordapp.com/embed/avatars/4.png"), 4200),
        (MockMember(11, "偶尔冒泡", "https://cdn.discordapp.com/embed/avatars/0.png"), 3800),
        (MockMember(12, "新人菜鸟", "https://cdn.discordapp.com/embed/avatars/1.png"), 3400),
        (MockMember(13, "话痨专家", "https://cdn.discordapp.com/embed/avatars/2.png"), 3100),
        (MockMember(14, "游戏大神", "https://cdn.discordapp.com/embed/avatars/3.png"), 2800),
        (MockMember(15, "摸鱼选手", "https://cdn.discordapp.com/embed/avatars/4.png"), 2500),
        (MockMember(16, "周末战士", "https://cdn.discordapp.com/embed/avatars/0.png"), 2200),
        (MockMember(17, "早起鸟儿", "https://cdn.discordapp.com/embed/avatars/1.png"), 1900),
        (MockMember(18, "夜猫子", "https://cdn.discordapp.com/embed/avatars/2.png"), 1600),
        (MockMember(19, "吃瓜群众", "https://cdn.discordapp.com/embed/avatars/3.png"), 1300),
        (MockMember(20, "路过打酱油", "https://cdn.discordapp.com/embed/avatars/4.png"), 1000),
    ]
    
    # 生成图片
    try:
        image = await make_leaderboard_image_v2(mock_data, limit=20)
        
        # 保存到本地
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"kkcoin_rankv2_preview_{timestamp}.png"
        image.save(output_path, "PNG")
        
        print(f"✅ 图片已生成: {output_path}")
        print(f"📐 尺寸: {image.size[0]}x{image.size[1]}")
        print(f"📊 包含 {len(mock_data)} 位用户")
        
        # 尝试打开图片预览（Windows）
        try:
            os.startfile(output_path)
            print("🖼️ 已自动打开预览")
        except:
            print(f"💡 请手动打开查看: {os.path.abspath(output_path)}")
            
    except FileNotFoundError as e:
        print(f"❌ 找不到必要文件:")
        print(f"   {e}")
        print(f"\n⚠️ 请确认：")
        print(f"   1. assets/kkcoin_rank_v2_bg.png 背景图已存在")
        print(f"   2. fonts/NotoSansCJKtc-Regular.otf 字体文件已存在")
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("=" * 60)
    print("KKCoin RankV2 排行榜生成器测试")
    print("=" * 60)
    asyncio.run(test_rankv2())
