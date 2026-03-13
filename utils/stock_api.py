"""
股票市場 API 層
處理價格獲取、圖表生成、快取等功能
"""

import yfinance as yf
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

# 快取存放處
_price_cache: Dict[str, Tuple[float, datetime]] = {}
_chart_cache: Dict[str, Tuple[str, datetime]] = {}
CACHE_DURATION_SECONDS = 300  # 5 分鐘快取


# ============================================================
# 價格操作
# ============================================================

async def fetch_price(symbol: str) -> Optional[float]:
    """
    獲取股票當前價格 (async 包裝)
    
    Args:
        symbol: 股票代號，例如 "2330.TW"
        
    Returns:
        當前價格，或 None 如取得失敗
    """
    # 檢查快取
    if symbol in _price_cache:
        price, cached_time = _price_cache[symbol]
        if datetime.now() - cached_time < timedelta(seconds=CACHE_DURATION_SECONDS):
            return price
    
    # 在線程池中執行 yfinance（避免阻塞事件迴圈）
    loop = asyncio.get_event_loop()
    
    try:
        def _fetch():
            ticker = yf.Ticker(symbol)
            # 使用 fast=True 加速，並取最新收盤價或現價
            data = ticker.history(period="1d")
            if data.empty:
                return None
            return float(data['Close'].iloc[-1])
        
        price = await loop.run_in_executor(None, _fetch)
        
        if price is not None:
            _price_cache[symbol] = (price, datetime.now())
            return price
        
        return None
    
    except Exception as e:
        logger.error(f"❌ 獲取 {symbol} 價格失敗: {e}")
        return None


async def fetch_historical_data(symbol: str, period: str = "1mo") -> Optional[Dict]:
    """
    獲取歷史價格數據
    
    Args:
        symbol: 股票代號，例如 "2330.TW"
        period: 時間區間，例如 "1d", "1mo", "1y"
        
    Returns:
        包含 dates 和 prices 的字典，或 None
    """
    loop = asyncio.get_event_loop()
    
    try:
        def _fetch():
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period)
            if data.empty:
                return None
            
            dates = [d.strftime('%Y-%m-%d') for d in data.index]
            prices = [float(p) for p in data['Close']]
            
            return {
                'dates': dates,
                'prices': prices,
                'latest': prices[-1] if prices else None
            }
        
        return await loop.run_in_executor(None, _fetch)
    
    except Exception as e:
        logger.error(f"❌ 獲取 {symbol} 歷史數據失敗: {e}")
        return None


# ============================================================
# 圖表操作
# ============================================================

def build_quickchart_url(
    symbol: str,
    prices: List[float],
    dates: List[str],
    height: int = 300,
    width: int = 800
) -> str:
    """
    構建 QuickChart 圖表 URL
    
    Args:
        symbol: 股票代號
        prices: 價格列表
        dates: 日期列表
        height: 圖表高度
        width: 圖表寬度
        
    Returns:
        QuickChart URL
    """
    # 對資料進行採樣，避免過多點導致 URL 過長（QuickChart 有 URL 長度限制）
    sample_rate = max(1, len(prices) // 30)  # 最多 30 個點
    sampled_prices = prices[::sample_rate]
    sampled_dates = dates[::sample_rate]
    
    # 計算顏色：最後一根 K 線與倒數第二根比較
    if len(sampled_prices) >= 2:
        color = "green" if sampled_prices[-1] >= sampled_prices[-2] else "red"
    else:
        color = "blue"
    
    chart_config = {
        "type": "line",
        "data": {
            "labels": sampled_dates,
            "datasets": [
                {
                    "label": symbol,
                    "data": sampled_prices,
                    "borderColor": color,
                    "borderWidth": 2,
                    "fill": False,
                    "tension": 0.1,
                    "pointRadius": 0,
                }
            ]
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": True,
            "scales": {
                "y": {
                    "ticks": {
                        "font": {"size": 10}
                    }
                },
                "x": {
                    "ticks": {
                        "font": {"size": 9},
                        "maxRotation": 45,
                        "minRotation": 0
                    }
                }
            },
            "plugins": {
                "legend": {
                    "labels": {"font": {"size": 11}}
                },
                "title": {
                    "display": True,
                    "text": f"{symbol} - {sampled_dates[-1] if sampled_dates else 'N/A'}"
                }
            }
        }
    }
    
    # 編碼為 URL encode 格式
    config_json = json.dumps(chart_config, separators=(',', ':'))
    # QuickChart 需要 base64 或 URL encode
    import base64
    encoded = base64.b64encode(config_json.encode()).decode()
    
    return f"https://quickchart.io/chart?bkg=white&c={encoded}"


async def fetch_chart(
    symbol: str,
    period: str = "1mo",
    force_refresh: bool = False
) -> Optional[str]:
    """
    獲取股票圖表 URL
    
    Args:
        symbol: 股票代號
        period: 時間區間
        force_refresh: 是否強制重新生成
        
    Returns:
        QuickChart URL，或 None
    """
    cache_key = f"{symbol}_{period}"
    
    # 檢查快取
    if not force_refresh and cache_key in _chart_cache:
        url, cached_time = _chart_cache[cache_key]
        if datetime.now() - cached_time < timedelta(seconds=CACHE_DURATION_SECONDS):
            return url
    
    try:
        # 獲取歷史數據
        hist_data = await fetch_historical_data(symbol, period)
        if not hist_data or not hist_data['prices']:
            return None
        
        # 構建 URL
        url = build_quickchart_url(
            symbol=symbol,
            prices=hist_data['prices'],
            dates=hist_data['dates']
        )
        
        # 快取
        _chart_cache[cache_key] = (url, datetime.now())
        return url
    
    except Exception as e:
        logger.error(f"❌ 生成 {symbol} 圖表失敗: {e}")
        return None


# ============================================================
# 熱門代號列表
# ============================================================

# 台股熱門代號
POPULAR_STOCKS_TW = [
    ("2330", "台積電", "2330.TW"),
    ("0050", "元大台灣50", "0050.TW"),
    ("0056", "元大高股息", "0056.TW"),
    ("2454", "聯發科", "2454.TW"),
    ("3034", "聯詠", "3034.TW"),
    ("2412", "中華電", "2412.TW"),
    ("1101", "台泥", "1101.TW"),
    ("9910", "豐興", "9910.TW"),
    ("2882", "國泰金", "2882.TW"),
    ("2891", "中信金", "2891.TW"),
    ("2886", "兆豐金", "2886.TW"),
    ("2884", "玉山金", "2884.TW"),
    ("1301", "台塑", "1301.TW"),
    ("1303", "南亞", "1303.TW"),
    ("3711", "日月光", "3711.TW"),
    ("2303", "聯電", "2303.TW"),
    ("2408", "南亞科", "2408.TW"),
    ("2357", "華碩", "2357.TW"),
    ("2498", "宏達電", "2498.TW"),
    ("2887", "台新金", "2887.TW"),
]

def get_popular_stocks() -> List[Tuple[str, str, str]]:
    """
    取得熱門股票清單
    
    Returns:
        [(code, name, symbol_with_tw), ...]
    """
    return POPULAR_STOCKS_TW
