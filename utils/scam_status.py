import random
import discord

SCAM_THEMES = [
    "正在監控詐騙訊息",
    "風控檢查中",
    "園區安全巡查",
    "監控異常活動",
    "智能防詐啟動中",
    "偵測中：詐騙新招",
    "園區指令輸入監控",
    "調閱資料庫中…",
    "已啟動防護盾",
    "等待群組警報",
    "數據分析進行中",
    "黑名單同步中",
    "掃描公開資訊",
    "跨群組溝通防詐",
    "舉報案件審查",
    "自動回報風險",
    "防詐知識推廣",
    "異常登入監控",
    "API 數據拉取中",
    "調查假冒帳號",
    "阻擋可疑連結",
    "追蹤資金流向",
    "風險評分計算中",
    "園區即時通報",
    "檢查用戶安全等級",
    "核對群組黑名單",
    "訊息內容分析中",
    "導入新型防詐模組",
    "巡查員工活動",
    "自動化回應訓練",
    "智能預警升級",
]

def get_scam_status():
    """隨機選出一個詐騙園區主題狀態"""
    return random.choice(SCAM_THEMES)

def build_discord_activity():
    """回傳 Discord Activity 物件，可直接給 change_presence"""
    return discord.Activity(type=discord.ActivityType.watching, name=get_scam_status())