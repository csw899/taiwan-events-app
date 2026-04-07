"""
社群媒體活動資料收集模組
- PTT 藝文/活動板
- Facebook Graph API
- Dcard 活動相關看板
"""
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from config import DAYS_AHEAD, REGIONS

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

EVENT_KEYWORDS = [
    "活動", "展覽", "展出", "演出", "演唱會", "音樂會", "市集",
    "表演", "講座", "工作坊", "節", "祭", "博覽會", "藝術節",
    "音樂節", "舞蹈", "戲劇", "展", "演",
]


def _make_id(source: str, title: str, extra: str = "") -> str:
    raw = f"{source}_{title}_{extra}"
    return hashlib.md5(raw.encode()).hexdigest()


def _get_region(text: str) -> str:
    for region, cities in REGIONS.items():
        for city in cities:
            if city in text:
                return region
    return "其他"


def _has_event_keyword(text: str) -> bool:
    return any(kw in text for kw in EVENT_KEYWORDS)


def _extract_city(text: str) -> str:
    for cities in REGIONS.values():
        for city in cities:
            if city in text:
                return city
    return "不明"


# ─── PTT ────────────────────────────────────────────────────

PTT_BASE = "https://www.ptt.cc"
PTT_BOARDS = [
    ("YiWen", "藝文"),       # 藝文板
    ("Drama", "戲劇"),       # 戲劇板
    ("galleryB", "藝廊"),    # 藝廊板
    ("MusicBand", "音樂"),   # 音樂板
]
PTT_COOKIES = {"over18": "1"}


def fetch_ptt_events() -> list:
    events = []
    for board, category in PTT_BOARDS:
        try:
            board_events = _scrape_ptt_board(board, category)
            events.extend(board_events)
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"PTT {board} 板抓取失敗: {e}")
    logger.info(f"PTT 共收集 {len(events)} 筆活動")
    return events


