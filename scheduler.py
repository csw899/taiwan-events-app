"""
排程模組：每日定時收集活動 + 推播 LINE
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, PushMessageRequest

from collector import collect_all_events
from config import DAYS_AHEAD, LINE_CHANNEL_ACCESS_TOKEN, PUSH_TIME, PUSH_TARGETS
from database import get_events_by_status, get_all_subscribers, init_db, upsert_event
from formatter import format_status_push, format_no_events

logger = logging.getLogger(__name__)


def collect_and_store():
    """收集活動並存入資料庫"""
    logger.info("開始收集活動資料...")
    events = collect_all_events()
    for ev in events:
        upsert_event(ev)
    logger.info(f"完成收集，共 {len(events)} 筆存入資料庫")


def push_daily_events():
    """推播當日活動給所有訂閱者"""
    today = datetime.today()
    end = today + timedelta(days=DAYS_AHEAD)
    today_str = today.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    data = get_events_by_status(today_str, end_str)

    if not data["ongoing"] and not data["upcoming"]:
        logger.info("無活動資料可推播")
        return

    messages = format_status_push(data, days=DAYS_AHEAD)
    if not messages:
        messages = [format_no_events()]

    # 推播目標：PUSH_TARGETS (env) + 所有訂閱者
    targets = set(t.strip() for t in PUSH_TARGETS if t.strip())
    for user_id, _ in get_all_subscribers():
        targets.add(user_id)

    if not targets:
        logger.warning("沒有推播目標，請設定 PUSH_TARGETS 環境變數")
        return

    config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    with ApiClient(config) as api_client:
        line_bot_api = MessagingApi(api_client)
        for target in targets:
            try:
                # LINE 每次最多推 5 則訊息
                for i in range(0, len(messages), 5):
                    batch = messages[i:i+5]
                    line_bot_api.push_message(
                        PushMessageRequest(to=target, messages=batch)
                    )
                logger.info(f"成功推播給 {target}")
            except Exception as e:
                logger.error(f"推播給 {target} 失敗: {e}")


def start_scheduler():
    """啟動排程器"""
    init_db()

    scheduler = BackgroundScheduler(timezone="Asia/Taipei")

    # 每週四早上 06:00 收集活動 (提前一天確保資料是最新的)
    scheduler.add_job(collect_and_store, "cron", day_of_week="thu", hour=6, minute=0, id="collect")

    # 每週五依設定時間推播 (預設 08:00)
    hour, minute = PUSH_TIME.split(":")
    scheduler.add_job(
        push_daily_events, "cron",
        day_of_week="fri",
        hour=int(hour), minute=int(minute),
        id="push"
    )

    scheduler.start()
    logger.info(f"排程器已啟動，每週五 {PUSH_TIME} 推播")
    return scheduler
