"""
股票市場 API 層
處理價格獲取、圖表生成、快取等功能
"""

import yfinance as yf
import asyncio
import json
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

# 快取存放處
_price_cache: Dict[str, Tuple[float, datetime]] = {}
_chart_cache: Dict[str, Tuple[str, datetime]] = {}
CACHE_DURATION_SECONDS = 300  # 5 分鐘快取

# QuickChart 短 URL API
QUICKCHART_SHORT_URL_API = "https://quickchart.io/chart/create"
QUICKCHART_CREATE_TIMEOUT = 30   # 秒
QUICKCHART_CREATE_RETRIES = 3    # 重試次數


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


async def fetch_historical_data(symbol: str, period: str = "3mo", interval: str = "1d") -> Optional[Dict]:
    """
    獲取歷史價格數據
    
    Args:
        symbol: 股票代號，例如 "2330.TW"
        period: 時間區間，例如 "5d", "1mo", "3mo", "2y"
        interval: K 線間隔，例如 "5m", "15m", "60m", "1d", "1mo", "3mo"
        
    Returns:
        包含 dates 和 prices 的字典，或 None
    """
    loop = asyncio.get_event_loop()
    
    try:
        def _fetch():
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)
            if data.empty:
                return None
            
            # 根據 interval 選擇日期格式
            if interval in ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"):
                dates = [d.strftime('%m/%d %H:%M') for d in data.index]
            elif interval == "1d":
                dates = [d.strftime('%m/%d') for d in data.index]
            else:
                dates = [d.strftime('%Y-%m') for d in data.index]
            
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
    from urllib.parse import quote

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
    
    # 使用 URL encoding（QuickChart 的 c 參數需要 URL-encoded JSON）
    config_json = json.dumps(chart_config, separators=(',', ':'))
    encoded = quote(config_json)
    
    return f"https://quickchart.io/chart?bkg=white&w={width}&h={height}&c={encoded}"


async def create_quickchart_short_url(chart_config: dict) -> Optional[str]:
    """
    透過 POST 請求取得 QuickChart 短 URL

    Args:
        chart_config: 圖表配置字典

    Returns:
        短 URL，或 None（失敗時）
    """
    loop = asyncio.get_event_loop()

    def _post():
        payload = {"chart": chart_config, "backgroundColor": "white"}
        for attempt in range(1, QUICKCHART_CREATE_RETRIES + 1):
            try:
                resp = requests.post(
                    QUICKCHART_SHORT_URL_API,
                    json=payload,
                    timeout=QUICKCHART_CREATE_TIMEOUT
                )
                if resp.status_code == 200:
                    data = resp.json()
                    url = data.get("url")
                    if url:
                        logger.info(f"✅ QuickChart 短 URL 已取得: {url}")
                        return url
                    logger.warning(f"⚠️ QuickChart 回應缺少 url 欄位: {data}")
                else:
                    logger.warning(
                        f"⚠️ QuickChart POST 失敗 (嘗試 {attempt}/{QUICKCHART_CREATE_RETRIES}): "
                        f"HTTP {resp.status_code}"
                    )
            except Exception as e:
                logger.warning(
                    f"⚠️ QuickChart POST 異常 (嘗試 {attempt}/{QUICKCHART_CREATE_RETRIES}): {e}"
                )
        return None

    try:
        return await loop.run_in_executor(None, _post)
    except Exception as e:
        logger.error(f"❌ create_quickchart_short_url 失敗: {e}")
        return None


