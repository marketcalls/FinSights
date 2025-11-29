"""
In-memory cache manager service.
"""
from datetime import datetime, timedelta
from typing import Optional, Any
from threading import Lock
from sqlalchemy.orm import Session

from app.config import TIMEZONE, CATEGORY_NAMES, SUBCATEGORY_NAMES
from app.models.news import News
from app.models.settings import StockSymbol


class CacheManager:
    """
    In-memory cache manager for news data.
    Frontend reads ONLY from this cache.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._cache = {
            "news": {
                "market": {},
                "sector": {},
                "macro": {},
                "regulation": {},
                "stock": {},
            },
            "last_updated": {},
            "all_news": [],  # Flat list for search
            "featured": [],
            "symbols": [],  # Stock symbols list
            "symbols_by_sector": {},  # Symbols grouped by sector
        }
        self._stock_cache_ttl = timedelta(minutes=30)
        self._initialized = True

    def get_all_categories(self) -> dict:
        """Get all category names."""
        return CATEGORY_NAMES

    def get_subcategory_name(self, subcategory: str) -> str:
        """Get display name for subcategory."""
        return SUBCATEGORY_NAMES.get(subcategory, subcategory.replace("_", " ").title())

    def load_from_db(self, db: Session):
        """Load all published news from database into cache on startup."""
        with self._lock:
            # Clear existing cache
            for category in self._cache["news"]:
                self._cache["news"][category] = {}
            self._cache["all_news"] = []
            self._cache["featured"] = []

            # Load all published news
            news_items = (
                db.query(News)
                .filter(News.is_published == True)
                .order_by(News.fetched_at.desc())
                .all()
            )

            for news in news_items:
                news_dict = news.to_dict()
                category = news.category
                subcategory = news.subcategory or "general"

                # Add to category cache
                if category in self._cache["news"]:
                    if subcategory not in self._cache["news"][category]:
                        self._cache["news"][category][subcategory] = []
                    self._cache["news"][category][subcategory].append(news_dict)

                # Add to flat list
                self._cache["all_news"].append(news_dict)

                # Add to featured if applicable
                if news.is_featured:
                    self._cache["featured"].append(news_dict)

                # Update last_updated
                cache_key = f"{category}_{subcategory}"
                if cache_key not in self._cache["last_updated"]:
                    self._cache["last_updated"][cache_key] = news.fetched_at

    def get_news_by_category(
        self, category: str, subcategory: Optional[str] = None, limit: int = 20
    ) -> list[dict]:
        """Get news for a specific category/subcategory."""
        with self._lock:
            if category not in self._cache["news"]:
                return []

            if subcategory:
                news_list = self._cache["news"][category].get(subcategory, [])
            else:
                # Get all subcategories for this category
                news_list = []
                for subcat_news in self._cache["news"][category].values():
                    news_list.extend(subcat_news)
                # Sort by fetched_at descending
                news_list.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)

            return news_list[:limit]

    def get_news_by_id(self, news_id: int) -> Optional[dict]:
        """Get a single news item by ID."""
        with self._lock:
            for news in self._cache["all_news"]:
                if news.get("id") == news_id:
                    return news
            return None

    def get_stock_news(self, symbol: str, limit: int = 20) -> list[dict]:
        """Get news for a specific stock symbol."""
        with self._lock:
            # Check if we have cached stock news
            if symbol in self._cache["news"]["stock"]:
                cached = self._cache["news"]["stock"][symbol]
                if cached.get("expires_at") and cached["expires_at"] > datetime.now(TIMEZONE):
                    return cached.get("news", [])[:limit]

            # If not cached or expired, return from all_news filtered by symbol
            filtered = []
            for news in self._cache["all_news"]:
                symbols = news.get("symbols", "") or ""
                if symbol.upper() in symbols.upper().split(","):
                    filtered.append(news)
            return filtered[:limit]

    def search_news(self, query: str, limit: int = 50) -> list[dict]:
        """Search news by text query."""
        with self._lock:
            query_lower = query.lower()
            results = []
            for news in self._cache["all_news"]:
                title = (news.get("title") or "").lower()
                summary = (news.get("summary") or "").lower()
                if query_lower in title or query_lower in summary:
                    results.append(news)
            return results[:limit]

    def get_featured_news(self, limit: int = 10) -> list[dict]:
        """Get featured news items."""
        with self._lock:
            return self._cache["featured"][:limit]

    def get_latest_news(self, limit: int = 20) -> list[dict]:
        """Get latest news across all categories."""
        with self._lock:
            return self._cache["all_news"][:limit]

    def get_last_updated(self, category: str, subcategory: str) -> Optional[datetime]:
        """Get last update time for a category."""
        cache_key = f"{category}_{subcategory}"
        return self._cache["last_updated"].get(cache_key)

    def add_news(self, news_dict: dict):
        """Add a single news item to cache."""
        with self._lock:
            category = news_dict.get("category", "market")
            subcategory = news_dict.get("subcategory", "general")

            # Add to category cache
            if category in self._cache["news"]:
                if subcategory not in self._cache["news"][category]:
                    self._cache["news"][category][subcategory] = []
                # Add to beginning (newest first)
                self._cache["news"][category][subcategory].insert(0, news_dict)

            # Add to flat list
            self._cache["all_news"].insert(0, news_dict)

            # Update last_updated
            cache_key = f"{category}_{subcategory}"
            self._cache["last_updated"][cache_key] = datetime.now(TIMEZONE)

            # Add to featured if applicable
            if news_dict.get("is_featured"):
                self._cache["featured"].insert(0, news_dict)

    def update_news(self, news_id: int, updates: dict):
        """Update a news item in cache."""
        with self._lock:
            # Update in all_news
            for i, news in enumerate(self._cache["all_news"]):
                if news.get("id") == news_id:
                    self._cache["all_news"][i].update(updates)
                    break

            # Update in category cache
            for category in self._cache["news"]:
                for subcategory in self._cache["news"][category]:
                    for i, news in enumerate(self._cache["news"][category][subcategory]):
                        if news.get("id") == news_id:
                            self._cache["news"][category][subcategory][i].update(updates)
                            return

    def remove_news(self, news_id: int):
        """Remove a news item from cache."""
        with self._lock:
            # Remove from all_news
            self._cache["all_news"] = [
                n for n in self._cache["all_news"] if n.get("id") != news_id
            ]

            # Remove from featured
            self._cache["featured"] = [
                n for n in self._cache["featured"] if n.get("id") != news_id
            ]

            # Remove from category cache
            for category in self._cache["news"]:
                for subcategory in self._cache["news"][category]:
                    self._cache["news"][category][subcategory] = [
                        n
                        for n in self._cache["news"][category][subcategory]
                        if n.get("id") != news_id
                    ]

    def set_stock_news(self, symbol: str, news_list: list[dict]):
        """Cache stock-specific news with TTL."""
        with self._lock:
            self._cache["news"]["stock"][symbol] = {
                "news": news_list,
                "expires_at": datetime.now(TIMEZONE) + self._stock_cache_ttl,
            }

    def get_cache_stats(self) -> dict:
        """Get cache statistics."""
        with self._lock:
            stats = {
                "total_news": len(self._cache["all_news"]),
                "featured_count": len(self._cache["featured"]),
                "symbols_count": len(self._cache["symbols"]),
                "categories": {},
            }
            for category in self._cache["news"]:
                if category != "stock":
                    cat_count = sum(
                        len(news_list)
                        for news_list in self._cache["news"][category].values()
                    )
                    stats["categories"][category] = cat_count
            return stats

    def load_symbols(self, db: Session):
        """Load stock symbols from database into cache."""
        with self._lock:
            self._cache["symbols"] = []
            self._cache["symbols_by_sector"] = {}

            symbols = (
                db.query(StockSymbol)
                .filter(StockSymbol.is_active == True)
                .order_by(StockSymbol.symbol)
                .all()
            )

            for sym in symbols:
                sym_dict = sym.to_dict()
                self._cache["symbols"].append(sym_dict)

                sector = sym.sector or "Other"
                if sector not in self._cache["symbols_by_sector"]:
                    self._cache["symbols_by_sector"][sector] = []
                self._cache["symbols_by_sector"][sector].append(sym_dict)

    def get_all_symbols(self) -> list[dict]:
        """Get all stock symbols."""
        with self._lock:
            return self._cache["symbols"]

    def get_nifty50_symbols(self) -> list[dict]:
        """Get Nifty 50 symbols only."""
        with self._lock:
            return [s for s in self._cache["symbols"] if s.get("is_nifty50")]

    def get_symbols_by_sector(self, sector: str = None) -> dict | list:
        """Get symbols grouped by sector or for a specific sector."""
        with self._lock:
            if sector:
                return self._cache["symbols_by_sector"].get(sector, [])
            return self._cache["symbols_by_sector"]

    def search_symbols(self, query: str, limit: int = 20) -> list[dict]:
        """Search symbols by symbol or company name."""
        with self._lock:
            query_upper = query.upper()
            query_lower = query.lower()
            results = []
            for sym in self._cache["symbols"]:
                symbol = sym.get("symbol", "")
                company = sym.get("company_name", "").lower()
                if query_upper in symbol or query_lower in company:
                    results.append(sym)
                    if len(results) >= limit:
                        break
            return results


# Singleton instance
cache_manager = CacheManager()
