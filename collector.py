"""
活動資料收集模組
- 文化部開放資料 API
- Accupass 活動網站爬蟲
"""
import hashlib
import logging
import re
import time
import warnings
from datetime import datetime, timedelta

import requests
import urllib3
from bs4 import BeautifulSoup

# 台灣政府網站 SSL 憑證有 Missing Subject Key Identifier 問題，關閉驗證
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from config import CULTURE_CATEGORIES, DAYS_AHEAD, REGIONS

logger = logging.getLogger(__name__)

CULTURE_API = "https://opendata.culture.tw/frontsite/trans/SearchShowAction.do"


def _get_region(city: str) -> str:
    city = city.strip()
    for region, cities in REGIONS.items():
        for c in cities:
            if c in city or city in c:
                return region
    return "其他"


def _make_id(source: str, title: str, start_date: str) -> str:
    raw = f"{source}_{title}_{start_date}"
    return hashlib.md5(raw.encode()).hexdigest()


# ─── 文化部 API ─────────────────────────────────────────────

CULTURE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://cloud.culture.tw/frontsite/trans/SearchShowAction.do",
}


def fetch_culture_events() -> list:
    events = []
    today = datetime.today()
    end_date = today + timedelta(days=DAYS_AHEAD)

    for cat_id, cat_name in CULTURE_CATEGORIES.items():
        try:
            resp = requests.get(
                CULTURE_API,
                params={"method": "doFindTypeJ", "category": cat_id},
                headers=CULTURE_HEADERS,
                timeout=30,
                verify=False,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"文化部分類 {cat_name}: 取得 {len(data)} 筆原始資料")
        except Exception as e:
            logger.warning(f"文化部 API 分類 {cat_name} 失敗: {type(e).__name__}: {e}")
            continue

        for item in data:
            try:
                start_str = item.get("startDate", "")
                end_str = item.get("endDate", "") or start_str

                # 解析日期
                start = _parse_date(start_str)
                end = _parse_date(end_str)
                if not start:
                    continue

                # 篩選日期範圍
                if end and end < today:
                    continue
                if start > end_date:
                    continue

                # 新 API：startDate/endDate 若空，從 showInfo[0].time 取
                show_info = item.get("showInfo", [])
                if not start_str and show_info:
                    start_str = show_info[0].get("time", "")
                    start = _parse_date(start_str)
                if not end_str and show_info:
                    end_str = show_info[0].get("endTime", start_str)
                    end = _parse_date(end_str)

                city = item.get("masterUnit", "") or (show_info[0].get("location", "") if show_info else "")
                city = _extract_city(city, item)

                event = {
                    "id": _make_id("culture", item.get("title", ""), start_str),
                    "title": item.get("title", "無標題"),
                    "category": cat_name,
                    "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": end.strftime("%Y-%m-%d") if end else start.strftime("%Y-%m-%d"),
                    "location": _get_location(item),
                    "city": city,
                    "region": _get_region(city),
                    "url": item.get("webSite", "") or f"https://cloud.culture.tw",
                    "description": item.get("descriptionFilterHtml", "")[:200],
                    "source": "文化部",
                }
                events.append(event)
            except Exception as e:
                logger.debug(f"解析文化部活動失敗: {e}")
                continue

        time.sleep(0.3)  # 避免請求過快

    logger.info(f"文化部共收集 {len(events)} 筆活動")
    return events


def _parse_date(s: str):
    if not s:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except ValueError:
            continue
    return None


def _extract_city(fallback: str, item: dict) -> str:
    show_info = item.get("showInfo", [])
    if show_info:
        location = show_info[0].get("location", "")
        # 嘗試從地址取出縣市
        for region_cities in REGIONS.values():
            for city in region_cities:
                if city in location:
                    return city
    return fallback[:10] if fallback else "不明"


def _get_location(item: dict) -> str:
    show_info = item.get("showInfo", [])
    if show_info:
        loc = show_info[0].get("locationName", "") or show_info[0].get("location", "")
        return loc[:50]
    return item.get("masterUnit", "")[:50]


# ─── Accupass 爬蟲 ──────────────────────────────────────────

ACCUPASS_URL = "https://www.accupass.com/search"

def fetch_accupass_events() -> list:
    events = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(ACCUPASS_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select(".EventCard, [class*='event-card'], [class*='EventCard']")
        for card in cards[:30]:
            try:
                title_el = card.select_one("h2, h3, [class*='title'], [class*='Title']")
                title = title_el.get_text(strip=True) if title_el else ""
                if not title:
                    continue

                date_el = card.select_one("[class*='date'], [class*='Date'], time")
                date_text = date_el.get_text(strip=True) if date_el else ""

                loc_el = card.select_one("[class*='location'], [class*='Location'], [class*='city']")
                location = loc_el.get_text(strip=True) if loc_el else ""

                link_el = card.select_one("a[href]")
                url = ""
                if link_el:
                    href = link_el["href"]
                    url = href if href.startswith("http") else f"https://www.accupass.com{href}"

                city = _extract_city_from_text(location)
                today_str = datetime.today().strftime("%Y-%m-%d")

                event = {
                    "id": _make_id("accupass", title, date_text),
                    "title": title,
                    "category": "活動",
                    "start_date": today_str,
                    "end_date": today_str,
                    "location": location[:50],
                    "city": city,
                    "region": _get_region(city),
                    "url": url,
                    "description": "",
                    "source": "Accupass",
                }
                events.append(event)
            except Exception as e:
                logger.debug(f"Accupass 活動解析失敗: {e}")
                continue

    except Exception as e:
        logger.warning(f"Accupass 爬取失敗: {e}")

    logger.info(f"Accupass 共收集 {len(events)} 筆活動")
    return events


def _extract_city_from_text(text: str) -> str:
    for region_cities in REGIONS.values():
        for city in region_cities:
            if city in text:
                return city
    return "不明"


# ─── 主要收集入口 ────────────────────────────────────────────

def collect_all_events() -> list:
    from social_collector import collect_social_events

    all_events = []
    all_events.extend(fetch_culture_events())
    all_events.extend(fetch_accupass_events())
    all_events.extend(collect_social_events())
    logger.info(f"總共收集 {len(all_events)} 筆活動 (含社群媒體)")
    return all_events
