"""
通用爬蟲模組 — 支援靜態頁面 + 動態 JS 渲染
提供 LLM Tool 介面供 AI 主動調用
"""

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── 全域設定 ──────────────────────────────────────────────────────────────
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 15
MAX_CONTENT_LENGTH = 8000  # 回傳給 LLM 的最大字元數


# ─── 資料結構 ──────────────────────────────────────────────────────────────
@dataclass
class ScrapeResult:
    url: str
    title: str
    content: str
    links: list[dict]
    metadata: dict
    success: bool
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content[:MAX_CONTENT_LENGTH],
            "links": self.links[:50],
            "metadata": self.metadata,
            "success": self.success,
            "error": self.error,
        }


# ─── 工具函式 ──────────────────────────────────────────────────────────────
def _clean_text(text: str) -> str:
    """清理文字：移除多餘空白、腳本、樣式"""
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_links(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """提取頁面連結"""
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        full_url = urljoin(base_url, href)
        text = a.get_text(strip=True)[:100]
        if text:
            links.append({"url": full_url, "text": text})
    return links


def _extract_metadata(soup: BeautifulSoup, url: str) -> dict:
    """提取頁面中繼資料"""
    meta = {"source_domain": urlparse(url).netloc}

    # Open Graph / Twitter Card
    for prop in [
        "og:title",
        "og:description",
        "og:image",
        "og:type",
        "twitter:card",
        "twitter:title",
    ]:
        tag = soup.find("meta", property=prop) or soup.find(
            "meta", attrs={"name": prop}
        )
        if tag and tag.get("content"):
            meta[prop] = tag["content"]

    # 標準 meta
    for name in ["description", "keywords", "author", "viewport"]:
        tag = soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            meta[name] = tag["content"]

    return meta


# ─── 靜態頁面爬取 ──────────────────────────────────────────────────────────
async def fetch_static(
    url: str,
    selector: str = "",
    format: str = "text",
    timeout: int = DEFAULT_TIMEOUT,
) -> ScrapeResult:
    """使用 aiohttp + BeautifulSoup 爬取靜態頁面"""
    try:
        headers = {"User-Agent": USER_AGENT}
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return ScrapeResult(
                        url=url,
                        title="",
                        content="",
                        links=[],
                        metadata={},
                        success=False,
                        error=f"HTTP {resp.status}",
                    )
                html = await resp.text()

        soup = BeautifulSoup(html, "lxml")

        # 移除不需要的標籤
        for tag in soup(
            ["script", "style", "noscript", "iframe", "nav", "footer", "header"]
        ):
            tag.decompose()

        # 標題
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        if not title:
            h1 = soup.find("h1")
            title = h1.get_text(strip=True) if h1 else urlparse(url).netloc

        # 內容提取
        if selector:
            elements = soup.select(selector)
            content = "\n\n".join(
                el.get_text(separator=" ", strip=True) for el in elements
            )
        else:
            # 嘗試找主要內容區域
            main = (
                soup.find("main")
                or soup.find("article")
                or soup.find("div", class_=lambda x: x and "content" in x.lower())
                or soup.body
            )
            content = (
                main.get_text(separator="\n", strip=True)
                if main
                else soup.get_text(separator="\n", strip=True)
            )

        content = _clean_text(content)

        # 格式化輸出
        if format == "markdown":
            # 簡易 HTML 轉 Markdown
            content = content.replace("\n\n", "\n\n").replace("\n", "\n")

        links = _extract_links(soup, url)
        metadata = _extract_metadata(soup, url)

        return ScrapeResult(
            url=url,
            title=title,
            content=content,
            links=links,
            metadata=metadata,
            success=True,
        )

    except asyncio.TimeoutError:
        return ScrapeResult(
            url=url,
            title="",
            content="",
            links=[],
            metadata={},
            success=False,
            error="Timeout",
        )
    except Exception as e:
        logger.error(f"靜態爬取失敗 {url}: {e}")
        return ScrapeResult(
            url=url,
            title="",
            content="",
            links=[],
            metadata={},
            success=False,
            error=str(e),
        )


# ─── 動態頁面爬取 ──────────────────────────────────────────────────────────
_playwright_browser = None
_playwright_lock = asyncio.Lock()


async def _get_playwright_browser():
    """取得或建立 Playwright 瀏覽器實例（單例）"""
    global _playwright_browser
    async with _playwright_lock:
        if _playwright_browser is None:
            try:
                from playwright.async_api import async_playwright

                playwright = await async_playwright().start()
                _playwright_browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                    ],
                )
                logger.info("✅ Playwright Chromium 啟動成功")
            except Exception as e:
                logger.error(f"Playwright 啟動失敗: {e}")
                raise
        return _playwright_browser


