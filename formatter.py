"""
LINE 訊息格式化模組
"""
from datetime import datetime, timedelta

REGION_EMOJI = {"北部": "🔵", "中部": "🟡", "南部": "🔴", "東部": "🟢", "其他": "⚪"}


def _event_bubble(ev: tuple, status: str) -> dict:
    """單一活動的 Flex bubble"""
    title, category, start_date, end_date, location, city, url = ev
    date_str = f"{start_date} ~ {end_date}" if start_date != end_date else start_date

    # 狀態標籤顏色
    if status == "ongoing":
        badge_text = "進行中"
        badge_color = "#27AE60"  # 綠色
        header_color = "#E8F8F0"
    else:
        badge_text = "即將開始"
        badge_color = "#2980B9"  # 藍色
        header_color = "#EBF5FB"

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": header_color,
            "paddingAll": "8px",
            "contents": [
                {
                    "type": "text",
                    "text": badge_text,
                    "size": "xs",
                    "weight": "bold",
                    "color": badge_color,
                    "flex": 0,
                },
                {
                    "type": "text",
                    "text": category or "活動",
                    "size": "xs",
                    "color": "#888888",
                    "align": "end",
                },
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "sm",
                    "wrap": True,
                    "maxLines": 2,
                },
                {
                    "type": "text",
                    "text": f"📍 {location or city or '地點不明'}",
                    "size": "xs",
                    "color": "#555555",
                    "wrap": True,
                },
                {
                    "type": "text",
                    "text": f"📆 {date_str}",
                    "size": "xs",
                    "color": "#555555",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "查看詳情",
                        "uri": url or "https://cloud.culture.tw",
                    },
                    "style": "link",
                    "height": "sm",
                }
            ],
        },
    }


def format_status_push(data: dict, region: str = None, days: int = 7) -> list:
    """
    格式化「進行中 + 即將開始」訊息
    data = {'ongoing': {region: [...]}, 'upcoming': {region: [...]}}
    region: 指定分區，None 表示全區
    """
    ongoing_map = data.get("ongoing", {})
    upcoming_map = data.get("upcoming", {})

    today = datetime.today()
    end = today + timedelta(days=days)

    # 統計數字
    ongoing_total = sum(len(v) for v in ongoing_map.values())
    upcoming_total = sum(len(v) for v in upcoming_map.values())

    if ongoing_total == 0 and upcoming_total == 0:
        return [{"type": "text", "text": "目前查無活動資料，請輸入「更新」重新收集。"}]

    messages = []

    # 總覽文字
    scope = region or "全台"
    header_text = (
        f"📢 {scope}活動總覽\n"
        f"（查詢至 {end.strftime('%m/%d')}）\n\n"
        f"🟢 進行中：{ongoing_total} 項\n"
        f"🔔 即將開始：{upcoming_total} 項"
    )
    messages.append({"type": "text", "text": header_text})

    # 決定要顯示的分區
    all_regions = sorted(
        set(list(ongoing_map.keys()) + list(upcoming_map.keys())),
        key=lambda r: ["北部", "中部", "南部", "東部", "其他"].index(r)
        if r in ["北部", "中部", "南部", "東部", "其他"] else 99,
    )
    if region:
        all_regions = [region] if region in all_regions else []

    for r in all_regions:
        emoji = REGION_EMOJI.get(r, "⚪")
        ongoing_evs = ongoing_map.get(r, [])
        upcoming_evs = upcoming_map.get(r, [])

        if not ongoing_evs and not upcoming_evs:
            continue

        bubbles = []

        # 進行中的活動
        for ev in ongoing_evs[:5]:
            bubbles.append(_event_bubble(ev, "ongoing"))

        # 即將開始的活動
        for ev in upcoming_evs[:5]:
            bubbles.append(_event_bubble(ev, "upcoming"))

        if not bubbles:
            continue

        flex_msg = {
            "type": "flex",
            "altText": f"{emoji} {r} 活動（進行中 {len(ongoing_evs)} / 即將 {len(upcoming_evs)}）",
            "contents": {
                "type": "carousel",
                "contents": bubbles,
            },
        }
        messages.append(flex_msg)

    return messages


def format_daily_push(events_by_region: dict, days: int = 7) -> list:
    """原有的每週推播格式（保持向下相容）"""
    today = datetime.today()
    end = today + timedelta(days=days)
    date_range = f"{today.strftime('%m/%d')} ~ {end.strftime('%m/%d')}"

    messages = []
    total = sum(len(v) for v in events_by_region.values())
    header_text = f"📅 近期活動推播 ({date_range})\n共 {total} 項活動\n\n"
    for region, evs in events_by_region.items():
        emoji = REGION_EMOJI.get(region, "⚪")
        header_text += f"{emoji} {region}：{len(evs)} 項\n"
    messages.append({"type": "text", "text": header_text.strip()})

    for region, evs in events_by_region.items():
        if not evs:
            continue
        bubbles = [_event_bubble(ev, "upcoming") for ev in evs[:8]]
        flex_msg = {
            "type": "flex",
            "altText": f"{REGION_EMOJI.get(region, '')} {region}近期活動",
            "contents": {"type": "carousel", "contents": bubbles},
        }
        messages.append(flex_msg)

    return messages


def format_no_events() -> dict:
    return {"type": "text", "text": "今日暫無近期活動資訊，請稍後再試。"}
