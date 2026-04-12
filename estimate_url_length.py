#!/usr/bin/env python3
"""估算 anime_ranking 多線圖的 URL 長度"""
import json
from urllib.parse import quote

# 模擬 10 部動畫的圖表配置
episode_labels = ['EP1', 'EP2', 'EP3', 'EP4', 'EP5', 'EP6', 'EP7', 'EP8', 'EP9', 'EP10', 'EP11', 'EP12']
colors = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8",
    "#F7DC6F", "#BB8FCE", "#85C1E2", "#F8B88B", "#ABEBC6"
]

datasets = []
for idx in range(10):
    name = f"動畫{idx+1}"[:8]
    color = colors[idx % len(colors)]
    
    # 模擬 12 集的數據
    data = [100 + (idx * 10 + i) for i in range(len(episode_labels))]
    
    datasets.append({
        "label": name,
        "data": data,
        "borderColor": color,
        "fill": False,
        "tension": 0.2,
        "pointRadius": 2
    })

# 構建圖表配置（簡化版本）
chart_config = {
    "type": "line",
    "data": {
        "labels": episode_labels,
        "datasets": datasets
    },
    "options": {
        "scales": {
            "y": {
                "title": {"display": True, "text": "觀看"}
            },
            "x": {
                "title": {"display": True, "text": "集"}
            }
        },
        "plugins": {
            "legend": {
                "position": "top",
                "labels": {"font": {"size": 8}}
            }
        }
    }
}

# 生成 URL
config_json = json.dumps(chart_config, separators=(',', ':'), ensure_ascii=False)
encoded = quote(config_json)
chart_url = f"https://quickchart.io/chart?bkg=white&w=850&h=350&c={encoded}"

print("=" * 60)
print("anime_ranking 多線圖 URL 長度估算")
print("=" * 60)
print(f"JSON 配置長度: {len(config_json)} 字符")
print(f"URL 編碼後長度: {len(encoded)} 字符")
print(f"完整 URL 長度: {len(chart_url)} 字符")
print()

if len(chart_url) <= 2048:
    print(f"✅ URL 長度 {len(chart_url)} ≤ 2048")
    print("   ✅ 可以直接在 Discord Embed 中設置圖片")
    print(f"   ✅ 剩餘空間: {2048 - len(chart_url)} 字符")
else:
    print(f"❌ URL 長度 {len(chart_url)} > 2048")
    print("   ❌ 將使用文字排行作為備選")
    print(f"   ❌ 超出: {len(chart_url) - 2048} 字符")

print()
print("URL 預覽（前 200 字符）:")
print(chart_url[:200] + "...")