async def fetch_dynamic(
    url: str,
    selector: str = "",
    format: str = "text",
    wait_for: str = "networkidle",
    timeout: int = 30,
    screenshot: bool = False,
) -> ScrapeResult:
    """使用 Playwright 爬取動態頁面（支援 JS 渲染）"""
    try:
        browser = await _get_playwright_browser()
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        # 設定超時
        page.set_default_timeout(timeout * 1000)

        # 導航
        response = await page.goto(url, wait_until=wait_for, timeout=timeout * 1000)
        if not response or response.status >= 400:
            await context.close()
            return ScrapeResult(
                url=url,
                title="",
                content="",
                links=[],
                metadata={},
                success=False,
                error=f"HTTP {response.status if response else 'No response'}",
            )

        # 等待特定選擇器（如果有）
        if selector:
            try:
                await page.wait_for_selector(selector, timeout=5000)
            except Exception:
                pass  # 繼續執行，不阻塞

        # 滾動頁面觸發懶加載
        await page.evaluate("""
            async () => {
                await new Promise(resolve => {
                    let total = 0;
                    const timer = setInterval(() => {
                        window.scrollBy(0, 300);
                        total += 300;
                        if (total >= document.body.scrollHeight) {
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                    setTimeout(() => { clearInterval(timer); resolve(); }, 3000);
                });
            }
        """)

        # 取得內容
        title = await page.title()
        html = await page.content()

        # 截圖（可選）
        screenshot_data = None
        if screenshot:
            screenshot_data = await page.screenshot(full_page=True)

        await context.close()

        # 用 BeautifulSoup 解析
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(
            ["script", "style", "noscript", "iframe", "nav", "footer", "header"]
        ):
            tag.decompose()

        if selector:
            elements = soup.select(selector)
            content = "\n\n".join(
                el.get_text(separator=" ", strip=True) for el in elements
            )
        else:
            main = soup.find("main") or soup.find("article") or soup.body
            content = (
                main.get_text(separator="\n", strip=True)
                if main
                else soup.get_text(separator="\n", strip=True)
            )

        content = _clean_text(content)
        links = _extract_links(soup, url)
        metadata = _extract_metadata(soup, url)
        metadata["rendered_with"] = "playwright"
        if screenshot_data:
            metadata["screenshot"] = "available"

        return ScrapeResult(
            url=url,
            title=title,
            content=content,
            links=links,
            metadata=metadata,
            success=True,
        )

    except Exception as e:
        logger.error(f"動態爬取失敗 {url}: {e}")
        return ScrapeResult(
            url=url,
            title="",
            content="",
            links=[],
            metadata={},
            success=False,
            error=str(e),
        )


# ─── 統一介面 ──────────────────────────────────────────────────────────────
async def fetch_webpage(
    url: str,
    selector: str = "",
    format: str = "text",
    dynamic: bool = False,
    wait_for: str = "networkidle",
    timeout: int = DEFAULT_TIMEOUT,
    screenshot: bool = False,
) -> ScrapeResult:
    """
    統一爬取介面，自動或手動選擇靜態/動態模式

    Args:
        url: 目標網址
        selector: CSS 選擇器（可選，指定提取區域）
        format: 輸出格式 - text, markdown
        dynamic: 是否使用 Playwright 動態渲染
        wait_for: Playwright 等待條件 - load, domcontentloaded, networkidle
        timeout: 超時秒數
        screenshot: 是否截圖（僅動態模式）
    """
    # 基本 URL 驗證
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ScrapeResult(
            url=url,
            title="",
            content="",
            links=[],
            metadata={},
            success=False,
            error="Invalid URL",
        )

    if dynamic:
        return await fetch_dynamic(url, selector, format, wait_for, timeout, screenshot)
    else:
        return await fetch_static(url, selector, format, timeout)


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    網頁搜尋（使用 DuckDuckGo HTML 搜尋，免 API Key）
    回傳: [{"title": ..., "url": ..., "snippet": ...}, ...]
    """
    try:
        search_url = (
            f"https://html.duckduckgo.com/html/?q={aiohttp.helpers.quote(query)}"
        )
        result = await fetch_static(search_url, selector=".result__body", timeout=10)

        if not result.success:
            return []

        soup = (
            BeautifulSoup(result.content, "lxml")
            if result.content
            else BeautifulSoup("", "lxml")
        )
        # 重新解析搜尋結果頁
        async with aiohttp.ClientSession() as session:
            async with session.get(
                search_url, headers={"User-Agent": USER_AGENT}
            ) as resp:
                html = await resp.text()

        soup = BeautifulSoup(html, "lxml")
        results = []
        for item in soup.select(".result__body")[:max_results]:
            title_el = item.select_one(".result__title a")
            snippet_el = item.select_one(".result__snippet")
            if title_el:
                results.append(
                    {
                        "title": title_el.get_text(strip=True),
                        "url": title_el.get("href", ""),
                        "snippet": snippet_el.get_text(strip=True)
                        if snippet_el
                        else "",
                    }
                )
        return results
    except Exception as e:
        logger.error(f"搜尋失敗: {e}")
        return []


# ─── 清理函式 ──────────────────────────────────────────────────────────────
async def close_playwright():
    """關閉 Playwright 瀏覽器（應用關閉時呼叫）"""
    global _playwright_browser
    async with _playwright_lock:
        if _playwright_browser:
            await _playwright_browser.close()
            _playwright_browser = None
            logger.info("🔒 Playwright 已關閉")


# ─── 測試函式 ──────────────────────────────────────────────────────────────
async def test_scraper():
    """測試爬蟲功能"""
    # 靜態測試
    print("=== 靜態爬取測試 ===")
    r1 = await fetch_webpage("https://example.com")
    print(f"成功: {r1.success}, 標題: {r1.title[:50]}")
    print(f"內容長度: {len(r1.content)}")
    print(f"連結數: {len(r1.links)}")

    # 動態測試（需要 Playwright）
    print("\n=== 動態爬取測試 ===")
    try:
        r2 = await fetch_webpage("https://example.com", dynamic=True)
        print(f"成功: {r2.success}, 標題: {r2.title[:50]}")
        print(f"內容長度: {len(r2.content)}")
        print(f"渲染引擎: {r2.metadata.get('rendered_with')}")
    except Exception as e:
        print(f"動態測試跳過: {e}")

    await close_playwright()


if __name__ == "__main__":
    asyncio.run(test_scraper())


# ─── Discord Cog Entry Point (stub - 此模組為工具模組，並非 Cog) ──────────────────
async def setup(bot):
    """此模組為工具函式庫，不需要作為 Cog 載入。保留此函數以防被錯誤載入。"""
    pass
