"""
Configuration settings for FinSights application.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import pytz

# Load environment variables
load_dotenv(override=True)

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SYMBOLS_FILE = BASE_DIR / "symbols" / "symbols.csv"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# Application settings
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR}/finsights.db")

# Admin defaults
ADMIN_DEFAULT_USERNAME = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
ADMIN_DEFAULT_PASSWORD = os.getenv("ADMIN_DEFAULT_PASSWORD", "admin123")

# Timezone
TIMEZONE_STR = os.getenv("TIMEZONE", "Asia/Kolkata")
TIMEZONE = pytz.timezone(TIMEZONE_STR)

# Session settings
SESSION_COOKIE_NAME = "finsights_session"
SESSION_MAX_AGE = 60 * 60 * 24  # 24 hours

# Trusted news sources (25+)
NEWS_SOURCES = [
    # Indian Financial News
    "moneycontrol.com",
    "economictimes.indiatimes.com",
    "business-standard.com",
    "livemint.com",
    "financialexpress.com",
    "cnbctv18.com",
    "ndtvprofit.com",
    "zeebiz.com",
    "businesstoday.in",
    "thehindubusinessline.com",
    "valueresearchonline.com",
    "tickertape.in",
    "equitymaster.com",

    # Regulatory Sources
    "sebi.gov.in",
    "nseindia.com",
    "bseindia.com",
    "rbi.org.in",
    "pib.gov.in",

    # Global Financial News
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",

    # Wire Services
    "ptinews.com",
    "aninews.in",
]

# Default news categories and their queries
DEFAULT_SCHEDULE_CONFIG = {
    "market_pre_market": {
        "enabled": True,
        "category": "market",
        "subcategory": "pre_market",
        "query": "Indian stock market pre-market analysis today opening Nifty Sensex",
        "schedule_type": "cron",
        "cron_time": "07:00",
    },
    "market_morning": {
        "enabled": True,
        "category": "market",
        "subcategory": "morning",
        "query": "Indian stock market morning update today Nifty Sensex trading",
        "schedule_type": "cron",
        "cron_time": "10:00",
    },
    "market_midday": {
        "enabled": True,
        "category": "market",
        "subcategory": "midday",
        "query": "Indian stock market midday summary today Nifty Sensex",
        "schedule_type": "cron",
        "cron_time": "13:00",
    },
    "market_post_market": {
        "enabled": True,
        "category": "market",
        "subcategory": "post_market",
        "query": "Indian stock market closing summary today Nifty Sensex",
        "schedule_type": "cron",
        "cron_time": "16:00",
    },
    "market_evening": {
        "enabled": True,
        "category": "market",
        "subcategory": "evening",
        "query": "Indian stock market evening wrap today analysis Nifty Sensex",
        "schedule_type": "cron",
        "cron_time": "18:00",
    },
    "sector_auto": {
        "enabled": True,
        "category": "sector",
        "subcategory": "auto",
        "query": "Indian auto sector stock market news Maruti Tata Motors Mahindra",
        "schedule_type": "interval",
        "interval_minutes": 120,
    },
    "sector_banking": {
        "enabled": True,
        "category": "sector",
        "subcategory": "banking",
        "query": "Indian banking sector NIFTY Bank news HDFC ICICI SBI",
        "schedule_type": "interval",
        "interval_minutes": 120,
    },
    "sector_pharma": {
        "enabled": True,
        "category": "sector",
        "subcategory": "pharma",
        "query": "Indian pharma sector stock news Sun Pharma Dr Reddy Cipla",
        "schedule_type": "interval",
        "interval_minutes": 120,
    },
    "sector_it": {
        "enabled": True,
        "category": "sector",
        "subcategory": "it",
        "query": "Indian IT sector TCS Infosys Wipro HCL Tech stock news",
        "schedule_type": "interval",
        "interval_minutes": 120,
    },
    "macro_economy": {
        "enabled": True,
        "category": "macro",
        "subcategory": "economy",
        "query": "Indian economy news GDP inflation growth",
        "schedule_type": "interval",
        "interval_minutes": 180,
    },
    "macro_rbi": {
        "enabled": True,
        "category": "macro",
        "subcategory": "rbi",
        "query": "RBI Reserve Bank India monetary policy interest rate news",
        "schedule_type": "interval",
        "interval_minutes": 180,
    },
    "macro_global": {
        "enabled": True,
        "category": "macro",
        "subcategory": "global",
        "query": "Global markets US Fed impact India stocks foreign investors",
        "schedule_type": "interval",
        "interval_minutes": 120,
    },
    "regulation_sebi": {
        "enabled": True,
        "category": "regulation",
        "subcategory": "sebi",
        "query": "SEBI regulations circulars India stock market rules",
        "schedule_type": "interval",
        "interval_minutes": 240,
    },
    "regulation_exchange": {
        "enabled": True,
        "category": "regulation",
        "subcategory": "exchange",
        "query": "NSE BSE circulars notices India stock exchange",
        "schedule_type": "interval",
        "interval_minutes": 240,
    },
}

# Category display names
CATEGORY_NAMES = {
    "market": "Market Updates",
    "sector": "Sector News",
    "macro": "Macro & Economy",
    "regulation": "Regulations",
    "stock": "Stock Specific",
}

SUBCATEGORY_NAMES = {
    "pre_market": "Pre-Market (7 AM)",
    "morning": "Morning (10 AM)",
    "midday": "Mid-Day (1 PM)",
    "post_market": "Post-Market (4 PM)",
    "evening": "Evening (6 PM)",
    "auto": "Auto Sector",
    "banking": "Banking Sector",
    "pharma": "Pharma Sector",
    "it": "IT Sector",
    "economy": "Economy",
    "rbi": "RBI & Monetary Policy",
    "global": "Global Impact",
    "sebi": "SEBI",
    "exchange": "NSE/BSE",
}
