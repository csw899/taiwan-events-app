"""
主程式：Flask 網頁伺服器 + API + LINE Bot Webhook (選用)
"""
import logging
import os
from datetime import datetime, timedelta

from flask import Flask, abort, jsonify, render_template, request

from config import DAYS_AHEAD, LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET
from database import get_events_by_status, get_recommended_events, init_db, upsert_subscriber
from scheduler import collect_and_store, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)


# ── 網頁首頁 ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API：取得活動 ─────────────────────────────────────────

@app.route("/api/events")
def api_events():
    today = datetime.today()
    end   = today + timedelta(days=DAYS_AHEAD)
    today_str = today.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")

    region = request.args.get("region", "").strip() or None

    data = get_events_by_status(today_str, end_str, region=region)

    # 將 tuple 轉為 list，並加入 region 欄位
    def to_list(region_map):
        result = {}
        for r, events in region_map.items():
            result[r] = [list(ev) + [r] for ev in events]
        return result

    return jsonify({
        "ongoing":  to_list(data["ongoing"]),
        "upcoming": to_list(data["upcoming"]),
        "updated_at": today.strftime("%Y-%m-%d %H:%M"),
    })


# ── API：最佳推薦 ─────────────────────────────────────────

@app.route("/api/recommend")
def api_recommend():
    today = datetime.today()
    end   = today + timedelta(days=DAYS_AHEAD)
    today_str = today.strftime("%Y-%m-%d")
    end_str   = end.strftime("%Y-%m-%d")
    data = get_recommended_events(today_str, end_str, top_n=10)
    return jsonify({
        "recommend": data,
        "updated_at": today.strftime("%Y-%m-%d %H:%M"),
    })


# ── API：手動更新資料 ─────────────────────────────────────

@app.route("/api/update", methods=["POST"])
def api_update():
    try:
        collect_and_store()
        return jsonify({"ok": True, "message": "✅ 活動資料已更新完成！"})
    except Exception as e:
        logger.error(f"更新失敗: {e}")
        return jsonify({"ok": False, "message": f"更新失敗：{e}"}), 500


# ── LINE Bot Webhook (選用) ───────────────────────────────

if LINE_CHANNEL_SECRET and LINE_CHANNEL_ACCESS_TOKEN:
    try:
        from linebot.v3 import WebhookHandler
        from linebot.v3.exceptions import InvalidSignatureError
        from linebot.v3.messaging import (
            ApiClient, Configuration, MessagingApi,
            PushMessageRequest, ReplyMessageRequest, TextMessage, FlexMessage, FlexContainer,
        )
        from linebot.v3.webhooks import FollowEvent, MessageEvent, TextMessageContent

        handler     = WebhookHandler(LINE_CHANNEL_SECRET)
        line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

        HELP_TEXT = """📋 活動資訊機器人指令：

🟢 活動狀態查詢：
  進行中 → 目前正在舉辦的活動
  即將開始 → 近期即將開辦的活動
  全部活動 → 進行中 + 即將開始

🔍 依地區查詢：
  北部 / 中部 / 南部 / 東部

🔄 更新資料：
  更新 → 重新收集最新活動

❓ 說明：
  說明 / help → 顯示此訊息"""

        from formatter import format_status_push, format_no_events

        def _to_line_message(msg_dict: dict):
            if msg_dict.get("type") == "text":
                return TextMessage(text=msg_dict["text"])
            elif msg_dict.get("type") == "flex":
                return FlexMessage(
                    alt_text=msg_dict.get("altText", "活動資訊"),
                    contents=FlexContainer.from_dict(msg_dict["contents"]),
                )
            return TextMessage(text=str(msg_dict))

        @app.route("/callback", methods=["POST"])
        def callback():
            signature = request.headers.get("X-Line-Signature", "")
            body = request.get_data(as_text=True)
            try:
                handler.handle(body, signature)
            except InvalidSignatureError:
                abort(400)
            return "OK"

        @handler.add(FollowEvent)
        def handle_follow(event):
            with ApiClient(line_config) as api_client:
                MessagingApi(api_client).reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=f"👋 歡迎使用台灣活動資訊！\n\n{HELP_TEXT}")]
                    )
                )

        @handler.add(MessageEvent, message=TextMessageContent)
        def handle_message(event):
            user_msg  = event.message.text.strip()
            user_id   = event.source.user_id
            today_str = datetime.today().strftime("%Y-%m-%d")
            end_str   = (datetime.today() + timedelta(days=DAYS_AHEAD)).strftime("%Y-%m-%d")

            with ApiClient(line_config) as api_client:
                api = MessagingApi(api_client)

                region = None
                if user_msg in ("北部", "中部", "南部", "東部"):
                    region = user_msg

                if user_msg in ("進行中", "即將開始", "全部活動", "推播",
                                "北部", "中部", "南部", "東部"):
                    data = get_events_by_status(today_str, end_str, region=region)
                    if user_msg == "進行中":
                        data = {"ongoing": data["ongoing"], "upcoming": {}}
                    elif user_msg == "即將開始":
                        data = {"ongoing": {}, "upcoming": data["upcoming"]}
                    msgs = format_status_push(data, region=region, days=DAYS_AHEAD)
                    reply_msgs = [_to_line_message(m) for m in msgs[:5]]

                elif user_msg == "更新":
                    reply_msgs = [TextMessage(text="⏳ 更新中，請稍候...")]
                    api.reply_message(ReplyMessageRequest(
                        reply_token=event.reply_token, messages=reply_msgs))
                    collect_and_store()
                    api.push_message(PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text="✅ 活動資料已更新完成！")]))
                    return

                elif user_msg in ("說明", "help", "Help"):
                    reply_msgs = [TextMessage(text=HELP_TEXT)]
                else:
                    reply_msgs = [TextMessage(text="輸入「說明」查看可用指令")]

                api.reply_message(ReplyMessageRequest(
                    reply_token=event.reply_token, messages=reply_msgs[:5]))

        logger.info("LINE Bot Webhook 已啟用")
    except Exception as e:
        logger.warning(f"LINE Bot 未啟用（{e}）")
else:
    logger.info("未設定 LINE Token，跳過 LINE Bot")


# ── 啟動 (gunicorn 或直接執行皆適用) ─────────────────────

def _startup():
    init_db()
    collect_and_store()
    start_scheduler()

_startup()  # gunicorn import 時也會執行

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"伺服器啟動於 http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