def _scrape_ptt_board(board: str, category: str, pages: int = 3) -> list:
    events = []
    url = f"{PTT_BASE}/bbs/{board}/index.html"

    for _ in range(pages):
        try:
            resp = requests.get(url, cookies=PTT_COOKIES, headers=HEADERS, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"PTT {board} 請求失敗: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        articles = soup.select("div.r-ent")

        for article in articles:
            try:
                title_el = article.select_one("div.title a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")

                # 過濾含活動關鍵字的標題
                if not _has_event_keyword(title):
                    continue

                # 移除 PTT 標題標籤 (如 [活動])
                clean_title = re.sub(r"^\[.*?\]\s*", "", title).strip()

                date_el = article.select_one("div.date")
                date_str = date_el.get_text(strip=True) if date_el else ""
                today = datetime.today()
                # PTT 日期格式 "M/DD"
                try:
                    month, day = date_str.strip().split("/")
                    post_date = datetime(today.year, int(month), int(day))
                    if post_date > today:  # 跨年處理
                        post_date = datetime(today.year - 1, int(month), int(day))
                    post_date_str = post_date.strftime("%Y-%m-%d")
                except Exception:
                    post_date_str = today.strftime("%Y-%m-%d")

                post_url = PTT_BASE + href if href else ""

                # 嘗試從文章內容取得地點資訊
                city = _try_fetch_ptt_article_city(post_url)

                event = {
                    "id": _make_id("ptt", title, href),
                    "title": clean_title or title,
                    "category": category,
                    "start_date": post_date_str,
                    "end_date": post_date_str,
                    "location": "",
                    "city": city,
                    "region": _get_region(city + title),
                    "url": post_url,
                    "description": f"PTT/{board} 板文章",
                    "source": f"PTT/{board}",
                }
                events.append(event)

            except Exception as e:
                logger.debug(f"PTT 文章解析失敗: {e}")
                continue

        # 翻到上一頁
        prev_el = soup.select_one("a.btn.wide:contains('上頁')")
        if not prev_el:
            # 嘗試另一種選法
            for btn in soup.select("a.btn.wide"):
                if "上頁" in btn.get_text():
                    prev_el = btn
                    break
        if prev_el and prev_el.get("href"):
            url = PTT_BASE + prev_el["href"]
        else:
            break

    return events


def _try_fetch_ptt_article_city(url: str) -> str:
    """嘗試從 PTT 文章內容提取縣市資訊"""
    if not url:
        return "不明"
    try:
        resp = requests.get(url, cookies=PTT_COOKIES, headers=HEADERS, timeout=8)
        text = resp.text[:3000]  # 只看前段
        city = _extract_city(text)
        return city
    except Exception:
        return "不明"


# ─── Facebook Graph API ──────────────────────────────────────

FB_API_BASE = "https://graph.facebook.com/v19.0"
# Token 從環境變數取得
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN", "")

# 台灣主要活動粉絲頁 ID (可自行擴充)
FB_PAGE_IDS = [
    "109850640854",    # 臺北市政府文化局
    "152036048177370", # 高雄市文化局
    "140496666001370", # 臺中市文化局
]


def fetch_facebook_events() -> list:
    if not FB_ACCESS_TOKEN:
        logger.warning("未設定 FB_ACCESS_TOKEN，跳過 Facebook 收集")
        return []

    events = []
    today = datetime.today()
    end_date = today + timedelta(days=DAYS_AHEAD)

    # 搜尋公開活動
    search_queries = ["台灣活動", "展覽 台灣", "音樂節 台灣", "市集 台灣"]
    for query in search_queries:
        try:
            resp = requests.get(
                f"{FB_API_BASE}/search",
                params={
                    "type": "event",
                    "q": query,
                    "fields": "name,start_time,end_time,place,description",
                    "access_token": FB_ACCESS_TOKEN,
                    "limit": 20,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])

            for item in data:
                try:
                    start_str = item.get("start_time", "")[:10]
                    end_str = item.get("end_time", start_str)[:10]

                    if not start_str:
                        continue

                    start = datetime.strptime(start_str, "%Y-%m-%d")
                    if start > end_date or start < today - timedelta(days=1):
                        continue

                    place = item.get("place", {})
                    location = place.get("name", "")
                    city = _extract_city(location + place.get("location", {}).get("city", ""))

                    event = {
                        "id": _make_id("facebook", item.get("id", ""), start_str),
                        "title": item.get("name", "無標題"),
                        "category": "活動",
                        "start_date": start_str,
                        "end_date": end_str,
                        "location": location[:50],
                        "city": city,
                        "region": _get_region(city + location),
                        "url": f"https://www.facebook.com/events/{item.get('id', '')}",
                        "description": item.get("description", "")[:200],
                        "source": "Facebook",
                    }
                    events.append(event)
                except Exception as e:
                    logger.debug(f"Facebook 活動解析失敗: {e}")
                    continue

            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Facebook 搜尋 '{query}' 失敗: {e}")

    # 從粉絲頁取得活動
    for page_id in FB_PAGE_IDS:
        try:
            resp = requests.get(
                f"{FB_API_BASE}/{page_id}/events",
                params={
                    "fields": "name,start_time,end_time,place,description",
                    "access_token": FB_ACCESS_TOKEN,
                    "limit": 10,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])

            for item in data:
                try:
                    start_str = item.get("start_time", "")[:10]
                    end_str = item.get("end_time", start_str)[:10]
                    place = item.get("place", {})
                    location = place.get("name", "")
                    city = _extract_city(location)

                    event = {
                        "id": _make_id("fb_page", item.get("id", ""), start_str),
                        "title": item.get("name", "無標題"),
                        "category": "活動",
                        "start_date": start_str,
                        "end_date": end_str,
                        "location": location[:50],
                        "city": city,
                        "region": _get_region(city + location),
                        "url": f"https://www.facebook.com/events/{item.get('id', '')}",
                        "description": item.get("description", "")[:200],
                        "source": "Facebook粉絲頁",
                    }
                    events.append(event)
                except Exception as e:
                    logger.debug(f"Facebook 粉絲頁活動解析失敗: {e}")
            time.sleep(0.3)
        except Exception as e:
            logger.warning(f"Facebook 粉絲頁 {page_id} 失敗: {e}")

    logger.info(f"Facebook 共收集 {len(events)} 筆活動")
    return events


# ─── Dcard ──────────────────────────────────────────────────

DCARD_API = "https://www.dcard.tw/service/api/v2/posts"
DCARD_FORUMS = [
    ("talent", "才藝"),
    ("music", "音樂"),
    ("photography", "攝影"),
    ("life", "生活"),
    ("travel", "旅遊"),
]


def fetch_dcard_events() -> list:
    events = []
    dcard_headers = {
        **HEADERS,
        "Referer": "https://www.dcard.tw/f",
        "Origin": "https://www.dcard.tw",
        "Accept": "application/json, text/plain, */*",
        "x-requested-with": "XMLHttpRequest",
    }
    for forum_id, forum_name in DCARD_FORUMS:
        try:
            resp = requests.get(
                DCARD_API,
                params={
                    "forumAlias": forum_id,
                    "popular": "false",
                    "limit": 30,
                },
                headers=dcard_headers,
                timeout=10,
            )
            resp.raise_for_status()
            posts = resp.json()

            for post in posts:
                try:
                    title = post.get("title", "")
                    if not _has_event_keyword(title):
                        continue

                    excerpt = post.get("excerpt", "")
                    created_at = post.get("createdAt", "")[:10]
                    if not created_at:
                        created_at = datetime.today().strftime("%Y-%m-%d")

                    city = _extract_city(title + excerpt)
                    post_id = post.get("id", "")

                    event = {
                        "id": _make_id("dcard", title, str(post_id)),
                        "title": title,
                        "category": forum_name,
                        "start_date": created_at,
                        "end_date": created_at,
                        "location": "",
                        "city": city,
                        "region": _get_region(city + title + excerpt),
                        "url": f"https://www.dcard.tw/f/{forum_id}/p/{post_id}",
                        "description": excerpt[:200],
                        "source": f"Dcard/{forum_name}",
                    }
                    events.append(event)
                except Exception as e:
                    logger.debug(f"Dcard 文章解析失敗: {e}")
                    continue

            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"Dcard {forum_id} 取得失敗: {e}")

    logger.info(f"Dcard 共收集 {len(events)} 筆活動")
    return events


# ─── 社群媒體總入口 ──────────────────────────────────────────

def collect_social_events() -> list:
    all_events = []
    all_events.extend(fetch_ptt_events())
    all_events.extend(fetch_facebook_events())
    all_events.extend(fetch_dcard_events())
    logger.info(f"社群媒體總共收集 {len(all_events)} 筆活動")
    return all_events
