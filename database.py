import sqlite3
from datetime import datetime
from config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT,
            start_date TEXT,
            end_date TEXT,
            location TEXT,
            city TEXT,
            region TEXT,
            url TEXT,
            description TEXT,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id TEXT PRIMARY KEY,
            region TEXT,
            notify_time TEXT DEFAULT '08:00',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def upsert_event(event: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO events
        (id, title, category, start_date, end_date, location, city, region, url, description, source)
        VALUES (:id, :title, :category, :start_date, :end_date, :location, :city, :region, :url, :description, :source)
    """, event)
    conn.commit()
    conn.close()


def get_events_by_region(region: str, start: str, end: str) -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT title, category, start_date, end_date, location, city, url
        FROM events
        WHERE region = ?
          AND start_date <= ?
          AND (end_date >= ? OR end_date IS NULL)
        ORDER BY start_date ASC
        LIMIT 10
    """, (region, end, start))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_events(start: str, end: str) -> dict:
    """依分區回傳活動字典"""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT title, category, start_date, end_date, location, city, url, region
        FROM events
        WHERE start_date <= ?
          AND (end_date >= ? OR end_date IS NULL)
        ORDER BY region, start_date ASC
    """, (end, start))
    rows = cur.fetchall()
    conn.close()

    result = {}
    for row in rows:
        r = row[7]
        if r not in result:
            result[r] = []
        result[r].append(row[:7])
    return result


def get_events_by_status(today: str, end: str, region: str = None) -> dict:
    """
    回傳 {'ongoing': {region: [...]}, 'upcoming': {region: [...]}}
    ongoing:  start_date <= today <= end_date
    upcoming: today < start_date <= end
    """
    conn = get_conn()
    cur = conn.cursor()

    region_filter = "AND region = ?" if region else ""
    params_base = [today, today] + ([region] if region else [])

    # 進行中
    cur.execute(f"""
        SELECT title, category, start_date, end_date, location, city, url, region
        FROM events
        WHERE start_date <= ?
          AND (end_date >= ? OR end_date IS NULL)
          {region_filter}
        ORDER BY region, end_date ASC
    """, params_base)
    ongoing_rows = cur.fetchall()

    # 即將開始
    params_up = [today, end] + ([region] if region else [])
    cur.execute(f"""
        SELECT title, category, start_date, end_date, location, city, url, region
        FROM events
        WHERE start_date > ?
          AND start_date <= ?
          {region_filter}
        ORDER BY region, start_date ASC
    """, params_up)
    upcoming_rows = cur.fetchall()

    conn.close()

    def _group(rows):
        result = {}
        for row in rows:
            r = row[7]
            if r not in result:
                result[r] = []
            result[r].append(row[:7])
        return result

    return {
        "ongoing": _group(ongoing_rows),
        "upcoming": _group(upcoming_rows),
    }


def get_recommended_events(today: str, end: str, top_n: int = 10) -> dict:
    """
    每個地區回傳推薦 top_n 筆活動
    評分：進行中+3、有描述+2、有網址+1、有地點+1
    類別多樣化：同類別最多選 3 筆
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT title, category, start_date, end_date, location, city, url, region, description
        FROM events
        WHERE start_date <= ?
          AND (end_date >= ? OR end_date IS NULL)
          AND region IN ('北部', '中部', '南部', '東部')
    """, (end, today))
    rows = cur.fetchall()
    conn.close()

    def _score(row):
        title, category, start, end_date, location, city, url, region, desc = row
        s = 0
        if start <= today <= (end_date or today):
            s += 3                                           # 進行中優先
        if desc and len(desc) > 20:
            s += 2                                           # 有詳細描述
        if url and url.startswith('http') and 'cloud.culture.tw' not in url:
            s += 1                                           # 有專屬連結
        if location and len(location.strip()) > 2:
            s += 1                                           # 有明確地點
        return s

    # 依地區分組並評分
    by_region = {}
    for row in rows:
        r = row[7]
        by_region.setdefault(r, []).append((_score(row), row))

    result = {}
    for region, scored in by_region.items():
        scored.sort(key=lambda x: -x[0])
        picked, cat_count = [], {}
        for s, row in scored:
            cat = row[1] or '其他'
            if cat_count.get(cat, 0) >= 3:
                continue
            cat_count[cat] = cat_count.get(cat, 0) + 1
            picked.append(list(row[:7]))                     # title~url
            if len(picked) >= top_n:
                break
        result[region] = picked

    return result


def upsert_subscriber(user_id: str, region: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO subscribers (user_id, region)
        VALUES (?, ?)
    """, (user_id, region))
    conn.commit()
    conn.close()


def get_all_subscribers() -> list:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, region FROM subscribers")
    rows = cur.fetchall()
    conn.close()
    return rows
