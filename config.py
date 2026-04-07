import os
from dotenv import load_dotenv

load_dotenv()

# LINE Bot 設定
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# 推播時間 (24小時制, 例如 "08:00")
PUSH_TIME = os.getenv("PUSH_TIME", "08:00")

# 要推播的 LINE 群組或使用者 ID (逗號分隔)
PUSH_TARGETS = os.getenv("PUSH_TARGETS", "").split(",")

# 資料庫路徑
DB_PATH = os.getenv("DB_PATH", "events.db")

# 活動預告天數 (收集未來幾天內的活動)
DAYS_AHEAD = int(os.getenv("DAYS_AHEAD", "7"))

# 台灣縣市分區
REGIONS = {
    "北部": ["臺北市", "台北市", "新北市", "基隆市", "桃園市", "新竹市", "新竹縣", "宜蘭縣"],
    "中部": ["臺中市", "台中市", "苗栗縣", "彰化縣", "南投縣", "雲林縣"],
    "南部": ["臺南市", "台南市", "高雄市", "嘉義市", "嘉義縣", "屏東縣", "澎湖縣"],
    "東部": ["花蓮縣", "臺東縣", "台東縣"],
}

# 文化部 API 活動類別
CULTURE_CATEGORIES = {
    "1": "音樂",
    "2": "戲劇",
    "3": "舞蹈",
    "4": "親子",
    "5": "展覽",
    "6": "講座",
    "7": "電影",
    "8": "其他",
}
