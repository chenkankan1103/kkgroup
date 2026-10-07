"""
bangumi (bgm.tv) API 客戶端 —— 補足巴哈動畫瘋缺少的動畫資料。

巴哈動畫瘋只給「什麼時候播、哪集上架」（videoSn / animeSn / 封面 / 集數），
沒有評分、排名、製作組、角色、簡介。bangumi 補的正是這一塊。

實測限制（2026-10-07，以實際請求驗證）：

1. **搜尋索引只吃簡體中文** —— 餵繁體標題直接回 0 筆結果。
   巴哈標題是繁體，所以搜尋前必須先過 zhconv 轉換。這是接這支 API 最大的坑：
   不轉換的話 25 部只對上 3 部，轉換後變成 36/41。
2. 巴哈 API **不提供日文原名**，無法改用日文搜尋繞過轉換問題。
3. v0 搜尋端點 ``POST /v0/search/subjects`` 對匿名請求永遠回 0 筆（疑似需要
   access token），改用舊版 ``GET /search/subject/{keyword}``。
4. 匿名請求有速率限制但官方未公布數字，本模組統一節流 ``THROTTLE_SEC`` 秒/次。
5. 標題比對必須 **兩邊都轉簡體再比**，否則繁簡字形差異會讓正確的配對被誤判成低分
   （例：「學生會也有洞！」對上「学生会也有洞！」實際正確，直接比卻只有 0.67）。

對照率實測：41 部巴哈當季新番 → 36 部（87.8%）成功對到 bangumi。
剩下對不上的主要是台譯與中譯不同的作品（拉拉熊↔輕鬆熊、超人力霸王↔奧特曼），
由 ``ALIASES`` 對照表補齊。

顯示端則相反：bangumi 的 ``name_cn`` 是簡體，所以 :func:`get_ranking`、
:func:`get_popular`、:func:`get_trending`、:func:`get_rating_by_title` 回傳的
``title`` 都已用 :func:`to_traditional` 轉回繁體，可直接推播給台灣用戶；
``name`` / ``name_cn`` 則保留 API 原值。
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import time
import urllib.parse
from contextlib import asynccontextmanager
from typing import Dict, Iterable, List, Optional

import aiohttp

try:
    import zhconv

    _HAS_ZHCONV = True
except ImportError:  # pragma: no cover - 依賴缺失時降級，不讓 bot 掛掉
    zhconv = None  # type: ignore[assignment]
    _HAS_ZHCONV = False

logger = logging.getLogger(__name__)

# ============================================================
# 常數
# ============================================================
API_BASE = "https://api.bgm.tv"
SEARCH_URL = API_BASE + "/search/subject/{}?responseGroup=small&max_results=5"
SUBJECT_URL = API_BASE + "/v0/subjects/{}"
EPISODES_URL = API_BASE + "/v0/episodes?subject_id={}"
CALENDAR_URL = API_BASE + "/calendar"

# bangumi 新版前端的私有端點。官網「動畫 > 近期注目」（/anime/browser/?sort=trends）
# 就是打這支；公開的 api.bgm.tv/v0 沒有 trends 排序（實測回 unknown sort: trends）。
P1_BASE = "https://next.bgm.tv/p1"
P1_TRENDS_URL = P1_BASE + "/subjects?type={}&sort=trends&limit={}"
P1_SUBJECT_URL = P1_BASE + "/subjects/{}"

TRENDS_PAGE_SIZE = 24  # 實測 limit 傳 20/50/100 都只回 24 筆，這是端點的硬上限

SUBJECT_TYPE_ANIME = "2"  # bangumi 分類：1=書籍 2=動畫 3=音樂 4=遊戲 6=三次元

HEADERS = {
    "User-Agent": "kkgroup-anime-bot/1.0 (https://github.com/kkgroup)",
    "Accept": "application/json",
}

REQUEST_TIMEOUT = 20
THROTTLE_SEC = 0.6  # 匿名速率限制未公布，保守取值

STRONG_MATCH = 0.80  # 視為「對上」的分數門檻
WEAK_MATCH = 0.55  # 視為「疑似」的分數門檻

# 台譯 ↔ 中譯對照表。
# 只放「zhconv 簡繁轉換救不了」的真·不同譯名；單純繁簡差異交給 zhconv。
# 之後遇到新的對不上案例，往這裡加即可。
ALIASES: Dict[str, str] = {
    "拉拉熊": "轻松熊",
    "超人力霸王": "奥特曼",
    "間諜家家酒": "间谍过家家",
    "我推的孩子": "【我推的孩子】",
    "小狸貓和小狐狸": "小浣熊",
    "你好，身為魔女的我，被心上人委託製作迷情藥": "你好，我是受心上人所托来做恋爱药的魔女。",
}

# 標題雜訊：副標題、開頭贅字、結尾引號
_SUBTITLE = re.compile(r"[：:～~].*$")
_LEAD_NOISE = re.compile(r"^(?:the\s*anime|動畫|动画)\s*[「『\"']?", re.I)
_TRAIL_NOISE = re.compile(r"[」』\"']$")
_PUNCT = re.compile(
    r"[\s　·・!！?？,，.。:：;；'\"“”‘’()（）\[\]【】<>《》\-—_~/\\|+&×☆★♪]"
)
_SEASON = re.compile(
    r"(第\s*[0-9一二三四五六七八九十]+\s*[季期部篇]|season\s*\d+|part\s*\d+)", re.I
)
_SEASON_EN = re.compile(r"(?:season|part)\s*(\d+)", re.I)
_SEASON_CN = re.compile(r"第\s*([一二三四五六七八九十]+)\s*([季期部篇])")
_CN_NUM = {
    "一": "1",
    "二": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
    "十": "10",
}

# ============================================================
# 節流：模組層級，跨呼叫者共用
# ============================================================
_throttle_lock = asyncio.Lock()
_last_call_at = 0.0


async def _throttle() -> None:
    """確保兩次 API 呼叫之間至少間隔 THROTTLE_SEC 秒。"""
    global _last_call_at
    async with _throttle_lock:
        wait = THROTTLE_SEC - (time.monotonic() - _last_call_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_at = time.monotonic()


# ============================================================
# 標題正規化與比對
# ============================================================
def to_simplified(text: str) -> str:
    """繁體轉簡體。bangumi 搜尋索引只認簡體，這是能否命中的關鍵。"""
    if not text:
        return ""
    if not _HAS_ZHCONV:
        return text
    return zhconv.convert(text, "zh-cn")


def to_traditional(text: str) -> str:
    """簡體轉繁體（台灣正體）。bangumi 的 ``name_cn`` 是簡體，要顯示給台灣用戶得轉回來。

    與 :func:`to_simplified` 對稱：搜尋前轉簡體，顯示前轉回繁體。

    用 ``zh-tw`` 而非 ``zh-hant``：zh-hant 挑的是正統字形，會把「為」寫成「爲」，
    而台灣標準是「為」。zh-tw 另外會把少數用語換成台灣講法（軟件→軟體），
    對作品名來說也是對的方向。
    """
    if not text:
        return ""
    if not _HAS_ZHCONV:
        return text
    return zhconv.convert(text, "zh-tw")


def _canon_season(text: str) -> str:
    """統一季數寫法：Season 2 / Part 2 / 第二季 → 第2季。"""
    text = _SEASON_EN.sub(r"第\1季", text)
    text = _SEASON_CN.sub(
        lambda m: "第" + _CN_NUM.get(m.group(1), m.group(1)) + m.group(2), text
    )
    return text


def normalize(title: str) -> str:
    """轉簡體 → 統一季數 → 去標點空白 → 小寫。比對前的標準化。"""
    text = _canon_season(to_simplified(title or ""))
    return _PUNCT.sub("", text.strip().lower())


def normalize_loose(title: str) -> str:
    """更寬鬆的版本：連季數標記也拿掉，用於「本體同名但季數不同」的情況。"""
    return _SEASON.sub("", normalize(title))


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def score_candidate(source_title: str, candidate: dict) -> float:
    """替單一 bangumi 候選打相似度分數，取 name_cn / name 的最佳值。

    兩邊都會先轉簡體再比，避免繁簡字形差異造成假性扣分。
    """
    src = normalize(source_title)
    src_loose = normalize_loose(source_title)
    best = 0.0
    for field in ("name_cn", "name"):
        raw = candidate.get(field) or ""
        cand = normalize(raw)
        if not cand:
            continue
        cand_loose = normalize_loose(raw)
        # 完全相同或互為子字串 → 直接給高分（涵蓋「副標題被截掉」的情況）
        if src and (src == cand or src in cand or cand in src):
            best = max(best, 0.98)
        elif (
            src_loose
            and cand_loose
            and (
                src_loose == cand_loose
                or src_loose in cand_loose
                or cand_loose in src_loose
            )
        ):
            best = max(best, 0.90)
        best = max(best, similarity(src, cand))
    return best


def search_variants(title: str) -> List[str]:
    """由精確到寬鬆產生多個搜尋字串；前一個找不到就退階用下一個。

    退階順序：全名 → 去掉「：副標題」→ 去掉「The Anime」贅字 → 兩者都去。
    """
    base = to_simplified(title).strip()
    variants = [base]
    core = _SUBTITLE.sub("", base).strip()
    if core and core != base:
        variants.append(core)
    cleaned = _TRAIL_NOISE.sub("", _LEAD_NOISE.sub("", base)).strip()
    if cleaned and cleaned not in variants:
        variants.append(cleaned)
    core2 = _TRAIL_NOISE.sub("", _SUBTITLE.sub("", cleaned)).strip()
    if core2 and core2 not in variants:
        variants.append(core2)
    # 台譯對照表：先試完全符合，再處理「台譯名只是標題一部分」的情況
    # （例：「超人力霸王狄奧」含台譯詞「超人力霸王」→ 換成「奥特曼狄奧」）
    # ALIASES 的 key 是繁體，替換後務必再過一次簡繁轉換，
    # 否則「超人力霸王狄奧」→「奥特曼狄奧」會留下沒轉到的繁體「奧」。
    stripped = title.strip()
    if stripped in ALIASES:
        alias_query = to_simplified(ALIASES[stripped])
    else:
        alias_query = ""
        for tw, cn in ALIASES.items():
            if tw in stripped:
                alias_query = to_simplified(stripped.replace(tw, cn))
                break
    if alias_query and alias_query not in variants:
        variants.append(alias_query)
    return variants


# ============================================================
# HTTP 層
# ============================================================
@asynccontextmanager
async def _session(session: Optional[aiohttp.ClientSession] = None):
    """沿用呼叫者提供的 session（批次用），否則自己開一個並負責關閉。"""
    if session is not None:
        yield session
        return
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as owned:
        yield owned


async def _get_json(session: aiohttp.ClientSession, url: str) -> Optional[object]:
    """GET 並解析 JSON，失敗一律回 None（不讓單次失敗中斷整批）。"""
    await _throttle()
    try:
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                logger.debug("bangumi 回應 %s: %s", resp.status, url)
                return None
            return await resp.json(content_type=None)
    except Exception as exc:
        logger.warning("bangumi 請求失敗 %s: %s", url, exc)
        return None


async def search_subject(
    keyword: str,
    *,
    session: Optional[aiohttp.ClientSession] = None,
    subject_type: Optional[str] = SUBJECT_TYPE_ANIME,
) -> List[dict]:
    """舊版搜尋 API。``subject_type=None`` 表示不限分類（特攝等非動畫用）。"""
    url = SEARCH_URL.format(urllib.parse.quote(keyword))
    if subject_type:
        url += f"&type={subject_type}"
    async with _session(session) as sess:
        data = await _get_json(sess, url)
    if not isinstance(data, dict):
        return []
    return data.get("list") or []


async def find_subject(
    title: str,
    *,
    session: Optional[aiohttp.ClientSession] = None,
    threshold: float = STRONG_MATCH,
) -> Optional[dict]:
    """把（繁體）標題對到 bangumi subject。

    找不到達門檻的結果就回 None——寧可沒有資料，也不要掛錯作品的評分。

    Returns:
        ``{"id", "name", "name_cn", "score", "query"}`` 或 ``None``
    """
    variants = search_variants(title)
    best_score, best_cand, used_query = 0.0, None, variants[0]

    async with _session(session) as sess:
        for query in variants:
            candidates = await search_subject(query, session=sess)
            if not candidates:
                # 動畫分類找不到（例如特攝）→ 放寬分類再試一次
                candidates = await search_subject(
                    query, session=sess, subject_type=None
                )
            for cand in candidates:
                # 同時對「原標題」和「實際用的查詢字串」評分。
                # 查詢字串可能是別名或去過副標題的版本（拉拉熊→轻松熊），
                # 只對原標題評分會把正確結果誤判成低分而丟掉。
                score = max(score_candidate(title, cand), score_candidate(query, cand))
                if score > best_score:
                    best_score, best_cand, used_query = score, cand, query
            if best_score >= threshold:
                break

    if best_cand is None or best_score < threshold:
        logger.debug("bangumi 對不上：%s（最高分 %.2f）", title, best_score)
        return None

    return {
        "id": best_cand.get("id"),
        "name": best_cand.get("name"),
        "name_cn": best_cand.get("name_cn"),
        "score": round(best_score, 3),
        "query": used_query,
    }


async def find_subjects(
    titles: Iterable[str],
    *,
    threshold: float = STRONG_MATCH,
) -> Dict[str, Optional[dict]]:
    """批次對照，共用同一個 session。回傳 ``{原標題: 結果或 None}``。"""
    result: Dict[str, Optional[dict]] = {}
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as sess:
        for title in titles:
            result[title] = await find_subject(title, session=sess, threshold=threshold)
    return result


async def get_subject_detail(
    subject_id: int,
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[dict]:
    """取單部完整資料：評分（score/rank/分佈）、標籤、infobox（製作組）、收藏數。"""
    async with _session(session) as sess:
        data = await _get_json(sess, SUBJECT_URL.format(subject_id))
    return data if isinstance(data, dict) else None


async def get_episodes(
    subject_id: int,
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> List[dict]:
    """取集數列表（含每集標題與播出日期）。"""
    async with _session(session) as sess:
        data = await _get_json(sess, EPISODES_URL.format(subject_id))
    if not isinstance(data, dict):
        return []
    return data.get("data") or []


async def get_calendar(
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> List[dict]:
    """取每日放送表（依星期一到日分組，當季約 100 部）。"""
    async with _session(session) as sess:
        data = await _get_json(sess, CALENDAR_URL)
    return data if isinstance(data, list) else []


# ============================================================
# 排行與熱門
# ============================================================
async def get_ranking(
    limit: int = 10,
    offset: int = 0,
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> List[dict]:
    """全站排行榜（依 bangumi 評分排名，涵蓋約 9000 部動畫）。

    注意：公開的 v0 端點 ``sort`` 只支援 ``rank`` 和 ``date``，**沒有「熱門」排序**
    （實測 ``sort=trends`` 回 ``unknown sort: trends``）。要官網那種熱門榜請用
    :func:`get_trending`；要「當季在看人數」則用 :func:`get_popular`。

    Returns:
        每筆 ``{"id", "title", "name", "name_cn", "score", "rank", "votes", "date"}``

        ``title`` 是已解析好的**繁體**顯示名稱（``name_cn`` 沒有時退回日文原名）——
        部分作品（如 CLANNAD）沒有中文名，直接取 ``name_cn`` 會拿到 None。
        ``name`` / ``name_cn`` 保留 API 原值（``name_cn`` 為簡體）。
    """
    url = (
        f"{API_BASE}/v0/subjects?type={SUBJECT_TYPE_ANIME}"
        f"&sort=rank&limit={limit}&offset={offset}"
    )
    async with _session(session) as sess:
        data = await _get_json(sess, url)
    if not isinstance(data, dict):
        return []
    out = []
    for item in data.get("data") or []:
        rating = item.get("rating") or {}
        out.append(
            {
                "id": item.get("id"),
                "title": to_traditional(item.get("name_cn")) or item.get("name"),
                "name": item.get("name"),
                "name_cn": item.get("name_cn"),
                "score": rating.get("score"),
                "rank": rating.get("rank"),
                "votes": rating.get("total"),
                "date": item.get("date"),
            }
        )
    return out


async def get_popular(
    limit: int = 10,
    *,
    weekday: Optional[int] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> List[dict]:
    """熱門程度：當季放送中「在看人數」最多的動畫。

    這是**放送表口徑**的熱度，不是官網「近期注目」那份榜。兩者差很多：這裡只涵蓋
    ``/calendar`` 當季有登記的作品（跨季續播、剛完結的常缺席），而且比的是累計
    在看人數，不是近期標記速度。要跟官網對齊請用 :func:`get_trending`。

    好處是放送表本身就帶 ``collection.doing``，一次請求拿到全部，不必逐部打 detail。

    Args:
        weekday: 1-7 只取某一天；``None`` 表示整週。

    Returns:
        每筆 ``{"id", "title", "name", "name_cn", "score", "doing", "air_weekday", "air_date"}``

        ``title`` 是已解析好的**繁體**顯示名稱，可直接推播；
        ``name`` / ``name_cn`` 保留 API 原值（``name_cn`` 為簡體）。
    """
    calendar = await get_calendar(session=session)
    items: List[dict] = []
    for day in calendar:
        if weekday is not None and (day.get("weekday") or {}).get("id") != weekday:
            continue
        items.extend(day.get("items") or [])

    items.sort(key=lambda i: (i.get("collection") or {}).get("doing", 0), reverse=True)
    return [
        {
            "id": item.get("id"),
            "title": to_traditional(item.get("name_cn")) or item.get("name"),
            "name": item.get("name"),
            "name_cn": item.get("name_cn"),
            "score": (item.get("rating") or {}).get("score"),
            "doing": (item.get("collection") or {}).get("doing", 0),
            "air_weekday": item.get("air_weekday"),
            "air_date": item.get("air_date"),
        }
        for item in items[:limit]
    ]


async def _fetch_doing(session: aiohttp.ClientSession, subject_id: Optional[int]) -> int:
    """補「正在看人數」。

    p1 的 ``collection`` 用數字當鍵（跟 v0 的具名鍵不同）：
    1=想看 2=看過 3=在看 4=擱置 5=拋棄，所以要的是 ``"3"``。
    拿不到就回 0——單一部失敗不該讓整份榜單開天窗。
    """
    if not subject_id:
        return 0
    detail = await _get_json(session, P1_SUBJECT_URL.format(subject_id))
    if not isinstance(detail, dict):
        return 0
    try:
        return int((detail.get("collection") or {}).get("3") or 0)
    except (TypeError, ValueError):
        return 0


async def get_trending(
    limit: int = 10,
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> List[dict]:
    """近期注目：與官網「動畫 > 近期注目」（``/anime/browser/?sort=trends``）同一份榜。

    公開的 v0 API 沒有這個排序（實測 ``sort=trends`` 回 ``unknown sort: trends``），
    但新版前端有私有端點 ``next.bgm.tv/p1/subjects`` 吃 ``sort=trends``，官網那頁
    就是打它。實測 24 筆的順序與官網逐筆一致。

    代價是這支端點**不給** ``collection``，所以「在看人數」得逐部補打
    ``p1/subjects/{id}``。:func:`_throttle` 是模組層級的鎖，``gather`` 也會被排成
    序列，20 部大約多花十幾秒——每週跑一次的 cron 吃得下。

    Args:
        limit: 取前幾名。端點每頁固定 24 筆，超過也只拿得到 24 筆。

    Returns:
        每筆 ``{"id", "title", "name", "name_cn", "score", "doing"}``

        ``title`` 是已解析好的**繁體**顯示名稱，可直接推播；
        ``name`` / ``name_cn`` 保留 API 原值（``name_cn`` 為簡體）。
    """
    url = P1_TRENDS_URL.format(SUBJECT_TYPE_ANIME, TRENDS_PAGE_SIZE)
    async with _session(session) as sess:
        data = await _get_json(sess, url)
        if not isinstance(data, dict):
            return []
        rows = (data.get("data") or [])[:limit]
        if not rows:
            return []
        doings = await asyncio.gather(
            *(_fetch_doing(sess, item.get("id")) for item in rows)
        )

    return [
        {
            "id": item.get("id"),
            "title": to_traditional(item.get("nameCN")) or item.get("name"),
            "name": item.get("name"),
            "name_cn": item.get("nameCN"),
            "score": (item.get("rating") or {}).get("score"),
            "doing": doing,
        }
        for item, doing in zip(rows, doings)
    ]


# ============================================================
# 便利函數：常見的「拿標題換評分」用法
# ============================================================
async def get_rating_by_title(
    title: str,
    *,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[dict]:
    """標題 → 評分摘要。找不到回 None。

    Returns:
        ``{"id", "title", "name_cn", "score", "rank", "votes", "matched_score"}``

        ``title`` 是**繁體**顯示名稱，可直接推播；``name_cn`` 保留 API 原值（簡體）。
    """
    found = await find_subject(title, session=session)
    if not found:
        return None
    detail = await get_subject_detail(found["id"], session=session)
    if not detail:
        return None
    rating = detail.get("rating") or {}
    name_cn = detail.get("name_cn")
    return {
        "id": found["id"],
        "title": to_traditional(name_cn) or detail.get("name"),
        "name_cn": name_cn,
        "score": rating.get("score"),
        "rank": rating.get("rank"),
        "votes": rating.get("total"),
        "matched_score": found["score"],
    }