async def fetch_chart(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
    force_refresh: bool = False,
    avg_cost: Optional[float] = None,
    chart_type: str = "candlestick"
) -> Optional[str]:
    """
    獲取股票圖表 URL（支援 K線蠟燭圖）
    
    Args:
        symbol: 股票代號
        period: 時間區間
        interval: K 線間隔，例如 "5m", "15m", "60m", "1d", "1mo", "3mo"
        force_refresh: 是否強制重新生成
        avg_cost: 用戶的平均成本（用於繪製成本線）
        chart_type: 圖表類型 "candlestick" 或 "line"
        
    Returns:
        QuickChart URL，或 None
    """
    cache_key = f"{symbol}_{period}_{interval}_{chart_type}"
    
    # 檢查快取（force_refresh=True 時強制跳過快取）
    if not force_refresh and cache_key in _chart_cache:
        url, cached_time = _chart_cache[cache_key]
        if datetime.now() - cached_time < timedelta(seconds=CACHE_DURATION_SECONDS):
            logger.debug(f"📊 圖表快取命中: {cache_key}")
            return url
    
    # 強制刷新時清除該快取
    if force_refresh and cache_key in _chart_cache:
        logger.info(f"🔄 清除圖表快取: {cache_key}")
        del _chart_cache[cache_key]
    
    try:
        # 獲取 OHLC 數據（用於蠟燭圖）
        hist_data = await fetch_historical_data(symbol, period=period, interval=interval)
        if not hist_data or not hist_data['prices']:
            logger.warning(f"⚠️ {symbol} 在 period={period} interval={interval} 下無歷史數據")
            return None
        
        # 構建圖表配置
        prices = hist_data['prices']
        dates = hist_data['dates']

        # 對資料進行採樣（最多 60 個點，減少 payload 大小）
        sample_rate = max(1, len(prices) // 60)
        sampled_prices = prices[::sample_rate]
        sampled_dates = dates[::sample_rate]

        # 台灣習慣：紅 = 漲，綠 = 跌
        color = "#FF0000" if len(prices) < 2 or prices[-1] >= prices[-2] else "#00AA00"

        # 建議資料集：價格線
        datasets = [
            {
                "label": symbol,
                "data": sampled_prices,
                "borderColor": color,
                "borderWidth": 2.5,
                "fill": False,
                "tension": 0.1,
                "pointRadius": 1,
                "pointBackgroundColor": color,
            }
        ]
        
        # 如果有成本線，添加到圖表
        if avg_cost is not None and avg_cost > 0:
            # 創建成本線（平直線）
            cost_line_data = [avg_cost] * len(sampled_prices)
            datasets.append({
                "label": f"成本: ${avg_cost:.2f}",
                "data": cost_line_data,
                "borderColor": "#FFD700",
                "borderWidth": 2,
                "fill": False,
                "tension": 0,
                "pointRadius": 0,
                "borderDash": [5, 5],  # 虛線
            })

        chart_config = {
            "type": "line",
            "data": {
                "labels": sampled_dates,
                "datasets": datasets
            },
            "options": {
                "responsive": True,
                "maintainAspectRatio": True,
                "backgroundColor": "#1a1a1a",  # 黑底
                "scales": {
                    "y": {
                        "ticks": {"font": {"size": 10}, "color": "#CCCCCC"},
                        "grid": {"color": "#333333"},
                        "title": {"display": True, "text": "價格", "color": "#CCCCCC"}
                    },
                    "x": {
                        "ticks": {
                            "font": {"size": 9},
                            "maxRotation": 45,
                            "minRotation": 0,
                            "color": "#CCCCCC"
                        },
                        "grid": {"color": "#333333"}
                    }
                },
                "plugins": {
                    "legend": {
                        "labels": {"font": {"size": 11}, "color": "#CCCCCC"},
                        "backgroundColor": "#2a2a2a"
                    },
                    "title": {
                        "display": True,
                        "text": f"{symbol} - {sampled_dates[-1] if sampled_dates else 'N/A'}",
                        "color": "#FFFFFF",
                        "font": {"size": 13, "weight": "bold"}
                    },
                    "filler": {
                        "propagate": True
                    }
                }
            }
        }

        print(f"[CHART_API] {symbol} 正在生成圖表 (period={period}, interval={interval}, 數據點={len(sampled_prices)})", flush=True)
        logger.info(
            f"📊 正在取得 {symbol} 圖表短 URL "
            f"(period={period}, interval={interval}, 數據點={len(sampled_prices)}, "
            f"cost_line={'是' if avg_cost else '否'})"
        )

        # 使用 POST API 取得短 URL
        url = await create_quickchart_short_url(chart_config)
        if not url:
            print(f"[CHART_API] {symbol} 短 URL 失敗，嘗試回退", flush=True)
            logger.warning(f"⚠️ {symbol} 圖表短 URL 取得失敗，嘗試回退至 URL encoding")
            url = build_quickchart_url(symbol=symbol, prices=prices, dates=dates)

        if url:
            print(f"[CHART_API] {symbol} 圖表 URL 成功: {url[:60]}...", flush=True)
            logger.info(f"✅ 圖表 URL 已生成: {symbol} ({period}/{interval})")
            _chart_cache[cache_key] = (url, datetime.now())
        else:
            print(f"[CHART_API] {symbol} 圖表 URL 生成失敗", flush=True)
        
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
