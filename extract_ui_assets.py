"""
从赛博朋克UI素材图中提取各个元素
自动检测并切割透明PNG中的各个UI组件
"""
from PIL import Image
import os
import numpy as np

def find_bounding_box(img_array):
    """找到非透明区域的边界框"""
    # 获取alpha通道
    alpha = img_array[:, :, 3]
    
    # 找到非透明像素
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    
    if not rows.any() or not cols.any():
        return None
    
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    
    return (cmin, rmin, cmax + 1, rmax + 1)

def extract_assets(source_path, output_dir="assets"):
    """提取UI素材"""
    print(f"🎨 开始从 {source_path} 提取素材...")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载原图
    img = Image.open(source_path).convert("RGBA")
    print(f"📐 原图尺寸: {img.size}")
    
    # 手动定义各个素材的大致位置（基于目测）
    assets = {
        "frame_top": (30, 20, 740, 350),          # 顶部大边框
        "trophy": (430, 375, 520, 465),            # 金色奖杯
        "arrow_down_green": (410, 380, 500, 470),  # 绿色向下箭头
        "arrow_down_red": (295, 570, 365, 640),    # 红色向下箭头
        "bar_style1": (75, 485, 365, 530),         # 能量条样式1
        "bar_style2": (400, 485, 685, 530),        # 能量条样式2
        "bar_style3": (175, 575, 260, 620),        # 能量条样式3（小）
        "bar_style4": (405, 570, 685, 615),        # 能量条样式4
        "panel_bottom": (110, 655, 695, 760),      # 底部面板
    }
    
    extracted = []
    
    for name, bbox in assets.items():
        try:
            # 裁剪区域
            cropped = img.crop(bbox)
            
            # 转换为numpy数组以查找精确边界
            arr = np.array(cropped)
            
            # 找到非透明区域的精确边界
            tight_bbox = find_bounding_box(arr)
            
            if tight_bbox:
                # 裁剪到精确边界
                final = cropped.crop(tight_bbox)
                
                # 保存
                output_path = os.path.join(output_dir, f"cyber_{name}.png")
                final.save(output_path, "PNG")
                
                print(f"✅ {name}: {final.size} -> {output_path}")
                extracted.append((name, output_path, final.size))
            else:
                print(f"⚠️ {name}: 未找到有效内容")
                
        except Exception as e:
            print(f"❌ {name} 提取失败: {e}")
    
    print(f"\n📦 共提取 {len(extracted)} 个素材")
    
    # 生成素材清单
    print("\n" + "="*60)
    print("素材清单：")
    print("="*60)
    for name, path, size in extracted:
        print(f"  {name:20s} {size[0]:4d}x{size[1]:4d}  {path}")
    
    return extracted

def create_full_background(source_path, output_path="assets/kkcoin_rank_v2_bg.png", 
                          target_size=(1920, 1080)):
    """使用顶部边框创建完整背景（旋转90度作为竖版边框）"""
    print(f"\n🎨 创建 {target_size} 完整背景...")
    
    img = Image.open(source_path).convert("RGBA")
    
    # 提取顶部边框
    frame_bbox = (30, 20, 740, 350)
    frame = img.crop(frame_bbox)
    
    # 裁剪到精确边界
    arr = np.array(frame)
    tight_bbox = find_bounding_box(arr)
    if tight_bbox:
        frame = frame.crop(tight_bbox)
    
    # 旋转90度（顺时针）
    frame = frame.rotate(-90, expand=True)
    
    # 创建目标尺寸的深色赛博背景
    bg = Image.new("RGBA", target_size, (10, 12, 20, 255))  # 深色背景
    
    # 将旋转后的边框缩放到合适大小（高度约为画面的80%）
    frame_height = int(target_size[1] * 0.8)  # 高度为屏幕的80%
    frame_width = int(frame.size[0] * (frame_height / frame.size[1]))
    
    frame_resized = frame.resize((frame_width, frame_height), Image.LANCZOS)
    
    # 将边框居中粘贴
    x = (target_size[0] - frame_width) // 2
    y = (target_size[1] - frame_height) // 2
    
    bg.paste(frame_resized, (x, y), frame_resized)
    
    # 保存
    bg.save(output_path, "PNG")
    print(f"✅ 完整背景已创建: {output_path}")
    print(f"   边框尺寸（旋转90度后）: {frame_resized.size}")
    print(f"   边框位置: ({x}, {y})")
    
    # 自动预览
    try:
        os.startfile(output_path)
        print("🖼️ 已自动打开预览")
    except:
        pass
    
    return output_path

if __name__ == "__main__":
    source = "cyber_ui_assets.png"  # 请将素材图重命名为此文件名
    
    if not os.path.exists(source):
        print(f"❌ 找不到素材文件: {source}")
        print("请将素材图片放在当前目录，并命名为 'cyber_ui_assets.png'")
        print("或修改脚本中的 source 变量为正确的文件名")
    else:
        # 提取各个小素材
        extract_assets(source)
        
        # 创建完整背景
        create_full_background(source)
        
        print("\n✅ 所有素材提取完成！")
        print("💡 可以运行 python test_kkcoin_rankv2.py 查看效果")
